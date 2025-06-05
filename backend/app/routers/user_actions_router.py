# backend/app/routers/user_actions_router.py
# Version: 1.4 (Added /stop-fns endpoint)

import logging
from typing import Optional
from datetime import datetime, timedelta, timezone as dt_timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, constr
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt

from ..db.database import get_db_session
from ..db.models import User, UserConfiguration, CheckinLog, UserAccountStatusEnum, CheckinMethodEnum, Message, MessageOverallStatusEnum # Thêm Message và MessageOverallStatusEnum
from ..core.security import get_current_active_user
from ..services.schedule_service import calculate_next_clc_prompt_at

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["User Actions"],
    dependencies=[Depends(get_current_active_user)]
)

try:
    from .auth_router import verify_password
except ImportError:
    logger.warning("Could not import verify_password from auth_router. Using fallback bcrypt implementation.")
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        if not plain_password or not hashed_password: return False
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except ValueError:
            logger.error(f"ValueError during bcrypt.checkpw, possibly invalid hash format: {hashed_password[:10]}...")
            return False

class CheckInRequest(BaseModel):
    pin_code: Optional[constr(min_length=4, max_length=4, pattern=r"^\d{4}$")] = None

class CheckInResponse(BaseModel): # Có thể dùng chung response model hoặc tạo riêng
    message: str
    account_status: UserAccountStatusEnum
    next_clc_prompt_at: Optional[datetime]
    wct_active_ends_at: Optional[datetime]

class StopFnsRequest(BaseModel):
    pin_code: constr(min_length=4, max_length=4, pattern=r"^\d{4}$") # PIN là bắt buộc

# Sử dụng lại CheckInResponse cho StopFnsResponse vì các trường cần trả về tương tự
StopFnsResponse = CheckInResponse


@router.post("/check-in", response_model=CheckInResponse, summary="User check-in action")
async def user_check_in(
    request_data: CheckInRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    # ... (Nội dung hàm user_check_in như ở version 1.3, không thay đổi)
    logger.info(f"User {current_user.email} attempting check-in.")

    if current_user.account_status != UserAccountStatusEnum.ANS_WCT:
        logger.warning(f"User {current_user.email} attempted check-in in invalid state: {current_user.account_status}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Check-in is not allowed in the current account state ({current_user.account_status}). Check-in is only allowed during WCT (Waiting Check-in Time)."
        )

    if current_user.use_pin_for_all_actions:
        if not request_data.pin_code:
            logger.warning(f"User {current_user.email} requires PIN for check-in, but no PIN provided.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PIN code is required for check-in as per your account settings."
            )
        
        if current_user.account_locked_until and current_user.account_locked_until > datetime.now(dt_timezone.utc):
            logger.warning(f"User {current_user.email} account is locked. Lock expires at {current_user.account_locked_until}.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account is locked due to too many failed PIN attempts. Please try again after {current_user.account_locked_until.strftime('%Y-%m-%d %H:%M:%S %Z')}."
            )

        if not current_user.pin_code:
            logger.error(f"User {current_user.email} requires PIN, but no PIN hash found in database.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN configuration error for user.")

        if not verify_password(request_data.pin_code, current_user.pin_code):
            current_user.failed_pin_attempts += 1
            lockout_threshold = 5 
            lockout_duration_minutes = 15
            
            if current_user.failed_pin_attempts >= lockout_threshold:
                current_user.account_locked_until = datetime.now(dt_timezone.utc) + timedelta(minutes=lockout_duration_minutes)
                current_user.account_locked_reason = "Too many failed PIN attempts during check-in."
                logger.warning(f"User {current_user.email} account locked until {current_user.account_locked_until} due to PIN failure.")
            
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN code.")
        else:
            current_user.failed_pin_attempts = 0
            current_user.account_locked_until = None
            current_user.account_locked_reason = None

    now_utc = datetime.now(dt_timezone.utc)
    current_user.last_successful_checkin_at = now_utc
    current_user.last_activity_at = now_utc
    current_user.account_status = UserAccountStatusEnum.ANS_CLC
    
    user_config = current_user.configuration
    if not user_config:
        logger.error(f"UserConfiguration not found for user {current_user.email} during check-in.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User configuration missing.")

    user_config.wct_active_ends_at = None
    
    try:
        user_config.next_clc_prompt_at = await calculate_next_clc_prompt_at(
            user_config, 
            current_user.timezone, 
            now_utc, 
            db
        )
    except Exception as e:
        logger.error(f"Error calculating next CLC prompt for user {current_user.email}: {e}", exc_info=True)
        user_config.next_clc_prompt_at = None 

    checkin_entry = CheckinLog(
        user_id=current_user.id,
        checkin_timestamp=now_utc,
        method=CheckinMethodEnum.manual_button
    )
    db.add(checkin_entry)

    try:
        await db.commit()
        await db.refresh(current_user)
        if user_config:
            await db.refresh(user_config) 
        logger.info(f"User {current_user.email} checked in successfully. Next CLC: {user_config.next_clc_prompt_at if user_config else 'N/A'}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error during check-in for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not process check-in due to a server error.")

    return CheckInResponse(
        message="Check-in successful.",
        account_status=current_user.account_status,
        next_clc_prompt_at=user_config.next_clc_prompt_at if user_config else None,
        wct_active_ends_at=user_config.wct_active_ends_at if user_config else None
    )


@router.post("/stop-fns", response_model=StopFnsResponse, summary="User stops Frozen and Send (FNS) state")
async def user_stop_fns(
    request_data: StopFnsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} attempting to stop FNS.")

    # 1. Kiểm tra trạng thái tài khoản
    if current_user.account_status != UserAccountStatusEnum.FNS:
        logger.warning(f"User {current_user.email} attempted to stop FNS but not in FNS state. Current state: {current_user.account_status}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is not in FNS (Frozen and Send) state."
        )

    # 2. Xác thực PIN (bắt buộc cho hành động này)
    if not current_user.pin_code:
        logger.error(f"User {current_user.email} attempting to stop FNS, but no PIN hash found in database. This is a configuration issue.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN configuration error for user. Cannot stop FNS.")

    if current_user.account_locked_until and current_user.account_locked_until > datetime.now(dt_timezone.utc):
        logger.warning(f"User {current_user.email} account is locked. Cannot stop FNS. Lock expires at {current_user.account_locked_until}.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is locked due to too many failed PIN attempts. Please try again after {current_user.account_locked_until.strftime('%Y-%m-%d %H:%M:%S %Z')}."
        )

    if not verify_password(request_data.pin_code, current_user.pin_code):
        current_user.failed_pin_attempts += 1
        lockout_threshold = 5 # Nên lấy từ SystemSettings
        lockout_duration_minutes = 15 # Nên lấy từ SystemSettings
        
        if current_user.failed_pin_attempts >= lockout_threshold:
            current_user.account_locked_until = datetime.now(dt_timezone.utc) + timedelta(minutes=lockout_duration_minutes)
            current_user.account_locked_reason = "Too many failed PIN attempts trying to stop FNS."
            logger.warning(f"User {current_user.email} account locked until {current_user.account_locked_until} due to PIN failure on FNS stop.")
        
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN code.")
    else:
        current_user.failed_pin_attempts = 0
        current_user.account_locked_until = None
        current_user.account_locked_reason = None

    # 3. Cập nhật thông tin người dùng và cấu hình
    now_utc = datetime.now(dt_timezone.utc)
    current_user.last_activity_at = now_utc
    current_user.account_status = UserAccountStatusEnum.ANS_CLC # Chuyển về ANS_CLC

    # Vô hiệu hóa FNS stop token (nếu có)
    current_user.is_fns_stop_token_used = True
    current_user.fns_stop_token_hash = None
    current_user.fns_stop_token_generated_at = None
    current_user.fns_stop_token_expires_at = None
    
    user_config = current_user.configuration
    if not user_config:
        logger.error(f"UserConfiguration not found for user {current_user.email} during FNS stop.")
        # Vẫn cho phép dừng FNS, nhưng không thể tính CLC mới. Có thể đặt user về INS.
        # Hoặc tạo UserConfiguration mặc định. Tạm thời, nếu không có config, vẫn chuyển về ANS_CLC
        # nhưng next_clc_prompt_at sẽ là None.
        pass # Để next_clc_prompt_at là None nếu không có config

    if user_config:
        user_config.wct_active_ends_at = None # Xóa WCT
        user_config.is_clc_enabled = True     # Kích hoạt lại CLC (nếu user có IM)
        try:
            user_config.next_clc_prompt_at = await calculate_next_clc_prompt_at(
                user_config, 
                current_user.timezone, 
                now_utc, 
                db
            )
        except Exception as e:
            logger.error(f"Error calculating next CLC prompt for user {current_user.email} after stopping FNS: {e}", exc_info=True)
            user_config.next_clc_prompt_at = None
    
    # TODO: Xử lý các tin nhắn đang trong hàng đợi FNS (ví dụ: đánh dấu là cancelled)
    # Ví dụ:
    # await db.execute(
    #     update(Message)
    #     .where(Message.user_id == current_user.id)
    #     .where(Message.overall_send_status.in_([MessageOverallStatusEnum.pending, MessageOverallStatusEnum.processing])) # Chỉ những tin đang chờ gửi do FNS
    #     .values(overall_send_status=MessageOverallStatusEnum.cancelled, updated_at=now_utc) # Hoặc một trạng thái "stopped_by_user"
    # )
    logger.warning(f"FNS stopped for user {current_user.email}. Pending FNS messages status not yet handled automatically.")


    try:
        await db.commit()
        await db.refresh(current_user)
        if user_config:
            await db.refresh(user_config)
        logger.info(f"User {current_user.email} stopped FNS successfully. New status: ANS_CLC. Next CLC: {user_config.next_clc_prompt_at if user_config else 'N/A'}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error during FNS stop for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not process FNS stop due to a server error.")

    return StopFnsResponse(
        message="FNS (Frozen and Send) state has been successfully stopped. Account is now active.",
        account_status=current_user.account_status,
        next_clc_prompt_at=user_config.next_clc_prompt_at if user_config else None,
        wct_active_ends_at=user_config.wct_active_ends_at if user_config else None # Sẽ là None
    )