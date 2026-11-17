"""Validação de tokens Supabase Auth sem expor service_role."""

from __future__ import annotations

import os
from typing import Any

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


def current_user(credentials: HTTPAuthorizationCredentials | None) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated"),
            issuer=os.getenv("SUPABASE_JWT_ISSUER", f"{supabase_url}/auth/v1"),
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid_bearer_token") from exc
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=401, detail="token_without_subject")
    metadata = claims.get("app_metadata") or {}
    role = metadata.get("role", "usuario") if isinstance(metadata, dict) else "usuario"
    if role not in {"admin", "analista", "usuario"}:
        role = "usuario"
    return {"id": subject, "email": claims.get("email"), "role": role}
