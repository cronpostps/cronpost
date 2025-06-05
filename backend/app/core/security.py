# backend/app/core/security.py
# Version: 1.2 (Eager load User.configuration in get_current_user)

import os
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional, Annotated 
import uuid
from pydantic import BaseModel, EmailStr

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt as python_jose_jwt, JWTError as JoseJWTError

from ..db.database import get_db_session
from ..db.models import User, UserAccountStatusEnum # UserAccountStatusEnum đã có
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload # THÊM IMPORT NÀY

logger = logging.getLogger(__name__)

# --- Cấu hình JWT (Lấy từ .env, tương tự các router khác) ---
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
    if not APP_JWT_SECRET_KEY or not APP_JWT_ALGORITHM:
        logger.error("JWT_SECRET_KEY or JWT_ALGORITHM is not configured for token validation.")
        raise credentials_exception

    try:
        payload = python_jose_jwt.decode(
            token,
            APP_JWT_SECRET_KEY,
            algorithms=[APP_JWT_ALGORITHM]
        )
        user_id_str: Optional[str] = payload.get("sub")
        email_from_token: Optional[str] = payload.get("email")

        if user_id_str is None or email_from_token is None:
            logger.warning(f"Token payload missing 'sub' or 'email'. Payload: {payload}")
            raise credentials_exception
        
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            logger.warning(f"Invalid user_id format in token: {user_id_str}")
            raise credentials_exception

        # TokenData không còn được sử dụng trực tiếp để query, nhưng vẫn hữu ích để cấu trúc payload
        # token_data = TokenData(sub=str(user_id), email=email_from_token, provider=payload.get("provider"))

    except JoseJWTError as e:
        logger.warning(f"JWTError during token decoding: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error during token decoding: {e}", exc_info=True)
        raise credentials_exception

    # CẬP NHẬT QUERY ĐỂ EAGER LOAD User.configuration
    stmt = (
        select(User)
        .where(User.id == user_id) # Sử dụng user_id đã được validate
        .options(selectinload(User.configuration)) # Eager load UserConfiguration
    )
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if user is None:
        logger.warning(f"User with id {user_id} from token not found in DB.") # Sử dụng user_id
        raise credentials_exception
    
    # Kiểm tra email từ token với email trong DB để tăng cường bảo mật (tùy chọn)
    if user.email != email_from_token:
        logger.error(f"Email mismatch for user_id {user_id}. Token email: {email_from_token}, DB email: {user.email}")
        raise credentials_exception
        
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    if current_user.account_status == UserAccountStatusEnum.FNS:
        logger.warning(f"Active user check failed: User {current_user.email} is in FNS status.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is in a frozen state.")
    return current_user