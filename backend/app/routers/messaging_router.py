# backend/app/routers/messaging_router.py
# Version: 1.0

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db_session
from ..db.models import User, InAppMessage # Import InAppMessage model
from ..core.security import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["In-App Messaging"],
    dependencies=[Depends(get_current_active_user)]
)

class UnreadCountResponse(BaseModel):
    unread_count: int

@router.get("/unread-count", response_model=UnreadCountResponse, summary="Get unread in-app messages count")
async def get_unread_in_app_messages_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info(f"Fetching unread in-app message count for user: {current_user.email}")

    unread_count_stmt = (
        select(func.count(InAppMessage.id))
        .where(InAppMessage.receiver_id == current_user.id)
        .where(InAppMessage.read_at == None)
        .where(InAppMessage.is_deleted_by_receiver == False) # Chỉ đếm những tin nhắn chưa bị người nhận xóa
    )
    
    unread_count_result = await db.execute(unread_count_stmt)
    count = unread_count_result.scalar_one_or_none() or 0
    
    return UnreadCountResponse(unread_count=count)