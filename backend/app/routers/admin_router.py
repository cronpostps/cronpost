# backend/app/routers/admin_router.py
# version: 1.0 (Initial version for admin functionalities)

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..db.database import get_db_session
from ..db.models import User, SystemSetting
from ..core.security import get_current_admin_user # SỬ DỤNG DEPENDENCY MỚI

logger = logging.getLogger(__name__)

# Router này sẽ yêu cầu user phải là admin cho tất cả các endpoint
router = APIRouter(
    tags=["Admin"],
    dependencies=[Depends(get_current_admin_user)]
)

class SystemSettingResponse(BaseModel):
    setting_key: str
    setting_value: str
    description: str

    class Config:
        from_attributes = True

@router.get("/system-settings", response_model=List[SystemSettingResponse], summary="Get all system settings")
async def get_all_system_settings(db: AsyncSession = Depends(get_db_session)):
    """
    Retrieves all system settings. Only accessible by admin users.
    """
    result = await db.execute(select(SystemSetting).order_by(SystemSetting.id))
    settings = result.scalars().all()
    return settings

# --- Các endpoint khác cho admin có thể được thêm vào đây ---
# Ví dụ: cập nhật một setting, xem danh sách user, nâng cấp user, ...
# @router.put("/system-settings/{key}")
# async def update_system_setting(...):
#     ...