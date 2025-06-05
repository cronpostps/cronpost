# backend/app/routers/signin_router.py
# Version: 1.2 (Removed non-existent keyword arguments 'login_successful', 'failure_reason' from LoginHistory instantiation)

import os
import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Request as FastAPIRequest
from pydantic import BaseModel, EmailStr

# Import từ project của bạn
from ..db.database import get_db_session
from ..db.models import User, LoginHistory 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import bcrypt
from jose import jwt as python_jose_jwt

try:
    from .auth_router import limiter as global_limiter
except ImportError:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    logger_temp = logging.getLogger(__name__) # Tạo logger tạm thời nếu cần
    logger_temp.warning("Could not import 'limiter' from .auth_router. Creating a new Limiter instance for signin_router.")
    global_limiter = Limiter(key_func=get_remote_address, default_limits=["100/hour"])


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Email/Password Sign-In"])

# --- Cấu hình JWT từ Biến Môi trường ---
APP_JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") 
APP_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# --- Hàm Tiện ích ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password: return False
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(dt_timezone.utc) + expires_delta
    else:
        expire = datetime.now(dt_timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.now(dt_timezone.utc)})
    return python_jose_jwt.encode(to_encode, APP_JWT_SECRET_KEY, algorithm=APP_JWT_ALGORITHM)

# --- Pydantic Models ---
class UserSignInRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel): 
    access_token: str
    token_type: str = "bearer"

# --- Rate Limit Definition ---
SIGNIN_RATE_LIMIT = "10/minute" 

@router.post("/signin", response_model=TokenResponse)
@global_limiter.limit(SIGNIN_RATE_LIMIT) 
async def signin_user_endpoint(
    form_data: UserSignInRequest,
    request: FastAPIRequest, 
    db_session: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Signin attempt for: {form_data.email} from IP: {request.client.host if request.client else 'N/A'}")
    
    user_stmt = await db_session.execute(select(User).filter_by(email=form_data.email))
    user = user_stmt.scalars().first()

    error_detail_invalid_credentials = "Incorrect email or password."

    if not user: 
        logger.warning(f"Signin failed for {form_data.email}: User not found.")
        # Ghi log đăng nhập thất bại (nếu muốn, cần thêm trường vào LoginHistory)
        # login_entry_failed = LoginHistory(
        #     user_id=None, # Hoặc một giá trị đặc biệt
        #     ip_address= str(request.client.host) if request.client else None,
        #     user_agent=request.headers.get("user-agent"),
        #     # login_successful=False, 
        #     # failure_reason="User not found"
        # )
        # db_session.add(login_entry_failed)
        # await db_session.commit() # Cân nhắc việc commit lỗi ở đây
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail_invalid_credentials,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.password_hash:
        logger.warning(f"Signin attempt for {form_data.email} failed: No password set (provider: {user.provider}).")
        detail_message = f"This account (registered via {user.provider or 'an external provider'}) does not have a password set. Please use '{user.provider or 'your original'}' sign-in method."
        if user.provider == 'google': # Cụ thể hóa cho Google
            detail_message = "This account is linked with Google. Please use 'Continue with Google' to sign in."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail_message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.password_hash):
        logger.warning(f"Signin failed for {form_data.email}: Incorrect password.")
        login_entry_failed = LoginHistory( # Chỉ ghi thông tin cơ bản nếu model không có trường chi tiết lỗi
            user_id=user.id, 
            ip_address= str(request.client.host) if request.client else None,
            user_agent=request.headers.get("user-agent")
            # Không truyền login_successful, failure_reason
        )
        db_session.add(login_entry_failed)
        try:
            await db_session.commit()
        except Exception as e_log: # Bắt lỗi nếu ghi log thất bại, nhưng vẫn raise lỗi 401
            logger.error(f"Error committing failed login attempt for {user.email}: {e_log}")
            await db_session.rollback()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail_invalid_credentials,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.provider == 'email' and not user.is_confirmed_by_email:
        logger.warning(f"Signin failed for {form_data.email} (provider: email): Email not confirmed.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not confirmed. Please check your inbox or resend the confirmation email.",
            headers={"X-Verification-Needed": "true", "X-Email": user.email} 
        )
    
    user.last_activity_at = datetime.now(dt_timezone.utc)
    login_entry_success = LoginHistory( # Chỉ ghi thông tin cơ bản
        user_id=user.id, 
        ip_address= str(request.client.host) if request.client else None,
        user_agent=request.headers.get("user-agent")
        # Không truyền login_successful
    )
    db_session.add(login_entry_success)
    
    try:
        await db_session.commit()
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error committing login history or last_activity for {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during sign-in process.")
    
    token_provider = user.provider if user.provider else "email"
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "provider": token_provider})
    
    logger.info(f"User {user.email} signed in successfully (provider on record: {user.provider}).")
    return TokenResponse(access_token=access_token, token_type="bearer")