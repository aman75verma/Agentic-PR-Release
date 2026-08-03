"""
main.py — FastAPI backend for the Agentic PR Release pipeline.

Endpoints:
  POST /webhook/pr     — GitHub webhook: triggered on PR open/update → runs review agent
  POST /webhook/merge  — GitHub webhook: triggered on merge → runs promotion agent loop
  GET  /admin/audit-log — Returns recent reviews, deployments, and rollbacks for the dashboard
  GET  /health          — Backend health check
  GET  /                — Serves the dashboard UI
"""

import os
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.agent import review_agent, promotion_agent
from backend.tools import db_tool

app = FastAPI(title="Agentic PR Release — Backend")

# Allow the dashboard to call our API from any origin (for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the dashboard static files
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")


@app.get("/")
def serve_dashboard():
    """Serve the dashboard UI."""
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentic-pr-backend"}


@app.post("/webhook/pr")
async def webhook_pr(request: Request, background_tasks: BackgroundTasks):
    """
    Called by GitHub Actions when a PR is opened or updated.
    Expects JSON: { "pr_number": 1 }
    Runs the review agent in the background so the webhook returns fast.
    """
    body = await request.json()
    pr_number = body.get("pr_number")

    if not pr_number:
        return {"status": "error", "detail": "Missing pr_number"}

    # Run review in the background so the webhook response is fast
    background_tasks.add_task(review_agent.review_pr, pr_number)

    return {"status": "accepted", "pr_number": pr_number, "message": "Review agent started"}


@app.post("/webhook/merge")
async def webhook_merge(request: Request, background_tasks: BackgroundTasks):
    """
    Called by GitHub Actions when a PR is merged to main.
    Expects JSON: { "image_tag": "abc123" }
    Runs the promotion pipeline (dev → staging → prod) in the background.
    """
    body = await request.json()
    image_tag = body.get("image_tag")

    if not image_tag:
        return {"status": "error", "detail": "Missing image_tag"}

    # Run promotion pipeline in the background
    background_tasks.add_task(promotion_agent.promote_through_pipeline, image_tag)

    return {"status": "accepted", "image_tag": image_tag, "message": "Promotion pipeline started"}


@app.get("/admin/audit-log")
def audit_log():
    """
    Returns recent reviews, deployments, and rollbacks for the dashboard.
    """
    import psycopg2
    from backend.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    cur = conn.cursor()

    # Fetch latest 20 of each
    cur.execute("SELECT id, pr_number, verdict, reasoning, created_at FROM pr_reviews ORDER BY created_at DESC LIMIT 20")
    reviews = [{"id": r[0], "pr_number": r[1], "verdict": r[2], "reasoning": r[3], "created_at": str(r[4])} for r in cur.fetchall()]

    cur.execute("SELECT id, environment, image_tag, status, triggered_by, created_at FROM deployments ORDER BY created_at DESC LIMIT 20")
    deployments = [{"id": r[0], "environment": r[1], "image_tag": r[2], "status": r[3], "triggered_by": r[4], "created_at": str(r[5])} for r in cur.fetchall()]

    cur.execute("SELECT id, deployment_id, reasoning, reverted_to_tag, created_at FROM rollbacks ORDER BY created_at DESC LIMIT 20")
    rollbacks = [{"id": r[0], "deployment_id": r[1], "reasoning": r[2], "reverted_to_tag": r[3], "created_at": str(r[4])} for r in cur.fetchall()]

    conn.close()

    return {
        "reviews": reviews,
        "deployments": deployments,
        "rollbacks": rollbacks,
    }
