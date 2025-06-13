# backend/app/routers/user_profile_router.py
# Version: 2.0.1 (Add User SMTP connection testing)

import logging
from typing import Optional, List
from datetime import datetime
import secrets
import pytz
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from pydantic import BaseModel, EmailStr, Field, constr, IPvAnyAddress
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..db.database import get_db_session
from ..db.models import User, UserReview, RatingPointsEnum, LoginHistory, UserSmtpSettings
from ..core.security import get_current_active_user, encrypt_data
from ..routers.auth_router import hash_password, verify_password
from ..services.email_service import send_email_async, test_smtp_connection

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["User Profile"],
    dependencies=[Depends(get_current_active_user)]
)

# --- Pydantic Models ---
class ProfileUpdateRequest(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=50)
    timezone: str
    trust_verifier_email: Optional[EmailStr] = None
    pin_code: Optional[constr(pattern=r"^\d{4}$")] = None

class SecurityOptionsUpdateRequest(BaseModel):
    use_pin_for_all_actions: bool
    checkin_on_signin: bool
    pin_code: Optional[constr(pattern=r"^\d{4}$")] = None

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=20)

class PinChangeRequest(BaseModel):
    current_pin: Optional[constr(pattern=r"^\d{4}$")] = None
    new_pin: constr(pattern=r"^\d{4}$")
    pin_question: Optional[str] = Field(None, max_length=255)

class PinRecoveryRequest(BaseModel):
    recovery_code: str
    new_pin: constr(pattern=r"^\d{4}$")

class PinVerificationRequest(BaseModel):
    pin_code: constr(pattern=r"^\d{4}$")

class ReviewRequest(BaseModel):
    rating_points: RatingPointsEnum
    comment: Optional[str] = Field(None, max_length=300)

# Model Response mới cho UserReview
class UserReviewResponse(BaseModel):
    user_id: uuid.UUID
    rating_points: RatingPointsEnum
    comment: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    message: str

class LoginHistoryResponse(BaseModel):
    login_time: datetime
    ip_address: Optional[IPvAnyAddress] = None
    user_agent: Optional[str] = None
    device_os: Optional[str] = None
    class Config:
        from_attributes = True

# User SMTP Settings Models
class SmtpTestResponse(BaseModel):
    success: bool
    message: str

class UserSmtpSettingsResponse(BaseModel):
    smtp_server: str
    smtp_port: int
    smtp_sender_email: EmailStr
    is_active: bool

    class Config:
        from_attributes = True # orm_mode for Pydantic v1

class UserSmtpSettingsUpdate(BaseModel):
    smtp_server: str
    smtp_port: int
    smtp_sender_email: EmailStr
    smtp_password: str

# --- Endpoints ---
# ... (Các endpoint khác giữ nguyên)

@router.put("/profile", response_model=MessageResponse, summary="Update user's profile information")
async def update_user_profile(profile_data: ProfileUpdateRequest, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db_session)):
    if profile_data.timezone not in pytz.all_timezones: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{profile_data.timezone}' is not a valid timezone.")
    current_user.user_name = profile_data.user_name; current_user.timezone = profile_data.timezone; current_user.trust_verifier_email = profile_data.trust_verifier_email
    await db.commit(); return {"message": "Profile updated successfully."}

@router.put("/security-options", response_model=MessageResponse, summary="Update user's security toggles")
async def update_security_options(options_data: SecurityOptionsUpdateRequest, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db_session)):
    # --- THÊM LOGIC KIỂM TRA BẢO MẬT ---
    if (options_data.use_pin_for_all_actions or options_data.checkin_on_signin) and not current_user.pin_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must create a PIN before enabling 'Require PIN' or 'Automatic Check-in'."
        )
    # --- KẾT THÚC CẬP NHẬT ---
    # Nếu user đã có PIN, mọi thay đổi trong mục này đều cần xác thực lại bằng PIN
    if current_user.pin_code:
        if not options_data.pin_code or not verify_password(options_data.pin_code, current_user.pin_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Incorrect PIN."
            )
    # --- KẾT THÚC LOGIC MỚI ---

    current_user.use_pin_for_all_actions = options_data.use_pin_for_all_actions
    current_user.checkin_on_signin = options_data.checkin_on_signin
    await db.commit()
    return {"message": "Security options updated successfully."}

@router.post("/change-password", response_model=MessageResponse, summary="Change user's password")
async def change_user_password(password_data: PasswordChangeRequest, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db_session)):
    if not current_user.password_hash or not verify_password(password_data.current_password, current_user.password_hash): raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect current password.")
    current_user.password_hash = hash_password(password_data.new_password); await db.commit(); return {"message": "Password updated successfully."}

@router.post("/change-pin", response_model=MessageResponse, summary="Set or change user's PIN") # Sửa response_model
async def change_user_pin(
    pin_data: PinChangeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    message: str
    # Trường hợp 1: User đã có PIN, đang muốn đổi PIN
    if current_user.pin_code:
        if not pin_data.current_pin or not verify_password(pin_data.current_pin, current_user.pin_code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect current PIN.")
        message = "PIN updated successfully."

    # Trường hợp 2: User chưa có PIN, đặt PIN lần đầu
    else:
        if pin_data.current_pin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current PIN must be empty when setting a PIN for the first time."
            )
        
        raw_recovery_code = secrets.token_urlsafe(22)
        current_user.pin_recovery_code_hash = hash_password(raw_recovery_code)
        current_user.pin_recovery_code_used = False
        message = "PIN has been set successfully. A recovery code has been sent to your email."
        
        # Gửi email trong nền
        email_body = {
            "user_name": current_user.user_name or current_user.email,
            "recovery_code": raw_recovery_code
        }
        background_tasks.add_task(
            send_email_async,
            "Your CronPost PIN Recovery Code",
            current_user.email,
            email_body,
            "pin_recovery_code.html"
        )

    # Cập nhật PIN mới và câu hỏi gợi nhớ
    current_user.pin_code = hash_password(pin_data.new_pin)
    current_user.pin_code_question = pin_data.pin_question
    
    await db.commit()
    
    return MessageResponse(message=message)

@router.post("/recover-pin", response_model=MessageResponse, summary="Recover PIN using a recovery code")
async def recover_user_pin(recovery_data: PinRecoveryRequest, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db_session)):
    if not current_user.pin_recovery_code_hash: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No recovery code was generated for this account.")
    if current_user.pin_recovery_code_used: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recovery code has already been used.")
    if not verify_password(recovery_data.recovery_code, current_user.pin_recovery_code_hash): raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid recovery code.")
    current_user.pin_code = hash_password(recovery_data.new_pin); current_user.pin_recovery_code_used = True
    await db.commit(); return {"message": "PIN successfully recovered and updated."}

@router.delete("/pin", response_model=MessageResponse, summary="Remove user's PIN and related data")
async def remove_user_pin(
    pin_data: PinVerificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Verifies the user's current PIN and removes it along with all related
    settings and recovery data.
    """
    # 1. Kiểm tra xem user có PIN để xóa không
    if not current_user.pin_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No PIN has been set for this account."
        )

    # 2. Xác thực mã PIN người dùng nhập
    if not verify_password(pin_data.pin_code, current_user.pin_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect PIN."
        )

    # 3. Nếu PIN đúng, tiến hành xóa PIN và các dữ liệu liên quan
    current_user.pin_code = None
    current_user.pin_code_question = None
    current_user.pin_recovery_code_hash = None
    current_user.pin_recovery_code_used = False
    current_user.use_pin_for_all_actions = False
    
    current_user.updated_at = datetime.now(pytz.UTC)

    await db.commit()   
    return {"message": "PIN has been successfully removed."}

# Sửa response_model
@router.put("/review", response_model=UserReviewResponse, summary="Create or update user review")
async def create_or_update_user_review(
    review_data: ReviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    review = await db.get(UserReview, current_user.id)
    if review:
        review.rating_points = review_data.rating_points
        review.comment = review_data.comment
    else:
        review = UserReview(user_id=current_user.id, rating_points=review_data.rating_points, comment=review_data.comment)
        db.add(review)
    await db.commit()
    await db.refresh(review)
    return review

# Sửa response_model
@router.get("/review", response_model=Optional[UserReviewResponse], summary="Get the current user's review")
async def get_user_review(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    return await db.get(UserReview, current_user.id)

@router.get("/access-history", response_model=List[LoginHistoryResponse], summary="Get user's recent login history")
async def get_access_history(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    stmt = (select(LoginHistory).where(LoginHistory.user_id == current_user.id).order_by(LoginHistory.login_time.desc()).limit(10))
    result = await db.execute(stmt)
    return result.scalars().all()

# --- START: SMTP SETTINGS ENDPOINTS ---

@router.get("/smtp-settings", response_model=UserSmtpSettingsResponse, summary="Get user's custom SMTP settings")
async def get_smtp_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieve the current user's saved SMTP settings.
    """
    stmt = select(UserSmtpSettings).where(UserSmtpSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    smtp_settings = result.scalars().first()
    
    if not smtp_settings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SMTP settings not found.")
    
    return smtp_settings

@router.put("/smtp-settings", response_model=SmtpTestResponse, summary="Create or Update user's SMTP settings")
async def update_smtp_settings(
    settings_data: UserSmtpSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Create or update the user's SMTP settings.
    It performs a connection test before saving the credentials.
    """
    success, message = await test_smtp_connection(
        server=settings_data.smtp_server,
        port=settings_data.smtp_port,
        username=settings_data.smtp_sender_email,
        password=settings_data.smtp_password
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        
    encrypted_password = encrypt_data(settings_data.smtp_password)
    
    stmt = select(UserSmtpSettings).where(UserSmtpSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    db_settings = result.scalars().first()
    
    if db_settings:
        db_settings.smtp_server = settings_data.smtp_server
        db_settings.smtp_port = settings_data.smtp_port
        db_settings.smtp_sender_email = settings_data.smtp_sender_email
        db_settings.smtp_password_encrypted = encrypted_password
        db_settings.is_active = True
        db_settings.last_test_successful = True
    else:
        db_settings = UserSmtpSettings(
            user_id=current_user.id,
            smtp_server=settings_data.smtp_server,
            smtp_port=settings_data.smtp_port,
            smtp_sender_email=settings_data.smtp_sender_email,
            smtp_password_encrypted=encrypted_password,
            is_active=True,
            last_test_successful=True
        )
        db.add(db_settings)
        
    await db.commit()
    
    return SmtpTestResponse(success=True, message="SMTP settings saved and connection successful!")


@router.delete("/smtp-settings", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user's SMTP settings")
async def delete_smtp_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Delete the current user's SMTP settings.
    """
    stmt = select(UserSmtpSettings).where(UserSmtpSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    db_settings = result.scalars().first()
    
    if db_settings:
        await db.delete(db_settings)
        await db.commit()
        
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- END: SMTP SETTINGS ENDPOINTS ---