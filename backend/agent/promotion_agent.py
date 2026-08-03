"""
promotion_agent.py — Decisions 2/3/4: Promote through dev → staging → prod (multi-tenant, event-driven)

With Approach B, deployments are async:
  1. Our server triggers a GitHub workflow_dispatch in the user's repo
  2. The workflow builds/deploys on GitHub Actions
  3. The workflow calls back to POST /webhook/deploy-result
  4. This agent resumes: LLM decides to promote, rollback, or complete

Pipeline state is tracked in the `pipeline_runs` table (or in-memory for MVP).
"""

import json
from groq import Groq
from backend.config import GROQ_API_KEY
from backend.agent.prompts import PROMOTION_SYSTEM_PROMPT
from backend.tools import deploy_tool, db_tool, slack_tool


client = Groq(api_key=GROQ_API_KEY)

ENVIRONMENT_ORDER = ["dev", "staging", "prod"]
NEXT_ENV = {"dev": "staging", "staging": "prod"}

# ── In-memory pipeline state (MVP) ───────────────────────────────────
# In production, this would be stored in a `pipeline_runs` table.
# Key: "owner/repo", Value: {image_tag, current_env, status}
_active_pipelines: dict[str, dict] = {}


def start_pipeline(image_tag: str, repo: str, token: str) -> dict:
    """
    Kick off the promotion pipeline by triggering a deploy to dev.
    Non-blocking — returns immediately after dispatching the workflow.
    """
    print(f"[promotion_agent] Starting pipeline for {repo} with image {image_tag}")

    # Save pipeline state
    _active_pipelines[repo] = {
        "image_tag": image_tag,
        "token": token,
        "current_env": "dev",
        "status": "deploying",
    }

    # Trigger deploy to dev
    result = deploy_tool.trigger_deploy(repo, token, "dev", image_tag)
    db_tool.log_deployment(repo=repo, environment="dev", image_tag=image_tag, status="deployed")

    if result["status"] != "ok":
        msg = f"🚨 Failed to trigger dev deploy for `{repo}`: {result.get('detail', 'unknown')}"
        slack_tool.send_message(msg)
        _active_pipelines[repo]["status"] = "failed"
        return {"status": "error", "detail": msg}

    slack_tool.send_message(f"🚀 Pipeline started for `{repo}` — deploying `{image_tag}` to *dev*...")
    return {"status": "accepted", "repo": repo, "image_tag": image_tag, "message": "Dev deploy triggered"}


def on_deploy_result(repo: str, environment: str, image_tag: str, deploy_status: str) -> dict:
    """
    Called when the deploy workflow reports back via /webhook/deploy-result.
    Resumes the promotion loop:
      1. Log the result
      2. Ask the LLM what to do
      3. Promote, rollback, or complete
    """
    print(f"[promotion_agent] Deploy result for {repo}/{environment}: {deploy_status}")

    pipeline = _active_pipelines.get(repo)
    if not pipeline:
        print(f"[promotion_agent] No active pipeline for {repo}, ignoring callback")
        return {"status": "ignored", "detail": f"No active pipeline for {repo}"}

    token = pipeline["token"]

    # Log the deploy result
    smoke_status = "smoke_test_passed" if deploy_status == "success" else "smoke_test_failed"
    db_tool.log_deployment(repo=repo, environment=environment, image_tag=image_tag, status=smoke_status)

    # Build context for the LLM
    smoke_result = {
        "status": deploy_status,
        "environment": environment,
        "detail": f"Deploy workflow reported: {deploy_status}",
    }

    prompt = PROMOTION_SYSTEM_PROMPT.format(
        image_tag=image_tag,
        environment=environment,
        smoke_result=json.dumps(smoke_result, indent=2),
    )

    # Ask LLM what to do
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Deploy to {environment} result: {deploy_status}. What should we do?"},
        ],
        temperature=0.1,
        max_tokens=300,
    )

    raw_response = response.choices[0].message.content.strip()

    try:
        decision = json.loads(raw_response)
        action = decision["action"]
        reasoning = decision["reasoning"]
    except (json.JSONDecodeError, KeyError):
        # Fallback to safe behavior
        if deploy_status == "success":
            action = "promote" if environment != "prod" else "complete"
            reasoning = f"LLM response unparseable, but deploy succeeded. Defaulting to {action}."
        else:
            action = "rollback"
            reasoning = f"LLM response unparseable and deploy failed. Defaulting to rollback."

    # Execute the decision
    if action == "rollback":
        rollback_result = deploy_tool.rollback(repo, token, environment)
        reverted_tag = rollback_result.get("reverted_to_tag", "unknown")
        db_tool.log_rollback(
            repo=repo,
            deployment_id=0,  # Simplified for MVP
            reasoning=reasoning,
            reverted_to_tag=reverted_tag,
        )
        msg = f"🚨 *Rollback in {environment}* for `{repo}`\n\nImage `{image_tag}` failed.\nReverted to `{reverted_tag}`.\n\nReason: {reasoning}"
        slack_tool.send_message(msg)
        _active_pipelines[repo]["status"] = "rolled_back"

    elif action == "promote":
        next_env = NEXT_ENV.get(environment, "unknown")
        _active_pipelines[repo]["current_env"] = next_env
        _active_pipelines[repo]["status"] = "deploying"

        # Trigger deploy to next environment
        deploy_tool.trigger_deploy(repo, token, next_env, image_tag)
        db_tool.log_deployment(repo=repo, environment=next_env, image_tag=image_tag, status="deployed")

        msg = f"✅ *{environment}* passed for `{repo}` (`{image_tag}`). Promoting to *{next_env}*."
        slack_tool.send_message(msg)

    elif action == "complete":
        msg = f"🎉 *Pipeline complete!* `{repo}` — Image `{image_tag}` successfully deployed to *prod*."
        slack_tool.send_message(msg)
        _active_pipelines[repo]["status"] = "complete"
        # Clean up
        del _active_pipelines[repo]

    return {
        "status": "ok",
        "repo": repo,
        "environment": environment,
        "action": action,
        "reasoning": reasoning,
    }


# ── Legacy synchronous entry point (kept for direct testing) ─────────
def promote_through_pipeline(image_tag: str, repo: str = "", token: str = "") -> dict:
    """
    Entry point called from /webhook/merge.
    With Approach B, this just kicks off the async pipeline.
    """
    if repo and token:
        return start_pipeline(image_tag, repo, token)
    return {"status": "error", "detail": "Missing repo or token"}


def get_pipeline_status(repo: str) -> dict | None:
    """Return the current pipeline state for a repo, or None."""
    return _active_pipelines.get(repo)
