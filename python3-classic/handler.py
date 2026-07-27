import json


def handle(req):
    if req:
        return json.dumps({"echo": req})

    return json.dumps({"message": "Hello from the classic watchdog"})
