"""The same echo/info API again, this time on the classic watchdog.

The classic watchdog forks `python3 index.py` once per request: the body
arrives on stdin, the response goes out on stdout, and the request metadata is
passed in `Http_*` environment variables.

That fork-per-request model is the reason to reach for this template. Because
each request is its own process, `exec_timeout` can actually kill work that
overruns -- the watchdog kills the child. With of-watchdog in http mode the
timeout aborts the HTTP response, but the Python thread serving it keeps
running inside the long-lived server, still holding its memory.

The costs are real: a process spawn per request, no warm state between
requests (so nothing to gate a readiness check on, and no connection pooling),
and the handler cannot choose a status code -- returning normally is 200, a
non-zero exit is 500.
"""

import json
import os
import platform
import socket
import time
from urllib.parse import unquote_plus

FUNCTION_NAME = os.getenv("OPENFAAS_NAME", "python3-classic")
RUNTIME = "python3 template (classic watchdog, fork per request)"

_started = time.monotonic()

# Set by the watchdog itself, so not real request headers.
_RESERVED = {
    "Http_Method",
    "Http_Path",
    "Http_Query",
    "Http_Host",
    "Http_ContentLength",
    "Http_Content_Length",
    "Http_Transfer_Encoding",
}


def _headers():
    """Rebuild the request headers from the watchdog's Http_* env vars."""
    headers = {}
    for key, value in os.environ.items():
        if key.startswith("Http_") and key not in _RESERVED:
            headers[key[len("Http_"):].replace("_", "-")] = value
    return headers


def _query():
    raw = os.getenv("Http_Query", "")
    query = {}
    for pair in raw.split("&"):
        if not pair:
            continue
        name, _, value = pair.partition("=")
        query[unquote_plus(name)] = unquote_plus(value)
    return query


def handle(req):
    query = _query()

    # Sleep on demand so there is something for exec_timeout to interrupt.
    # This is the whole point of the classic watchdog: the fork gets killed.
    if "sleep" in query:
        time.sleep(float(query["sleep"]))

    headers = _headers()

    body = {
        "function": FUNCTION_NAME,
        "runtime": RUNTIME,
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        # Always true: a fresh process per request has no warm-up to wait for.
        "ready": True,
        # Always ~0 for the same reason -- compare with the other three, whose
        # uptime climbs because the process is long-lived.
        "uptime_seconds": round(time.monotonic() - _started, 3),
        "method": os.getenv("Http_Method", ""),
        "path": os.getenv("Http_Path", "/"),
        "query": query,
        "headers": headers,
    }

    if req:
        body["echo"] = req
        body["bytes"] = len(req.encode("utf-8"))
        body["content_type"] = headers.get("Content-Type")

    return json.dumps(body)
