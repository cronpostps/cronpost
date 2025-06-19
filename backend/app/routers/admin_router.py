# /backend/app/routers/admin_router.py
# Version 2.2
# - Fixed NameError by reordering Pydantic models before endpoint definitions.

import logging
from typing import List, Optional, Literal, Dict
from datetime import datetime
import uuid
import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, constr, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, func, update, delete

from ..db.database import get_db_session
from ..db.models import (
    SystemSetting, User, UserMembershipTypeEnum, UserAccountStatusEnum, 
    Message, FmSchedule, SimpleCronMessage, EmailCheckinSettings, PinAttempt
)
from ..dependencies import get_current_admin_user, get_system_settings_dep
from ..services.email_service import send_email_async
from ..core.security import verify_user_pin_with_lockout

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["Admin"],
    dependencies=[Depends(get_current_admin_user)]
)

# --- Pydantic Models (Định nghĩa trước khi sử dụng) ---
class SystemSettingResponse(BaseModel):
    setting_key: str
    setting_value: Optional[str] = None
    description: Optional[str] = None
    class Config: from_attributes = True

class SettingUpdateRequest(BaseModel):
    value: str
    admin_pin: constr(pattern=r"^\d{4}$")

class PinVerifyRequest(BaseModel):
    admin_pin: constr(pattern=r"^\d{4}$")

class UserAdminView(BaseModel):
    id: uuid.UUID
    email: EmailStr
    user_name: Optional[str] = None
    membership_type: UserMembershipTypeEnum
    account_status: UserAccountStatusEnum
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    class Config: from_attributes = True

class UserListResponse(BaseModel):
    total_count: int
    users: List[UserAdminView]

class UserActionRequest(BaseModel):
    admin_pin: constr(pattern=r"^\d{4}$")

class MessageResponse(BaseModel):
    message: str

# --- Endpoints ---

@router.post("/verify-pin", summary="Verify admin's PIN for initial access")
async def verify_admin_pin(
    pin_data: PinVerifyRequest,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(get_current_admin_user),
    settings: Dict[str, str] = Depends(get_system_settings_dep)
):
    if not current_admin.pin_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin PIN is not set.")
    
    await verify_user_pin_with_lockout(db, current_admin, pin_data.admin_pin, settings)
    return {"message": "PIN verified successfully."}


@router.get("/system-settings", response_model=List[SystemSettingResponse], summary="Get all system settings")
async def get_all_system_settings(db: AsyncSession = Depends(get_db_session)):
    stmt = select(SystemSetting).order_by(SystemSetting.id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.put("/system-settings/{setting_key}", summary="Update a specific system setting")
async def update_system_setting(
    setting_key: str,
    update_data: SettingUpdateRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
    settings: Dict[str, str] = Depends(get_system_settings_dep)
):
    await verify_user_pin_with_lockout(db, current_admin, update_data.admin_pin, settings)
    
    setting = (await db.execute(select(SystemSetting).filter_by(setting_key=setting_key))).scalars().first()
    if not setting: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Setting with key '{setting_key}' not found.")
    setting.setting_value = update_data.value
    await db.commit()
    logger.info(f"Admin '{current_admin.email}' updated setting '{setting_key}' to '{update_data.value}'")
    return {"message": f"Setting '{setting_key}' updated successfully."}


@router.get("/users", response_model=UserListResponse, summary="List, search, sort, and paginate users")
async def get_users_list(
    db: AsyncSession = Depends(get_db_session), 
    skip: int = 0, limit: int = 10, 
    search: Optional[str] = None, 
    sort_by: Optional[Literal['membership_type', 'last_activity_at', 'created_at']] = Query('created_at'), 
    sort_dir: Optional[Literal['asc', 'desc']] = Query('desc')
):
    base_query = select(User)
    if search:
        search_term = f"%{search.lower()}%"
        base_query = base_query.where(or_(func.lower(User.email).like(search_term), func.lower(User.user_name).like(search_term)))
    
    count_query = select(func.count()).select_from(base_query.subquery())
    total_count = (await db.execute(count_query)).scalar_one()
    
    sort_column = getattr(User, sort_by, User.created_at)
    base_query = base_query.order_by(sort_column.desc() if sort_dir == 'desc' else sort_column.asc())
    
    final_query = base_query.offset(skip).limit(limit)
    result = await db.execute(final_query)
    
    return UserListResponse(total_count=total_count, users=result.scalars().all())


# --- USER ACTION ENDPOINTS ---

@router.put("/users/{user_id}/upgrade", response_model=UserAdminView, summary="Upgrade a user to Premium")
async def upgrade_user_to_premium(user_id: uuid.UUID, action_data: UserActionRequest, current_admin: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db_session), settings: Dict[str, str] = Depends(get_system_settings_dep)):
    await verify_user_pin_with_lockout(db, current_admin, action_data.admin_pin, settings)
    target_user = await db.get(User, user_id)
    if not target_user: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target_user.membership_type == UserMembershipTypeEnum.premium: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a Premium member.")
    
    target_user.membership_type = UserMembershipTypeEnum.premium
    target_user.membership_expires_at = None
    
    await db.commit()
    await db.refresh(target_user)
    
    logger.info(f"Admin '{current_admin.email}' upgraded user '{target_user.email}' to Premium.")
    return target_user

@router.put("/users/{user_id}/downgrade", response_model=UserAdminView, summary="Downgrade a user to Free")
async def downgrade_user_to_free(user_id: uuid.UUID, action_data: UserActionRequest, current_admin: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db_session), settings: Dict[str, str] = Depends(get_system_settings_dep)):
    await verify_user_pin_with_lockout(db, current_admin, action_data.admin_pin, settings)
    target_user = await db.get(User, user_id)
    if not target_user: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target_user.membership_type == UserMembershipTypeEnum.free: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a Free member.")
    
    checkin_settings_record = (await db.execute(select(EmailCheckinSettings).filter_by(user_id=user_id))).scalar_one_or_none()
    if checkin_settings_record:
        await db.delete(checkin_settings_record)
        logger.info(f"Deleted email_checkin_settings for downgraded user {target_user.email}")
    
    active_fm_stmt = update(FmSchedule).where(FmSchedule.message.has(user_id=user_id)).values(repeat_number=0)
    await db.execute(active_fm_stmt)
    active_scm_stmt = update(SimpleCronMessage).where(SimpleCronMessage.user_id == user_id).values(repeat_number=0)
    await db.execute(active_scm_stmt)
    msg_attachment_stmt = update(Message).where(Message.user_id == user_id).values(attachment_file_id=None)
    await db.execute(msg_attachment_stmt)
    
    target_user.membership_type = UserMembershipTypeEnum.free
    
    await db.commit()
    await db.refresh(target_user)
    
    logger.info(f"Admin '{current_admin.email}' downgraded user '{target_user.email}' to Free.")
    return target_user

@router.delete("/users/{user_id}", response_model=MessageResponse, summary="Delete a user account")
async def delete_user(user_id: uuid.UUID, action_data: UserActionRequest, current_admin: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db_session), settings: Dict[str, str] = Depends(get_system_settings_dep)):
    await verify_user_pin_with_lockout(db, current_admin, action_data.admin_pin, settings)
    target_user = await db.get(User, user_id)
    if not target_user: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target_user.id == current_admin.id: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins cannot delete their own account.")
    
    deleted_email = target_user.email
    await db.delete(target_user)
    await db.commit()
    
    logger.info(f"Admin '{current_admin.email}' deleted user '{deleted_email}' (ID: {user_id}).")
    return MessageResponse(message=f"User {deleted_email} has been successfully deleted.")

@router.post("/users/{user_id}/reset-pin", response_model=MessageResponse, summary="Reset a user's PIN by admin")
async def reset_user_pin(
    user_id: uuid.UUID, 
    action_data: UserActionRequest, 
    background_tasks: BackgroundTasks, 
    current_admin: User = Depends(get_current_admin_user), 
    db: AsyncSession = Depends(get_db_session), 
    settings: Dict[str, str] = Depends(get_system_settings_dep)
):
    await verify_user_pin_with_lockout(db, current_admin, action_data.admin_pin, settings)
    
    target_user = await db.get(User, user_id)
    if not target_user: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    target_user.pin_code = None
    target_user.pin_code_question = None
    target_user.pin_recovery_code_hash = None
    target_user.pin_recovery_code_used = False
    target_user.use_pin_for_all_actions = False
    target_user.failed_pin_attempts = 0
    target_user.account_locked_until = None
    target_user.account_locked_reason = None
    
    delete_attempts_stmt = delete(PinAttempt).where(PinAttempt.user_id == user_id)
    await db.execute(delete_attempts_stmt)
    logger.info(f"Admin '{current_admin.email}' cleared all pin_attempts for user '{target_user.email}'.")

    email_body = {"user_name": target_user.user_name or target_user.email, "user_email": target_user.email}
    background_tasks.add_task(send_email_async, "Your CronPost PIN has been reset", target_user.email, email_body, "admin_pin_reset.html")
    
    await db.commit()
    
    logger.info(f"Admin '{current_admin.email}' fully reset PIN for user '{target_user.email}'.")
    return MessageResponse(message=f"PIN for user {target_user.email} has been completely reset. Lockout status and attempt history have been cleared.")