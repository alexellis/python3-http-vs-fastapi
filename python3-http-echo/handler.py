def handle(event, context):
    if event.path == "/ready":
        # Check real dependencies here (DB, model); return a 503 until ready.
        return {"statusCode": 200, "body": "OK"}

    if event.method == "POST":
        return {"statusCode": 200, "body": {"echo": event.body.decode()}}

    return {"statusCode": 200, "body": {"message": "Hello from python3-http"}}
