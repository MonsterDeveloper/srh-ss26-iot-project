from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    actor: str
    request_id: str | None
    dashboard: bool


def require_bearer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    dashboard_actor: str | None = Header(default=None, alias="X-Dashboard-Actor"),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> AuthContext:
    settings = get_settings()
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing bearer token")
    token = credentials.credentials
    is_dashboard = secrets.compare_digest(token, settings.dashboard_api_bearer_token)
    is_legacy = secrets.compare_digest(token, settings.api_bearer_token)
    if not is_dashboard and not is_legacy:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing bearer token")
    actor = dashboard_actor.strip()[:255] if is_dashboard and dashboard_actor and dashboard_actor.strip() else "api-client"
    return AuthContext(actor=actor, request_id=request_id[:255] if request_id else None, dashboard=is_dashboard)


def require_dashboard(context: AuthContext = Depends(require_bearer)) -> AuthContext:
    if not context.dashboard:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dashboard service token required")
    return context
