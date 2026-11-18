"""Authentication: Firebase ID tokens (Google sign-in), optionally restricted to an e-mail allow-list.
The verified e-mail identifies the user: every row is owned by it (see app.database).

The check needs no service account: Google's public certificates verify the token signature and
the project id is the expected audience. Disabled by default so local use needs no sign-in."""

import cachecontrol
import requests
from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings

# Certificates are cached between requests by the HTTP cache headers Google sends.
_transport = google_requests.Request(session=cachecontrol.CacheControl(requests.Session()))


def verify_token(token: str) -> dict:
    return id_token.verify_firebase_token(token, _transport, audience=settings.firebase_project_id)


def require_user(authorization: str | None = Header(default=None)) -> str | None:
    """FastAPI dependency: returns the signed-in e-mail, or None when authentication is disabled."""
    if not settings.auth_enabled:
        return None
    if not settings.firebase_project_id or not (settings.allowed_emails or settings.open_signup):
        # Fail closed: a half-configured deployment must not be open.
        raise HTTPException(503, "Authentication is enabled but FIREBASE_PROJECT_ID is missing, or neither ALLOWED_EMAILS nor OPEN_SIGNUP is set")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required")
    try:
        claims = verify_token(authorization.split(" ", 1)[1].strip())
    except Exception as error:  # noqa: BLE001 - any verification failure is a 401
        raise HTTPException(401, "Invalid or expired sign-in") from error
    email = (claims.get("email") or "").lower()
    if not claims.get("email_verified") or not email or (settings.allowed_emails and email not in settings.allowed_emails):
        raise HTTPException(403, "This account is not allowed to use this app")
    return email
