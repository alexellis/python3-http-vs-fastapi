"""The same behaviour again, written against the python3-http template.

Nothing here builds a web server or a Dockerfile -- the template supplies
of-watchdog, Flask and waitress, and calls handle() once per request with an
event/context pair. The trade is less control for far less boilerplate.

/_/health and /_/ready are served by the watchdog. /ready below is a custom
readiness endpoint, wired up in stack.yaml via com.openfaas.ready.http.path.
"""

import os
import platform
import threading
import time

FUNCTION_NAME = os.getenv("OPENFAAS_NAME", "python3-http-echo")
RUNTIME = "python3-http template (Flask + waitress) behind of-watchdog"

# Stands in for real start-up work, so the readiness probe has something to
# gate on. Set to 0 to be ready immediately.
INIT_DELAY_SECONDS = float(os.getenv("init_delay_seconds", "5"))

_started = time.monotonic()
_ready = False


def _initialize():
    """Stand-in for real start-up work: model load, cache warm-up, DB pool."""
    global _ready
    time.sleep(INIT_DELAY_SECONDS)
    _ready = True


# Kick init off the request path at module load, so waitress can bind and
# answer probes while it runs.
threading.Thread(target=_initialize, daemon=True).start()


def _info(context):
    return {
        "function": FUNCTION_NAME,
        "runtime": RUNTIME,
        "python": platform.python_version(),
        "hostname": context.hostname,
        "ready": _ready,
        "uptime_seconds": round(time.monotonic() - _started, 3),
    }


def handle(event, context):
    if event.path == "/ready":
        return {
            "statusCode": 200 if _ready else 503,
            "body": {"status": "ready" if _ready else "initializing", **_info(context)},
        }

    # ?sleep=N stalls the response. exec_timeout cuts the caller loose, but the
    # waitress worker thread keeps running to completion inside the long-lived
    # process -- the same limitation as fastapi-watchdog.
    delay = event.query.get("sleep")
    if delay:
        time.sleep(float(delay))

    body = {
        **_info(context),
        "method": event.method,
        "path": event.path,
        "query": dict(event.query),
        "headers": dict(event.headers),
    }

    if event.body:
        body["echo"] = event.body.decode("utf-8", "replace")
        body["bytes"] = len(event.body)
        body["content_type"] = event.headers.get("Content-Type")

    return {"statusCode": 200, "body": body}
