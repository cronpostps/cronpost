# /backend/app/dependencies.py
# Version 1.6 (Fixed circular import by moving oauth2_scheme here)

import os
import logging
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer # Thêm import này
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError, jwt

from .db.database import get_db_session
from .db import models
from .db.models import SystemSetting
from typing import Dict

logger = logging.getLogger(__name__)

# --- Di chuyển định nghĩa oauth2_scheme từ security.py sang đây ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/signin")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db_session)):
    """
    Decodes JWT token to get user, using async database session.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256") 

    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Internal server error: SECRET_KEY not set")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        email: str = payload.get("email") 
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    stmt = select(models.User).where(models.User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    """
    Checks if the user is active and verified.
    """
    if not current_user.is_confirmed_by_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Email not confirmed"
        )
    return current_user

async def get_current_admin_user(current_user: models.User = Depends(get_current_active_user)):
    """
    Checks if the user has admin privileges.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have administrative privileges."
        )
    return current_user

async def get_system_settings_dep(db: AsyncSession = Depends(get_db_session)) -> Dict[str, str]:
    """
    Dependency to fetch all system settings and provide them as a dictionary.
    """
    stmt = select(SystemSetting)
    result = await db.execute(stmt)
    settings = result.scalars().all()
    return {setting.setting_key: setting.setting_value for setting in settings}