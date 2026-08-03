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
    repo_full_name      TEXT NOT NULL,        -- "alice/her-cool-app"
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
