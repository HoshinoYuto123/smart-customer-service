"""Small signed-cookie identity layer for anonymous web sessions.

This is intentionally an identity boundary rather than a full account system.
Production deployments must provide a strong, shared ``AUTH_SECRET`` and can
later replace this module with their SSO/JWT verifier without changing routes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, WebSocket

from app.core.config import get_app_config

COOKIE_NAME = "scs_auth"


@dataclass(frozen=True)
class Principal:
    user_id: str


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(user_id: str | None = None) -> tuple[str, Principal]:
    config = get_app_config().auth
    principal = Principal(user_id=user_id or f"anon_{uuid.uuid4().hex}")
    payload = {
        "sub": principal.user_id,
        "exp": int(time.time()) + config.token_ttl_seconds,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(config.secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}", principal


def verify_token(token: str) -> Principal:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            get_app_config().auth.secret.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64decode(supplied_signature)):
            raise ValueError("invalid signature")
        payload = json.loads(_b64decode(encoded))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired token")
        user_id = str(payload["sub"])
        if not user_id:
            raise ValueError("missing subject")
        return Principal(user_id=user_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="身份凭证无效或已过期") from exc


def set_auth_cookie(response: Response, token: str) -> None:
    config = get_app_config().auth
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=config.token_ttl_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


def get_request_principal(request: Request) -> Principal:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="缺少身份凭证")
    return verify_token(token)


def get_websocket_principal(websocket: WebSocket) -> Principal:
    token = websocket.cookies.get(COOKIE_NAME, "")
    if not token:
        token = websocket.query_params.get("token", "")
    return verify_token(token)
