"""
deploy_tool — Trigger deployments via GitHub Actions workflow_dispatch (Approach B).

In the multi-tenant SaaS model, we don't run docker-compose locally.
Instead, we trigger the `agentic_deploy.yml` workflow in the user's repo.
That workflow runs on the user's GitHub Actions runner, builds/deploys
their code, and reports back to our server via a callback URL.

Actions:
  trigger_deploy    — Dispatch the deploy workflow in the user's repo
  rollback          — Look up last good tag and trigger a deploy with it
  run_smoke_test    — Hit a URL to check if the deployment is alive (optional)
"""

import requests as http_requests
from backend.config import AGENT_PUBLIC_URL
from backend.tools import db_tool


def trigger_deploy(repo: str, token: str, environment: str, image_tag: str) -> dict:
    """
    Trigger the agentic_deploy.yml workflow in the user's repo via workflow_dispatch.

    The workflow receives:
      - environment: dev / staging / prod
      - image_tag: the git SHA or Docker image tag to deploy
      - callback_url: where to POST the result back to our server

    Returns immediately — the actual deploy is async on GitHub Actions.
    """
    callback_url = f"{AGENT_PUBLIC_URL}/webhook/deploy-result"
    url = f"https://api.github.com/repos/{repo}/actions/workflows/agentic_deploy.yml/dispatches"

    resp = http_requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "ref": "main",
            "inputs": {
                "environment": environment,
                "image_tag": image_tag,
                "callback_url": callback_url,
            },
        },
        timeout=15,
    )

    # GitHub returns 204 No Content on success
    if resp.status_code == 204:
        return {"status": "ok", "environment": environment, "image_tag": image_tag, "message": "Workflow dispatched"}
    return {"status": "error", "detail": resp.text, "status_code": resp.status_code}


def rollback(repo: str, token: str, environment: str) -> dict:
    """
    Query the DB for the last known-good tag for this repo+environment
    and trigger a deploy with it.
    """
    tag_result = db_tool.get_last_good_tag(repo=repo, environment=environment)
    if tag_result["status"] == "not_found" or tag_result["image_tag"] is None:
        return {"status": "error", "detail": f"No known-good tag found for {repo}/{environment}"}

    good_tag = tag_result["image_tag"]
    deploy_result = trigger_deploy(repo, token, environment, good_tag)
    if deploy_result["status"] == "ok":
        return {"status": "ok", "environment": environment, "reverted_to_tag": good_tag}
    return deploy_result


def run_smoke_test(environment: str, health_url: str = "") -> dict:
    """
    Optional server-side smoke test — hit a health URL.

    In Approach B, the deploy workflow itself can run tests.
    This function is a lightweight fallback for when the user
    provides environment URLs they want us to check.
    """
    if not health_url:
        # No URL provided — trust the deploy workflow's exit status
        return {"status": "pass", "environment": environment, "detail": "No health URL configured, trusting workflow"}

    try:
        resp = http_requests.get(health_url, timeout=10)
        if resp.status_code == 200:
            return {"status": "pass", "environment": environment, "response": resp.text[:500]}
        return {"status": "fail", "environment": environment, "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "fail", "environment": environment, "detail": str(e)}


# ── Dispatcher (called by the agent) ──────────────────────────────────
def run(action: str, repo: str, token: str, environment: str, image_tag: str = "") -> dict:
    """Route an action to the right function."""
    if action == "deploy":
        return trigger_deploy(repo, token, environment, image_tag)
    elif action == "rollback":
        return rollback(repo, token, environment)
    elif action == "run_smoke_test":
        return run_smoke_test(environment)
    else:
        return {"status": "error", "detail": f"Unknown action: {action}"}
