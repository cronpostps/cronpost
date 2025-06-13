# /backend/app/dependencies.py
# Version 1.5 (Refactored to be fully asynchronous and consistent)

import os
import logging
import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError, jwt

from .db.database import get_db_session # Sử dụng dependency bất đồng bộ
from .db import models
from .core.security import oauth2_scheme # Bỏ import ALGORITHM

logger = logging.getLogger(__name__)

# --- Bỏ hàm get_db() đồng bộ cũ ---

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
    # Lấy thuật toán từ biến môi trường thay vì import
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256") 

    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Internal server error: SECRET_KEY not set")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        # Lấy email hoặc user_id từ payload, tùy thuộc vào cách bạn tạo token
        email: str = payload.get("email") 
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Sử dụng câu lệnh select bất đồng bộ
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
    # Trong model của bạn không có trường is_active, tôi tạm thời bỏ qua
    # if not current_user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")

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