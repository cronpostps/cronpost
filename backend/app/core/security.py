# backend/app/core/security.py
# Version: 1.3 (Added admin user dependency)

import os
import logging
from typing import Optional, Annotated
import uuid
from pydantic import BaseModel, EmailStr

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt as python_jose_jwt, JWTError as JoseJWTError

from ..db.database import get_db_session
from ..db.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

APP_JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
APP_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/signin")

class TokenData(BaseModel):
    sub: Optional[str] = None
    email: Optional[EmailStr] = None
    provider: Optional[str] = None

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = python_jose_jwt.decode(token, APP_JWT_SECRET_KEY, algorithms=[APP_JWT_ALGORITHM])
        user_id_str: Optional[str] = payload.get("sub")
        if user_id_str is None: raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (JoseJWTError, ValueError):
        raise credentials_exception
    
    stmt = select(User).where(User.id == user_id).options(selectinload(User.configuration), selectinload(User.review))
    user = (await db.execute(stmt)).scalars().first()
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    # ... (logic get_current_active_user giữ nguyên)
    return current_user

# --- HÀM MỚI ĐỂ XÁC THỰC ADMIN ---
async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    """
    Dependency to get the current active user and check if they are an admin.
    """
    if not current_user.is_admin:
        logger.warning(f"Non-admin user {current_user.email} attempted to access an admin route.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource."
        )
    logger.info(f"Admin access granted for user: {current_user.email}")
    return current_user