"""
repo_manager.py — Install/uninstall workflow files in user repos & manage enabled repos.

Uses the GitHub Contents API to programmatically commit workflow YAML files
into the user's repository when they click "Enable" on the dashboard.

Functions:
  get_user_repos       — Fetch user's public repos from GitHub
  install_workflows    — Create all 3 workflow files via GitHub API
  uninstall_workflows  — Delete the 3 workflow files via GitHub API
  check_workflows      — Check if workflow files exist in a repo
  enable_repo          — Install workflows + register in DB
  disable_repo         — Uninstall workflows + unregister from DB
"""

import os
import base64
import psycopg2
import requests as http_requests

from backend.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

API = "https://api.github.com"

# The 3 workflow template files we inject
WORKFLOW_TEMPLATES = [
    "agentic_pr_review.yml",
    "agentic_merge_notify.yml",
    "agentic_deploy.yml",
]

# Directory containing the template files
_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "workflow_templates")


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )


# ── GitHub Repo Listing ─────────────────────────────────────────────

def get_user_repos(token: str) -> list:
    """Fetch the user's public repos from GitHub, sorted by most recently updated."""
    repos = []
    page = 1
    while True:
        resp = http_requests.get(
            f"{API}/user/repos",
            headers=_headers(token),
            params={
                "visibility": "public",
                "sort": "updated",
                "per_page": 30,
                "page": page,
                "affiliation": "owner",
            },
            timeout=15,
        )
        if not resp.ok:
            break
        batch = resp.json()
        if not batch:
            break
        for r in batch:
            repos.append({
                "full_name": r["full_name"],
                "name": r["name"],
                "description": r.get("description") or "",
                "language": r.get("language") or "",
                "stargazers_count": r.get("stargazers_count", 0),
                "updated_at": r.get("updated_at", ""),
                "html_url": r.get("html_url", ""),
                "default_branch": r.get("default_branch", "main"),
            })
        if len(batch) < 30:
            break
        page += 1
    return repos


# ── Workflow Installation ────────────────────────────────────────────

def _read_template(filename: str, agent_url: str) -> str:
    """Read a workflow template file and replace {AGENT_URL} placeholder."""
    filepath = os.path.join(_TEMPLATES_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return content.replace("{AGENT_URL}", agent_url)


def _put_file(repo: str, token: str, path: str, content: str, message: str) -> dict:
    """Create or update a file in a GitHub repo via the Contents API."""
    url = f"{API}/repos/{repo}/contents/{path}"

    # Check if file already exists (need its SHA to update)
    existing_sha = None
    check = http_requests.get(url, headers=_headers(token), timeout=15)
    if check.ok:
        existing_sha = check.json().get("sha")

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if existing_sha:
        payload["sha"] = existing_sha

    resp = http_requests.put(url, headers=_headers(token), json=payload, timeout=15)
    if resp.ok or resp.status_code == 201:
        return {"status": "ok", "path": path}
    return {"status": "error", "path": path, "detail": resp.text, "status_code": resp.status_code}


def _delete_file(repo: str, token: str, path: str) -> dict:
    """Delete a file from a GitHub repo via the Contents API."""
    url = f"{API}/repos/{repo}/contents/{path}"

    # Get file SHA (required for deletion)
    check = http_requests.get(url, headers=_headers(token), timeout=15)
    if not check.ok:
        # File doesn't exist — nothing to delete
        return {"status": "ok", "path": path, "detail": "File not found, skipping"}

    sha = check.json().get("sha")
    resp = http_requests.delete(
        url,
        headers=_headers(token),
        json={"message": f"Remove {path} (Agentic PR Release)", "sha": sha},
        timeout=15,
    )
    if resp.ok:
        return {"status": "ok", "path": path}
    return {"status": "error", "path": path, "detail": resp.text}


def install_workflows(repo: str, token: str, agent_url: str) -> dict:
    """Install all 3 workflow files into the user's repo."""
    results = []
    for template_name in WORKFLOW_TEMPLATES:
        content = _read_template(template_name, agent_url)
        path = f".github/workflows/{template_name}"
        result = _put_file(
            repo, token, path, content,
            message=f"Add {template_name} (Agentic PR Release)",
        )
        results.append(result)

    all_ok = all(r["status"] == "ok" for r in results)
    return {
        "status": "ok" if all_ok else "partial_error",
        "results": results,
    }


def uninstall_workflows(repo: str, token: str) -> dict:
    """Remove all 3 workflow files from the user's repo."""
    results = []
    for template_name in WORKFLOW_TEMPLATES:
        path = f".github/workflows/{template_name}"
        result = _delete_file(repo, token, path)
        results.append(result)

    all_ok = all(r["status"] == "ok" for r in results)
    return {
        "status": "ok" if all_ok else "partial_error",
        "results": results,
    }


def check_workflows(repo: str, token: str) -> dict:
    """Check which workflow files exist in the user's repo."""
    found = {}
    for template_name in WORKFLOW_TEMPLATES:
        path = f".github/workflows/{template_name}"
        url = f"{API}/repos/{repo}/contents/{path}"
        resp = http_requests.get(url, headers=_headers(token), timeout=15)
        found[template_name] = resp.ok

    all_installed = all(found.values())
    return {
        "status": "ok",
        "all_installed": all_installed,
        "files": found,
    }


# ── Enable / Disable Repos ──────────────────────────────────────────

def enable_repo(user_id: int, repo_full_name: str, description: str,
                language: str, token: str, agent_url: str) -> dict:
    """
    Enable a repo: install workflows + insert into enabled_repos.
    Called when user clicks "Enable" on the dashboard.
    """
    # Step 1: Install workflows into the repo
    install_result = install_workflows(repo_full_name, token, agent_url)
    workflows_installed = install_result["status"] == "ok"

    # Step 2: Register in our DB
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO enabled_repos (user_id, repo_full_name, repo_description, repo_language, workflows_installed)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, repo_full_name) DO UPDATE SET
                repo_description = EXCLUDED.repo_description,
                repo_language = EXCLUDED.repo_language,
                workflows_installed = EXCLUDED.workflows_installed
            RETURNING id
            """,
            (user_id, repo_full_name, description, language, workflows_installed),
        )
        repo_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok",
        "repo_id": repo_id,
        "repo_full_name": repo_full_name,
        "workflows_installed": workflows_installed,
        "install_details": install_result,
    }


def disable_repo(user_id: int, repo_full_name: str, token: str) -> dict:
    """
    Disable a repo: uninstall workflows + delete from enabled_repos.
    Called when user clicks "Disconnect" on the dashboard.
    """
    # Step 1: Uninstall workflows from the repo
    uninstall_result = uninstall_workflows(repo_full_name, token)

    # Step 2: Remove from our DB
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM enabled_repos WHERE user_id = %s AND repo_full_name = %s",
            (user_id, repo_full_name),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok",
        "repo_full_name": repo_full_name,
        "uninstall_details": uninstall_result,
    }


def get_enabled_repos(user_id: int) -> list:
    """Return all enabled repos for a user."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT repo_full_name, repo_description, repo_language, workflows_installed, enabled_at FROM enabled_repos WHERE user_id = %s ORDER BY enabled_at DESC",
            (user_id,),
        )
        return [{
            "repo_full_name": r[0],
            "description": r[1] or "",
            "language": r[2] or "",
            "workflows_installed": r[3],
            "enabled_at": str(r[4]),
        } for r in cur.fetchall()]
    finally:
        conn.close()
