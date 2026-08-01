# Build Logs

## 2026-07-30
- Project initialized, docs created, repo pushed to GitHub
- Analyzed project, proposed 6 improvements (FastAPI, SQLite, docker-compose, /version, github_tool expand, retry logic)
- User approved all 6 improvements + Groq LLM + separate demo repo + Render deployment goal
- Updated `ProjectChunks.md` and `Agentic PR Release.md` with all locked decisions
- Created `Study.md` with per-chunk study guide
- **Implemented Chunk 1:** Created `demo-app` (FastAPI) with health, tasks, and version endpoints. Built Docker image and tested happy path and bug injection. Pushed to remote.
- **Implemented Chunk 2:** Created `docker-compose.yml` defining `taskapi-dev`, `taskapi-staging`, and `taskapi-prod` services. Verified all three containers successfully spun up and exposed on ports 8081, 8082, and 8083.
- **Implemented Chunk 3:** Created `backend/db/schema_pg.sql` with PostgreSQL definitions for `pr_reviews`, `deployments`, and `rollbacks`. Added a `db` service to `docker-compose.yml` to automatically initialize the database. Tested container startup and verified inserts work correctly.

## 2026-08-01
- **Implemented Chunk 4:** Created all 4 MCP tools as standalone Python modules in `backend/tools/`:
  - `db_tool.py` — CRUD operations against Postgres (log_review, log_deployment, log_rollback, get_last_good_tag)
  - `github_tool.py` — GitHub REST API (get_diff, post_comment, add_label, approve_pr, merge_pr)
  - `slack_tool.py` — Slack Incoming Webhook (send_message, graceful skip if unconfigured)
  - `deploy_tool.py` — Docker-compose management (deploy, rollback, run_smoke_test with 3-attempt retry)
  - Created `backend/config.py` for centralized secrets/settings and `backend/.env.example`
  - All 7 tests passed: DB writes, DB reads, smoke test against live dev container, and Slack graceful skip
- **Implemented Chunks 5 and 6:** 
  - Created `backend/agent/prompts.py` with strict JSON rubrics for PR review and Promotion gates.
  - Created `backend/agent/review_agent.py` to fetch PR diffs, query Llama 3.3 for a verdict, post GitHub comments, and log to Postgres.
  - Created `backend/agent/promotion_agent.py` to orchestrate sequential deployment (dev → staging → prod), smoke testing, LLM decision making, and auto-rollback.
  - Created `backend/main.py` (FastAPI) exposing `/webhook/pr` and `/webhook/merge` (triggering agents via background tasks) and `/admin/audit-log`. Tested server startup and endpoints.
- **Implemented Chunk 7:**
  - Created `.github/workflows/pr_review.yml` to trigger the `review_agent` when a PR is opened.
  - Created `.github/workflows/merge_promotion.yml` to build/push a Docker image to Docker Hub and trigger the `promotion_agent` when a PR is merged to `main`.
