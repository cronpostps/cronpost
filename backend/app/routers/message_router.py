# backend/app/routers/message_router.py
# Version: 1.0

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, and_, or_
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, aliased

from ..db.database import get_db_session
from ..db.models import User, Message, FmSchedule, MessageOverallStatusEnum
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.security import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["Messages"],
    dependencies=[Depends(get_current_active_user)]
)

class MessageOverviewResponse(BaseModel):
    im_status: str  # e.g., "Active", "Inactive", "Not Set"
    fm_active_count: int
    fm_inactive_count: int
    scm_active_count: int
    scm_inactive_count: int

@router.get("/overview", response_model=MessageOverviewResponse, summary="Get message overview statistics")
async def get_message_overview(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Fetching message overview for user: {current_user.email}")

    # 1. Initial Message (IM) Status
    im_status_str = "Not Set"
    im_stmt = select(Message).where(
        Message.user_id == current_user.id,
        Message.is_initial_message == True
    )
    im_result = await db.execute(im_stmt)
    initial_message = im_result.scalars().first()

    if initial_message:
        if initial_message.overall_send_status in [MessageOverallStatusEnum.pending, MessageOverallStatusEnum.processing]:
            im_status_str = "Active"
        else:
            im_status_str = "Inactive" # Covers sent, failed, cancelled

    # 2. Follow-up Messages (FM) Counts
    FmScheduleAlias = aliased(FmSchedule)
    
    # Active FMs
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

    # All FMs (messages that have an FmSchedule entry and are not IM)
    all_fm_stmt = (
        select(func.count(Message.id))
        .join(FmScheduleAlias, Message.id == FmScheduleAlias.message_id) # Ensure it's an FM by joining
        .where(
            Message.user_id == current_user.id,
            Message.is_initial_message == False
        )
    )
    all_fm_count_result = await db.execute(all_fm_stmt)
    all_fm_count_val = all_fm_count_result.scalar_one_or_none() or 0
    
    fm_inactive_count_val = all_fm_count_val - fm_active_count_val


    # 3. Simple Cron Messages (SCM) Counts
    # GIẢ ĐỊNH: Hiện tại chưa có cách phân biệt SCM rõ ràng trong DB.
    # Tạm thời trả về 0. Sẽ cập nhật khi có logic cụ thể.
    scm_active_count_val = 0
    scm_inactive_count_val = 0
    # Logic ví dụ nếu SCM là message không phải IM và không có FmSchedule:
    # scm_base_query = select(Message).where(
    #     Message.user_id == current_user.id,
    #     Message.is_initial_message == False,
    #     ~Message.id.in_(select(FmSchedule.message_id)) # Not an FM
    # )
    # active_scm_stmt = select(func.count(Message.id)).select_from(scm_base_query.alias("scm_subquery")).where(
    #     Message.overall_send_status.in_([MessageOverallStatusEnum.pending, MessageOverallStatusEnum.processing])
    # )
    # # ... và tương tự cho inactive

    return MessageOverviewResponse(
        im_status=im_status_str,
        fm_active_count=fm_active_count_val,
        fm_inactive_count=fm_inactive_count_val,
        scm_active_count=scm_active_count_val,
        scm_inactive_count=scm_inactive_count_val
    )