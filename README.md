# FastAPI on OpenFaaS — four ways

The same tiny HTTP service, built four different ways, so you can compare what
each layer buys you. All four are deployed to the same gateway from one
`stack.yaml`, and all four answer identically:

| Request | Response |
|---|---|
| `GET /` | JSON reflecting the request: function name, runtime, Python version, hostname, method, path, query, headers |
| `POST /` (any body) | The same, plus `echo`, `bytes` and `content_type` |
| `GET /ready` | `200` once start-up work has finished, `503` while it is still running |
| `?sleep=N` | Stalls for N seconds before responding, to exercise timeouts |

## The four functions

| Folder | `lang` | Watchdog | Who serves port 8080 | Who serves `/_/health` and `/_/ready` |
|---|---|---|---|---|
| [`fastapi`](./fastapi) | `dockerfile` | none | uvicorn | the app itself |
| [`fastapi-watchdog`](./fastapi-watchdog) | `dockerfile` | of-watchdog `0.11.7`, `mode=http` | of-watchdog | of-watchdog |
| [`python3-http-echo`](./python3-http-echo) | `python3-http` | of-watchdog, from the template | of-watchdog | of-watchdog |
| [`python3-classic`](./python3-classic) | `python3` | classic watchdog, fork per request | classic watchdog | classic watchdog |

### 1. `fastapi` — a microservice, no watchdog

Nothing OpenFaaS-specific is installed in the image. It is a FastAPI app that
happens to satisfy the [OpenFaaS workload
definition](https://docs.openfaas.com/reference/workloads/) on its own:

* serves HTTP on TCP port 8080
* implements `/_/health` (liveness) and `/_/ready` (readiness)
* stateless, ephemeral storage
* graceful shutdown on `SIGTERM` — uvicorn handles this

This is the path for "I already have a service and I want to run it on
OpenFaaS". The cost is that you own everything the watchdog would have given
you. In particular, **the watchdog environment variables do nothing here** —
`read_timeout`, `write_timeout`, `exec_timeout`, `max_inflight` and
`prefix_logs` are read by the watchdog process, which is not in this image.
Timeouts and concurrency become uvicorn's problem.

### 2. `fastapi-watchdog` — the same app, behind of-watchdog

The Dockerfile is adapted from the `python3-http` template (same non-root `app`
user, same build args, same layout) with Flask/waitress swapped for
FastAPI/uvicorn. of-watchdog runs in HTTP mode: it owns port 8080 and proxies
everything except `/_/health` and `/_/ready` to uvicorn on `127.0.0.1:5000`.

You keep full control of the framework and the image, and get back the
watchdog's consistent timeouts, request logging, graceful shutdown and
`max_inflight` concurrency limiting.

### 3. `python3-http-echo` — the template, used as-is

No Dockerfile to maintain. `faas-cli new --lang python3-http` gives you a
`handler.py` and a `requirements.txt`, and the template supplies of-watchdog,
Flask, waitress and the `event`/`context` contract. Least control, least code.

### 4. `python3-classic` — the classic watchdog

`faas-cli new --lang python3`, from
[templates-classic](https://github.com/openfaas/templates-classic). The classic
watchdog forks `python3 index.py` once per request: body on stdin, response on
stdout, request metadata in `Http_*` environment variables.

That fork-per-request model is the whole reason to reach for it — see
[Timeouts](#timeouts) below. The costs are a process spawn per request, no warm
state (so no connection pooling, and nothing to gate a readiness check on), and
no control over the status code: returning normally is `200`, a non-zero exit
is `500`. Its `uptime_seconds` is always `0.0`, which is the point.

## Timeouts

**This is the one behavioural difference that is not just plumbing.** Every
function takes `?sleep=N`, and the three watchdog-based ones are all configured
with `exec_timeout: 10s`. Firing `?sleep=20` at each, through the gateway:

| Function | Caller gets | Was the work actually stopped? |
|---|---|---|
| `fastapi` | `200` after **20s** | No — there is no watchdog and uvicorn was given no timeout, so nothing enforces anything |
| `fastapi-watchdog` | `504` at 10s | **No** — the coroutine ran the full 20s |
| `python3-http-echo` | `504` at 10s | **No** — the waitress thread ran the full 20s |
| `python3-classic` | `408` at 10s | **Yes** — the watchdog killed the child process |

The middle two are the trap. `exec_timeout` cuts the *caller* loose on time, so
it looks like it worked, but the Python is still running — holding its memory,
its DB connections and its share of the GIL. Under load you accumulate
abandoned work that no timeout will ever reclaim. From the deployed logs:

```
13:10:46  sleeping for 20s
13:10:56  Upstream HTTP killed due to exec_timeout: 10s      <- caller gets its 504 here
13:11:06  slept for 20s -- still running after any timeout   <- 10s past the timeout
```

Against `python3-classic`, the same request:

```
13:11:07  Forking fprocess.
13:11:17  Killing process: python3 index.py                  <- the work genuinely stops
```

So if you need a hard upper bound on how long work can run — not just on how
long a caller waits — you need the classic watchdog, or you need to enforce the
deadline inside your own handler. A long-lived Python server cannot be
preempted from outside.

## Readiness

The first three do five seconds of simulated start-up work (`init_delay_seconds`)
before reporting ready, so the readiness probe has something real to gate on.
Each exposes `/ready`, wired up in `stack.yaml`:

```yaml
annotations:
  com.openfaas.ready.http.path: /ready
  com.openfaas.ready.http.initialDelaySeconds: "2"
  com.openfaas.ready.http.periodSeconds: "2"
```

Without this, the first request after a cold start or scale-from-zero lands on
a Pod that is up but not yet able to do any work. Note that `/ready` returns
`503` while initialising — any non-2xx will do.

For the two of-watchdog functions you can also route the probe through the
watchdog's combined check, so the Pod is taken out of rotation when *either*
your check fails or `max_inflight` is saturated:

```yaml
environment:
  max_inflight: 2
  ready_path: /ready
annotations:
  com.openfaas.ready.http.path: /_/ready
```

That option is not available to `fastapi` (no watchdog to combine with) or to
`python3-classic` (the classic watchdog has no `ready_path`, and a fresh
process per request has no warm-up state to gate on anyway).

## Build, run, deploy

```bash
# Run any one of them locally on :8081
faas-cli local-run fastapi --port 8081
curl -s http://127.0.0.1:8081/ | jq
curl -s -d 'hello' http://127.0.0.1:8081/ | jq

# Publish and deploy one function
faas-cli up --filter fastapi --tag=digest

# ...or all four
faas-cli up --tag=digest
```

`--tag=digest` *replaces* the tag with a content hash of the handler folder, so
every deploy pushes a tag the cluster will actually pull. Re-deploying an
unchanged `:latest` leaves the old image running. Note that `digest` replaces
rather than appends — unlike `sha`, `branch` and `describe`, which append — so
the `${TAG:-latest}` in `stack.yaml` only takes effect when you *don't* pass
`--tag=digest`.

The gateway defaults to `https://openfaas.o6s.io` and the registry to
`docker.io/alexellis2`; both are overridable:

```bash
OPENFAAS_URL=http://127.0.0.1:8080 REGISTRY=ttl.sh/alex faas-cli up --tag=digest
```

Once deployed:

```bash
faas-cli describe fastapi
curl -s https://openfaas.o6s.io/function/fastapi | jq
```

## Gotcha: never `pip install --user` in a function image

Both FastAPI images originally installed their dependencies with
`pip install --user` as the non-root `app` user — the same idiom the
`python3-http` template uses. They worked perfectly under `local-run` and
crash-looped in the cluster with:

```
ModuleNotFoundError: No module named 'fastapi'
```

The cause is the `functions.setNonRootUser=true` Helm value, which forces every
function container to run as UID `12000`, overriding the image's `USER app`.
UID 12000 has no `/etc/passwd` entry, so `HOME` becomes `/` and Python looks for
user packages in `/.local/lib/python3.13/site-packages` — not the
`/home/app/.local/...` they were installed into.

Reproduce it without a cluster:

```bash
docker run --rm --user 12000 --entrypoint python <image> -c "import fastapi"
```

The fix is to install system-wide as root, then drop to `USER app`:

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt   # as root, system-wide
COPY --chown=app:app main.py .
USER app
```

This also affects the official `python3-http` template, which installs the
function's own `requirements.txt` with `--user`. Its own dependencies (Flask,
waitress) go in system-wide as root, so a function with an empty
`requirements.txt` is fine — add a single dependency and it fails the same way
on a cluster with `setNonRootUser` enabled.
