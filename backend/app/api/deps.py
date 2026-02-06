from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.crud.user import get_user_by_email
from app.db.session import get_db
from app.schemas.user import TokenPayload


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        token_data = TokenPayload(**payload)
    except (JWTError, ValueError):
        raise credentials_exception

    if token_data.sub is None:
        raise credentials_exception

    user = get_user_by_email(db, email=token_data.sub)
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def get_current_user_optional(
    token: Annotated[Optional[str], Depends(oauth2_scheme_optional)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Like get_current_user, but returns None when the Authorization header is missing.

    If a token is provided but invalid, raises 401.
    """
    if not token:
        return None

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        token_data = TokenPayload(**payload)
    except (JWTError, ValueError):
        raise credentials_exception

    if token_data.sub is None:
        raise credentials_exception

    user = get_user_by_email(db, email=token_data.sub)
    if user is None or not user.is_active:
        raise credentials_exception

    return user

