# Project 2 (Final): Agentic Release Pipeline
### PR Review Agent + Auto-Promote (Dev → Staging → Prod) + Self-Healing Rollback

> This replaces the earlier "Incident Automation Agent" concept — it absorbs all of that project's features (GitHub API, Slack alerts, failure investigation) and adds full dev→staging→prod pipeline coverage on top. One project, not two.

---

## 1. What This Project Is

An agent embedded in a CI/CD pipeline that owns the full path from code change to production:
1. **Reviews** a pull request's diff and decides approve / request-changes
2. **Promotes** the change automatically through dev → staging → prod, running smoke tests at each gate
3. **Rolls back** automatically if a stage fails, investigates why, and alerts Slack with its reasoning

**Design principle for this build: low lift, high signal.** You are not standing up real infrastructure. The demo app is a deliberately trivial API with a controllable "bug switch." The three environments are three lightweight deployments of the *same* Docker image, not three different systems. What's real and non-trivial is the **pipeline logic and the agent's decision-making** — that's the part recruiters and interviewers actually probe, and it's the part worth spending your limited time on.

---

## 2. Business Value & Features (for your README/resume framing)

**The pitch:** manual release processes are slow and error-prone — someone has to review code, watch a deploy, check it didn't break anything, and manually roll back if it did. This automates that judgment loop, the same category of work as GitHub Copilot's PR review features, Vercel's preview-deploy-and-promote flow, and internal platform engineering tools at larger companies.

**Core features:**
- Automated PR review against a concrete rubric (tests present? no hardcoded secrets? diff size reasonable?) with a posted comment and approve/request-changes decision
- Automatic staged promotion (dev → staging → prod) gated by smoke tests, not a single "deploy and hope" step
- Self-healing rollback: on failure, the agent doesn't just alert — it investigates (diff + logs) and reverts to the last known-good version
- Full audit trail: every decision (review, promote, rollback) logged with the agent's reasoning, queryable later
- Slack notifications at each meaningful event (PR reviewed, promoted, rolled back)

**Honest scope note (say this upfront, don't hide it):** the three environments are simulated on lightweight free-tier hosting rather than separate production-grade infrastructure. The pipeline gates, agent decisions, and rollback logic are fully real — this is a deliberate scope choice to keep the project buildable in a short timeframe while preserving the parts that actually demonstrate skill.

---

## 3. Architecture

```
      PR opened/updated on demo repo
                 │
                 ▼
        GitHub Actions trigger
                 │
                 ▼
        ┌─────────────────┐
        │  Agent Backend    │◀──── MCP Tools ────┐
        │  (FastAPI)         │                     │
        └────────┬─────────┘                     │
                 │                        ┌────────┴────────┐
       Decision 1: Review PR       │  github_tool     │ (diff, comments, labels)
                 │                        │  slack_tool      │ (post messages)
                 ▼                        │  deploy_tool     │ (trigger/rollback deploy)
         merge → deploy to DEV            │  db_tool         │ (audit log read/write)
                 │                        └─────────────────┘
       Decision 2: smoke test DEV
          pass → promote to STAGING
          fail → rollback + Slack alert
                 │
       Decision 3: smoke test STAGING
          pass → promote to PROD
          fail → rollback + Slack alert
                 │
       Decision 4: smoke test PROD
          pass → done, Slack summary
          fail → rollback PROD + Slack alert
                 │
                 ▼
        Postgres: full audit log of
        every decision + reasoning
```

**Environments (simulated, cheaply):** three small deployments of the same Docker image — e.g. three free Fly.io apps (`taskapi-dev`, `taskapi-staging`, `taskapi-prod`) or three docker-compose services on different ports if you want to avoid cloud accounts entirely. "Promotion" = redeploying the same image tag to the next environment and updating the audit table. No separate infra to design.

---

## 4. Detailed Flow

1. A PR is opened against the demo repo → GitHub Actions webhook (or poll) notifies the agent backend.
2. **Agent decision 1 — Review:** LLM fetches the diff via `github_tool`, checks it against a fixed rubric, posts a PR comment and either approves or requests changes.
3. On merge → GitHub Actions builds the image, tags it, deploys to **dev** via `deploy_tool`.
4. Smoke test script runs against dev (a few curl/HTTP checks against the demo app's endpoints, including hitting the bug-switch state).
5. **Agent decision 2:** if smoke tests pass → promote same image to **staging**. If they fail → agent calls `deploy_tool` to roll back dev, investigates via logs, posts a Slack alert via `slack_tool` with its diagnosis.
6. Repeat smoke test + agent decision for staging → prod.
7. Every decision (review verdict, promotion, rollback + reasoning) is written to Postgres via `db_tool` — this becomes your audit trail / dashboard data.
8. Final Slack message on success: "PR #X promoted dev → staging → prod, all smoke tests passed."

---

## 5. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| CI trigger | GitHub Actions | Real pipeline, industry-standard |
| Agent backend | FastAPI (Python) | Consistent with demo app |
| LLM | Groq API (Llama 3.3) | Free tier, fast, tool-calling capable |
| Tool protocol | MCP | Same protocol as Project 1 — consistent story across both projects |
| Demo app | FastAPI with `INJECT_BUG` + `/version` env var toggles | Lets you trigger real failures on demand + verify promotions visually |
| Deploy target | docker-compose (3 local services) → DockerHub + Render | Local dev first, cloud deploy for demo URLs |
| Database | PostgreSQL (via Docker) | Production-grade, easy to deploy to Render |
| Messaging | Slack Incoming Webhook | Real integration, simple to set up |
| Containerization | Docker | Same image promoted across environments |
| Dashboard | Minimal React page or simple `/admin` HTML view | Shows audit trail — don't over-invest here |
| Target repo | Separate repo (e.g., `taskapi-demo`) | Keeps pipeline code separate from test PRs |

---

## 6. Prerequisites

**Must know before starting:**
- Git/GitHub PR workflow (branches, merges, PR API basics)
- What CI/CD staged pipelines are and why gates exist
- Basic Docker (image, tag, container, docker-compose)

**Learn while building:**
- GitHub Actions YAML (triggers, jobs)
- GitHub REST API (PRs, comments, labels)
- Slack Incoming Webhooks (simplest possible integration — a POST request with JSON, no need for a full Slack App)
- Multi-step agent tool-calling loops (same concept as Project 1, applied to a different domain)

You already know most of this if you built Project 1 — that's the point of this design.

---

## 7. Your Assignments (kept deliberately light — this project is meant to move fast)

Given the time constraint, don't hand-build everything like a from-scratch learning exercise. Instead:

- [ ] **You decide and lock the rubric** the PR review agent uses (what counts as "risky"?) — this is a real design decision, own it, don't let AI silently pick it.
- [ ] **You build the bug-toggle demo app yourself** (it's ~20 lines) — you need to fully trust what "broken" means to judge the agent's rollback correctly.
- [ ] **You trace one full promotion cycle manually** (dev→staging→prod, success case) before layering in failure/rollback handling — confirm you understand each step before automating around it.
- [ ] **You manually trigger 2-3 rollback scenarios** and confirm the agent's stated reasoning is actually correct — this is your eval set and your demo script.
- [ ] Let AI generate the MCP tool boilerplate, GitHub/Slack API wiring, and CI YAML — this is repetitive integration code, low learning value to hand-write given your timeline.

---

## 8. Compressed Build Timeline (aim: ~1 week)

| Day | Milestone |
|---|---|
| 1 | Demo app with bug toggle + GitHub Actions pipeline building/deploying it to dev |
| 2 | Three environments live (dev/staging/prod) + manual promotion working (no agent yet) |
| 3 | PR review agent (Decision 1) working end-to-end |
| 4 | Promotion agent (Decisions 2-3) + smoke tests wired in |
| 5 | Rollback logic + Slack alerts |
| 6 | Audit log + minimal dashboard |
| 7 | README, demo recording, polish |
