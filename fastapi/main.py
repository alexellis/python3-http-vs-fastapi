"""A FastAPI microservice deployed to OpenFaaS without a watchdog.

Nothing OpenFaaS-specific is installed in this image. The app satisfies the
OpenFaaS workload definition on its own:

  * serves HTTP traffic on TCP port 8080
  * implements /_/health  (liveness)  and /_/ready (readiness)
  * is stateless and assumes ephemeral storage
  * shuts down gracefully on SIGTERM (uvicorn handles this)

https://docs.openfaas.com/reference/workloads/

Because there is no watchdog, the watchdog's environment variables
(read_timeout, write_timeout, exec_timeout, max_inflight, prefix_logs, ...)
have no effect here — timeouts and concurrency are uvicorn's job.
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

# Probes from the kubelet fire every couple of seconds and would otherwise be
# the entire log. The of-watchdog drops them by User-Agent prefix, so do the
# same here -- see executor/http_runner.go in openfaas/of-watchdog.
PROBE_USER_AGENT = "kube-probe"

# No timestamp in the format: the platform's log collector adds its own, and
# a second one just doubles up in "faas-cli logs" output.
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("function")

FUNCTION_NAME = os.getenv("OPENFAAS_NAME", "fastapi")
RUNTIME = "FastAPI + uvicorn, no watchdog"

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


@app.get("/_/health")
async def health():
    """Liveness: the process is up and serving. Kill and restart it if not."""
    return {"status": "alive", **_info()}


@app.get("/_/ready")
@app.get("/ready")
async def ready():
    """Readiness: alive, but not yet able to take traffic until init finishes."""
    body = {"status": "ready" if _ready else "initializing", **_info()}
    return JSONResponse(body, status_code=200 if _ready else 503)


@app.api_route("/{path:path}", methods=["GET", "PUT", "POST", "PATCH", "DELETE"])
async def echo(request: Request, path: str):
    """Reflect the request back as JSON, echoing any body that was sent."""
    # ?sleep=N stalls the response. Nothing here can interrupt it: there is no
    # watchdog, and uvicorn is given no timeout, so the work runs to completion
    # even after the caller has given up. Compare with python3-classic.
    delay = request.query_params.get("sleep")
    if delay:
        logger.info("sleeping for %ss", delay)
        await asyncio.sleep(float(delay))
        logger.info("slept for %ss -- nothing here can interrupt it", delay)

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

    # Port 8080 is the OpenFaaS contract for a workload without a watchdog.
    # access_log is off because uvicorn's own access record cannot see the
    # User-Agent -- the access_log middleware above logs instead.
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        access_log=False,
    )
