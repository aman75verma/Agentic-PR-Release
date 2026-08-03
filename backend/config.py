import os
from pathlib import Path
from dotenv import load_dotenv

# Always find .env relative to this file's directory (backend/)
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

# Groq LLM (Chunk 5)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Slack
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# Database (Postgres via Docker)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5433")
DB_NAME = os.environ.get("DB_NAME", "auditlog")
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")

# GitHub OAuth App
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

# Session
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me-in-prod")

# Public URL of this server (for workflow templates)
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8000")

# Environment URLs (docker-compose ports, default values)
ENV_URLS = {
    "dev": os.environ.get("DEV_URL", "http://localhost:8081"),
    "staging": os.environ.get("STAGING_URL", "http://localhost:8082"),
    "prod": os.environ.get("PROD_URL", "http://localhost:8083"),
}
