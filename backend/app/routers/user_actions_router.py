# backend/app/routers/user_actions_router.py
# Version: 1.6
# Changelog:
# - Refactored all PIN verification to use the centralized verify_user_pin_with_lockout service.

import logging
from typing import Optional, Dict
from datetime import datetime, timezone as dt_timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..db.database import get_db_session
from ..db.models import User, CheckinLog, SystemSetting, UserAccountStatusEnum, CheckinMethodEnum
# Import service và dependency cần thiết
from ..core.security import get_current_active_user, verify_user_pin_with_lockout
from ..dependencies import get_system_settings_dep
from ..services.schedule_service import calculate_next_clc_prompt_at

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

# Bỏ hàm get_pin_lockout_settings vì đã có dịch vụ tập trung

@router.post("/check-in", response_model=ActionResponse, summary="User check-in action")
async def user_check_in(
    request_data: CheckInRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
    settings: Dict[str, str] = Depends(get_system_settings_dep) # Thêm dependency
):
    logger.info(f"User {current_user.email} attempting check-in.")

    if current_user.account_status != UserAccountStatusEnum.ANS_WCT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Check-in is only allowed during WCT (Waiting Check-in Time).")

    # === LOGIC KIỂM TRA PIN ĐÃ ĐƯỢC CHUẨN HÓA ===
    if current_user.use_pin_for_all_actions:
        if not request_data.pin_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PIN code is required for check-in.")
        
        # Gọi dịch vụ tập trung
        await verify_user_pin_with_lockout(db, current_user, request_data.pin_code, settings)
    # ============================================

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
    db: AsyncSession = Depends(get_db_session),
    settings: Dict[str, str] = Depends(get_system_settings_dep) # Thêm dependency
):
    logger.info(f"User {current_user.email} attempting to stop FNS.")

    if current_user.account_status != UserAccountStatusEnum.FNS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not in FNS (Frozen and Send) state.")

    if not current_user.pin_code:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN configuration error for user. Cannot stop FNS.")

    # === LOGIC KIỂM TRA PIN ĐÃ ĐƯỢC CHUẨN HÓA ===
    await verify_user_pin_with_lockout(db, current_user, request_data.pin_code, settings)
    # ============================================
    
    now_utc = datetime.now(dt_timezone.utc)
    current_user.last_activity_at = now_utc
    current_user.account_status = UserAccountStatusEnum.ANS_CLC
    
    # Invalidate stop token
    current_user.is_fns_stop_token_used = True

    user_config = current_user.configuration
    if user_config:
        user_config.wct_active_ends_at = None
        user_config.next_clc_prompt_at = await calculate_next_clc_prompt_at(user_config, current_user.timezone, now_utc, db)

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