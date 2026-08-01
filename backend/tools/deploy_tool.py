"""
deploy_tool — Deploy, rollback, and smoke-test the demo app environments.

Actions:
  deploy          — Restart a docker-compose service with a new IMAGE_TAG
  rollback        — Redeploy with the last known-good tag from the DB
  run_smoke_test  — Hit /health, /tasks, /version with retry logic
"""

import subprocess
import time
import requests as http_requests
from backend.config import ENV_URLS
from backend.tools import db_tool

# Map environment names to docker-compose service names
SERVICE_MAP = {
    "dev": "taskapi-dev",
    "staging": "taskapi-staging",
    "prod": "taskapi-prod",
}


def deploy(environment: str, image_tag: str) -> dict:
    """
    Redeploy a docker-compose service with a new IMAGE_TAG.
    We update the env var and recreate the container.
    """
    service = SERVICE_MAP.get(environment)
    if not service:
        return {"status": "error", "detail": f"Unknown environment: {environment}"}

    try:
        # Set the IMAGE_TAG env var and recreate just this service
        result = subprocess.run(
            ["docker-compose", "up", "-d", "--no-deps", "--build", service],
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **__import__("os").environ,
                "IMAGE_TAG": image_tag,
            },
        )
        if result.returncode != 0:
            return {"status": "error", "detail": result.stderr}
        return {"status": "ok", "environment": environment, "image_tag": image_tag}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def run_smoke_test(environment: str) -> dict:
    """
    Hit /health, /tasks, and /version on the environment.
    Uses retry logic: 3 attempts, 2 seconds apart.
    """
    base_url = ENV_URLS.get(environment)
    if not base_url:
        return {"status": "error", "detail": f"Unknown environment: {environment}"}

    endpoints = ["/health", "/tasks", "/version"]
    results = {}

    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        success = False
        last_error = ""

        for attempt in range(1, 4):  # 3 attempts
            try:
                resp = http_requests.get(url, timeout=5)
                if resp.status_code == 200:
                    results[endpoint] = {"status": "pass", "response": resp.json()}
                    success = True
                    break
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
            except Exception as e:
                last_error = str(e)

            if attempt < 3:
                time.sleep(2)

        if not success:
            results[endpoint] = {"status": "fail", "error": last_error}

    # Overall pass/fail
    all_passed = all(r["status"] == "pass" for r in results.values())
    return {
        "status": "pass" if all_passed else "fail",
        "environment": environment,
        "results": results,
    }


def rollback(environment: str) -> dict:
    """
    Query the DB for the last known-good tag and redeploy with it.
    """
    tag_result = db_tool.get_last_good_tag(environment)
    if tag_result["status"] == "not_found" or tag_result["image_tag"] is None:
        return {"status": "error", "detail": f"No known-good tag found for {environment}"}

    good_tag = tag_result["image_tag"]
    deploy_result = deploy(environment, good_tag)
    if deploy_result["status"] == "ok":
        return {"status": "ok", "environment": environment, "reverted_to_tag": good_tag}
    return deploy_result


# ── Dispatcher (called by the agent) ──────────────────────────────────
def run(action: str, environment: str, image_tag: str = "") -> dict:
    """Route an action to the right function."""
    if action == "deploy":
        return deploy(environment, image_tag)
    elif action == "rollback":
        return rollback(environment)
    elif action == "run_smoke_test":
        return run_smoke_test(environment)
    else:
        return {"status": "error", "detail": f"Unknown action: {action}"}
