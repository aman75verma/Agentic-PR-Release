"""
slack_tool — Post messages to a Slack channel via Incoming Webhook.

Actions:
  send_message — Post a text message to Slack
"""

import requests
from backend.config import SLACK_WEBHOOK_URL


def send_message(message: str) -> dict:
    """Send a message to the configured Slack webhook."""
    if not SLACK_WEBHOOK_URL:
        # Gracefully skip if webhook is not configured yet
        print(f"[slack_tool] (no webhook configured) Would send: {message}")
        return {"status": "skipped", "detail": "No SLACK_WEBHOOK_URL configured"}

    resp = requests.post(
        SLACK_WEBHOOK_URL,
        json={"text": message},
        timeout=10,
    )
    if resp.ok:
        return {"status": "ok"}
    return {"status": "error", "detail": resp.text}


# ── Dispatcher (called by the agent) ──────────────────────────────────
def run(message: str) -> dict:
    """Route to send_message."""
    return send_message(message)
