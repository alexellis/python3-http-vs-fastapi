# python3-http vs FastAPI on OpenFaaS

The same HTTP function built four ways, to compare the options for Python on
OpenFaaS. Each returns a greeting on `GET /` and echoes the body on `POST /`.

| Folder | Template | Notes |
|---|---|---|
| [`python3-http-echo`](./python3-http-echo) | `python3-http` | The default template: just a handler, no Dockerfile. |
| [`python3-classic`](./python3-classic) | `python3` | Classic watchdog, forks the handler once per request. |
| [`fastapi-watchdog`](./fastapi-watchdog) | `dockerfile` | A FastAPI app behind of-watchdog in HTTP mode. |
| [`fastapi`](./fastapi) | `dockerfile` | A plain FastAPI app that serves port 8080 itself, no watchdog. |

## Deploy

```bash
faas-cli up
```

The registry and gateway are overridable:

```bash
REGISTRY=ghcr.io/me OPENFAAS_URL=https://gateway.example.com faas-cli up
```

## Invoke

```bash
curl https://openfaas.o6s.io/function/fastapi
# {"message":"Hello from FastAPI"}

curl https://openfaas.o6s.io/function/fastapi -d "hello"
# {"echo":"hello"}
```
