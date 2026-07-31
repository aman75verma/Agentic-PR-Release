CREATE TABLE IF NOT EXISTS pr_reviews (
    id SERIAL PRIMARY KEY,
    pr_number INTEGER NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('approved', 'changes_requested')),
    reasoning TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deployments (
    id SERIAL PRIMARY KEY,
    environment TEXT NOT NULL CHECK (environment IN ('dev', 'staging', 'prod')),
    image_tag TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('deployed', 'smoke_test_passed', 'smoke_test_failed', 'rolled_back')),
    triggered_by TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rollbacks (
    id SERIAL PRIMARY KEY,
    deployment_id INTEGER REFERENCES deployments(id),
    reasoning TEXT NOT NULL,
    reverted_to_tag TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
