"""
auth.py — GitHub OAuth authentication for Agentic PR Release.

Flow:
  1. User clicks "Sign in with GitHub" → GET /auth/github/login
  2. Redirect to github.com/login/oauth/authorize
  3. GitHub redirects back → GET /auth/github/callback?code=xxx
  4. Exchange code for access_token, fetch user profile, upsert in DB
  5. Set signed session cookie, redirect to /#/repos

Session: Uses itsdangerous URLSafeTimedSerializer to sign a cookie
containing the user_id. Cookie expires in 7 days.
"""

import requests as http_requests
import psycopg2
from urllib.parse import urlencode

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from backend.config import (
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    SESSION_SECRET,
    AGENT_PUBLIC_URL,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
)

# ── Session helpers ──────────────────────────────────────────────────

COOKIE_NAME = "agentic_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

_serializer = URLSafeTimedSerializer(SESSION_SECRET)


def _sign_user_id(user_id: int) -> str:
    """Create a signed cookie value from a user_id."""
    return _serializer.dumps(user_id)


def _unsign_user_id(cookie_value: str) -> int | None:
    """Extract user_id from a signed cookie, or None if invalid/expired."""
    try:
        return _serializer.loads(cookie_value, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


# ── Database helpers ─────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )


def _upsert_user(github_id: int, username: str, display_name: str,
                  avatar_url: str, access_token: str) -> int:
    """Insert or update a user, return the internal user id."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (github_id, username, display_name, avatar_url, access_token)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (github_id) DO UPDATE SET
                username     = EXCLUDED.username,
                display_name = EXCLUDED.display_name,
                avatar_url   = EXCLUDED.avatar_url,
                access_token = EXCLUDED.access_token,
                updated_at   = now()
            RETURNING id
            """,
            (github_id, username, display_name, avatar_url, access_token),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        return user_id
    finally:
        conn.close()


def _get_user_by_id(user_id: int) -> dict | None:
    """Fetch a user row by internal id."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, github_id, username, display_name, avatar_url FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "github_id": row[1],
            "username": row[2],
            "display_name": row[3],
            "avatar_url": row[4],
        }
    finally:
        conn.close()


# ── OAuth endpoints ──────────────────────────────────────────────────

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

# Scopes: repo (read/write PRs, contents), workflow (write .github/workflows), read:user (profile info)
OAUTH_SCOPES = "repo workflow read:user"


def github_login():
    """Redirect the user to GitHub's OAuth authorization page."""
    params = urlencode({
        "client_id": GITHUB_CLIENT_ID,
        "scope": OAUTH_SCOPES,
        "redirect_uri": f"{AGENT_PUBLIC_URL}/auth/github/callback",
    })
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{params}")


def github_callback(code: str):
    """
    Exchange the authorization code for an access token,
    fetch the user profile, upsert into DB, set session cookie.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing code parameter")

    # Step 1: Exchange code for access_token
    token_resp = http_requests.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": f"{AGENT_PUBLIC_URL}/auth/github/callback",
        },
        timeout=15,
    )

    if not token_resp.ok:
        raise HTTPException(status_code=502, detail="Failed to exchange code with GitHub")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")

    if not access_token:
        error = token_data.get("error_description", token_data.get("error", "Unknown error"))
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {error}")

    # Step 2: Fetch the user's GitHub profile
    user_resp = http_requests.get(
        GITHUB_USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )

    if not user_resp.ok:
        raise HTTPException(status_code=502, detail="Failed to fetch GitHub user profile")

    profile = user_resp.json()
    github_id = profile["id"]
    username = profile["login"]
    display_name = profile.get("name") or username
    avatar_url = profile.get("avatar_url", "")

    # Step 3: Upsert user in our DB
    user_id = _upsert_user(github_id, username, display_name, avatar_url, access_token)

    # Step 4: Set signed session cookie and redirect to dashboard
    response = RedirectResponse("/#/repos", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=_sign_user_id(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production with HTTPS
    )
    return response


# ── Session helpers (used by other endpoints) ────────────────────────

def get_current_user(request: Request) -> dict | None:
    """
    Read the session cookie and return the user dict, or None.
    Does NOT raise — use require_auth() for protected endpoints.
    """
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    user_id = _unsign_user_id(cookie)
    if user_id is None:
        return None
    return _get_user_by_id(user_id)


def require_auth(request: Request) -> dict:
    """
    FastAPI dependency: returns the current user or raises 401.
    Usage:
        @app.get("/api/something")
        def something(user: dict = Depends(require_auth)):
            ...
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_user_token(user_id: int) -> str | None:
    """Fetch the stored GitHub access_token for a user."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT access_token FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_token_for_repo(repo_full_name: str) -> str | None:
    """
    Look up the GitHub token for the user who enabled this repo.
    Used by webhook handlers to find the right credentials.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.access_token
            FROM enabled_repos er
            JOIN users u ON u.id = er.user_id
            WHERE er.repo_full_name = %s
            LIMIT 1
            """,
            (repo_full_name,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def logout():
    """Clear the session cookie."""
    response = JSONResponse({"status": "ok", "message": "Logged out"})
    response.delete_cookie(COOKIE_NAME)
    return response
