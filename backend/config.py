import os
from dotenv import load_dotenv

load_dotenv()

# Groq LLM (Chunk 5)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
TARGET_REPO = os.environ.get("TARGET_REPO", "aman75verma/taskapi-demo")

# Slack
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# Database (Postgres via Docker)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5433")
DB_NAME = os.environ.get("DB_NAME", "auditlog")
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")

# Environment URLs (docker-compose ports)
ENV_URLS = {
    "dev": os.environ.get("DEV_URL", "http://localhost:8081"),
    "staging": os.environ.get("STAGING_URL", "http://localhost:8082"),
    "prod": os.environ.get("PROD_URL", "http://localhost:8083"),
}
