# backend/app/routers/user_router.py
# Version 3.3
# - Fixed ImportError by importing password helpers from auth_router instead of security.

import logging
import uuid
import secrets
import pytz
from typing import Optional, List, Dict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from pydantic import BaseModel, EmailStr, Field, constr
from pydantic.networks import IPvAnyAddress
from sqlalchemy import func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

# Local imports
from ..db.database import get_db_session
from ..db.models import (
    User, UserConfiguration, SystemSetting, Message, FmSchedule,
    MessageOverallStatusEnum, UserAccountStatusEnum, UserMembershipTypeEnum,
    RatingPointsEnum, EmailCheckinSettings, LoginHistory, UserReview,
    UserSmtpSettings, PinAttempt
)
# === SỬA LỖI IMPORT ===
from ..core.security import (
    get_current_active_user, encrypt_data, verify_user_pin_with_lockout
)
# Import các hàm xử lý password từ đúng vị trí
from ..routers.auth_router import verify_password, hash_password
# ======================
from ..dependencies import get_system_settings_dep
from ..services.email_service import send_email_async, test_smtp_connection

# Configure logging
logger = logging.getLogger(__name__)

# Router configuration
router = APIRouter(
    tags=["Users"],
    dependencies=[Depends(get_current_active_user)]
)

# --- Pydantic Models ---
# Base Response Models
class MessageResponse(BaseModel):
    message: str

class SmtpTestResponse(BaseModel):
    success: bool
    message: str

# User Profile Related Models
class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    user_name: Optional[str] = None
    provider: Optional[str] = None
    is_confirmed_by_email: bool
    is_admin: bool
    account_status: UserAccountStatusEnum
    membership_type: UserMembershipTypeEnum
    timezone: Optional[str] = None
    language: Optional[str] = None
    next_clc_prompt_at: Optional[datetime] = None
    wct_active_ends_at: Optional[datetime] = None
    uploaded_storage_bytes: int
    messages_remaining: Optional[int] = None
    storage_limit_gb: Optional[int] = None
    use_pin_for_all_actions: bool
    checkin_on_signin: bool
    trust_verifier_email: Optional[str] = None
    pin_code_question: Optional[str] = None
    rating_points: Optional[RatingPointsEnum] = None
    has_pin: bool
    use_checkin_token_email: bool
    send_additional_reminder: bool
    additional_reminder_minutes: Optional[int] = None
    max_message_chars_free: int
    max_message_chars_premium: int
    class Config:
        from_attributes = True

class LoginHistoryResponse(BaseModel):
    login_time: datetime
    ip_address: Optional[IPvAnyAddress] = None  # Updated to use IPvAnyAddress
    user_agent: Optional[str] = None
    device_os: Optional[str] = None
    class Config:
        from_attributes = True

class ProfileUpdateRequest(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=50)
    timezone: str
    trust_verifier_email: Optional[EmailStr] = None

# Security Related Models
class SecurityOptionsUpdateRequest(BaseModel):
    use_pin_for_all_actions: bool
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

# Review Related Models
class ReviewRequest(BaseModel):
    rating_points: RatingPointsEnum
    comment: Optional[str] = Field(None, max_length=300)

class UserReviewResponse(BaseModel):
    user_id: uuid.UUID
    rating_points: RatingPointsEnum
    comment: Optional[str] = None
    updated_at: datetime
    class Config:
        from_attributes = True

# SMTP Settings Related Models
class UserSmtpSettingsUpdate(BaseModel):
    smtp_server: str
    smtp_port: int
    smtp_sender_email: EmailStr
    smtp_password: str

class UserSmtpSettingsResponse(BaseModel):
    smtp_server: str
    smtp_port: int
    smtp_sender_email: EmailStr
    is_active: bool
    class Config:
        from_attributes = True

# Check-in Settings Related Models
class CheckinSettingsUpdate(BaseModel):
    checkin_on_signin: bool
    use_checkin_token_email: bool
    send_additional_reminder: bool
    additional_reminder_minutes: Optional[int] = Field(None, ge=1, le=1440)

class CheckinSettingsResponse(BaseModel):
    checkin_on_signin: bool
    use_checkin_token_email: bool
    send_additional_reminder: bool
    additional_reminder_minutes: Optional[int] = None
    class Config:
        from_attributes = True

# --- Helper Functions ---
async def get_system_settings(db_session: AsyncSession, keys: List[str]) -> Dict[str, Optional[str]]:
    stmt = select(SystemSetting).where(SystemSetting.setting_key.in_(keys))
    result = await db_session.execute(stmt)
    settings_map = {s.setting_key: s.setting_value for s in result.scalars().all()}
    return {key: settings_map.get(key) for key in keys}

# --- API Endpoints ---
# Profile Management
@router.get("/me", response_model=UserProfileResponse, summary="Get current user profile")
async def read_users_me(
    current_user: User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(get_db_session)
):
    # Function content is correct, no changes needed
    logger.info(f"Fetching profile for user: {current_user.email}")
    user = (await db_session.execute(
        select(User).where(User.id == current_user.id)
        .options(selectinload(User.configuration), selectinload(User.review), selectinload(User.email_checkin_settings))
    )).scalars().first()
    user_config: Optional[UserConfiguration] = user.configuration
    checkin_settings: Optional[EmailCheckinSettings] = user.email_checkin_settings
    setting_keys_needed = [
    "max_total_messages_free", "max_total_messages_premium", "max_total_upload_storage_gb_premium",
    "max_message_content_length_free", "max_message_content_length_premium"
    ]
    settings = await get_system_settings(db_session, setting_keys_needed)
    try:
        if user.membership_type == UserMembershipTypeEnum.premium:
            max_messages_allowed = int(settings.get("max_total_messages_premium", "1000"))
            storage_limit_gb_for_user = int(settings.get("max_total_upload_storage_gb_premium", "1"))
        else:
            max_messages_allowed = int(settings.get("max_total_messages_free", "10"))
            storage_limit_gb_for_user = 0
    except (ValueError, TypeError):
        max_messages_allowed = 10; storage_limit_gb_for_user = 0
    active_messages_stmt = (select(func.count(Message.id)).outerjoin(FmSchedule).where(Message.user_id == user.id, or_(Message.overall_send_status.in_([MessageOverallStatusEnum.pending, MessageOverallStatusEnum.processing]), FmSchedule.repeat_number > 0)))
    active_messages_count = (await db_session.execute(active_messages_stmt)).scalar_one_or_none() or 0
    response_data = {
        "id": user.id, "email": user.email, "user_name": user.user_name, "provider": user.provider,
        "is_confirmed_by_email": user.is_confirmed_by_email, "is_admin": user.is_admin,
        "account_status": user.account_status, "membership_type": user.membership_type,
        "timezone": user.timezone, "language": user.language,
        "next_clc_prompt_at": user_config.next_clc_prompt_at if user_config else None,
        "wct_active_ends_at": user_config.wct_active_ends_at if user_config else None,
        "uploaded_storage_bytes": user.uploaded_storage_bytes,
        "messages_remaining": max_messages_allowed - active_messages_count,
        "storage_limit_gb": storage_limit_gb_for_user,
        "use_pin_for_all_actions": user.use_pin_for_all_actions,
        "checkin_on_signin": user.checkin_on_signin,
        "trust_verifier_email": user.trust_verifier_email,
        "pin_code_question": user.pin_code_question,
        "rating_points": user.review.rating_points if user.review else None,
        "has_pin": True if user.pin_code else False,
        "use_checkin_token_email": checkin_settings.use_checkin_token_email if checkin_settings else False,
        "send_additional_reminder": checkin_settings.send_additional_reminder if checkin_settings else False,
        "additional_reminder_minutes": checkin_settings.additional_reminder_minutes if checkin_settings else 5,
        "max_message_chars_free": int(settings.get('max_message_content_length_free', 5000)),
        "max_message_chars_premium": int(settings.get('max_message_content_length_premium', 50000))
    }
    return UserProfileResponse(**response_data)


@router.get("/access-history", response_model=List[LoginHistoryResponse], summary="Get user's recent login history")
async def get_access_history(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    # Function content is correct, no changes needed
    stmt = (
        select(LoginHistory)
        .where(LoginHistory.user_id == current_user.id)
        .order_by(LoginHistory.login_time.desc())
        .limit(10)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.put("/profile", response_model=MessageResponse, summary="Update user profile")
async def update_user_profile(
    profile_data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    if profile_data.timezone not in pytz.all_timezones:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {profile_data.timezone}"
        )
    
    current_user.user_name = profile_data.user_name
    current_user.timezone = profile_data.timezone
    current_user.trust_verifier_email = profile_data.trust_verifier_email
    await db.commit()
    return {"message": "Profile updated successfully"}


@router.put("/security-options", response_model=MessageResponse, summary="Update security options")
async def update_security_options(
    options_data: SecurityOptionsUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
    settings: Dict[str, str] = Depends(get_system_settings_dep)
):
    """
    FIXED: Restored PIN verification logic to prevent security vulnerability.
    """
    if options_data.use_pin_for_all_actions and not current_user.pin_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must create a PIN before enabling 'Require PIN for all actions'."
        )
    
    # Logic xác thực PIN được phục hồi tại đây
    if current_user.pin_code:
        if not options_data.pin_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your current PIN is required to change this security setting."
            )
        await verify_user_pin_with_lockout(db, current_user, options_data.pin_code, settings)

    current_user.use_pin_for_all_actions = options_data.use_pin_for_all_actions
    await db.commit()
    return {"message": "Security options updated successfully."}


@router.put("/change-password", response_model=MessageResponse, summary="Change user password")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    if not current_user.password_hash or not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect current password."
        )
    
    current_user.password_hash = hash_password(password_data.new_password)
    await db.commit()
    return {"message": "Password updated successfully."}

@router.post("/verify-pin-session", response_model=MessageResponse)
async def verify_pin_for_session(
    pin_data: PinVerificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
    settings: Dict[str, str] = Depends(get_system_settings_dep)
):
    """Verify PIN for session-wide authorization"""
    if not current_user.pin_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="PIN is not set for this account."
        )
    await verify_user_pin_with_lockout(db, current_user, pin_data.pin_code, settings)
    return {"message": "PIN verified successfully for this session."}

@router.post("/change-pin", response_model=MessageResponse)
async def change_user_pin(
    pin_data: PinChangeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
    settings: Dict[str, str] = Depends(get_system_settings_dep)
):
    """Set or change user's PIN"""
    if current_user.pin_code:
        if not pin_data.current_pin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current PIN is required to change it."
            )
        await verify_user_pin_with_lockout(db, current_user, pin_data.current_pin, settings)
        message = "PIN updated successfully."
    else:
        raw_recovery_code = secrets.token_urlsafe(22)
        current_user.pin_recovery_code_hash = hash_password(raw_recovery_code)
        current_user.pin_recovery_code_used = False
        current_user.use_pin_for_all_actions = True
        message = "PIN set successfully. Recovery code sent to email."
        
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

    current_user.pin_code = hash_password(pin_data.new_pin)
    current_user.pin_code_question = pin_data.pin_question
    await db.commit()
    return MessageResponse(message=message)

@router.post("/recover-pin", response_model=MessageResponse)
async def recover_user_pin(
    recovery_data: PinRecoveryRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Recover PIN using a recovery code"""
    if not current_user.pin_recovery_code_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recovery code was generated for this account."
        )
    if current_user.pin_recovery_code_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recovery code has already been used."
        )
    if not verify_password(recovery_data.recovery_code, current_user.pin_recovery_code_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid recovery code."
        )
    
    current_user.pin_code = hash_password(recovery_data.new_pin)
    current_user.pin_recovery_code_used = True
    await db.commit()
    return {"message": "PIN successfully recovered and updated."}

@router.get("/smtp-settings", response_model=UserSmtpSettingsResponse)
async def get_smtp_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get user's custom SMTP settings"""
    stmt = select(UserSmtpSettings).where(UserSmtpSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    smtp_settings = result.scalars().first()
    if not smtp_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SMTP settings not found."
        )
    return smtp_settings

@router.put("/smtp-settings", response_model=SmtpTestResponse)
async def update_smtp_settings(
    settings_data: UserSmtpSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Create or Update user's SMTP settings"""
    success, message = await test_smtp_connection(
        server=settings_data.smtp_server,
        port=settings_data.smtp_port,
        username=settings_data.smtp_sender_email,
        password=settings_data.smtp_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

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

@router.delete("/smtp-settings", status_code=status.HTTP_204_NO_CONTENT)
async def delete_smtp_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete user's SMTP settings"""
    stmt = select(UserSmtpSettings).where(UserSmtpSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    db_settings = result.scalars().first()
    if db_settings:
        await db.delete(db_settings)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/checkin-settings", response_model=CheckinSettingsResponse)
async def get_checkin_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get user's check-in settings"""
    settings = (await db.execute(
        select(EmailCheckinSettings)
        .where(EmailCheckinSettings.user_id == current_user.id)
    )).scalars().first()
    
    if not settings:
        settings = EmailCheckinSettings(user_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return {
        "checkin_on_signin": current_user.checkin_on_signin,
        "use_checkin_token_email": settings.use_checkin_token_email,
        "send_additional_reminder": settings.send_additional_reminder,
        "additional_reminder_minutes": settings.additional_reminder_minutes
    }

@router.put("/checkin-settings", response_model=MessageResponse)
async def update_checkin_settings(
    update_data: CheckinSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Update user's check-in settings"""
    settings = (await db.execute(
        select(EmailCheckinSettings)
        .where(EmailCheckinSettings.user_id == current_user.id)
    )).scalars().first()
    
    if not settings:
        settings = EmailCheckinSettings(user_id=current_user.id)
        db.add(settings)
    
    current_user.checkin_on_signin = update_data.checkin_on_signin
    settings.use_checkin_token_email = update_data.use_checkin_token_email
    settings.send_additional_reminder = update_data.send_additional_reminder
    settings.additional_reminder_minutes = update_data.additional_reminder_minutes
    
    await db.commit()
    return {"message": "Check-in options updated successfully"}

@router.put("/review", response_model=UserReviewResponse)
async def create_or_update_user_review(
    review_data: ReviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Create or update user review"""
    review = await db.get(UserReview, current_user.id)
    if review:
        review.rating_points = review_data.rating_points
        review.comment = review_data.comment
    else:
        review = UserReview(
            user_id=current_user.id,
            rating_points=review_data.rating_points,
            comment=review_data.comment
        )
        db.add(review)
    
    await db.commit()
    await db.refresh(review)
    return review

@router.get("/review", response_model=Optional[UserReviewResponse])
async def get_user_review(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get the current user's review"""
    return await db.get(UserReview, current_user.id)

@router.delete("/review", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_review(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete user's review"""
    review = await db.get(UserReview, current_user.id)
    if review:
        await db.delete(review)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.delete("/pin", response_model=MessageResponse, summary="Remove user's PIN and related data")
async def remove_user_pin(
    pin_data: PinVerificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
    settings: Dict[str, str] = Depends(get_system_settings_dep)
):
    if not current_user.pin_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="No PIN has been set for this account."
        )
    
    # Verify PIN before allowing deletion
    await verify_user_pin_with_lockout(db, current_user, pin_data.pin_code, settings)

    # Reset all PIN and lockout related fields
    current_user.pin_code = None
    current_user.pin_code_question = None
    current_user.pin_recovery_code_hash = None
    current_user.pin_recovery_code_used = False
    current_user.use_pin_for_all_actions = False
    current_user.failed_pin_attempts = 0
    current_user.account_locked_until = None
    current_user.account_locked_reason = None
    
    # Delete all attempt history for this user
    delete_attempts_stmt = delete(PinAttempt).where(PinAttempt.user_id == current_user.id)
    await db.execute(delete_attempts_stmt)
    
    await db.commit()
    return {"message": "PIN has been successfully removed."}