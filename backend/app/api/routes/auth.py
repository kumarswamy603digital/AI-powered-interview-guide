from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.crud.user import authenticate_user, create_user, get_user_by_email
from app.db.session import get_db
from app.schemas.user import Token, UserCreate, UserLogin, UserRead


router = APIRouter(prefix="/api/auth", tags=["auth"])


DbSessionDep = Annotated[Session, Depends(get_db)]


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: DbSessionDep):
    existing = get_user_by_email(db, email=user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    user = create_user(db, user_in=user_in)
    return user


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: DbSessionDep):
    user = authenticate_user(db, email=user_in.email, password=user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.email)
    return Token(access_token=access_token)


@router.get("/me", response_model=UserRead)
def read_me(current_user: Annotated[UserRead, Depends(get_current_user)]):
    return current_user

