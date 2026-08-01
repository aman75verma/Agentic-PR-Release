"""
promotion_agent.py — Decisions 2/3/4: Promote through dev → staging → prod

Loops through each environment sequentially:
  1. Deploy the image
  2. Run smoke test
  3. Ask LLM what to do next (promote / rollback / complete)
  4. Execute the LLM's decision
"""

import json
from groq import Groq
from backend.config import GROQ_API_KEY
from backend.agent.prompts import PROMOTION_SYSTEM_PROMPT
from backend.tools import deploy_tool, db_tool, slack_tool


client = Groq(api_key=GROQ_API_KEY)

ENVIRONMENT_ORDER = ["dev", "staging", "prod"]
NEXT_ENV = {"dev": "staging", "staging": "prod"}


def promote_through_pipeline(image_tag: str) -> dict:
    """
    Sequential promotion loop: dev → staging → prod.
    At each stage: deploy, smoke test, ask LLM, act on decision.
    Stops on rollback or after prod succeeds.
    """
    results = []

    for environment in ENVIRONMENT_ORDER:
        stage_result = _process_stage(environment, image_tag)
        results.append(stage_result)

        if stage_result["action"] == "rollback":
            # Pipeline stops here — don't promote further
            break
        elif stage_result["action"] == "complete":
            # We reached prod and passed — pipeline done!
            break

    return {"status": "ok", "image_tag": image_tag, "stages": results}


def _process_stage(environment: str, image_tag: str) -> dict:
    """
    Process a single environment stage:
    1. Deploy
    2. Smoke test
    3. LLM decides: promote / rollback / complete
    4. Execute the decision
    """
    # Step 1: Deploy to this environment
    deploy_result = deploy_tool.deploy(environment, image_tag)
    db_tool.log_deployment(environment=environment, image_tag=image_tag, status="deployed")

    if deploy_result["status"] != "ok":
        msg = f"🚨 Deploy to {environment} failed: {deploy_result.get('detail', 'unknown error')}"
        slack_tool.send_message(msg)
        return {"environment": environment, "action": "rollback", "reasoning": msg}

    # Step 2: Run smoke test
    smoke_result = deploy_tool.run_smoke_test(environment)
    smoke_status = smoke_result["status"]  # "pass" or "fail"

    # Update deployment status in DB
    db_status = "smoke_test_passed" if smoke_status == "pass" else "smoke_test_failed"
    db_tool.log_deployment(environment=environment, image_tag=image_tag, status=db_status)

    # Step 3: Ask LLM what to do
    prompt = PROMOTION_SYSTEM_PROMPT.format(
        image_tag=image_tag,
        environment=environment,
        smoke_result=json.dumps(smoke_result, indent=2),
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Smoke test result for {environment}: {smoke_status}. What should we do?"},
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
        # If LLM response is unparseable, fall back to safe behavior
        if smoke_status == "pass":
            action = "promote" if environment != "prod" else "complete"
            reasoning = f"LLM response unparseable, but smoke test passed. Defaulting to {action}."
        else:
            action = "rollback"
            reasoning = f"LLM response unparseable and smoke test failed. Defaulting to rollback."

    # Step 4: Execute the decision
    if action == "rollback":
        rollback_result = deploy_tool.rollback(environment)
        reverted_tag = rollback_result.get("reverted_to_tag", "unknown")
        db_tool.log_rollback(
            deployment_id=0,  # Simplified — in production you'd track the actual deployment ID
            reasoning=reasoning,
            reverted_to_tag=reverted_tag,
        )
        msg = f"🚨 *Rollback in {environment}*\n\nImage `{image_tag}` failed smoke tests.\nReverted to `{reverted_tag}`.\n\nReason: {reasoning}"
        slack_tool.send_message(msg)

    elif action == "promote":
        next_env = NEXT_ENV.get(environment, "unknown")
        msg = f"✅ *{environment}* passed smoke tests for `{image_tag}`. Promoting to *{next_env}*."
        slack_tool.send_message(msg)

    elif action == "complete":
        msg = f"🎉 *Pipeline complete!* Image `{image_tag}` successfully deployed to *prod*. All smoke tests passed."
        slack_tool.send_message(msg)

    return {
        "environment": environment,
        "action": action,
        "reasoning": reasoning,
        "smoke_status": smoke_status,
    }
