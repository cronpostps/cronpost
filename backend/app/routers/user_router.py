# backend/app/routers/user_router.py
# Version: 1.5
# Changelog:
# - Added trust_verifier_email and checkin_on_signin to UserProfileResponse model and endpoint.

import logging
import uuid
from typing import Optional, List, Dict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..db.database import get_db_session
from ..db.models import (
    User,
    UserConfiguration,
    SystemSetting,
    Message,
    FmSchedule,
    MessageOverallStatusEnum,
    UserAccountStatusEnum,
    UserMembershipTypeEnum,
    RatingPointsEnum
)
from ..core.security import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["Users"],
    dependencies=[Depends(get_current_active_user)]
)


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
    
    class Config:
        from_attributes = True

async def get_system_settings(db_session: AsyncSession, keys: List[str]) -> Dict[str, Optional[str]]:
    stmt = select(SystemSetting).where(SystemSetting.setting_key.in_(keys))
    result = await db_session.execute(stmt)
    settings_map = {s.setting_key: s.setting_value for s in result.scalars().all()}
    return {key: settings_map.get(key) for key in keys}


@router.get("/me", response_model=UserProfileResponse, summary="Get current user profile")
async def read_users_me(
    current_user: User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Fetching profile for user: {current_user.email}")

    user_config: Optional[UserConfiguration] = current_user.configuration

    next_clc = user_config.next_clc_prompt_at if user_config else None
    wct_ends = user_config.wct_active_ends_at if user_config else None

    setting_keys_needed = [
        "max_total_messages_free",
        "max_total_messages_premium",
        "max_total_upload_storage_gb_premium"
    ]
    settings = await get_system_settings(db_session, setting_keys_needed)

    max_messages_allowed = 0
    storage_limit_gb_for_user = 0

    try:
        if current_user.membership_type == UserMembershipTypeEnum.premium:
            max_messages_allowed = int(settings.get("max_total_messages_premium", "1000"))
            storage_limit_gb_for_user = int(settings.get("max_total_upload_storage_gb_premium", "1"))
        else:
            max_messages_allowed = int(settings.get("max_total_messages_free", "10"))
            storage_limit_gb_for_user = 0
    except (ValueError, TypeError):
        logger.error(f"Could not parse system settings for limits for user {current_user.email}. Using hardcoded defaults.")
        if current_user.membership_type == UserMembershipTypeEnum.premium:
            max_messages_allowed = 1000
            storage_limit_gb_for_user = 1
        else:
            max_messages_allowed = 10
            storage_limit_gb_for_user = 0
            
    active_messages_stmt = (
        select(func.count(Message.id))
        .outerjoin(FmSchedule, Message.id == FmSchedule.message_id)
        .where(
            Message.user_id == current_user.id,
            or_(
                Message.overall_send_status.in_([MessageOverallStatusEnum.pending, MessageOverallStatusEnum.processing]),
                FmSchedule.repeat_number > 0
            )
        )
    )

    active_messages_count_result = await db_session.execute(active_messages_stmt)
    active_messages_count = active_messages_count_result.scalar_one_or_none() or 0
    
    messages_remaining_val = max_messages_allowed - active_messages_count

    user_rating = None
    if hasattr(current_user, 'review') and current_user.review:
        user_rating = current_user.review.rating_points

    response_data = {
        "id": current_user.id,
        "email": current_user.email,
        "user_name": current_user.user_name,
        "provider": current_user.provider,
        "is_confirmed_by_email": current_user.is_confirmed_by_email,
        "is_admin": current_user.is_admin,
        "account_status": current_user.account_status,
        "membership_type": current_user.membership_type,
        "timezone": current_user.timezone,
        "language": current_user.language,
        "next_clc_prompt_at": next_clc,
        "wct_active_ends_at": wct_ends,
        "uploaded_storage_bytes": current_user.uploaded_storage_bytes,
        "messages_remaining": messages_remaining_val,
        "storage_limit_gb": storage_limit_gb_for_user,
        "use_pin_for_all_actions": current_user.use_pin_for_all_actions,
        "checkin_on_signin": current_user.checkin_on_signin,
        "trust_verifier_email": current_user.trust_verifier_email,
        "pin_code_question": current_user.pin_code_question,
        "rating_points": user_rating,
        "has_pin": True if current_user.pin_code else False
    }
    
    return UserProfileResponse(**response_data)