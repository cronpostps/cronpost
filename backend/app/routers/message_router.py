# backend/app/routers/message_router.py
# Version: 1.4
# Changelog:
# - Integrated calculate_next_fm_send_at into FM creation and update.
# - Added helper _get_im_sent_at_utc to fetch Initial Message send time.
# - Ensured FmSchedule.next_send_at is populated.

import logging
import uuid
from typing import Optional, List, Any 
from datetime import datetime, timezone as dt_timezone, date as py_date, time as py_time 

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError, BaseModel, EmailStr, Field  # BaseModel was missing
from ..models.message_models import (
    InitialMessageCreateUpdateRequest,
    InitialMessageWithScheduleResponse,
    MessageResponseBase,
    UserConfigurationResponse,
    FollowMessageCreateRequest,
    FollowMessageResponse,
    FollowMessageUpdateRequest
)
from sqlalchemy import func, and_, or_, update, delete
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload, aliased # aliased đã có

from ..db.database import get_db_session
from ..db.models import (
    User, Message, FmSchedule, MessageOverallStatusEnum,
    UserConfiguration, UserAccountStatusEnum, SendingHistory, # Thêm SendingHistory
    CLCTypeEnum, DayOfWeekEnum, WTCDurationUnitEnum, FMScheduleTriggerTypeEnum,
    SendingAttemptStatusEnum # Thêm SendingAttemptStatusEnum
)
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.security import get_current_active_user
from ..services.schedule_service import calculate_next_clc_prompt_at, calculate_next_fm_send_at # Import calculate_next_fm_send_at

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["Messages"],
    dependencies=[Depends(get_current_active_user)]
)

# --- Helper Function ---
async def _get_im_sent_at_utc(user_id: uuid.UUID, db: AsyncSession) -> Optional[datetime]:
    """
    Fetches the actual send time (UTC) of the user's Initial Message.
    Returns None if IM doesn't exist or hasn't been successfully sent.
    """
    im_stmt = (
        select(Message.id)
        .where(Message.user_id == user_id)
        .where(Message.is_initial_message == True)
        .limit(1)
    )
    im_id_result = await db.execute(im_stmt)
    im_id = im_id_result.scalar_one_or_none()

    if not im_id:
        return None

    # Check SendingHistory for the IM
    # IM is typically sent once. If sent multiple times due to retry, get the first successful one.
    history_stmt = (
        select(SendingHistory.sent_at)
        .where(SendingHistory.message_id == im_id)
        .where(SendingHistory.status == SendingAttemptStatusEnum.success) # Chỉ lấy lần gửi thành công
        .order_by(SendingHistory.sent_at.asc()) # Lấy lần gửi thành công đầu tiên
        .limit(1)
    )
    history_result = await db.execute(history_stmt)
    im_sent_time = history_result.scalar_one_or_none()
    
    if im_sent_time and isinstance(im_sent_time, datetime):
        return im_sent_time.astimezone(dt_timezone.utc) if im_sent_time.tzinfo else pytz.utc.localize(im_sent_time)

    return None


class MessageOverviewResponse(BaseModel):
    im_status: str
    fm_active_count: int
    fm_inactive_count: int
    scm_active_count: int
    scm_inactive_count: int

@router.get("/overview", response_model=MessageOverviewResponse, summary="Get message overview statistics")
async def get_message_overview( # Giữ nguyên
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Fetching message overview for user: {current_user.email}")
    im_status_str = "Not Set"
    im_stmt = select(Message).where(
        Message.user_id == current_user.id,
        Message.is_initial_message == True
    )
    im_result = await db.execute(im_stmt)
    initial_message_db = im_result.scalars().first()

    if initial_message_db:
        if initial_message_db.overall_send_status in [MessageOverallStatusEnum.pending, MessageOverallStatusEnum.processing]:
            im_status_str = "Active"
        else:
            im_status_str = "Inactive"

    FmScheduleAlias = aliased(FmSchedule)
    active_fm_stmt = (
        select(func.count(Message.id))
        .join(FmScheduleAlias, Message.id == FmScheduleAlias.message_id)
        .where(
            Message.user_id == current_user.id,
            Message.is_initial_message == False,
            FmScheduleAlias.is_active == True,
            Message.overall_send_status.in_([MessageOverallStatusEnum.pending, MessageOverallStatusEnum.processing])
        )
    )
    active_fm_count_result = await db.execute(active_fm_stmt)
    fm_active_count_val = active_fm_count_result.scalar_one_or_none() or 0

    all_fm_stmt = (
        select(func.count(Message.id))
        .join(FmScheduleAlias, Message.id == FmScheduleAlias.message_id)
        .where(
            Message.user_id == current_user.id,
            Message.is_initial_message == False
        )
    )
    all_fm_count_result = await db.execute(all_fm_stmt)
    all_fm_count_val = all_fm_count_result.scalar_one_or_none() or 0
    fm_inactive_count_val = all_fm_count_val - fm_active_count_val

    scm_active_count_val = 0
    scm_inactive_count_val = 0

    return MessageOverviewResponse(
        im_status=im_status_str,
        fm_active_count=fm_active_count_val,
        fm_inactive_count=fm_inactive_count_val,
        scm_active_count=scm_active_count_val,
        scm_inactive_count=scm_inactive_count_val
    )

@router.put("/im", response_model=InitialMessageWithScheduleResponse, summary="Create or Update Initial Message and its Schedule")
async def create_or_update_initial_message( # Giữ nguyên
    im_data: InitialMessageCreateUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} attempting to create/update Initial Message.")
    schedule_data = im_data.schedule
    now_utc = datetime.now(dt_timezone.utc)

    if schedule_data.clc_type == CLCTypeEnum.specific_days:
        if not schedule_data.clc_day_number_interval or schedule_data.clc_day_number_interval < 2: 
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="For 'specific_days' CLC type, 'clc_day_number_interval' must be provided and be 2 or greater."
            )
    is_unloop_checkin = schedule_data.clc_type == CLCTypeEnum.specific_date_in_year
    if is_unloop_checkin:
        if not schedule_data.clc_specific_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="For 'specific_date_in_year' CLC type, 'clc_specific_date' must be provided."
            )
        try:
            user_tz = dt_timezone.utc
            if current_user.timezone:
                from pytz import timezone as pytz_timezone, exceptions as pytz_exceptions
                try: user_tz = pytz_timezone(current_user.timezone)
                except pytz_exceptions.UnknownTimeZoneError:
                    logger.warning(f"Unknown timezone '{current_user.timezone}'. Defaulting to UTC for WCT check.")
            
            if not isinstance(schedule_data.clc_specific_date, py_date) or not isinstance(schedule_data.clc_prompt_time, py_time):
                 raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid date or time format for schedule.")

            im_send_datetime_naive = datetime.combine(schedule_data.clc_specific_date, schedule_data.clc_prompt_time)
            try:
                im_send_datetime_user_tz = user_tz.localize(im_send_datetime_naive, is_dst=None)
            except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError) as e_tz:
                logger.warning(f"Timezone localization error for unloop IM schedule for user {current_user.email}: {e_tz}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"The chosen time ({schedule_data.clc_prompt_time.strftime('%H:%M')}) is invalid or ambiguous for the date {schedule_data.clc_specific_date.strftime('%Y-%m-%d')} in your timezone ({current_user.timezone}). Please choose a different time.")

            im_send_datetime_utc = im_send_datetime_user_tz.astimezone(dt_timezone.utc)
            wct_duration_minutes = schedule_data.wct_duration_value
            if schedule_data.wct_duration_unit == WTCDurationUnitEnum.hours: wct_duration_minutes *= 60
            wct_start_datetime_utc = im_send_datetime_utc - timedelta(minutes=wct_duration_minutes)

            if now_utc >= wct_start_datetime_utc: 
                 logger.warning(f"Unloop IM for user {current_user.email}: Submit time {now_utc} is within or after WCT_start {wct_start_datetime_utc}.")
                 raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="For a non-repeating schedule, the submit time cannot be within or after the calculated Waiting Check-in Time (WCT). Please choose a later schedule."
                 )
        except ValidationError as ve:
            logger.error(f"Pydantic validation error for unloop IM schedule for user {current_user.email}: {ve.errors()}", exc_info=False)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid schedule data: {ve.errors()}")
        except Exception as e:
            logger.error(f"Error validating unloop IM schedule for user {current_user.email}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid schedule for non-repeating message.")

    user_config = current_user.configuration
    if not user_config:
        logger.info(f"No UserConfiguration for {current_user.email}, creating.")
        user_config = UserConfiguration(user_id=current_user.id)
        db.add(user_config)
    
    user_config.clc_type = schedule_data.clc_type
    user_config.clc_prompt_time = schedule_data.clc_prompt_time
    user_config.clc_day_number_interval = schedule_data.clc_day_number_interval if schedule_data.clc_type == CLCTypeEnum.specific_days else None
    user_config.clc_day_of_week = schedule_data.clc_day_of_week if schedule_data.clc_type == CLCTypeEnum.day_of_week else None
    user_config.clc_date_of_month = schedule_data.clc_date_of_month if schedule_data.clc_type == CLCTypeEnum.date_of_month else None
    user_config.clc_date_of_year = schedule_data.clc_date_of_year if schedule_data.clc_type == CLCTypeEnum.date_of_year else None
    user_config.clc_specific_date = schedule_data.clc_specific_date if schedule_data.clc_type == CLCTypeEnum.specific_date_in_year else None
    user_config.wct_duration_value = schedule_data.wct_duration_value
    user_config.wct_duration_unit = schedule_data.wct_duration_unit
    user_config.is_clc_enabled = True
    user_config.wct_active_ends_at = None

    try:
        user_config.next_clc_prompt_at = await calculate_next_clc_prompt_at(user_config, current_user.timezone, now_utc, db)
        if user_config.next_clc_prompt_at is None and not is_unloop_checkin:
             logger.error(f"calculate_next_clc_prompt_at returned None for LOOPED IM (user: {current_user.email}).")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not calculate a valid next schedule. Check date/time settings (e.g., day 31 in a short month).")
    except ValueError as ve:
        logger.error(f"ValueError from calculate_next_clc_prompt_at for {current_user.email}: {ve}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error from calculate_next_cllc_prompt_at for {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error calculating schedule.")

    im_stmt_db = select(Message).where(Message.user_id == current_user.id, Message.is_initial_message == True)
    im_result_db = await db.execute(im_stmt_db)
    initial_message_db = im_result_db.scalars().first()

    if initial_message_db:
        initial_message_db.title = im_data.message.title
        initial_message_db.content = im_data.message.content
        initial_message_db.overall_send_status = MessageOverallStatusEnum.pending
        initial_message_db.updated_at = now_utc
    else:
        initial_message_db = Message(
            user_id=current_user.id, title=im_data.message.title, content=im_data.message.content,
            is_initial_message=True, message_order=0, overall_send_status=MessageOverallStatusEnum.pending,
            created_at=now_utc, updated_at=now_utc
        )
        db.add(initial_message_db)

    original_account_status = current_user.account_status
    if current_user.account_status == UserAccountStatusEnum.INS:
        current_user.account_status = UserAccountStatusEnum.ANS_CLC
        logger.info(f"User {current_user.email} status changed from INS to ANS_CLC.")
    current_user.last_activity_at = now_utc
    if original_account_status != current_user.account_status: db.add(current_user)

    try:
        await db.commit()
        await db.refresh(initial_message_db); await db.refresh(user_config)
        if original_account_status != current_user.account_status: await db.refresh(current_user)
        logger.info(f"IM and schedule saved for user {current_user.email}.")
    except Exception as e:
        await db.rollback()
        logger.error(f"DB error saving IM/schedule for {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not save.")

    return InitialMessageWithScheduleResponse(
        message=MessageResponseBase.from_orm(initial_message_db),
        configuration=UserConfigurationResponse.from_orm(user_config),
        account_status_after_update=current_user.account_status
    )


@router.post("/fms", response_model=FollowMessageResponse, status_code=status.HTTP_201_CREATED, summary="Create a new Follow Message")
async def create_follow_message(
    fm_data: FollowMessageCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} creating new Follow Message with trigger type {fm_data.schedule.trigger_type}.")

    im_sent_time_utc = await _get_im_sent_at_utc(current_user.id, db)
    
    # Kiểm tra xem IM có tồn tại không, không chỉ dựa vào im_sent_time_utc
    # vì IM có thể đã được set lịch nhưng chưa gửi.
    im_stmt = select(Message.id).where(Message.user_id == current_user.id, Message.is_initial_message == True)
    im_exists_id = (await db.execute(im_stmt)).scalar_one_or_none()
    if not im_exists_id:
        logger.warning(f"User {current_user.email} attempted to create FM without an existing IM.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Initial Message (IM) must be configured before Follow Messages (FM) can be added."
        ) # 

    max_order_stmt = select(func.max(Message.message_order)).where(
        Message.user_id == current_user.id, Message.is_initial_message == False
    )
    current_max_order = (await db.execute(max_order_stmt)).scalar_one_or_none()
    new_message_order = (current_max_order + 1) if current_max_order is not None else 1
    now_utc = datetime.now(dt_timezone.utc)

    new_fm_message = Message(
        user_id=current_user.id, title=fm_data.message.title, content=fm_data.message.content,
        is_initial_message=False, message_order=new_message_order,
        overall_send_status=MessageOverallStatusEnum.pending,
        created_at=now_utc, updated_at=now_utc
    )
    db.add(new_fm_message)
    await db.flush() 

    schedule_in = fm_data.schedule
    temp_fm_schedule_for_calc = FmSchedule( # Tạo instance tạm để truyền vào hàm tính toán
        message_id=new_fm_message.id, trigger_type=schedule_in.trigger_type,
        sending_time_of_day=schedule_in.sending_time_of_day, repeat_count=schedule_in.repeat_count,
        days_after_im_value=schedule_in.days_after_im_value, day_of_week_value=schedule_in.day_of_week_value,
        date_of_month_value=schedule_in.date_of_month_value, date_of_year_value=schedule_in.date_of_year_value,
        specific_date_value=schedule_in.specific_date_value, is_active=True, current_repetition=0
    )
    
    calculated_next_send_at = None
    try:
        calculated_next_send_at = await calculate_next_fm_send_at(
            fm_schedule=temp_fm_schedule_for_calc, # Truyền instance tạm
            user_timezone_str=current_user.timezone,
            im_sent_at_utc=im_sent_time_utc,
            db=db
        )
    except ValueError as ve: # Bắt lỗi từ calculate_next_fm_send_at (ví dụ: ambiguous time)
        logger.error(f"ValueError calculating next FM send time for user {current_user.email}: {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


    new_fm_schedule_db = FmSchedule(
        message_id=new_fm_message.id, trigger_type=schedule_in.trigger_type,
        sending_time_of_day=schedule_in.sending_time_of_day,
        repeat_count=schedule_in.repeat_count if schedule_in.trigger_type != FMScheduleTriggerTypeEnum.specific_date else 0,
        days_after_im_value=schedule_in.days_after_im_value if schedule_in.trigger_type == FMScheduleTriggerTypeEnum.days_after_im_sent else None,
        day_of_week_value=schedule_in.day_of_week_value if schedule_in.trigger_type == FMScheduleTriggerTypeEnum.day_of_week else None,
        date_of_month_value=schedule_in.date_of_month_value if schedule_in.trigger_type == FMScheduleTriggerTypeEnum.date_of_month else None,
        date_of_year_value=schedule_in.date_of_year_value if schedule_in.trigger_type == FMScheduleTriggerTypeEnum.date_of_year else None,
        specific_date_value=schedule_in.specific_date_value if schedule_in.trigger_type == FMScheduleTriggerTypeEnum.specific_date else None,
        is_active=True, current_repetition=0,
        next_send_at=calculated_next_send_at, # Gán giá trị đã tính
        created_at=now_utc, updated_at=now_utc
    )
    db.add(new_fm_schedule_db)
    
    current_user.last_activity_at = now_utc
    db.add(current_user)

    try:
        await db.commit()
        await db.refresh(new_fm_message)
        await db.refresh(new_fm_schedule_db)
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error creating FM for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create Follow Message.")
    
    # fm_response = FollowMessageResponse.from_orm(new_fm_message)
    # fm_response.fm_schedule = new_fm_schedule_db # Gán trực tiếp nếu model cho phép
    # Hoặc load lại từ DB để đảm bảo response đầy đủ
    
    # Load lại FM với schedule để response
    stmt_get_fm = (
        select(Message)
        .where(Message.id == new_fm_message.id)
        .options(joinedload(Message.fm_schedule))
    )
    refreshed_fm_with_schedule = (await db.execute(stmt_get_fm)).scalars().first()
    if not refreshed_fm_with_schedule: # Không nên xảy ra
        raise HTTPException(status_code=500, detail="Failed to retrieve created FM for response.")

    return refreshed_fm_with_schedule


@router.get("/fms", response_model=List[FollowMessageResponse], summary="List all Follow Messages for the current user")
async def list_follow_messages( # Giữ nguyên
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
    skip: int = 0,
    limit: int = 100
):
    logger.info(f"User {current_user.email} listing Follow Messages.")
    stmt = (
        select(Message)
        .where(Message.user_id == current_user.id)
        .where(Message.is_initial_message == False) 
        .options(joinedload(Message.fm_schedule)) 
        .order_by(Message.message_order) 
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    fms_db = result.scalars().all()
    return fms_db


@router.get("/fms/{fm_id}", response_model=FollowMessageResponse, summary="Get a specific Follow Message")
async def get_follow_message( # Giữ nguyên
    fm_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} getting FM with id {fm_id}.")
    stmt = (
        select(Message)
        .where(Message.id == fm_id)
        .where(Message.user_id == current_user.id)
        .where(Message.is_initial_message == False)
        .options(joinedload(Message.fm_schedule)) 
    )
    result = await db.execute(stmt)
    fm_db = result.scalars().first()

    if not fm_db:
        logger.warning(f"FM with id {fm_id} not found for user {current_user.email}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow Message not found.")
    return fm_db


@router.put("/fms/{fm_id}", response_model=FollowMessageResponse, summary="Update a specific Follow Message")
async def update_follow_message(
    fm_id: uuid.UUID,
    fm_update_data: FollowMessageUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} updating FM with id {fm_id}.")

    stmt = (
        select(Message)
        .where(Message.id == fm_id)
        .where(Message.user_id == current_user.id)
        .where(Message.is_initial_message == False)
        .options(joinedload(Message.fm_schedule))
    )
    result = await db.execute(stmt)
    fm_db = result.scalars().first()

    if not fm_db:
        logger.warning(f"FM with id {fm_id} not found for user {current_user.email} to update.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow Message not found.")

    update_data_dict = fm_update_data.model_dump(exclude_unset=True)
    now_utc = datetime.now(dt_timezone.utc)
    needs_schedule_recalculation = False

    if "message" in update_data_dict:
        message_content_data = update_data_dict["message"]
        if "title" in message_content_data: fm_db.title = message_content_data["title"]
        if "content" in message_content_data: fm_db.content = message_content_data["content"]
        fm_db.updated_at = now_utc
        # Consider resetting overall_send_status to pending if content changes significantly
        # fm_db.overall_send_status = MessageOverallStatusEnum.pending 

    if "schedule" in update_data_dict:
        if not fm_db.fm_schedule: # Nếu FM chưa có schedule (trường hợp hiếm), tạo mới
             fm_db.fm_schedule = FmSchedule(message_id=fm_db.id, created_at=now_utc)
             db.add(fm_db.fm_schedule) # Add to session if newly created
             await db.flush() # Get ID if needed for new schedule

        schedule_changes = update_data_dict["schedule"]
        fm_schedule_db = fm_db.fm_schedule
        
        original_trigger_type = fm_schedule_db.trigger_type
        new_trigger_type = schedule_changes.get('trigger_type', original_trigger_type)

        for key, value in schedule_changes.items():
            if hasattr(fm_schedule_db, key):
                setattr(fm_schedule_db, key, value)
        fm_schedule_db.updated_at = now_utc
        needs_schedule_recalculation = True
        
        # Nullify irrelevant fields based on new trigger_type
        fm_schedule_db.days_after_im_value = schedule_changes.get('days_after_im_value') if new_trigger_type == FMScheduleTriggerTypeEnum.days_after_im_sent else None
        fm_schedule_db.day_of_week_value = schedule_changes.get('day_of_week_value') if new_trigger_type == FMScheduleTriggerTypeEnum.day_of_week else None
        fm_schedule_db.date_of_month_value = schedule_changes.get('date_of_month_value') if new_trigger_type == FMScheduleTriggerTypeEnum.date_of_month else None
        fm_schedule_db.date_of_year_value = schedule_changes.get('date_of_year_value') if new_trigger_type == FMScheduleTriggerTypeEnum.date_of_year else None
        fm_schedule_db.specific_date_value = schedule_changes.get('specific_date_value') if new_trigger_type == FMScheduleTriggerTypeEnum.specific_date else None
        
        if new_trigger_type == FMScheduleTriggerTypeEnum.specific_date:
            fm_schedule_db.repeat_count = 0
        elif 'repeat_count' not in schedule_changes: # Nếu không update repeat_count và trigger type đổi từ specific_date
            if original_trigger_type == FMScheduleTriggerTypeEnum.specific_date:
                fm_schedule_db.repeat_count = 0 # Mặc định là 0 cho các loại khác nếu không được cung cấp

    if needs_schedule_recalculation and fm_db.fm_schedule:
        im_sent_time_utc = await _get_im_sent_at_utc(current_user.id, db)
        try:
            fm_db.fm_schedule.next_send_at = await calculate_next_fm_send_at(
                fm_schedule=fm_db.fm_schedule,
                user_timezone_str=current_user.timezone,
                im_sent_at_utc=im_sent_time_utc,
                db=db
            )
        except ValueError as ve:
            logger.error(f"ValueError calculating next FM send time during update for {fm_id}: {ve}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        
        fm_db.fm_schedule.is_active = True # Kích hoạt lại lịch nếu có thay đổi
        fm_db.fm_schedule.current_repetition = 0 # Reset số lần lặp lại khi lịch thay đổi

    current_user.last_activity_at = now_utc
    db.add(current_user)

    try:
        await db.commit()
        await db.refresh(fm_db)
        if fm_db.fm_schedule: await db.refresh(fm_db.fm_schedule)
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error updating FM {fm_id} for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update Follow Message.")

    return fm_db


@router.delete("/fms/{fm_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a specific Follow Message")
async def delete_follow_message( # Giữ nguyên
    fm_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"User {current_user.email} deleting FM with id {fm_id}.")
    
    stmt_get = select(Message.id).where(
        Message.id == fm_id,
        Message.user_id == current_user.id,
        Message.is_initial_message == False
    )
    message_to_delete_id = (await db.execute(stmt_get)).scalar_one_or_none()
    if not message_to_delete_id:
        logger.warning(f"FM with id {fm_id} not found for user {current_user.email} to delete.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow Message not found.")

    stmt_delete = delete(Message).where(Message.id == fm_id) # Cascade delete sẽ xóa FmSchedule và MessageReceivers
    result = await db.execute(stmt_delete)
    
    # Không cần kiểm tra result.rowcount nữa vì query trên đã check

    current_user.last_activity_at = datetime.now(dt_timezone.utc)
    db.add(current_user)

    try:
        await db.commit()
        logger.info(f"FM with id {fm_id} deleted successfully for user {current_user.email}.")
    except Exception as e:
        await db.rollback()
        logger.error(f"Database error deleting FM {fm_id} for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not delete Follow Message.")
    
    return None