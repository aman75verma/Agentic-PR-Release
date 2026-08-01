"""
db_tool — Audit log operations against PostgreSQL.

Actions:
  log_review       — Insert a PR review record
  log_deployment   — Insert a deployment record
  log_rollback     — Insert a rollback record
  get_last_good_tag — Query the most recent 'smoke_test_passed' tag for an environment
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


def log_review(pr_number: int, verdict: str, reasoning: str) -> dict:
    """Insert a PR review and return the created row id."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pr_reviews (pr_number, verdict, reasoning) VALUES (%s, %s, %s) RETURNING id",
            (pr_number, verdict, reasoning),
        )
        row_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "id": row_id}
    finally:
        conn.close()


def log_deployment(environment: str, image_tag: str, status: str, triggered_by: str = "agent") -> dict:
    """Insert a deployment record and return the created row id."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO deployments (environment, image_tag, status, triggered_by) VALUES (%s, %s, %s, %s) RETURNING id",
            (environment, image_tag, status, triggered_by),
        )
        row_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "id": row_id}
    finally:
        conn.close()


def log_rollback(deployment_id: int, reasoning: str, reverted_to_tag: str) -> dict:
    """Insert a rollback record."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO rollbacks (deployment_id, reasoning, reverted_to_tag) VALUES (%s, %s, %s) RETURNING id",
            (deployment_id, reasoning, reverted_to_tag),
        )
        row_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "id": row_id}
    finally:
        conn.close()


def get_last_good_tag(environment: str) -> dict:
    """Return the image_tag of the most recent 'smoke_test_passed' deployment for the given environment."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT image_tag FROM deployments WHERE environment = %s AND status = 'smoke_test_passed' ORDER BY created_at DESC LIMIT 1",
            (environment,),
        )
        row = cur.fetchone()
        if row:
            return {"status": "ok", "image_tag": row[0]}
        return {"status": "not_found", "image_tag": None}
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
