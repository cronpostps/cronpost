# backend/app/routers/signin_router.py
# Version: 1.3 (Added IM check on sign-in to adjust account_status to INS if no IM and status is ANS_...)

import os
import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Request as FastAPIRequest
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from user_agents import parse

from ..db.database import get_db_session
from ..db.models import User, LoginHistory, Message, UserAccountStatusEnum, UserConfiguration # Thêm Message, UserAccountStatusEnum, UserConfiguration
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload # Để load UserConfiguration

import bcrypt
from jose import jwt as python_jose_jwt

# Giả sử limiter được import từ auth_router hoặc một module chung
try:
    from .auth_router import limiter as global_limiter
except ImportError:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("Could not import 'limiter' from .auth_router. Creating a new Limiter instance for signin_router.")
    global_limiter = Limiter(key_func=get_remote_address, default_limits=["100/hour"])


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Email/Password Sign-In"])

APP_JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
APP_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

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

class UserSignInRequest(BaseModel):
    email: EmailStr
    password: str
    # captchaToken: Optional[str] = None # Bỏ qua captcha ở signin_router hiện tại, vì nó đã có ở auth_router cho signup

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Thêm message để frontend có thể hiển thị nếu trạng thái bị thay đổi
    message: Optional[str] = None
    account_status_after_signin: Optional[UserAccountStatusEnum] = None


SIGNIN_RATE_LIMIT = "10/minute"

@router.post("/signin", response_model=TokenResponse)
@global_limiter.limit(SIGNIN_RATE_LIMIT)
async def signin_user_endpoint(
    form_data: UserSignInRequest,
    request: FastAPIRequest,
    db_session: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Signin attempt for: {form_data.email} from IP: {request.client.host if request.client else 'N/A'}")
    
    # Load user cùng với configuration để có thể cập nhật nếu cần
    user_stmt = await db_session.execute(
        select(User).filter_by(email=form_data.email).options(selectinload(User.configuration))
    )
    user = user_stmt.scalars().first()

    error_detail_invalid_credentials = "Incorrect email or password."
    status_adjusted_message: Optional[str] = None

    if not user:
        logger.warning(f"Signin failed for {form_data.email}: User not found.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail_invalid_credentials,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.password_hash:
        logger.warning(f"Signin attempt for {form_data.email} failed: No password set (provider: {user.provider}).")
        detail_message = f"This account (registered via {user.provider or 'an external provider'}) does not have a password set. Please use '{user.provider or 'your original'}' sign-in method."
        if user.provider == 'google':
            detail_message = "This account is linked with Google. Please use 'Continue with Google' to sign in."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail_message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.password_hash):
        logger.warning(f"Signin failed for {form_data.email}: Incorrect password.")
        # Ghi log đăng nhập thất bại (LoginHistory)
        login_entry_failed = LoginHistory(
            user_id=user.id,
            ip_address=str(request.client.host) if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        db_session.add(login_entry_failed)
        try:
            await db_session.commit()
        except Exception as e_log:
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
    
    # --- BEGIN LOGIC KIỂM TRA IM VÀ ĐIỀU CHỈNH ACCOUNT_STATUS ---
    if user.account_status in [UserAccountStatusEnum.ANS_CLC, UserAccountStatusEnum.ANS_WCT]:
        im_stmt = select(Message.id).where(
            Message.user_id == user.id,
            Message.is_initial_message == True
        ).limit(1)
        im_result = await db_session.execute(im_stmt)
        initial_message_exists = im_result.scalars().first() is not None

        if not initial_message_exists:
            logger.info(f"User {user.email} is in status {user.account_status} but has no IM. Reverting to INS.")
            original_status = user.account_status
            user.account_status = UserAccountStatusEnum.INS
            status_adjusted_message = f"Account status updated to INS as no Initial Message was found. Original status: {original_status}."
            
            # Nếu có user.configuration, xóa các trường liên quan đến CLC/WCT
            user_config = user.configuration # Đã được eager load
            if user_config:
                user_config.next_clc_prompt_at = None
                user_config.wct_active_ends_at = None
                user_config.is_clc_enabled = False # Vô hiệu hóa CLC
                db_session.add(user_config) # Đánh dấu user_config để commit
                logger.info(f"Cleared CLC/WCT config for user {user.email} due to reversion to INS.")
            db_session.add(user) # Đánh dấu user để commit
    # --- END LOGIC KIỂM TRA IM ---
    
    user.last_activity_at = datetime.now(dt_timezone.utc)
    user_agent_string = request.headers.get("user-agent")
    device_os_info = parse(user_agent_string).os.family if user_agent_string else None

    login_entry_success = LoginHistory(
        user_id=user.id,
        ip_address= str(request.client.host) if request.client else None,
        user_agent=request.headers.get("user-agent"),
        device_os=device_os_info
    )
    db_session.add(login_entry_success)
    
    try:
        await db_session.commit()
        await db_session.refresh(user) # Refresh user để lấy trạng thái mới nhất nếu có thay đổi
        if user.configuration: # Refresh cả configuration nếu nó đã được load và có thể đã thay đổi
            await db_session.refresh(user.configuration)
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error committing login history or status update for {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during sign-in process.")
    
    token_provider = user.provider if user.provider else "email"
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "provider": token_provider})
    
    logger.info(f"User {user.email} signed in successfully (provider: {user.provider}). Account status: {user.account_status}.")
    return TokenResponse(
        access_token=access_token, 
        token_type="bearer",
        message=status_adjusted_message, # Trả về thông báo nếu trạng thái bị thay đổi
        account_status_after_signin=user.account_status # Trả về trạng thái cuối cùng
    )