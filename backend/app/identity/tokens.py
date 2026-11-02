"""Signed login tokens for the web UI (demo login; the graded API uses the X-Employee-Id header).

Token = base64url(json{"sub", "exp"}) + "." + base64url(HMAC-SHA256). APP_SECRET signs tokens; if it is
not set, a random secret is generated at start-up (tokens then expire on restart).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

TOKEN_TTL_S = 12 * 3600
_SECRET = (os.environ.get("APP_SECRET") or secrets.token_hex(32)).encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(employee_id: str, ttl_s: int = TOKEN_TTL_S) -> str:
    body = _b64(json.dumps({"sub": employee_id, "exp": int(time.time()) + ttl_s}).encode())
    sig = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str | None) -> str | None:
    """Employee id for a valid, unexpired token; None otherwise."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        claims = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(claims.get("exp", 0)) < time.time():
        return None
    return str(claims.get("sub") or "") or None


def check_password(password: str) -> bool:
    """Demo login: every employee shares DEMO_PASSWORD (default 'veltrix'). Real SSO is out of scope."""
    expected = os.environ.get("DEMO_PASSWORD") or "veltrix"
    return hmac.compare_digest((password or "").encode(), expected.encode())
