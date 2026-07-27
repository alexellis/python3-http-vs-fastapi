import json
import os


def handle(req):
    # The classic watchdog passes the request body as a string, and the HTTP
    # method in the Http_Method environment variable.
    if os.getenv("Http_Method") == "POST":
        return json.dumps({"echo": req})

    return json.dumps({"message": "Hello from the classic watchdog"})
