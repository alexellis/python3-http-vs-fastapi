"""The same FastAPI app, this time fronted by the OpenFaaS of-watchdog.

The watchdog owns port 8080 and proxies to uvicorn on 127.0.0.1:5000, so:

  * /_/health and /_/ready are served by the watchdog, not by this app --
    requests to those paths never reach uvicorn
  * the watchdog supplies graceful shutdown, request logging, timeouts
    (read_timeout / write_timeout / exec_timeout) and max_inflight
  * /ready below is a *custom* readiness endpoint, wired up in stack.yaml via
    the com.openfaas.ready.http.path annotation

https://github.com/openfaas/of-watchdog
"""

import asyncio
import logging
import os
import platform
import socket
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# The watchdog forwards every header upstream, so the kubelet's probes arrive
# here with their original User-Agent. The watchdog already drops them from its
# own log by that prefix -- do the same, or they become the entire log.
PROBE_USER_AGENT = "kube-probe"

# No timestamp in the format: the platform's log collector adds its own, and
# a second one just doubles up in "faas-cli logs" output.
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("function")

FUNCTION_NAME = os.getenv("OPENFAAS_NAME", "fastapi-watchdog")
RUNTIME = "FastAPI + uvicorn behind of-watchdog (http mode)"

# Stands in for real start-up work, so the readiness probe has something to
# gate on. Set to 0 to be ready immediately.
INIT_DELAY_SECONDS = float(os.getenv("init_delay_seconds", "5"))

_started = time.monotonic()
_ready = False


async def _initialize():
    """Stand-in for real start-up work: model load, cache warm-up, DB pool."""
    global _ready
    await asyncio.sleep(INIT_DELAY_SECONDS)
    _ready = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kick init off the request path so the server can bind and answer probes
    # while it runs.
    task = asyncio.create_task(_initialize())
    yield
    task.cancel()


app = FastAPI(title=FUNCTION_NAME, lifespan=lifespan)


@app.middleware("http")
async def access_log(request: Request, call_next):
    """Log every request except the kubelet's probes."""
    started = time.monotonic()
    response = await call_next(request)

    if not request.headers.get("user-agent", "").startswith(PROBE_USER_AGENT):
        logger.info(
            "%s %s - %d (%.4fs)",
            request.method,
            request.url.path,
            response.status_code,
            time.monotonic() - started,
        )

    return response


def _info():
    return {
        "function": FUNCTION_NAME,
        "runtime": RUNTIME,
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "ready": _ready,
        "uptime_seconds": round(time.monotonic() - _started, 3),
    }


@app.get("/ready")
async def ready():
    """Custom readiness: alive, but not able to take traffic until init ends."""
    body = {"status": "ready" if _ready else "initializing", **_info()}
    return JSONResponse(body, status_code=200 if _ready else 503)


@app.api_route("/{path:path}", methods=["GET", "PUT", "POST", "PATCH", "DELETE"])
async def echo(request: Request, path: str):
    """Reflect the request back as JSON, echoing any body that was sent."""
    # ?sleep=N stalls the response. exec_timeout cuts the caller loose at the
    # deadline, but this coroutine keeps running inside the long-lived uvicorn
    # process: the "slept" line below is logged in full, long after the caller
    # gave up. Only python3-classic can actually stop the work.
    delay = request.query_params.get("sleep")
    if delay:
        logger.info("sleeping for %ss", delay)
        await asyncio.sleep(float(delay))
        logger.info("slept for %ss -- still running after any timeout", delay)

    payload = {
        **_info(),
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "headers": dict(request.headers),
    }

    body = await request.body()
    if body:
        payload["echo"] = body.decode("utf-8", "replace")
        payload["bytes"] = len(body)
        payload["content_type"] = request.headers.get("content-type")

    return payload


if __name__ == "__main__":
    import uvicorn

    # Bind to loopback only -- the watchdog is the only client, and it is the
    # process that serves 8080 to the outside world. access_log is off because
    # uvicorn's own access record cannot see the User-Agent -- the access_log
    # middleware above logs instead.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        access_log=False,
    )
