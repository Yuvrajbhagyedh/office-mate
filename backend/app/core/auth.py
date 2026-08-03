"""Auth helpers: JWT + FastAPI dependencies. Login = employee_id + DOB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import settings
from ..deps import user_store
from ..storage.users import UserRecord

_bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def parse_dob(value: str) -> str:
    """Accept YYYY-MM-DD or DD/MM/YYYY / DD-MM-YYYY and return YYYY-MM-DD."""
    raw = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Invalid date of birth. Use YYYY-MM-DD or DD/MM/YYYY.")


def normalize_dob(value: str) -> str:
    try:
        return parse_dob(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def create_access_token(*, employee_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.auth_token_hours)
    payload = {"sub": employee_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.auth_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.auth_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
) -> UserRecord:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    employee_id = payload.get("sub")
    if not employee_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = user_store.get_by_employee_id(employee_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(user: Annotated[UserRecord, Depends(get_current_user)]) -> UserRecord:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def seed_users() -> None:
    """Ensure demo admin + employee accounts exist (employee_id + DOB)."""
    seeds = [
        (
            settings.seed_admin_employee_id,
            settings.seed_admin_dob,
            settings.seed_admin_name,
            "admin",
        ),
        (
            settings.seed_employee_id,
            settings.seed_employee_dob,
            settings.seed_employee_name,
            "employee",
        ),
    ]
    for employee_id, dob, name, role in seeds:
        if not employee_id or not dob:
            continue
        if user_store.get_by_employee_id(employee_id):
            continue
        user_store.create(
            employee_id=employee_id,
            dob=parse_dob(dob),
            name=name or employee_id,
            role=role,
        )
