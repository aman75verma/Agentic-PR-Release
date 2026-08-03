"""
main.py — FastAPI backend for the Agentic PR Release pipeline.

Public endpoints:
  GET  /                                    — Serves the dashboard UI
  GET  /health                              — Backend health check
  GET  /auth/github/login                   — Redirect to GitHub OAuth
  GET  /auth/github/callback                — Handle OAuth callback
  POST /webhook/pr                          — PR notification (from user's GitHub Actions)
  POST /webhook/merge                       — Merge notification (from user's GitHub Actions)
  POST /webhook/deploy-result               — Deploy callback (from user's deploy workflow)

Authenticated endpoints:
  GET  /auth/me                             — Current user info
  POST /auth/logout                         — Clear session
  GET  /api/repos                           — User's public GitHub repos
  GET  /api/repos/enabled                   — User's enabled repos
  POST /api/repos/enable                    — Enable repo + install workflows
  POST /api/repos/disable                   — Disable repo + remove workflows
  GET  /api/repos/{owner}/{repo}/reviews    — PR reviews for a repo
  GET  /api/repos/{owner}/{repo}/deployments — Deployments for a repo
  GET  /api/repos/{owner}/{repo}/rollbacks  — Rollbacks for a repo
  GET  /api/repos/{owner}/{repo}/stats      — Summary stats for a repo
"""

import os
from fastapi import FastAPI, Request, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend import auth
from backend import repo_manager
from backend.tools import db_tool
from backend.config import AGENT_PUBLIC_URL

app = FastAPI(title="Agentic PR Release — Backend")

# Allow the dashboard to call our API from any origin (for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Serve the dashboard static files
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")


# ═══════════════════════════════════════════════════════════════════════
# STATIC / HEALTH
# ═══════════════════════════════════════════════════════════════════════

@app.get("/")
def serve_dashboard():
    """Serve the dashboard UI."""
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentic-pr-backend"}


# ═══════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════

@app.get("/auth/github/login")
def github_login():
    """Redirect user to GitHub's OAuth authorization page."""
    return auth.github_login()


@app.get("/auth/github/callback")
def github_callback(code: str = Query(None)):
    """Handle the OAuth callback from GitHub."""
    return auth.github_callback(code)


@app.get("/auth/me")
def me(user: dict = Depends(auth.require_auth)):
    """Return the currently authenticated user's info."""
    return {"status": "ok", "user": user}


@app.post("/auth/logout")
def logout():
    """Clear the session cookie."""
    return auth.logout()


# ═══════════════════════════════════════════════════════════════════════
# WEBHOOK ROUTES (called by GitHub Actions in user repos)
# ═══════════════════════════════════════════════════════════════════════

@app.post("/webhook/pr")
async def webhook_pr(request: Request, background_tasks: BackgroundTasks):
    """
    Called by agentic_pr_review.yml in user repos when a PR is opened/updated.
    Expects JSON: { "pr_number": 1, "repo": "owner/repo" }
    """
    body = await request.json()
    pr_number = body.get("pr_number")
    repo = body.get("repo")

    if not pr_number or not repo:
        return {"status": "error", "detail": "Missing pr_number or repo"}

    token = auth.get_token_for_repo(repo)
    if not token:
        return {"status": "error", "detail": f"Repo {repo} is not enabled or token not found"}

    from backend.agent import review_agent
    background_tasks.add_task(review_agent.review_pr, pr_number, repo, token)

    return {"status": "accepted", "pr_number": pr_number, "repo": repo, "message": "Review agent started"}


@app.post("/webhook/merge")
async def webhook_merge(request: Request, background_tasks: BackgroundTasks):
    """
    Called by agentic_merge_notify.yml in user repos when code is merged.
    Expects JSON: { "image_tag": "abc123", "repo": "owner/repo" }
    """
    body = await request.json()
    image_tag = body.get("image_tag")
    repo = body.get("repo")

    if not image_tag or not repo:
        return {"status": "error", "detail": "Missing image_tag or repo"}

    token = auth.get_token_for_repo(repo)
    if not token:
        return {"status": "error", "detail": f"Repo {repo} is not enabled or token not found"}

    from backend.agent import promotion_agent
    background_tasks.add_task(promotion_agent.promote_through_pipeline, image_tag, repo, token)

    return {"status": "accepted", "image_tag": image_tag, "repo": repo, "message": "Promotion pipeline started"}


@app.post("/webhook/deploy-result")
async def webhook_deploy_result(request: Request, background_tasks: BackgroundTasks):
    """
    Callback from agentic_deploy.yml in user repos.
    Expects JSON: { "repo": "...", "environment": "...", "image_tag": "...", "status": "success|failure" }
    """
    body = await request.json()
    repo = body.get("repo")
    environment = body.get("environment")
    image_tag = body.get("image_tag")
    deploy_status = body.get("status")

    if not all([repo, environment, image_tag, deploy_status]):
        return {"status": "error", "detail": "Missing required fields"}

    from backend.agent import promotion_agent
    background_tasks.add_task(
        promotion_agent.on_deploy_result, repo, environment, image_tag, deploy_status
    )

    return {"status": "accepted", "repo": repo, "environment": environment, "deploy_status": deploy_status}


# ═══════════════════════════════════════════════════════════════════════
# API ROUTES — REPO MANAGEMENT (authenticated)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/repos")
def list_repos(user: dict = Depends(auth.require_auth)):
    """List the user's public GitHub repos."""
    token = auth.get_user_token(user["id"])
    if not token:
        return {"status": "error", "detail": "No token found"}

    repos = repo_manager.get_user_repos(token)

    # Mark which repos are already enabled
    enabled = repo_manager.get_enabled_repos(user["id"])
    enabled_names = {r["repo_full_name"] for r in enabled}

    for r in repos:
        r["enabled"] = r["full_name"] in enabled_names

    return {"status": "ok", "repos": repos}


@app.get("/api/repos/enabled")
def list_enabled_repos(user: dict = Depends(auth.require_auth)):
    """List repos the user has enabled for the pipeline."""
    enabled = repo_manager.get_enabled_repos(user["id"])
    return {"status": "ok", "enabled_repos": enabled}


@app.post("/api/repos/enable")
async def enable_repo(request: Request, user: dict = Depends(auth.require_auth)):
    """
    Enable a repo: install 3 workflow files + register in DB.
    Expects JSON: { "repo": "owner/name", "description": "...", "language": "..." }
    """
    body = await request.json()
    repo_full_name = body.get("repo")
    description = body.get("description", "")
    language = body.get("language", "")

    if not repo_full_name:
        return {"status": "error", "detail": "Missing repo"}

    token = auth.get_user_token(user["id"])
    if not token:
        return {"status": "error", "detail": "No token found"}

    result = repo_manager.enable_repo(
        user_id=user["id"],
        repo_full_name=repo_full_name,
        description=description,
        language=language,
        token=token,
        agent_url=AGENT_PUBLIC_URL,
    )

    return result


@app.post("/api/repos/disable")
async def disable_repo(request: Request, user: dict = Depends(auth.require_auth)):
    """
    Disable a repo: uninstall workflow files + remove from DB.
    Expects JSON: { "repo": "owner/name" }
    """
    body = await request.json()
    repo_full_name = body.get("repo")

    if not repo_full_name:
        return {"status": "error", "detail": "Missing repo"}

    token = auth.get_user_token(user["id"])
    if not token:
        return {"status": "error", "detail": "No token found"}

    result = repo_manager.disable_repo(
        user_id=user["id"],
        repo_full_name=repo_full_name,
        token=token,
    )

    return result


# ═══════════════════════════════════════════════════════════════════════
# API ROUTES — REPO DATA (authenticated)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/repos/{owner}/{repo}/stats")
def repo_stats(owner: str, repo: str, user: dict = Depends(auth.require_auth)):
    """Return summary stats for a repo (total reviews, deployments, rollbacks, success rate)."""
    repo_full = f"{owner}/{repo}"
    stats = db_tool.get_repo_stats(repo_full)
    return {"status": "ok", "repo": repo_full, **stats}


@app.get("/api/repos/{owner}/{repo}/reviews")
def repo_reviews(owner: str, repo: str, limit: int = 20, user: dict = Depends(auth.require_auth)):
    """Return recent PR reviews for a repo."""
    repo_full = f"{owner}/{repo}"
    reviews = db_tool.get_reviews_for_repo(repo_full, limit=limit)
    return {"status": "ok", "repo": repo_full, "reviews": reviews}


@app.get("/api/repos/{owner}/{repo}/deployments")
def repo_deployments(owner: str, repo: str, limit: int = 20, user: dict = Depends(auth.require_auth)):
    """Return recent deployments for a repo."""
    repo_full = f"{owner}/{repo}"
    deployments = db_tool.get_deployments_for_repo(repo_full, limit=limit)
    return {"status": "ok", "repo": repo_full, "deployments": deployments}


@app.get("/api/repos/{owner}/{repo}/rollbacks")
def repo_rollbacks(owner: str, repo: str, limit: int = 20, user: dict = Depends(auth.require_auth)):
    """Return recent rollbacks for a repo."""
    repo_full = f"{owner}/{repo}"
    rollbacks = db_tool.get_rollbacks_for_repo(repo_full, limit=limit)
    return {"status": "ok", "repo": repo_full, "rollbacks": rollbacks}
