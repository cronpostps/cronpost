# backend/app/core/security.py
# Version: 1.0 (Handles JWT decoding and current user dependency)

import os
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional, Annotated # Thêm Annotated cho FastAPI 0.100+
import uuid
from pydantic import BaseModel, EmailStr

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer # Dùng để khai báo scheme lấy token từ header
from jose import jwt as python_jose_jwt, JWTError as JoseJWTError # Sử dụng alias như trong auth_router

from ..db.database import get_db_session
from ..db.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

# --- Cấu hình JWT (Lấy từ .env, tương tự các router khác) ---
APP_JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") 
APP_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# OAuth2PasswordBearer trỏ đến một URL endpoint (ví dụ: /api/auth/signin) 
# nơi client có thể lấy token. Dù chúng ta không dùng luồng password bearer trực tiếp ở đây
# nhưng nó cần thiết để FastAPI biết cách trích xuất token từ header "Authorization: Bearer <token>"
# URL này có thể là bất kỳ URL nào, nó không thực sự được gọi bởi dependency này.
# Quan trọng là nó định nghĩa "scheme".
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/signin") # Sử dụng prefix /api

class TokenData(BaseModel): # Pydantic model cho dữ liệu trong token
    sub: Optional[str] = None # User ID (subject)
    email: Optional[EmailStr] = None
    provider: Optional[str] = None

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], # Lấy token từ header Authorization
    db: AsyncSession = Depends(get_db_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not APP_JWT_SECRET_KEY or not APP_JWT_ALGORITHM:
        logger.error("JWT_SECRET_KEY or JWT_ALGORITHM is not configured for token validation.")
        raise credentials_exception # Không thể xác thực nếu thiếu key hoặc thuật toán

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

        token_data = TokenData(sub=str(user_id), email=email_from_token, provider=payload.get("provider"))
    
    except JoseJWTError as e: # Bắt lỗi cụ thể từ python-jose
        logger.warning(f"JWTError during token decoding: {e}")
        raise credentials_exception
    except Exception as e: # Bắt các lỗi khác có thể xảy ra khi decode
        logger.error(f"Unexpected error during token decoding: {e}", exc_info=True)
        raise credentials_exception

    user = await db.get(User, token_data.sub) # Lấy user từ DB bằng ID (sub)
    if user is None:
        logger.warning(f"User with id {token_data.sub} from token not found in DB.")
        raise credentials_exception
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)] # Sử dụng User từ Pydantic Base Model hoặc SQLAlchemy model
) -> User: # Trả về User model từ SQLAlchemy
    # Thêm các kiểm tra khác nếu cần, ví dụ: user.is_active (nếu bạn có trường đó)
    # hoặc user.account_status
    if current_user.account_status == UserAccountStatusEnum.FNS: # Ví dụ: không cho user FNS truy cập API thường
        logger.warning(f"Active user check failed: User {current_user.email} is in FNS status.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is in a frozen state.")
    # Bạn có thể thêm kiểm tra is_confirmed_by_email ở đây nếu muốn,
    # nhưng nó đã được kiểm tra ở signin và khi tạo token cho Google user.
    return current_user