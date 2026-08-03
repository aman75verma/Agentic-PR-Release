"""
github_tool — Interact with any GitHub repo via the REST API.

Multi-tenant: every function takes `repo` and `token` params.
No global headers or repo references.

Actions:
  get_diff     — Fetch the unified diff of a PR
  post_comment — Post a comment on a PR
  add_label    — Add a label to a PR
  approve_pr   — Submit an approving review
  merge_pr     — Merge a PR
"""

import requests

API = "https://api.github.com"


def _headers(token: str, accept: str = "application/vnd.github+json") -> dict:
    """Build auth headers from a per-user token."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_diff(pr_number: int, repo: str, token: str) -> dict:
    """Fetch the diff of a pull request."""
    url = f"{API}/repos/{repo}/pulls/{pr_number}"
    resp = requests.get(
        url, headers=_headers(token, "application/vnd.github.v3.diff"), timeout=15
    )
    if resp.ok:
        return {"status": "ok", "diff": resp.text}
    return {"status": "error", "detail": resp.text}


def post_comment(pr_number: int, comment_body: str, repo: str, token: str) -> dict:
    """Post a comment on a pull request."""
    url = f"{API}/repos/{repo}/issues/{pr_number}/comments"
    resp = requests.post(
        url, headers=_headers(token), json={"body": comment_body}, timeout=15
    )
    if resp.ok:
        return {"status": "ok", "comment_url": resp.json().get("html_url")}
    return {"status": "error", "detail": resp.text}


def add_label(pr_number: int, label: str, repo: str, token: str) -> dict:
    """Add a label to a pull request."""
    url = f"{API}/repos/{repo}/issues/{pr_number}/labels"
    resp = requests.post(
        url, headers=_headers(token), json={"labels": [label]}, timeout=15
    )
    if resp.ok:
        return {"status": "ok"}
    return {"status": "error", "detail": resp.text}


def approve_pr(pr_number: int, repo: str, token: str) -> dict:
    """Submit an approving review on a pull request."""
    url = f"{API}/repos/{repo}/pulls/{pr_number}/reviews"
    resp = requests.post(
        url, headers=_headers(token), json={"event": "APPROVE"}, timeout=15
    )
    if resp.ok:
        return {"status": "ok"}
    return {"status": "error", "detail": resp.text}


def merge_pr(pr_number: int, repo: str, token: str) -> dict:
    """Merge a pull request."""
    url = f"{API}/repos/{repo}/pulls/{pr_number}/merge"
    resp = requests.put(
        url, headers=_headers(token), json={"merge_method": "squash"}, timeout=15
    )
    if resp.ok:
        return {"status": "ok", "sha": resp.json().get("sha")}
    return {"status": "error", "detail": resp.text}


# ── Dispatcher (called by the agent) ──────────────────────────────────
def run(action: str, pr_number: int, repo: str, token: str, **kwargs) -> dict:
    """Route an action to the right function."""
    if action == "get_diff":
        return get_diff(pr_number, repo=repo, token=token)
    elif action == "post_comment":
        return post_comment(pr_number, kwargs.get("comment_body", ""), repo=repo, token=token)
    elif action == "add_label":
        return add_label(pr_number, kwargs.get("label", ""), repo=repo, token=token)
    elif action == "approve_pr":
        return approve_pr(pr_number, repo=repo, token=token)
    elif action == "merge_pr":
        return merge_pr(pr_number, repo=repo, token=token)
    else:
        return {"status": "error", "detail": f"Unknown action: {action}"}
