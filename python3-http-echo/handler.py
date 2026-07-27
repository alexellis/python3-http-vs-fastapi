def handle(event, context):
    if event.method == "POST":
        return {"statusCode": 200, "body": {"echo": event.body.decode()}}

    return {"statusCode": 200, "body": {"message": "Hello from python3-http"}}
