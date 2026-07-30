# Project 2 — Implementation Blueprint
### Every decision locked. Chunk-by-chunk, ready for a lesser model to implement.

---

## CHUNK 0 — Scope (Locked)

**Project:** Agentic Release Pipeline — PR review + auto-promote (dev→staging→prod) + self-healing rollback.

**Explicit scope-limiting decisions (do not expand these):**
- Environments are simulated via 3 lightweight deployments of the same image — not real production infra.
- The demo app is intentionally trivial — a few endpoints plus a bug toggle. Do not build real product features into it.
- Smoke tests are simple HTTP checks (status code + expected response shape) — not a full test suite.

If you (or your coding agent) find yourselves adding features beyond what's in this document, stop — that's scope creep against the time budget.

---

## CHUNK 1 — Demo App (Locked — Updated)

A minimal FastAPI app, `demo-app/app.py`:

```python
import os
from fastapi import FastAPI, HTTPException

app = FastAPI(title="TaskAPI Demo")

BUG_MODE = os.environ.get("INJECT_BUG", "false").lower() == "true"
ENV_NAME = os.environ.get("ENV_NAME", "unknown")
IMAGE_TAG = os.environ.get("IMAGE_TAG", "local")

@app.get("/health")
def health():
    if BUG_MODE:
        raise HTTPException(status_code=500, detail="simulated failure")
    return {"status": "ok"}

@app.get("/tasks")
def tasks():
    if BUG_MODE:
        raise Exception("simulated crash")
    return {"tasks": ["write report", "review PR", "deploy app"]}

@app.get("/version")
def version():
    return {"version": IMAGE_TAG, "environment": ENV_NAME}
```

`Dockerfile` for this app: standard Python slim base, copy app, `pip install fastapi uvicorn`, `CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]`.

**Definition of done:** running the container with `INJECT_BUG=false` returns 200 on `/health`, `/tasks`, and `/version`; with `INJECT_BUG=true` returns 500 / crashes. The `/version` endpoint always works regardless of bug mode.

---

## CHUNK 2 — Environments (Locked — docker-compose)

Three deployments of the same image via **docker-compose**, differing by `ENV_NAME` and `INJECT_BUG`:

| Environment | docker-compose service | Port |
|---|---|---|
| dev | `taskapi-dev` | 8081 |
| staging | `taskapi-staging` | 8082 |
| prod | `taskapi-prod` | 8083 |

**Deployment method: docker-compose** (locked). One `docker-compose.yml` with three services, all built from the same image, differing only in env vars and exposed port. "Promotion" = restarting the next service with the new image tag.

**End goal:** Push images to DockerHub and deploy to Render for production demo URLs.

**Definition of done:** all three environments are independently reachable (three localhost ports) and each returns 200 on `/health` by default.

---

## CHUNK 3 — Database / Audit Log (Locked — SQLite)

Using **SQLite** for simplicity (zero setup, file-based). Can swap to PostgreSQL for Render deployment later.

```sql
CREATE TABLE IF NOT EXISTS pr_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_number INTEGER NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('approved', 'changes_requested')),
    reasoning TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    environment TEXT NOT NULL CHECK (environment IN ('dev', 'staging', 'prod')),
    image_tag TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('deployed', 'smoke_test_passed', 'smoke_test_failed', 'rolled_back')),
    triggered_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rollbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deployment_id INTEGER REFERENCES deployments(id),
    reasoning TEXT NOT NULL,
    reverted_to_tag TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**Definition of done:** three tables exist in `backend/db/audit.db`; a manual `INSERT` into each succeeds.

---

## CHUNK 4 — MCP Tool Definitions (Locked)

### Tool 1: `github_tool`
```json
{
  "name": "github_tool",
  "description": "Interact with the demo repo on GitHub: fetch PR diffs, post PR comments, add labels, approve or merge PRs.",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": { "type": "string", "enum": ["get_diff", "post_comment", "add_label", "approve_pr", "merge_pr"] },
      "pr_number": { "type": "integer" },
      "comment_body": { "type": "string" },
      "label": { "type": "string" }
    },
    "required": ["action", "pr_number"]
  }
}
```

### Tool 2: `slack_tool`
```json
{
  "name": "slack_tool",
  "description": "Post a message to the team Slack channel about a pipeline event (review result, promotion, rollback).",
  "input_schema": {
    "type": "object",
    "properties": {
      "message": { "type": "string" }
    },
    "required": ["message"]
  }
}
```
Implementation: a single POST to your Slack Incoming Webhook URL with `{"text": message}`. No SDK needed.

### Tool 3: `deploy_tool`
```json
{
  "name": "deploy_tool",
  "description": "Deploy or roll back the demo app in a given environment.",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": { "type": "string", "enum": ["deploy", "rollback", "run_smoke_test"] },
      "environment": { "type": "string", "enum": ["dev", "staging", "prod"] },
      "image_tag": { "type": "string" }
    },
    "required": ["action", "environment"]
  }
}
```
- `deploy`: redeploys the given environment with `image_tag` (docker-compose: restart service with new image)
- `rollback`: redeploys the environment with the last known-good tag (query `deployments` table for the most recent `smoke_test_passed` row for that environment)
- `run_smoke_test`: hits `/health`, `/tasks`, and `/version` on that environment's URL, returns pass/fail. **Uses retry logic** (3 attempts, 2s apart) to handle container startup delay.

### Tool 4: `db_tool`
```json
{
  "name": "db_tool",
  "description": "Write or read pipeline audit log entries (PR reviews, deployments, rollbacks).",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": { "type": "string", "enum": ["log_review", "log_deployment", "log_rollback", "get_last_good_tag"] },
      "payload": { "type": "object" }
    },
    "required": ["action"]
  }
}
```

---

## CHUNK 5 — Agent Decision Logic (Locked — Groq / Llama 3.3)

**LLM Provider:** Groq API (Llama 3.3) — free tier, fast inference, tool-calling capable.
**Target repo:** A separate demo repo (e.g., `taskapi-demo`) — keeps pipeline code separate from test PRs.

### Decision 1 — PR Review (system prompt)
```
You are reviewing a pull request for a demo project. You will be given the PR diff.
Check against this rubric:
1. Does the diff include or modify tests? (not always required, but flag if a non-trivial code change has zero test changes)
2. Any hardcoded secrets, API keys, or credentials visible in the diff?
3. Is the diff a reasonable size (flag if enormous/unfocused)?

Respond with a verdict: "approved" or "changes_requested", plus 2-3 sentences of reasoning.
Post this as a PR comment using github_tool, and log it using db_tool.
If approved, call github_tool with action=approve_pr.
```

### Decision 2/3/4 — Promotion Gate (same logic reused per environment)
```
You just deployed to {environment}. Run a smoke test using deploy_tool.
If it passes: log success via db_tool, and if this is not prod, trigger deploy_tool
to deploy the same image_tag to the next environment (dev→staging, staging→prod).
If it fails: call deploy_tool with action=rollback for {environment}, log the rollback
and your reasoning via db_tool, and send a Slack alert via slack_tool explaining what
failed and what you rolled back to.
```

**This is a sequential loop, not one prompt** — the backend orchestrator calls the LLM once per environment stage, feeding in the smoke test result each time. Implement it as a simple Python loop over `["dev", "staging", "prod"]`, not a single giant agent call.

---

## CHUNK 6 — Backend Structure (Locked)

```
backend/
  main.py                  # FastAPI app, webhook endpoint
  agent/
    review_agent.py         # Decision 1
    promotion_agent.py      # Decisions 2-4, looped per environment
    prompts.py               # Chunk 5 prompts
  tools/
    github_tool.py
    slack_tool.py
    deploy_tool.py
    db_tool.py
  db/
    schema.sql               # Chunk 3
  requirements.txt
  Dockerfile
```

**Required endpoints:**
- `POST /webhook/pr` — triggered by GitHub Actions on PR open/update → runs review agent
- `POST /webhook/merge` — triggered on merge to main → runs promotion agent loop across all 3 environments
- `GET /admin/audit-log` — returns recent reviews/deployments/rollbacks for your dashboard

---

## CHUNK 7 — GitHub Actions Pipeline (Locked)

`.github/workflows/pipeline.yml` — two workflows:

**Workflow A — on PR:**
```yaml
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  notify-agent:
    runs-on: ubuntu-latest
    steps:
      - name: Call review agent webhook
        run: curl -X POST $AGENT_URL/webhook/pr -d '{"pr_number": "${{ github.event.pull_request.number }}"}'
```

**Workflow B — on merge to main:**
```yaml
on:
  push:
    branches: [main]
jobs:
  build-and-notify:
    runs-on: ubuntu-latest
    steps:
      - name: Build and push image
        run: | 
          docker build -t taskapi:${{ github.sha }} ./demo-app
          # push to a registry (Docker Hub free tier or GitHub Container Registry)
      - name: Call promotion agent webhook
        run: curl -X POST $AGENT_URL/webhook/merge -d '{"image_tag": "${{ github.sha }}"}'
```

---

## CHUNK 8 — Minimal Dashboard (Locked, keep this small)

One React page, `AuditLog.tsx`, that calls `GET /admin/audit-log` and renders a simple table: timestamp, event type (review/deploy/rollback), environment, verdict/status, reasoning text (truncated, expandable). No auth, no styling investment beyond making it legible. This is a "proof it works" screen, not a product — don't over-invest time here.

---

## CHUNK 9 — Eval / Demo Scenarios (Locked)

Manually run these 4 scenarios and record the outcome — this is your test suite AND your demo script:

1. **Happy path:** open a clean PR (small diff, includes a test) → expect `approved` → merge → expect successful promotion through all 3 environments.
2. **Bad PR:** open a PR with an obvious hardcoded secret in the diff → expect `changes_requested`.
3. **Dev failure:** merge a change that sets `INJECT_BUG=true` in dev's config → expect smoke test fail → rollback → Slack alert, staging/prod untouched.
4. **Staging failure:** let dev pass, but flip the bug toggle for staging only → expect promotion to staging, smoke test fail there, rollback of staging only, prod untouched.

**Definition of done:** all 4 scenarios produce the expected audit log entries and Slack messages.

---

## CHUNK 10 — Build Order (Locked)

1. Chunk 1 (demo app) → verify bug toggle works locally
2. Chunk 2 (3 environments) → verify all reachable
3. Chunk 3 (DB schema) → verify tables exist
4. Chunk 4 (MCP tools) → verify each tool works standalone (test scripts, not through the agent yet)
5. Chunk 5 + 6 (agent logic + backend) → verify Decision 1 (PR review) end-to-end first, since it's simplest
6. Extend to Decisions 2-4 (promotion loop) → verify happy path (Scenario 1)
7. Verify failure/rollback scenarios (2-4)
8. Chunk 7 (wire real GitHub Actions triggers) → replace manual webhook calls with real pipeline triggers
9. Chunk 8 (dashboard) → last, and keep it minimal
10. README + demo recording

**Stop here.** Do not add environments, tools, or features beyond this list — the goal is a complete, demoable, explainable system within the time budget, not a maximal one.
