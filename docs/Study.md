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

**Total prep: ~1-2 hours if you know Python.**

---

## Chunk 2 — Environments (docker-compose)

| Topic | Depth | What to Know |
|---|---|---|
| docker-compose basics | **Medium** | `docker-compose.yml` syntax: services, ports, environment variables, `docker-compose up/down`. |
| Multi-service Docker apps | **Basic** | How multiple services share a network, differ by env vars. |
| Staged deployments (dev/staging/prod) | **Conceptual** | Why companies have multiple environments and gates between them. |

**Total prep: ~1 hour.**

---

## Chunk 3 — Database (SQLite)

| Topic | Depth | What to Know |
|---|---|---|
| SQL basics | **Basic** | `CREATE TABLE`, `INSERT`, `SELECT`, `CHECK` constraints. |
| SQLite | **Basic** | File-based database, no server needed. Python has built-in `sqlite3` module. |
| Python `sqlite3` module | **Basic** | `connect()`, `cursor()`, `execute()`, `commit()`. ~20 min tutorial. |

**Total prep: ~30 min if you know SQL.**

---

## Chunk 4 — MCP Tools

| Topic | Depth | What to Know |
|---|---|---|
| MCP (Model Context Protocol) | **Medium** | What it is (a protocol for LLMs to call external tools), how tool schemas work (JSON), how a tool server exposes functions. |
| GitHub REST API | **Medium** | PR endpoints: get diff, post comment, add label, create review, merge. Use PyGithub or raw `requests`. |
| Slack Incoming Webhooks | **Basic** | One POST request with `{"text": "message"}` to a webhook URL. 5 min setup. |
| HTTP requests in Python | **Basic** | `requests.get()`, `requests.post()`, response status codes. |

**Total prep: ~2-3 hours.**

---

## Chunk 5 & 6 — Agent Logic + Backend

| Topic | Depth | What to Know |
|---|---|---|
| LLM tool-calling / function-calling | **Medium-Deep** | How an LLM receives tool schemas, decides to call tools, and how you execute the tool and return results. This is the core "agentic" concept. |
| Groq API | **Basic** | API key, chat completions endpoint, tool_choice parameter. Very similar to OpenAI's API. |
| FastAPI (webhooks, POST endpoints) | **Medium** | Receiving JSON payloads, async handlers, background tasks. |
| Agent loop pattern | **Medium** | The "prompt → LLM → tool call → execute → feed result back → repeat" loop. Understand this conceptually before coding. |

**Total prep: ~3-4 hours. This is the hardest chunk.**

---

## Chunk 7 — GitHub Actions

| Topic | Depth | What to Know |
|---|---|---|
| GitHub Actions YAML | **Medium** | Triggers (`on: pull_request`, `on: push`), jobs, steps, secrets, `${{ github.event }}` expressions. |
| Webhooks concept | **Basic** | Server A calls Server B's URL when something happens. GitHub Actions → your backend. |
| Docker image registries | **Basic** | What DockerHub/GHCR is, `docker push`, `docker pull`. |

**Total prep: ~1-2 hours.**

---

## Chunk 8 — Dashboard

| Topic | Depth | What to Know |
|---|---|---|
| React basics (if using React) | **Basic** | Components, `useState`, `useEffect`, `fetch()`. OR just use plain HTML + JS. |
| Fetching API data | **Basic** | `fetch('/admin/audit-log')` → render as table. |

**Total prep: ~1 hour. Keep this minimal.**

---

## Chunk 9 — Eval / Demo

No new concepts. This is just running your 4 test scenarios and recording results.

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
