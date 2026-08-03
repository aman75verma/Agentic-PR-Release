# 📚 Study Guide — Agentic PR Release

> Learn what you need **per chunk**, at the right depth. Don't pre-study everything — read each chunk's section when you reach it.

---

## Chunk 1 — Demo App

| Topic | Depth | What to Know |
|---|---|---|
| Python (functions, decorators, env vars) | Should already know | Core of everything |
| FastAPI basics | **Basic** | Routes with `@app.get()`, returning dicts (auto-JSON), `HTTPException` for errors. That's it for this chunk. |
| `os.environ.get()` | **Basic** | Reads environment variables. One line concept. |
| Docker fundamentals | **Medium** | Understand: Dockerfile → `docker build` → image → `docker run` → container. Know the `-e` flag for env vars, `-p` for port mapping. |
| Health check endpoints | **Conceptual** | Why `/health` exists in production (load balancers, orchestrators check it). 5 min read. |

---

## Chunk 2 — Environments (docker-compose)

| Topic | Depth | What to Know |
|---|---|---|
| docker-compose basics | **Medium** | `docker-compose.yml` syntax: services, ports, environment variables, `docker-compose up/down`. |
| Multi-service Docker apps | **Basic** | How multiple services share a network, differ by env vars. |
| Staged deployments (dev/staging/prod) | **Conceptual** | Why companies have multiple environments and gates between them. |

---

## Chunk 3 — Database (PostgreSQL via Docker)

| Topic | Depth | What to Know |
|---|---|---|
| SQL basics | **Basic** | `CREATE TABLE`, `INSERT`, `SELECT`, `CHECK` constraints. |
| Postgres + Docker | **Basic** | Running the `postgres` image, mounting initialization scripts to `/docker-entrypoint-initdb.d/`. |
| Python `psycopg2` module | **Basic** | How to connect to Postgres from Python, execute queries, and commit. |

---

## Chunk 4 — MCP Tools

| Topic | Depth | What to Know |
|---|---|---|
| MCP (Model Context Protocol) | **Medium** | What it is (a protocol for LLMs to call external tools), how tool schemas work (JSON), how a tool server exposes functions. |
| GitHub REST API | **Medium** | PR endpoints: get diff, post comment, add label, create review, merge. Use PyGithub or raw `requests`. |
| Slack Incoming Webhooks | **Basic** | One POST request with `{"text": "message"}` to a webhook URL. 5 min setup. |
| HTTP requests in Python | **Basic** | `requests.get()`, `requests.post()`, response status codes. |

---

## Chunk 5 & 6 — Agent Logic + Backend

| Topic | Depth | What to Know |
|---|---|---|
| LLM tool-calling / function-calling | **Medium-Deep** | How an LLM receives tool schemas, decides to call tools, and how you execute the tool and return results. This is the core "agentic" concept. |
| Groq API | **Basic** | API key, chat completions endpoint, tool_choice parameter. Very similar to OpenAI's API. |
| FastAPI (webhooks, POST endpoints) | **Medium** | Receiving JSON payloads, async handlers, background tasks. |
| Agent loop pattern | **Medium** | The "prompt → LLM → tool call → execute → feed result back → repeat" loop. Understand this conceptually before coding. |

---

## Chunk 7 — GitHub Actions

| Topic | Depth | What to Know |
|---|---|---|
| GitHub Actions YAML | **Medium** | Triggers (`on: pull_request`, `on: push`), jobs, steps, secrets, `${{ github.event }}` expressions. |
| Webhooks concept | **Basic** | Server A calls Server B's URL when something happens. GitHub Actions → your backend. |
| Docker image registries | **Basic** | What DockerHub/GHCR is, `docker push`, `docker pull`. |

---

## Multi-Tenant SaaS Pivot (SmartChunks Phase)

As we transition from a single-tenant demo to a real product where any GitHub user can monitor their own repositories, we introduced Several new concepts:

| Topic | Depth | What to Know |
|---|---|---|
| GitHub OAuth Flow | **Medium** | How OAuth works: User clicks login → redirected to GitHub to authorize → GitHub redirects back with a `code` → our server exchanges `code` for an `access_token` and fetches user profile. |
| Session Management (Cookies) | **Basic** | How to set `Set-Cookie` headers via FastAPI responses. Difference between `httponly` (JS can't read it) and standard cookies. |
| Cryptography & `itsdangerous` | **Medium** | Instead of standard JWTs, we use `itsdangerous.URLSafeTimedSerializer` to cryptographically sign a simple `user_id` inside a cookie. This prevents tampering. |
| Multi-Tenant Database Design | **Basic** | Updating schemas (e.g., `pr_reviews`, `deployments`) to include a `repo` column and establishing foreign keys to a new `users` table. |
| Token Routing & Webhooks | **Advanced** | Webhooks don't have session cookies. When a webhook arrives from a repo, our server must extract the `repo` name from the payload, look up which `user_id` enabled it, and fetch *their* `access_token` to make GitHub API calls. |
| GitHub Contents API | **Medium** | Using the `PUT /repos/{owner}/{repo}/contents/{path}` API endpoint to programmatically commit workflow YAML files directly into users' repositories when they click "Enable" on the dashboard. |
| Event-Driven Deployment Architecture (Approach B) | **Advanced** | Shifting from running `docker-compose` locally to using `workflow_dispatch` API calls to trigger a deployment YAML in the user's repo. Our pipeline becomes stateful, waiting for the GitHub Action to call our `/webhook/deploy-result` endpoint before the LLM decides to promote to the next environment or rollback. |

---

## Key Concepts (Understand Before Starting)

These aren't deep-study topics — just make sure you can explain each in 1-2 sentences:

| Concept | One-liner |
|---|---|
| **CI/CD** | Automated pipeline that builds, tests, and deploys code on every change |
| **Staged deployment** | Code goes through dev → staging → prod with checks at each gate |
| **Smoke test** | Quick "is it alive?" check after deployment (hit /health, check 200) |
| **Rollback** | Revert to previous known-good version when something breaks |
| **MCP** | Protocol that lets LLMs call external tools in a standardized way |
| **Webhook** | "Don't call me, I'll call you" — a server notifies your URL when events happen |
| **Agent loop** | LLM decides → calls tool → gets result → decides again (repeat until done) |
| **Docker image tag** | Version label on a container image (often the git commit SHA) |

---

## Deep Dive Concepts

### 1. How Rollback & Version Tracking Works
- **Git Commit SHA to Docker Tag:** Every code commit generates a unique hash (e.g., `a1b2c3d`). The build pipeline tags the Docker image with this SHA (`taskapi:a1b2c3d`).
- **Postgres as Pipeline Memory:** When a deployment passes its smoke test, Postgres logs `(environment, image_tag, 'smoke_test_passed')`.
- **Rollback Mechanism:** If a future deployment fails, `deploy_tool.rollback()` queries Postgres via `get_last_good_tag` for the most recent passing tag and redeploys that exact image version.

### 2. Context Required for LLM PR Reviews
To decide whether to approve a PR or request changes, the LLM receives high-signal context:
- **PR Diff:** Line-by-line code additions/deletions fetched via `github_tool.get_diff()`.
- **Fixed Rubric:** System prompt constraints (checking for hardcoded secrets, presence of tests, and reasonable diff size).
- **PR Metadata:** PR title and description to understand intent.

### 3. Securing Multi-Tenant Workflows
- Our server acts on behalf of Alice for Alice's repos, and Bob for Bob's repos.
- We never hardcode `GITHUB_TOKEN` anymore. Each API call (like getting diffs or posting comments) dynamically injects the appropriate `access_token` by performing a database lookup on the `repo` field passed by the incoming webhook.
