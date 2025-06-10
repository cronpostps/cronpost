# backend/app/routers/user_actions_router.py
# Version: 1.5
# Changelog:
# - Refactored PIN lockout logic to use values from the database (system_settings)
#   instead of hard-coded values.

import logging
from typing import Optional
from datetime import datetime, timedelta, timezone as dt_timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..db.database import get_db_session
from ..db.models import User, CheckinLog, SystemSetting, UserAccountStatusEnum, CheckinMethodEnum
from ..core.security import get_current_active_user
from ..services.schedule_service import calculate_next_clc_prompt_at
from ..routers.auth_router import verify_password

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["User Actions"],
    dependencies=[Depends(get_current_active_user)]
)

class CheckInRequest(BaseModel):
    pin_code: Optional[constr(min_length=4, max_length=4, pattern=r"^\d{4}$")] = None

class ActionResponse(BaseModel):
    message: str
    account_status: UserAccountStatusEnum
    next_clc_prompt_at: Optional[datetime]
    wct_active_ends_at: Optional[datetime]

class StopFnsRequest(BaseModel):
    pin_code: constr(min_length=4, max_length=4, pattern=r"^\d{4}$")

async def get_pin_lockout_settings(db: AsyncSession) -> (int, int):
    """Helper to fetch PIN lockout settings from the database."""
    keys = ["failed_pin_attempts_lockout_threshold", "pin_lockout_duration_minutes"]
    stmt = select(SystemSetting).where(SystemSetting.setting_key.in_(keys))
    result = await db.execute(stmt)
    settings = {s.setting_key: s.setting_value for s in result.scalars().all()}
    
    threshold = int(settings.get("failed_pin_attempts_lockout_threshold", 5))
    duration = int(settings.get("pin_lockout_duration_minutes", 15))
    
    return threshold, duration

@router.post("/check-in", response_model=ActionResponse, summary="User check-in action")
async def user_check_in(
    request_data: CheckInRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} attempting check-in.")

    if current_user.account_status != UserAccountStatusEnum.ANS_WCT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Check-in is only allowed during WCT (Waiting Check-in Time).")

    if current_user.use_pin_for_all_actions:
        if not request_data.pin_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PIN code is required for check-in.")
        
        lockout_threshold, lockout_duration = await get_pin_lockout_settings(db)

        if current_user.account_locked_until and current_user.account_locked_until > datetime.now(dt_timezone.utc):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Account is locked. Please try again after {current_user.account_locked_until.strftime('%Y-%m-%d %H:%M:%S %Z')}.")

        if not current_user.pin_code or not verify_password(request_data.pin_code, current_user.pin_code):
            current_user.failed_pin_attempts += 1
            if current_user.failed_pin_attempts >= lockout_threshold:
                current_user.account_locked_until = datetime.now(dt_timezone.utc) + timedelta(minutes=lockout_duration)
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN code.")
        else:
            current_user.failed_pin_attempts = 0
            current_user.account_locked_until = None

    now_utc = datetime.now(dt_timezone.utc)
    current_user.last_successful_checkin_at = now_utc
    current_user.last_activity_at = now_utc
    current_user.account_status = UserAccountStatusEnum.ANS_CLC
    
    user_config = current_user.configuration
    if user_config:
        user_config.wct_active_ends_at = None
        user_config.next_clc_prompt_at = await calculate_next_clc_prompt_at(user_config, current_user.timezone, now_utc, db)

    db.add(CheckinLog(user_id=current_user.id, method=CheckinMethodEnum.manual_button))
    
    await db.commit()
    await db.refresh(current_user)
    if user_config: await db.refresh(user_config)

    return ActionResponse(
        message="Check-in successful.",
        account_status=current_user.account_status,
        next_clc_prompt_at=user_config.next_clc_prompt_at if user_config else None,
        wct_active_ends_at=None
    )

@router.post("/stop-fns", response_model=ActionResponse, summary="User stops Frozen and Send (FNS) state")
async def user_stop_fns(
    request_data: StopFnsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} attempting to stop FNS.")

    if current_user.account_status != UserAccountStatusEnum.FNS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not in FNS (Frozen and Send) state.")

    if not current_user.pin_code:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN configuration error for user. Cannot stop FNS.")

    lockout_threshold, lockout_duration = await get_pin_lockout_settings(db)
    
    if current_user.account_locked_until and current_user.account_locked_until > datetime.now(dt_timezone.utc):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Account is locked. Please try again after {current_user.account_locked_until.strftime('%Y-%m-%d %H:%M:%S %Z')}.")

    if not verify_password(request_data.pin_code, current_user.pin_code):
        current_user.failed_pin_attempts += 1
        if current_user.failed_pin_attempts >= lockout_threshold:
            current_user.account_locked_until = datetime.now(dt_timezone.utc) + timedelta(minutes=lockout_duration)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN code.")
    
    current_user.failed_pin_attempts = 0
    current_user.account_locked_until = None
    current_user.last_activity_at = datetime.now(dt_timezone.utc)
    current_user.account_status = UserAccountStatusEnum.ANS_CLC
    
    # Invalidate stop token
    current_user.is_fns_stop_token_used = True

    user_config = current_user.configuration
    if user_config:
        user_config.wct_active_ends_at = None
        user_config.next_clc_prompt_at = await calculate_next_clc_prompt_at(user_config, current_user.timezone, datetime.now(dt_timezone.utc), db)

    # TODO: Add logic to cancel any pending messages in the sending queue for this user.
    logger.warning(f"FNS stopped for user {current_user.email}. Pending FNS messages status not yet handled automatically.")

    await db.commit()
    await db.refresh(current_user)
    if user_config: await db.refresh(user_config)
    
    return ActionResponse(
        message="FNS state has been successfully stopped. Account is now active.",
        account_status=current_user.account_status,
        next_clc_prompt_at=user_config.next_clc_prompt_at if user_config else None,
        wct_active_ends_at=None
    )