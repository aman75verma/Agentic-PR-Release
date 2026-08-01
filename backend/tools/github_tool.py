"""
github_tool — Interact with a GitHub repo via the REST API.

Actions:
  get_diff     — Fetch the unified diff of a PR
  post_comment — Post a comment on a PR
  add_label    — Add a label to a PR
  approve_pr   — Submit an approving review
  merge_pr     — Merge a PR
"""

import requests
from backend.config import GITHUB_TOKEN, TARGET_REPO

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def get_diff(pr_number: int) -> dict:
    """Fetch the diff of a pull request."""
    url = f"{API}/repos/{TARGET_REPO}/pulls/{pr_number}"
    headers = {**HEADERS, "Accept": "application/vnd.github.v3.diff"}
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.ok:
        return {"status": "ok", "diff": resp.text}
    return {"status": "error", "detail": resp.text}


def post_comment(pr_number: int, comment_body: str) -> dict:
    """Post a comment on a pull request."""
    url = f"{API}/repos/{TARGET_REPO}/issues/{pr_number}/comments"
    resp = requests.post(url, headers=HEADERS, json={"body": comment_body}, timeout=15)
    if resp.ok:
        return {"status": "ok", "comment_url": resp.json().get("html_url")}
    return {"status": "error", "detail": resp.text}


def add_label(pr_number: int, label: str) -> dict:
    """Add a label to a pull request."""
    url = f"{API}/repos/{TARGET_REPO}/issues/{pr_number}/labels"
    resp = requests.post(url, headers=HEADERS, json={"labels": [label]}, timeout=15)
    if resp.ok:
        return {"status": "ok"}
    return {"status": "error", "detail": resp.text}


def approve_pr(pr_number: int) -> dict:
    """Submit an approving review on a pull request."""
    url = f"{API}/repos/{TARGET_REPO}/pulls/{pr_number}/reviews"
    resp = requests.post(
        url, headers=HEADERS, json={"event": "APPROVE"}, timeout=15
    )
    if resp.ok:
        return {"status": "ok"}
    return {"status": "error", "detail": resp.text}


def merge_pr(pr_number: int) -> dict:
    """Merge a pull request."""
    url = f"{API}/repos/{TARGET_REPO}/pulls/{pr_number}/merge"
    resp = requests.put(url, headers=HEADERS, json={"merge_method": "squash"}, timeout=15)
    if resp.ok:
        return {"status": "ok", "sha": resp.json().get("sha")}
    return {"status": "error", "detail": resp.text}


# ── Dispatcher (called by the agent) ──────────────────────────────────
def run(action: str, pr_number: int, **kwargs) -> dict:
    """Route an action to the right function."""
    if action == "get_diff":
        return get_diff(pr_number)
    elif action == "post_comment":
        return post_comment(pr_number, kwargs.get("comment_body", ""))
    elif action == "add_label":
        return add_label(pr_number, kwargs.get("label", ""))
    elif action == "approve_pr":
        return approve_pr(pr_number)
    elif action == "merge_pr":
        return merge_pr(pr_number)
    else:
        return {"status": "error", "detail": f"Unknown action: {action}"}
