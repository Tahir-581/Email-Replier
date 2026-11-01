"""Auth routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from src.api.deps import CurrentUser, DbDep
from src.api.schemas import LoginRequest, TokenResponse
from src.api.security import create_access_token, hash_password, verify_password
from src.db.models import User
from src.utils.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


async def ensure_admin_user(db) -> None:
    """Create default dashboard admin if no users exist."""
    result = await db.execute(select(User).limit(1))
    if result.scalar_one_or_none():
        return
    email = (settings.DASHBOARD_ADMIN_EMAIL or "admin@example.com").lower()
    password = settings.DASHBOARD_ADMIN_PASSWORD or "admin123"
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name="Dashboard Admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbDep):
    await ensure_admin_user(db)
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    token = create_access_token(str(user.id), {"email": user.email})
    return TokenResponse(access_token=token, user=user.to_dict())


@router.get("/me")
async def me(user: CurrentUser):
    return user.to_dict()
