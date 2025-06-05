# backend/app/routers/password_reset_router.py
# Version: 1.5 (Integrated captcha_service, and final fixes)

import os
import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional # Đảm bảo import Optional

# import httpx # Không cần trực tiếp ở đây nữa, vì đã chuyển sang captcha_service
import bcrypt # Cần cho hash/verify password

from fastapi import APIRouter, HTTPException, Depends, status, Request as FastAPIRequest, BackgroundTasks
from fastapi.responses import JSONResponse # Cần cho JSONResponse
from pydantic import BaseModel, EmailStr, Field

# Import các thành phần cần thiết từ project của bạn
from ..db.database import get_db_session
from ..db.models import User, PasswordResetToken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update # Import 'update' trực tiếp từ sqlalchemy

# Import hàm xác minh Turnstile từ service mới
from ..services.captcha_service import verify_turnstile_captcha

# Import các hàm và đối tượng cần thiết từ auth_router.py hoặc các module chung
try:
    from .auth_router import limiter as global_limiter
    # Cần đảm bảo hash_password và verify_password được import từ auth_router hoặc một service khác
    from .auth_router import hash_password, verify_password
    from .auth_router import send_payload_to_n8n_task # send_payload_to_n8n_task vẫn cần
except ImportError:
    # Fallback imports nếu chạy riêng (không khuyến khích cho production)
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    global_limiter = Limiter(key_func=get_remote_address, default_limits=["100/hour"])
    # Dummy send_payload_to_n8n_task nếu không import được
    async def send_payload_to_n8n_task(payload: dict): logging.getLogger(__name__).info(f"Dummy send_payload_to_n8n_task: {payload}")
    # Dummy hash/verify password nếu không import được
    def hash_password(p: str) -> str: return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    def verify_password(p: str, h: str) -> bool: return bcrypt.checkpw(p.encode('utf-8'),h.encode('utf-8')) if p and h else False


from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Password Reset"]) # Giữ nguyên không có prefix ở đây, để main.py định nghĩa

# --- Cấu hình từ Biến Môi trường ---
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost")
N8N_EMAIL_WEBHOOK_URL = os.environ.get("N8N_EMAIL_WEBHOOK_URL")

PASSWORD_RESET_SECRET_KEY = os.environ.get("PASSWORD_RESET_SECRET_KEY", "default-password-reset-secret-key-please-change")
PASSWORD_RESET_SALT = os.environ.get("PASSWORD_RESET_SALT", "password-reset-salt")
PASSWORD_RESET_TOKEN_LIFESPAN_HOURS = int(os.environ.get("PASSWORD_RESET_TOKEN_LIFESPAN_HOURS", "1"))

password_reset_serializer = URLSafeTimedSerializer(PASSWORD_RESET_SECRET_KEY)

# --- Pydantic Models ---
class PasswordResetRequestForm(BaseModel):
    email: EmailStr
    captchaToken: str

class PasswordResetConfirmForm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6, max_length=20)
    confirm_new_password: str

class MessageResponse(BaseModel):
    message: str

# --- Rate Limit Definition ---
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

    # GỌI HÀM XÁC MINH TURNSTILE TỪ SERVICE CHUNG
    if not await verify_turnstile_captcha(
        token=form_data.captchaToken,
        client_ip=request.client.host if request.client else None
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CAPTCHA.")

    user_stmt = await db_session.execute(select(User).filter_by(email=form_data.email))
    user = user_stmt.scalars().first()

    if user and user.password_hash is not None:
        # 1. Tạo token đặt lại mật khẩu
        token_payload = {"user_id": str(user.id), "email": user.email, "purpose": "password_reset"}
        reset_token_str = password_reset_serializer.dumps(token_payload, salt=PASSWORD_RESET_SALT)

        # 2. Hash token để lưu vào DB (sử dụng bcrypt)
        token_hash_for_db = hash_password(reset_token_str)
        
        expires_at = datetime.now(dt_timezone.utc) + timedelta(hours=PASSWORD_RESET_TOKEN_LIFESPAN_HOURS)

        # 3. Vô hiệu hóa các token cũ chưa sử dụng của user này
        await db_session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.is_used == False,
                PasswordResetToken.token_expires_at > datetime.now(dt_timezone.utc)
            )
            .values(is_used=True, updated_at=datetime.now(dt_timezone.utc))
        )
        
        # 4. Tạo record token mới
        new_reset_token_record = PasswordResetToken(
            user_id=user.id,
            reset_token_hash=token_hash_for_db,
            token_expires_at=expires_at
        )
        db_session.add(new_reset_token_record)
        try:
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Failed to save password reset token for {user.email}: {e}", exc_info=True)
            return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"message": "If an account with that email exists and is eligible for password reset, a link has been sent."})

        # 5. Gửi email chứa link với token gốc (reset_token_str)
        # Đảm bảo link không có .html ở cuối nếu bạn đã cấu hình Nginx để xử lý clean URLs
        password_reset_link = f"{FRONTEND_BASE_URL}/reset-password?token={reset_token_str}"
        
        email_payload = {
            "receiver_email": user.email,
            "user_name": user.user_name or user.email.split('@')[0],
            "password_reset_link": password_reset_link,
            "token_lifespan_hours": PASSWORD_RESET_TOKEN_LIFESPAN_HOURS,
            "email_type": "password_reset_request"
        }
        background_tasks.add_task(send_payload_to_n8n_task, email_payload)
        logger.info(f"Password reset email dispatched for {user.email}.")
    else:
        if user and user.provider != 'email' and user.provider is not None:
             logger.warning(f"Password reset attempt for non-email provider account: {form_data.email} (provider: {user.provider})")
        else:
            logger.info(f"Password reset requested for non-existent or ineligible email: {form_data.email}")
            
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"message": "If an account with that email exists and is eligible for password reset, a link has been sent."})


# --- Endpoint để thực sự đặt lại mật khẩu ---
@router.post("/reset-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
@global_limiter.limit(RESET_PASSWORD_RATE_LIMIT)
async def reset_password_endpoint(
    form_data: PasswordResetConfirmForm,
    request: FastAPIRequest,
    db_session: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Attempting password reset with token: {form_data.token[:10]}...")
    
    if form_data.new_password != form_data.confirm_new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password and confirmation do not match.")

    user_id_from_token = None
    email_from_token = None
    try:
        token_payload = password_reset_serializer.loads(
            form_data.token,
            salt=PASSWORD_RESET_SALT,
            max_age=PASSWORD_RESET_TOKEN_LIFESPAN_HOURS * 3600
        )
        user_id_from_token = uuid.UUID(token_payload["user_id"])
        email_from_token = token_payload["email"]
        if token_payload.get("purpose") != "password_reset":
            logger.warning(f"Invalid token purpose for reset-password: {token_payload.get('purpose')}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token.")
    except SignatureExpired:
        logger.warning(f"Password reset token expired: {form_data.token[:10]}...")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset token has expired. Please request a new one.")
    except BadTimeSignature:
        logger.warning(f"Invalid password reset token (BadTimeSignature): {form_data.token[:10]}...")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password reset token.")
    except Exception as e:
        logger.error(f"Error decoding password reset token {form_data.token[:10]}...: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or malformed password reset token.")

    stmt_tokens = await db_session.execute(
        select(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user_id_from_token,
            PasswordResetToken.token_expires_at > datetime.now(dt_timezone.utc),
            PasswordResetToken.is_used == False
        )
        .order_by(PasswordResetToken.created_at.desc())
    )
    eligible_tokens = stmt_tokens.scalars().all()

    found_valid_token_record = None
    for token_record in eligible_tokens:
        if verify_password(form_data.token, token_record.reset_token_hash):
            found_valid_token_record = token_record
            break
    
    if not found_valid_token_record:
        logger.warning(f"No valid, unused or unexpired password reset token found for user_id {user_id_from_token} with provided token {form_data.token[:10]}...")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired password reset token. Please request a new one.")
    
    user = await db_session.get(User, user_id_from_token)
    if not user:
        logger.error(f"User with ID {user_id_from_token} from valid token not found. Data inconsistency?")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User not found for this reset token. Please contact support.")

    user.password_hash = hash_password(form_data.new_password)
    user.updated_at = datetime.now(dt_timezone.utc)
    found_valid_token_record.is_used = True
    found_valid_token_record.updated_at = datetime.now(dt_timezone.utc)

    try:
        await db_session.commit()
        logger.info(f"Password successfully reset for user {user.email}.")
        return {"message": "Your password has been successfully reset."}
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Failed to update password for user {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while resetting your password.")