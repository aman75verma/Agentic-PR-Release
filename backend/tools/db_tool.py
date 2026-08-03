"""
db_tool — Audit log operations against PostgreSQL (multi-tenant).

All write functions now take a `repo` param to scope data per-repository.

Actions:
  log_review       — Insert a PR review record
  log_deployment   — Insert a deployment record
  log_rollback     — Insert a rollback record
  get_last_good_tag — Query the most recent 'smoke_test_passed' tag for a repo + environment

Dashboard queries:
  get_reviews_for_repo     — Latest reviews for a repo
  get_deployments_for_repo — Latest deployments for a repo
  get_rollbacks_for_repo   — Latest rollbacks for a repo
"""

import psycopg2
from backend.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


def _get_conn():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


# ── Write operations ─────────────────────────────────────────────────

def log_review(repo: str, pr_number: int, verdict: str, reasoning: str) -> dict:
    """Insert a PR review and return the created row id."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pr_reviews (repo, pr_number, verdict, reasoning) VALUES (%s, %s, %s, %s) RETURNING id",
            (repo, pr_number, verdict, reasoning),
        )
        row_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "id": row_id}
    finally:
        conn.close()


def log_deployment(repo: str, environment: str, image_tag: str, status: str, triggered_by: str = "agent") -> dict:
    """Insert a deployment record and return the created row id."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO deployments (repo, environment, image_tag, status, triggered_by) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (repo, environment, image_tag, status, triggered_by),
        )
        row_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "id": row_id}
    finally:
        conn.close()


def log_rollback(repo: str, deployment_id: int, reasoning: str, reverted_to_tag: str) -> dict:
    """Insert a rollback record."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO rollbacks (repo, deployment_id, reasoning, reverted_to_tag) VALUES (%s, %s, %s, %s) RETURNING id",
            (repo, deployment_id, reasoning, reverted_to_tag),
        )
        row_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "id": row_id}
    finally:
        conn.close()


def get_last_good_tag(repo: str, environment: str) -> dict:
    """Return the image_tag of the most recent 'smoke_test_passed' deployment for a repo + environment."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT image_tag FROM deployments WHERE repo = %s AND environment = %s AND status = 'smoke_test_passed' ORDER BY created_at DESC LIMIT 1",
            (repo, environment),
        )
        row = cur.fetchone()
        if row:
            return {"status": "ok", "image_tag": row[0]}
        return {"status": "not_found", "image_tag": None}
    finally:
        conn.close()


# ── Dashboard read queries ───────────────────────────────────────────

def get_reviews_for_repo(repo: str, limit: int = 20) -> list:
    """Return the latest PR reviews for a repo."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, pr_number, verdict, reasoning, created_at FROM pr_reviews WHERE repo = %s ORDER BY created_at DESC LIMIT %s",
            (repo, limit),
        )
        return [
            {"id": r[0], "pr_number": r[1], "verdict": r[2], "reasoning": r[3], "created_at": str(r[4])}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def get_deployments_for_repo(repo: str, limit: int = 20) -> list:
    """Return the latest deployments for a repo."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, environment, image_tag, status, triggered_by, created_at FROM deployments WHERE repo = %s ORDER BY created_at DESC LIMIT %s",
            (repo, limit),
        )
        return [
            {"id": r[0], "environment": r[1], "image_tag": r[2], "status": r[3], "triggered_by": r[4], "created_at": str(r[5])}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def get_rollbacks_for_repo(repo: str, limit: int = 20) -> list:
    """Return the latest rollbacks for a repo."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, deployment_id, reasoning, reverted_to_tag, created_at FROM rollbacks WHERE repo = %s ORDER BY created_at DESC LIMIT %s",
            (repo, limit),
        )
        return [
            {"id": r[0], "deployment_id": r[1], "reasoning": r[2], "reverted_to_tag": r[3], "created_at": str(r[4])}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def get_repo_stats(repo: str) -> dict:
    """Return summary stats for a repo dashboard."""
    conn = _get_conn()
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM pr_reviews WHERE repo = %s", (repo,))
        total_reviews = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM deployments WHERE repo = %s", (repo,))
        total_deployments = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM rollbacks WHERE repo = %s", (repo,))
        total_rollbacks = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM deployments WHERE repo = %s AND status IN ('deployed', 'smoke_test_passed')",
            (repo,),
        )
        successful = cur.fetchone()[0]
        success_rate = round((successful / total_deployments * 100), 1) if total_deployments > 0 else 0

        return {
            "total_reviews": total_reviews,
            "total_deployments": total_deployments,
            "total_rollbacks": total_rollbacks,
            "success_rate": success_rate,
        }
    finally:
        conn.close()


# ── Dispatcher (called by the agent) ──────────────────────────────────
def run(action: str, payload: dict | None = None) -> dict:
    """Route an action to the right function."""
    payload = payload or {}
    if action == "log_review":
        return log_review(**payload)
    elif action == "log_deployment":
        return log_deployment(**payload)
    elif action == "log_rollback":
        return log_rollback(**payload)
    elif action == "get_last_good_tag":
        return get_last_good_tag(**payload)
    else:
        return {"status": "error", "detail": f"Unknown action: {action}"}
