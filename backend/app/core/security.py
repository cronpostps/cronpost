# backend/app/core/security.py
# Version 2.0 (Added Fernet encryption/decryption)

import os
import logging
from typing import Optional, Annotated
import uuid
from pydantic import BaseModel, EmailStr
from cryptography.fernet import Fernet

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt as python_jose_jwt, JWTError as JoseJWTError

from ..db.database import get_db_session
from ..db.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
APP_JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
APP_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY") # Đọc khóa mã hóa từ .env

# --- INITIALIZATION ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/signin")

# Khởi tạo Fernet để mã hóa, báo lỗi nếu không tìm thấy key
if not ENCRYPTION_KEY:
    logger.critical("CRITICAL: ENCRYPTION_KEY is not set in the environment. SMTP password encryption will fail.")
    fernet = None
else:
    fernet = Fernet(ENCRYPTION_KEY.encode())

class TokenData(BaseModel):
    sub: Optional[str] = None
    email: Optional[EmailStr] = None
    provider: Optional[str] = None

# --- CÁC HÀM MÃ HÓA / GIẢI MÃ MỚI ---
def encrypt_data(data: str) -> str:
    """Mã hóa một chuỗi và trả về chuỗi đã mã hóa."""
    if not fernet:
        raise ValueError("Encryption service is not available due to missing ENCRYPTION_KEY.")
    if not isinstance(data, str):
        raise TypeError("Data to be encrypted must be a string.")
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Giải mã một chuỗi và trả về chuỗi gốc."""
    if not fernet:
        raise ValueError("Decryption service is not available due to missing ENCRYPTION_KEY.")
    if not isinstance(encrypted_data, str):
        raise TypeError("Encrypted data must be a string.")
    return fernet.decrypt(encrypted_data.encode()).decode()


# --- CÁC DEPENDENCY HIỆN CÓ ---
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
    # Logic to check if user is active (e.g., email confirmed)
    # if not current_user.is_confirmed_by_email:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN, 
    #         detail="Email not confirmed"
    #     )
    return current_user

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