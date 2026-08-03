"""Authentication endpoints — login with employee ID + date of birth."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import create_access_token, get_current_user, normalize_dob
from ..deps import user_store
from ..schemas import LoginRequest, LoginResponse, MeResponse
from ..storage.users import UserRecord

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    dob = normalize_dob(body.dob)
    user = user_store.get_by_employee_id(body.employee_id)
    if not user or user.dob != dob:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID or date of birth",
        )
    token = create_access_token(employee_id=user.employee_id, role=user.role)
    return LoginResponse(
        access_token=token,
        employee_id=user.employee_id,
        name=user.name,
        role=user.role,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: Annotated[UserRecord, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(employee_id=user.employee_id, name=user.name, role=user.role)
