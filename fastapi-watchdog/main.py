import os

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()


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
    # The watchdog serves 8080 and the health checks, and proxies here.
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
