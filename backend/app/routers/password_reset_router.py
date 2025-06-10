# backend/app/routers/password_reset_router.py
# Version: 1.6.0
# Mô tả: Tích hợp email_service để gửi email trực tiếp, loại bỏ n8n.

import os
import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

import bcrypt

from fastapi import APIRouter, HTTPException, Depends, status, Request as FastAPIRequest, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from ..db.database import get_db_session
from ..db.models import User, PasswordResetToken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update

# --- IMPORT MỚI & THAY ĐỔI ---
from ..services.captcha_service import verify_turnstile_captcha
from ..services.email_service import send_email_async # Import hàm gửi email mới

try:
    from .auth_router import limiter as global_limiter, hash_password, verify_password
except ImportError:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    global_limiter = Limiter(key_func=get_remote_address, default_limits=["100/hour"])
    def hash_password(p: str) -> str: return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    def verify_password(p: str, h: str) -> bool: return bcrypt.checkpw(p.encode('utf-8'),h.encode('utf-8')) if p and h else False

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Password Reset"])

# --- Cấu hình (giữ nguyên) ---
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost")
PASSWORD_RESET_SECRET_KEY = os.environ.get("PASSWORD_RESET_SECRET_KEY", "default-password-reset-secret-key-please-change")
PASSWORD_RESET_SALT = os.environ.get("PASSWORD_RESET_SALT", "password-reset-salt")
PASSWORD_RESET_TOKEN_LIFESPAN_HOURS = int(os.environ.get("PASSWORD_RESET_TOKEN_LIFESPAN_HOURS", "1"))
password_reset_serializer = URLSafeTimedSerializer(PASSWORD_RESET_SECRET_KEY)

# --- Pydantic Models (giữ nguyên) ---
class PasswordResetRequestForm(BaseModel):
    email: EmailStr
    captchaToken: str

class PasswordResetConfirmForm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6, max_length=20)
    confirm_new_password: str

class MessageResponse(BaseModel):
    message: str

# --- Rate Limit Definition (giữ nguyên) ---
REQUEST_PASSWORD_RESET_RATE_LIMIT = "2/hour"
RESET_PASSWORD_RATE_LIMIT = "5/minute"

# --- Endpoint Yêu cầu Đặt lại Mật khẩu ---
@router.post("/request-password-reset", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@global_limiter.limit(REQUEST_PASSWORD_RESET_RATE_LIMIT)
async def request_password_reset_endpoint(
    form_data: PasswordResetRequestForm,
    request: FastAPIRequest,
    background_tasks: BackgroundTasks,
    db_session: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Password reset requested for email: {form_data.email} from IP: {request.client.host if request.client else 'N/A'}")

    if not await verify_turnstile_captcha(
        token=form_data.captchaToken,
        client_ip=request.client.host if request.client else None
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CAPTCHA.")

    user_stmt = await db_session.execute(select(User).filter_by(email=form_data.email))
    user = user_stmt.scalars().first()

    if user and user.password_hash is not None:
        token_payload = {"user_id": str(user.id), "email": user.email, "purpose": "password_reset"}
        reset_token_str = password_reset_serializer.dumps(token_payload, salt=PASSWORD_RESET_SALT)
        token_hash_for_db = hash_password(reset_token_str)
        expires_at = datetime.now(dt_timezone.utc) + timedelta(hours=PASSWORD_RESET_TOKEN_LIFESPAN_HOURS)

        await db_session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.is_used == False)
            .values(is_used=True, updated_at=datetime.now(dt_timezone.utc))
        )
        
        new_reset_token_record = PasswordResetToken(
            user_id=user.id, reset_token_hash=token_hash_for_db, token_expires_at=expires_at
        )
        db_session.add(new_reset_token_record)
        
        try:
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Failed to save password reset token for {user.email}: {e}", exc_info=True)
            return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"message": "If an account with that email exists, an email has been sent."})

        # --- THAY THẾ LOGIC GỬI EMAIL ---
        password_reset_link = f"{FRONTEND_BASE_URL}/reset-password?token={reset_token_str}"
        email_subject = "Your CronPost Password Reset Request"
        template_body = {
            "user_name": user.user_name or user.email.split('@')[0],
            "password_reset_link": password_reset_link,
            "token_lifespan_hours": PASSWORD_RESET_TOKEN_LIFESPAN_HOURS,
        }
        background_tasks.add_task(send_email_async, email_subject, user.email, template_body, "password_reset.html")
        # ---------------------------

        logger.info(f"Password reset email dispatched for {user.email}.")
    else:
        logger.info(f"Password reset requested for non-existent or ineligible email: {form_data.email}")
            
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"message": "If an account with that email exists and is eligible for password reset, a link has been sent."})


# --- Endpoint để thực sự đặt lại mật khẩu (giữ nguyên) ---
@router.post("/reset-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@global_limiter.limit(RESET_PASSWORD_RATE_LIMIT)
async def reset_password_endpoint(
    form_data: PasswordResetConfirmForm,
    request: FastAPIRequest,
    db_session: AsyncSession = Depends(get_db_session)
):
    # ... (giữ nguyên logic)
    logger.info(f"Attempting password reset with token: {form_data.token[:10]}...")
    if form_data.new_password != form_data.confirm_new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password and confirmation do not match.")
    user_id_from_token = None; email_from_token = None
    try:
        token_payload = password_reset_serializer.loads(form_data.token, salt=PASSWORD_RESET_SALT, max_age=PASSWORD_RESET_TOKEN_LIFESPAN_HOURS * 3600)
        user_id_from_token = uuid.UUID(token_payload["user_id"]); email_from_token = token_payload["email"]
        if token_payload.get("purpose") != "password_reset":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token.")
    except SignatureExpired:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset token has expired. Please request a new one.")
    except BadTimeSignature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password reset token.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or malformed password reset token.")
    stmt_tokens = await db_session.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user_id_from_token, PasswordResetToken.token_expires_at > datetime.now(dt_timezone.utc), PasswordResetToken.is_used == False).order_by(PasswordResetToken.created_at.desc()))
    eligible_tokens = stmt_tokens.scalars().all()
    found_valid_token_record = None
    for token_record in eligible_tokens:
        if verify_password(form_data.token, token_record.reset_token_hash):
            found_valid_token_record = token_record; break
    if not found_valid_token_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired password reset token. Please request a new one.")
    user = await db_session.get(User, user_id_from_token)
    if not user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User not found for this reset token. Please contact support.")
    user.password_hash = hash_password(form_data.new_password); user.updated_at = datetime.now(dt_timezone.utc)
    found_valid_token_record.is_used = True; found_valid_token_record.updated_at = datetime.now(dt_timezone.utc)
    try:
        await db_session.commit();
        logger.info(f"Password successfully reset for user {user.email}.")
        return {"message": "Your password has been successfully reset."}
    except Exception as e:
        await db_session.rollback();
        logger.error(f"Failed to update password for user {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while resetting your password.")