from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Membership, User
from .settings import saas_settings


_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = os.urandom(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        n,
        r,
        p,
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(digest).decode().rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64 + "=" * (-len(salt_b64) % 4))
        expected = base64.urlsafe_b64decode(digest_b64 + "=" * (-len(digest_b64) % 4))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(*, user: User, tenant_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "tenant_id": tenant_id,
        "role": role,
        "is_superuser": user.is_superuser,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=saas_settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, saas_settings.jwt_secret, algorithm=saas_settings.jwt_algorithm)


@dataclass(slots=True)
class Principal:
    user_id: str
    tenant_id: str
    email: str
    role: str
    is_superuser: bool = False


def decode_access_token(token: str) -> Principal:
    try:
        payload = jwt.decode(
            token,
            saas_settings.jwt_secret,
            algorithms=[saas_settings.jwt_algorithm],
            options={"require": ["sub", "tenant_id", "iat", "exp"]},
        )
        return Principal(
            user_id=str(payload["sub"]),
            tenant_id=str(payload["tenant_id"]),
            email=str(payload.get("email", "")),
            role=str(payload.get("role", "member")),
            is_superuser=bool(payload.get("is_superuser", False)),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    principal = decode_access_token(credentials.credentials)
    user = db.get(User, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account unavailable")
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == principal.user_id,
            Membership.tenant_id == principal.tenant_id,
        )
    )
    if membership is None and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Tenant membership required")
    if membership is not None:
        principal.role = membership.role
    principal.is_superuser = user.is_superuser
    principal.email = user.email
    return principal


def require_admin(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if principal.role not in {"owner", "admin"} and not principal.is_superuser:
        raise HTTPException(status_code=403, detail="Workspace admin role required")
    return principal


def require_owner(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if principal.role != "owner" and not principal.is_superuser:
        raise HTTPException(status_code=403, detail="Workspace owner role required")
    return principal


def require_superuser(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if not principal.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")
    return principal
