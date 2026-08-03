"""
review_agent.py — Decision 1: PR Review (multi-tenant)

Takes a PR number + repo + token, fetches the diff from GitHub,
sends it to the LLM with the review rubric, and posts the verdict as a PR comment.
"""

import json
from groq import Groq
from backend.config import GROQ_API_KEY
from backend.agent.prompts import PR_REVIEW_SYSTEM_PROMPT
from backend.tools import github_tool, db_tool


client = Groq(api_key=GROQ_API_KEY)


def review_pr(pr_number: int, repo: str, token: str) -> dict:
    """
    Full PR review flow (multi-tenant):
    1. Fetch diff from GitHub using the repo owner's token
    2. Send diff + rubric to LLM
    3. Post verdict as PR comment
    4. If approved, submit an approving review
    5. Log the review in Postgres with repo context
    """
    print(f"[review_agent] Starting review for PR #{pr_number} on {repo}")

    # Step 1: Get the PR diff
    diff_result = github_tool.get_diff(pr_number, repo=repo, token=token)
    if diff_result["status"] != "ok":
        return {"status": "error", "detail": f"Failed to fetch diff: {diff_result}"}

    diff_text = diff_result["diff"]

    # Truncate very large diffs to avoid token limits
    if len(diff_text) > 10000:
        diff_text = diff_text[:10000] + "\n\n... (diff truncated for review)"

    # Step 2: Send to LLM for review
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": PR_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the PR diff for PR #{pr_number} on {repo}:\n\n```diff\n{diff_text}\n```"},
        ],
        temperature=0.2,
        max_tokens=500,
    )

    raw_response = response.choices[0].message.content.strip()

    # Step 3: Parse the LLM's JSON response
    try:
        decision = json.loads(raw_response)
        verdict = decision["verdict"]
        reasoning = decision["reasoning"]
    except (json.JSONDecodeError, KeyError):
        # Fallback: treat raw text as reasoning, default to changes_requested
        verdict = "changes_requested"
        reasoning = f"LLM response could not be parsed: {raw_response}"

    # Step 4: Post comment on the PR
    comment_body = f"## 🤖 Agent PR Review\n\n**Verdict:** `{verdict}`\n\n**Reasoning:** {reasoning}"
    github_tool.post_comment(pr_number, comment_body, repo=repo, token=token)

    # Step 5: If approved, submit an approving review
    if verdict == "approved":
        github_tool.approve_pr(pr_number, repo=repo, token=token)

    # Step 6: Log in Postgres with repo context
    db_tool.log_review(repo=repo, pr_number=pr_number, verdict=verdict, reasoning=reasoning)

    print(f"[review_agent] PR #{pr_number} on {repo}: {verdict}")
    return {
        "status": "ok",
        "repo": repo,
        "pr_number": pr_number,
        "verdict": verdict,
        "reasoning": reasoning,
    }
