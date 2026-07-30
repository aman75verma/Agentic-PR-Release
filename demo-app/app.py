import os
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException

app = FastAPI(title="TaskAPI Demo")

BUG_MODE = os.environ.get("INJECT_BUG", "false").lower() == "true"
ENV_NAME = os.environ.get("ENV_NAME", "unknown")
IMAGE_TAG = os.environ.get("IMAGE_TAG", "local")

@app.get("/health")
def health():
    if BUG_MODE:
        raise HTTPException(status_code=500, detail="simulated failure")
    return {"status": "ok"}

@app.get("/tasks")
def tasks():
    if BUG_MODE:
        raise Exception("simulated crash")
    return {"tasks": ["write report", "review PR", "deploy app"]}

@app.get("/version")
def version():
    return {"version": IMAGE_TAG, "environment": ENV_NAME}