# backend/app/core/security.py
# Version 2.4
# - Added logic to prune old pin_attempts to a configured limit (default 50).
# - Added necessary sqlalchemy imports.

import os
import logging
from typing import Optional, Annotated, Dict
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from pydantic import BaseModel, EmailStr
from cryptography.fernet import Fernet

from fastapi import Depends, HTTPException, status
from jose import jwt as python_jose_jwt, JWTError as JoseJWTError

from ..db.database import get_db_session
from ..db.models import User, PinAttempt
from sqlalchemy.ext.asyncio import AsyncSession
# sqlalchemy imports for pruning logic
from sqlalchemy import select, func, delete 
from sqlalchemy.orm import selectinload

from ..routers.auth_router import verify_password
from ..dependencies import get_system_settings_dep, oauth2_scheme

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
APP_JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
APP_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY.encode()) if ENCRYPTION_KEY else None

# --- CORE FUNCTIONS ---
def encrypt_data(data: str) -> str:
    if not fernet: raise ValueError("Encryption service not available.")
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    if not fernet: raise ValueError("Decryption service not available.")
    return fernet.decrypt(encrypted_data.encode()).decode()

async def get_user_from_token(token: str, db: AsyncSession) -> Optional[User]:
    """
    Giải mã JWT token và lấy thông tin người dùng tương ứng từ database.
    Hàm này không phải là một dependency của FastAPI, dùng cho các trường hợp
    như xác thực SSE qua query parameter.
    Trả về object User nếu thành công, hoặc None nếu token không hợp lệ.
    """
    try:
        payload = python_jose_jwt.decode(token, APP_JWT_SECRET_KEY, algorithms=[APP_JWT_ALGORITHM])
        user_id_str = payload.get("sub")
        if not user_id_str:
            logger.warning("Token payload is missing 'sub' (user_id).")
            return None
        user_id = uuid.UUID(user_id_str)

    except (JoseJWTError, ValueError, TypeError) as e:
        logger.warning(f"Token validation failed: {e}")
        return None

    # Lấy thông tin người dùng từ database
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    return user

# --- Centralized PIN Verification Service ---
async def verify_user_pin_with_lockout(
    db: AsyncSession,
    user: User,
    submitted_pin: str,
    settings: Dict[str, str]
):
    # 1. Check if account is currently locked
    if user.account_locked_until and user.account_locked_until > datetime.now(dt_timezone.utc):
        remaining_seconds = (user.account_locked_until - datetime.now(dt_timezone.utc)).total_seconds()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "type": "account_locked",
                "message": "PIN entry is locked.",
                "remaining_seconds": round(remaining_seconds)
            }
        )

    # 2. Verify the PIN
    is_correct = verify_password(submitted_pin, user.pin_code)

    # === NEW: Prune old pin attempts if limit is reached ===
    # This logic runs before adding the new attempt.
    max_log_entries = int(settings.get('max_pin_attempts_log_per_user', 50))
    
    count_stmt = select(func.count(PinAttempt.id)).where(PinAttempt.user_id == user.id)
    current_attempts_count = (await db.execute(count_stmt)).scalar_one()

    if current_attempts_count >= max_log_entries:
        # Find the ID of the oldest attempt for this user (lowest ID)
        oldest_attempt_id_stmt = (
            select(PinAttempt.id)
            .where(PinAttempt.user_id == user.id)
            .order_by(PinAttempt.id.asc())
            .limit(1)
            .scalar_subquery()
        )
        
        # Delete that oldest attempt to make room for the new one
        if oldest_attempt_id_stmt is not None:
            delete_stmt = delete(PinAttempt).where(PinAttempt.id == oldest_attempt_id_stmt)
            await db.execute(delete_stmt)
            logger.info(f"Pruned oldest PIN attempt for user {user.email} to maintain log limit of {max_log_entries}.")
    # === End of pruning logic ===

    # 3. Log the current attempt
    db.add(PinAttempt(user_id=user.id, is_successful=is_correct))
    
    # 4. Handle correct PIN
    if is_correct:
        if user.failed_pin_attempts > 0 or user.account_locked_until:
            user.failed_pin_attempts = 0
            user.account_locked_until = None
            user.account_locked_reason = None
        await db.commit()
        return True

    # 5. Handle incorrect PIN
    else:
        user.failed_pin_attempts += 1
        threshold = int(settings.get('failed_pin_attempts_lockout_threshold', 5))
        base_duration_min = int(settings.get('pin_lockout_duration_minutes', 15))
        
        if user.failed_pin_attempts >= threshold:
            lockout_multiplier = user.failed_pin_attempts // threshold
            lockout_duration_min = lockout_multiplier * base_duration_min
            user.account_locked_until = datetime.now(dt_timezone.utc) + timedelta(minutes=lockout_duration_min)
            user.account_locked_reason = f"Locked after {user.failed_pin_attempts} failed attempts."
            
            await db.commit()
            
            remaining_seconds = lockout_duration_min * 60
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "type": "account_locked",
                    "message": "Incorrect PIN. Your account is now locked.",
                    "remaining_seconds": round(remaining_seconds)
                }
            )
        else:
            attempts_remaining = threshold - user.failed_pin_attempts
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Incorrect PIN. You have {attempts_remaining} attempts remaining before your account is locked."
            )

# --- DEPENDENCIES ---
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db_session)) -> User:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = python_jose_jwt.decode(token, APP_JWT_SECRET_KEY, algorithms=[APP_JWT_ALGORITHM])
        user_id = uuid.UUID(payload.get("sub"))
    except (JoseJWTError, ValueError, TypeError):
        raise credentials_exception
    user = (await db.execute(select(User).where(User.id == user_id).options(selectinload(User.configuration), selectinload(User.review)))).scalars().first()
    if user is None: raise credentials_exception
    return user

async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.is_confirmed_by_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Email not confirmed"
        )
    return current_user

async def get_current_admin_user(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    if not current_user.is_admin:
        logger.warning(f"Non-admin user {current_user.email} attempted to access an admin route.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource.")
    logger.info(f"Admin access granted for user: {current_user.email}")
    return current_user