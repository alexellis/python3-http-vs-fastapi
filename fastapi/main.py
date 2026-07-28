import os

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()


# Without a watchdog, the app serves the OpenFaaS health and readiness checks.
@app.get("/_/health")
@app.get("/_/ready")
def health():
    return "OK"


@app.get("/ready")
def ready():
    # Check real dependencies here (DB, model); return a 503 until ready.
    return "OK"


@app.get("/")
def index():
    return {"message": "Hello from FastAPI"}


@app.post("/")
async def echo(request: Request):
    body = await request.body()
    return {"echo": body.decode()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
