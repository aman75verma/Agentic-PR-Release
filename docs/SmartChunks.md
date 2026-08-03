# SmartChunks — Implementation Roadmap

### Ordered for smooth dependency flow. Backend first, then frontend.

---

## What's Changing — Big Picture

```
BEFORE (single-tenant demo):                AFTER (multi-tenant SaaS):
─────────────────────────────                ─────────────────────────────
Agentic PR Release/                          Agentic PR Release/
├── .github/workflows/  ← REMOVE            ├── backend/
│   ├── pr_review.yml                        │   ├── main.py          (rewritten)
│   └── merge_promotion.yml                  │   ├── auth.py          (NEW)
├── demo-app/           ← REMOVE            │   ├── repo_manager.py  (NEW)
│   ├── app.py                               │   ├── config.py        (updated)
│   └── Dockerfile                           │   ├── workflow_templates/  (NEW)
├── backend/                                 │   │   ├── pr_review.yml
│   ├── main.py                              │   │   ├── merge_notify.yml
│   ├── tools/ (hardcoded token)             │   │   └── deploy.yml
│   └── agent/ (single repo)                 │   ├── agent/           (multi-tenant)
├── docker-compose.yml  ← SIMPLIFY           │   ├── tools/           (multi-tenant)
├── dashboard/index.html ← REDESIGN         │   └── db/schema_pg.sql (expanded)
└── scratch_create_pr.py ← REMOVE           ├── dashboard/index.html (full redesign)
                                             ├── docker-compose.yml   (db only)
                                             └── docs/
```

**Key removals:**
- `.github/workflows/` — these are server-side workflows that don't belong here. The workflows live in the USER'S repo (we inject them).
- `demo-app/` — this was the trivial test app. We're not shipping a demo app anymore; users bring their own repos.
- `scratch_create_pr.py` — dev artifact.
- 3 taskapi services from `docker-compose.yml` — no more local containers. Deployments happen on user's side via GitHub Actions (Approach B).

---

## CHUNK S1 — Cleanup & Restructure

**Goal:** Strip the repo down to just the server + dashboard. Remove everything that belonged to the "single-tenant demo" phase.

### Delete
- `demo-app/` (entire folder)
- `.github/workflows/pr_review.yml`
- `.github/workflows/merge_promotion.yml`
- `.github/workflows/` (the empty dir)
- `.github/` (the empty dir)
- `scratch_create_pr.py`

### Modify

#### [MODIFY] `docker-compose.yml`
Keep ONLY the `db` service. Remove `taskapi-dev`, `taskapi-staging`, `taskapi-prod`:

```yaml
version: '3.8'
services:
  db:
    image: postgres:15-alpine
    container_name: taskapi-db
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: password
      POSTGRES_DB: auditlog
    ports:
      - "5433:5432"
    volumes:
      - ./backend/db/schema_pg.sql:/docker-entrypoint-initdb.d/schema.sql
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  pgdata:
```

#### [MODIFY] `.gitignore`
Add entries for safety:

```
venv/
__pycache__/
*.pyc
.env
backend/.env
.DS_Store
node_modules/
*.log
```

### Definition of Done
- Repo has no `demo-app/`, no `.github/workflows/`, no `scratch_create_pr.py`
- `docker-compose up db` starts only Postgres
- Git status is clean after commit

---

## CHUNK S2 — Database Schema & Config

**Goal:** Expand the DB for multi-tenancy (users, repos) and update config for OAuth.

### Modify

#### [MODIFY] `backend/db/schema_pg.sql`

```sql
-- ── Users ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    github_id       INTEGER UNIQUE NOT NULL,
    username        TEXT NOT NULL,
    display_name    TEXT,
    avatar_url      TEXT,
    access_token    TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- ── Enabled Repos ──────────────────────────────
CREATE TABLE IF NOT EXISTS enabled_repos (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_full_name      TEXT NOT NULL,
    repo_description    TEXT,
    repo_language       TEXT,
    workflows_installed BOOLEAN DEFAULT false,
    enabled_at          TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE(user_id, repo_full_name)
);

-- ── PR Reviews (now per-repo) ──────────────────
CREATE TABLE IF NOT EXISTS pr_reviews (
    id          SERIAL PRIMARY KEY,
    repo        TEXT NOT NULL,
    pr_number   INTEGER NOT NULL,
    verdict     TEXT NOT NULL CHECK (verdict IN ('approved', 'changes_requested')),
    reasoning   TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);

-- ── Deployments (now per-repo) ─────────────────
CREATE TABLE IF NOT EXISTS deployments (
    id              SERIAL PRIMARY KEY,
    repo            TEXT NOT NULL,
    environment     TEXT NOT NULL CHECK (environment IN ('dev', 'staging', 'prod')),
    image_tag       TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN (
        'deployed', 'smoke_test_passed', 'smoke_test_failed', 'rolled_back'
    )),
    triggered_by    TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- ── Rollbacks (now per-repo) ───────────────────
CREATE TABLE IF NOT EXISTS rollbacks (
    id              SERIAL PRIMARY KEY,
    repo            TEXT NOT NULL,
    deployment_id   INTEGER REFERENCES deployments(id),
    reasoning       TEXT NOT NULL,
    reverted_to_tag TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- ── Indexes ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_reviews_repo ON pr_reviews(repo);
CREATE INDEX IF NOT EXISTS idx_deployments_repo ON deployments(repo);
CREATE INDEX IF NOT EXISTS idx_rollbacks_repo ON rollbacks(repo);
CREATE INDEX IF NOT EXISTS idx_enabled_repos_user ON enabled_repos(user_id);
```

#### [MODIFY] `backend/config.py`

Remove `GITHUB_TOKEN`, `TARGET_REPO`. Add:

```python
# GitHub OAuth App
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# Session
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me-in-prod")

# Public URL of this server (for workflow templates)
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8000")
```

#### [MODIFY] `backend/.env.example` and `backend/.env`

Update with new vars, remove old ones.

#### [MODIFY] `backend/requirements.txt`

```
fastapi
uvicorn
requests
psycopg2-binary
python-dotenv
groq
itsdangerous
```

### Definition of Done
- Drop old DB: `docker-compose down -v && docker-compose up db`
- All 6 tables created, indexes created
- `config.py` imports correctly with new vars
- No references to `GITHUB_TOKEN` or `TARGET_REPO` in config

---

## CHUNK S3 — GitHub OAuth Module

**Goal:** Users can sign in with GitHub. Session is managed via signed cookies.

### Create

#### [NEW] `backend/auth.py`

Contains:
- `github_login()` → redirect to `https://github.com/login/oauth/authorize?client_id=X&scope=repo,read:user`
- `github_callback(code)` → exchange code for token → upsert user in DB → set signed cookie → redirect to `/#/repos`
- `get_current_user(request)` → read cookie → return user dict or None
- `require_auth(request)` → FastAPI dependency that raises 401 if not logged in
- `logout()` → clear cookie

**OAuth scopes:** `repo` (read/write repo contents, PRs) + `read:user` (profile info)

**Session:** Use `itsdangerous.URLSafeTimedSerializer` to sign a cookie containing `user_id`. No JWT needed — keep it simple.

### Modify

#### [MODIFY] `backend/main.py`

Wire in the 4 auth routes:
```
GET  /auth/github/login     → auth.github_login()
GET  /auth/github/callback  → auth.github_callback()
GET  /auth/me               → auth.get_current_user()
POST /auth/logout            → auth.logout()
```

### Definition of Done
- Start backend, visit `/auth/github/login` → redirects to GitHub
- Authorize → callback creates user in DB, sets cookie
- `GET /auth/me` returns `{username, avatar_url, github_id}`
- `POST /auth/logout` clears cookie, `/auth/me` returns 401

### Prerequisite (Manual — do before starting this chunk)
Create a GitHub OAuth App at `github.com/settings/developers`:
- **Name:** Agentic PR Release
- **Homepage:** `http://localhost:8000`
- **Callback:** `http://localhost:8000/auth/github/callback`
- Copy Client ID + Secret → paste into `backend/.env`

---

## CHUNK S4 — Multi-Tenant Tools

**Goal:** Every tool accepts `repo` and `token` params instead of using globals.

### Modify

#### [MODIFY] `backend/tools/github_tool.py`

Every function signature changes:

```python
# All functions get repo + token params:
def get_diff(pr_number, repo, token) -> dict
def post_comment(pr_number, comment_body, repo, token) -> dict
def add_label(pr_number, label, repo, token) -> dict
def approve_pr(pr_number, repo, token) -> dict
def merge_pr(pr_number, repo, token) -> dict
```

Remove global `HEADERS` and `TARGET_REPO` imports. Build headers inside each function.

#### [MODIFY] `backend/tools/db_tool.py`

Add `repo` param to all write functions:

```python
def log_review(repo, pr_number, verdict, reasoning) -> dict
def log_deployment(repo, environment, image_tag, status, triggered_by="agent") -> dict
def log_rollback(repo, deployment_id, reasoning, reverted_to_tag) -> dict
def get_last_good_tag(repo, environment) -> dict  # filter by repo too
```

Add new query functions for the dashboard:

```python
def get_reviews_for_repo(repo, limit=20) -> list
def get_deployments_for_repo(repo, limit=20) -> list
def get_rollbacks_for_repo(repo, limit=20) -> list
```

#### [MODIFY] `backend/tools/deploy_tool.py`

**Complete rewrite.** Remove all docker-compose logic. Replace with GitHub workflow dispatch (Approach B):

```python
def trigger_deploy_workflow(repo, token, environment, image_tag, callback_url):
    """Trigger the agentic_deploy.yml workflow in the user's repo."""
    requests.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/agentic_deploy.yml/dispatches",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        json={
            "ref": "main",
            "inputs": {
                "environment": environment,
                "image_tag": image_tag,
                "callback_url": callback_url,
            }
        }
    )
```

Remove `SERVICE_MAP`, `subprocess` imports, docker-compose calls.

### Definition of Done
- `github_tool.get_diff(5, "aman75verma/taskapi-demo", token)` works
- `db_tool.log_review("alice/app", 1, "approved", "looks good")` inserts with `repo` column
- `deploy_tool.trigger_deploy_workflow(...)` sends a POST to GitHub API

---

## CHUNK S5 — Multi-Tenant Agents

**Goal:** Review and promotion agents work with per-user context. Promotion becomes event-driven.

### Modify

#### [MODIFY] `backend/agent/review_agent.py`

```python
def review_pr(pr_number: int, repo: str, token: str) -> dict:
    diff_result = github_tool.get_diff(pr_number, repo=repo, token=token)
    # ... LLM review (unchanged) ...
    github_tool.post_comment(pr_number, comment_body, repo=repo, token=token)
    db_tool.log_review(repo=repo, pr_number=pr_number, verdict=verdict, reasoning=reasoning)
```

#### [MODIFY] `backend/agent/promotion_agent.py`

The promotion loop changes from synchronous to **event-driven** (because Approach B deploys are async):

```
BEFORE (synchronous):
  for env in [dev, staging, prod]:
      deploy(env)          ← blocks until done
      smoke_test(env)      ← blocks until done
      llm_decide()

AFTER (event-driven):
  start_pipeline(repo, image_tag):
      trigger_deploy_workflow(repo, "dev", image_tag)
      save pipeline state: {repo, image_tag, current_stage: "dev", status: "deploying"}
      return  ← non-blocking

  on_deploy_result(repo, env, status):  ← called by /webhook/deploy-result
      load pipeline state
      if status == "success":
          llm_decide() → promote or complete
          if promote: trigger_deploy_workflow(repo, next_env, image_tag)
      if status == "failure":
          llm_decide() → rollback
          notify slack
```

#### [NEW] Pipeline state tracking

Add a `pipeline_runs` table (or use in-memory dict for MVP):

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          SERIAL PRIMARY KEY,
    repo        TEXT NOT NULL,
    image_tag   TEXT NOT NULL,
    current_env TEXT NOT NULL DEFAULT 'dev',
    status      TEXT NOT NULL DEFAULT 'in_progress',
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);
```

### Definition of Done
- `review_agent.review_pr(5, "aman75verma/taskapi-demo", token)` reviews and posts on correct repo
- `promotion_agent.start_pipeline(...)` triggers dev deploy and saves state
- Callback at `/webhook/deploy-result` resumes the pipeline and triggers next stage

---

## CHUNK S6 — Workflow Templates & Auto-Installer

**Goal:** Define the 3 workflow files we inject into user repos. Build the installer.

### Create

#### [NEW] `backend/workflow_templates/agentic_pr_review.yml`

```yaml
# Installed by Agentic PR Release
name: Agentic PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened]
jobs:
  notify-agent:
    runs-on: ubuntu-latest
    steps:
      - name: Notify Agentic PR Release
        run: |
          curl -sS -X POST "{AGENT_URL}/webhook/pr" \
            -H "Content-Type: application/json" \
            -d '{
              "pr_number": ${{{{ github.event.pull_request.number }}}},
              "repo": "${{{{ github.repository }}}}",
              "pr_title": "${{{{ github.event.pull_request.title }}}}",
              "sender": "${{{{ github.actor }}}}"
            }'
```

#### [NEW] `backend/workflow_templates/agentic_merge_notify.yml`

```yaml
# Installed by Agentic PR Release
name: Agentic Merge Notification
on:
  push:
    branches: [main]
jobs:
  notify-agent:
    runs-on: ubuntu-latest
    steps:
      - name: Notify Agentic PR Release
        run: |
          curl -sS -X POST "{AGENT_URL}/webhook/merge" \
            -H "Content-Type: application/json" \
            -d '{
              "repo": "${{{{ github.repository }}}}",
              "image_tag": "${{{{ github.sha }}}}",
              "sender": "${{{{ github.actor }}}}"
            }'
```

#### [NEW] `backend/workflow_templates/agentic_deploy.yml`

The one our server triggers via `workflow_dispatch`:

```yaml
# Installed by Agentic PR Release
# Customize the "Build and Deploy" step for your infrastructure.
name: Agentic Deploy
on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment (dev/staging/prod)'
        required: true
        type: string
      image_tag:
        description: 'Git SHA or image tag to deploy'
        required: true
        type: string
      callback_url:
        description: 'Callback URL to report result'
        required: true
        type: string
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build and Deploy
        run: |
          echo "Deploying ${{{{ inputs.image_tag }}}} to ${{{{ inputs.environment }}}}"
          # ┌──────────────────────────────────────────────┐
          # │  CUSTOMIZE THIS SECTION FOR YOUR INFRA       │
          # │  Examples:                                   │
          # │  • docker build + push                       │
          # │  • kubectl apply                             │
          # │  • aws ecs update-service                    │
          # └──────────────────────────────────────────────┘
          echo "Deploy complete (customize me!)"

      - name: Report success
        if: success()
        run: |
          curl -sS -X POST "${{{{ inputs.callback_url }}}}" \
            -H "Content-Type: application/json" \
            -d '{"repo":"${{{{ github.repository }}}}","environment":"${{{{ inputs.environment }}}}","image_tag":"${{{{ inputs.image_tag }}}}","status":"success"}'

      - name: Report failure
        if: failure()
        run: |
          curl -sS -X POST "${{{{ inputs.callback_url }}}}" \
            -H "Content-Type: application/json" \
            -d '{"repo":"${{{{ github.repository }}}}","environment":"${{{{ inputs.environment }}}}","image_tag":"${{{{ inputs.image_tag }}}}","status":"failure"}'
```

#### [NEW] `backend/repo_manager.py`

```python
def get_user_repos(user_token) -> list
    """GET /user/repos?visibility=public&sort=updated"""

def install_workflows(repo, token, agent_url) -> dict
    """Create all 3 workflow files via GitHub Contents API (PUT)"""

def uninstall_workflows(repo, token) -> dict
    """Delete the 3 workflow files via GitHub API (GET sha → DELETE)"""

def check_workflows_installed(repo, token) -> dict
    """Check if the 3 files exist in .github/workflows/"""

def enable_repo(user_id, repo, description, language, token, agent_url) -> dict
    """Install workflows + insert into enabled_repos"""

def disable_repo(user_id, repo, token) -> dict
    """Uninstall workflows + delete from enabled_repos"""
```

### Definition of Done
- Template files exist in `backend/workflow_templates/`
- `install_workflows("aman75verma/taskapi-demo", token, url)` creates 3 files on GitHub
- `uninstall_workflows(...)` removes them
- Verify files appear/disappear on GitHub

---

## CHUNK S7 — API Endpoints (main.py rewrite)

**Goal:** Wire everything together into the final API.

### Modify

#### [MODIFY] `backend/main.py`

Full endpoint list:

**Public:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve dashboard HTML |
| `GET` | `/health` | Server health check |
| `GET` | `/auth/github/login` | Redirect to GitHub OAuth |
| `GET` | `/auth/github/callback` | Handle OAuth callback |
| `POST` | `/webhook/pr` | PR notification (from user's GH Actions) |
| `POST` | `/webhook/merge` | Merge notification (from user's GH Actions) |
| `POST` | `/webhook/deploy-result` | Deploy callback (from user's deploy workflow) |

**Authenticated:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/me` | Current user info |
| `POST` | `/auth/logout` | Clear session |
| `GET` | `/api/repos` | User's public GitHub repos |
| `GET` | `/api/repos/enabled` | User's enabled repos |
| `POST` | `/api/repos/enable` | Enable repo + install workflows |
| `POST` | `/api/repos/disable` | Disable repo + remove workflows |
| `GET` | `/api/repos/{owner}/{repo}/reviews` | PR reviews for repo |
| `GET` | `/api/repos/{owner}/{repo}/deployments` | Deployments for repo |
| `GET` | `/api/repos/{owner}/{repo}/rollbacks` | Rollbacks for repo |
| `GET` | `/api/repos/{owner}/{repo}/stats` | Summary stats |

**Webhook routing logic:**
```python
@app.post("/webhook/pr")
async def webhook_pr(request, background_tasks):
    body = await request.json()
    repo = body["repo"]
    token = lookup_token_for_repo(repo)  # query enabled_repos → users table
    background_tasks.add_task(review_agent.review_pr, body["pr_number"], repo, token)
```

### Definition of Done
- All endpoints respond correctly
- Auth routes work end-to-end
- Webhook routes look up correct user token by repo name
- Deploy-result callback resumes promotion pipeline

---

## CHUNK S8 — Frontend: Landing Page + Auth

**Goal:** Beautiful landing page with GitHub sign-in.

### Modify

#### [MODIFY] `dashboard/index.html`

**Full rewrite** as an SPA with hash routing (`#/`, `#/repos`, `#/setup/...`, `#/dashboard/...`).

**Landing page (`#/`):**
- Dark premium design (current color palette)
- Hero: "AI-Powered PR Reviews & Zero-Touch Deployments"
- Subtle animated gradient background
- 3 feature cards:
  - 🔍 **Smart PR Review** — AI reviews every PR for security, tests, code quality
  - 🚀 **Auto-Deploy Pipeline** — Automated dev → staging → prod with smoke tests
  - ⏪ **Self-Healing Rollback** — Instant rollback when smoke tests fail + Slack alerts
- Big "Sign in with GitHub" button
- "How it works" section: 3-step flow (Connect → Enable → Monitor)

**Post-login header:**
- Logo + nav (Repos, Docs)
- User avatar + username + dropdown (Settings, Logout)

### Definition of Done
- Landing page is visually stunning at `http://localhost:8000`
- "Sign in" → OAuth flow → redirects to `/#/repos`
- Header shows user info after login
- Logout works

---

## CHUNK S9 — Frontend: Repo Selector + Setup

**Goal:** User sees their repos, can enable/disable them.

### Modify (same file)

**Repos page (`#/repos`):**
- Grid of repo cards from `GET /api/repos`
- Each card: repo name, description, language badge, stars, last updated
- **Enable** button → calls `POST /api/repos/enable`
- Enabled repos: green ✅ badge + "Dashboard →" link + "Disconnect" button
- Search/filter bar at top
- Empty state for no repos

**Setup page (`#/setup/{owner}/{repo}`):**
- Auto-navigated after clicking Enable
- Live progress checklist:
  - ☐ → ✅ Installing `agentic_pr_review.yml`
  - ☐ → ✅ Installing `agentic_merge_notify.yml`
  - ☐ → ✅ Installing `agentic_deploy.yml`
- Success state: "All workflows installed! Open Dashboard →"
- Failure state: error message + manual copy-paste instructions
- Link to view installed files on GitHub

**Disconnect flow:**
- Confirmation modal: "This will remove all Agentic PR Release workflows from `owner/repo`. Continue?"
- Calls `POST /api/repos/disable`
- Removes workflows from GitHub
- Repo returns to "not enabled" state

### Definition of Done
- Repos load and display nicely
- Enable creates 3 workflow files in repo
- Setup page shows live progress
- Disconnect removes workflows + updates UI
- Search/filter works

---

## CHUNK S10 — Frontend: Dashboard (per repo)

**Goal:** Full audit dashboard for a selected enabled repo.

### Modify (same file)

**Dashboard page (`#/dashboard/{owner}/{repo}`):**

**Header:**
- Breadcrumb: Repos > `owner/repo`
- Repo name with GitHub link icon
- Status badge (Active)
- "Disconnect" button
- Auto-refresh toggle (every 15s)

**Stats bar:**
- Total Reviews | Deployments | Rollbacks | Success Rate

**Pipeline visualization:**
```
┌─────┐  ──→  ┌─────────┐  ──→  ┌──────┐
│ DEV │       │ STAGING │       │ PROD │
└─────┘       └─────────┘       └──────┘
 ✅ v3         🔄 v3             ✅ v2
```
- Color-coded stages: green (passed), yellow (in-progress), red (failed), gray (pending)
- Current image tag per environment

**Tabs:**
1. **Agent Reviews** — verdict badge, PR number (clickable to GitHub), PR title, reasoning (expandable), timestamp
2. **Deployments** — environment badge, image tag, status badge, triggered by, timestamp
3. **Rollbacks** — linked deployment ID, reverted-to tag, reasoning (expandable), timestamp

**Standard features:**
- Auto-refresh with visual indicator
- Loading skeletons during fetch
- Empty states per tab
- Responsive layout
- Click-to-expand reasoning
- Time-ago formatting with full timestamp on hover

### Definition of Done
- Dashboard loads data filtered by selected repo
- All 3 tabs render with correct badges and formatting
- Pipeline visualization shows current state
- Auto-refresh works with toggle
- Disconnect button works from dashboard
- Responsive on mobile

---

## CHUNK S11 — End-to-End Testing & Polish

**Goal:** Verify all flows work. Update docs.

### Test Scenarios

| # | Scenario | Expected Result |
|---|---|---|
| 1 | **Onboarding** | Landing → login → repos → enable → workflows installed → dashboard |
| 2 | **PR Review** | Open PR on enabled repo → workflow fires → agent reviews → comment on PR → shows on dashboard |
| 3 | **Merge + Deploy** | Merge PR → workflow fires → server starts pipeline → triggers deploy workflow → callback → next stage |
| 4 | **Disconnect** | Click disconnect → workflows removed from GitHub → repo gone from dashboard |
| 5 | **Re-enable** | Enable a previously disconnected repo → workflows re-installed → works again |

### Docs

#### [MODIFY] `docs/Logs.md` — Add all session entries

#### [MODIFY] `docs/ProjectChunks.md` — Add note that SmartChunks supersedes for the multi-tenant pivot

### Definition of Done
- All 5 scenarios pass
- No hardcoded tokens or repo names in codebase
- `.env.example` is clean
- Docs updated

---

## Build Order Summary

```
S1 (Cleanup) → S2 (DB + Config) → S3 (OAuth) ─────────────────┐
                    │                                            │
                    └→ S4 (Multi-tenant Tools) → S5 (Agents) → S6 (Workflows) → S7 (API) → S8 (Landing) → S9 (Repos) → S10 (Dashboard) → S11 (Testing)
```

| Chunk | Effort | Focus |
|---|---|---|
| S1 | Small | Delete files, trim compose |
| S2 | Small | SQL + config |
| S3 | Medium | New auth module |
| S4 | Medium | Refactor tools |
| S5 | Medium | Refactor agents + event-driven |
| S6 | Medium | New templates + installer |
| S7 | Large | Full API rewrite |
| S8 | Large | Landing page + auth UI |
| S9 | Medium | Repo selector + setup |
| S10 | Large | Dashboard redesign |
| S11 | Medium | E2E testing |
