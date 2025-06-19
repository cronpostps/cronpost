# backend/app/routers/user_actions_router.py
# Version: 2.0.0
# Changelog:
# - Added full CRUD API endpoints for user contacts.
# - Implemented improved logic for contact name handling.

import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone as dt_timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
from sqlalchemy import delete

from ..db.database import get_db_session
from ..db.models import User, CheckinLog, SystemSetting, UserAccountStatusEnum, CheckinMethodEnum, Contact
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

class BlockUserRequest(BaseModel):
    blocked_user_email: EmailStr

class ContactCreateRequest(BaseModel):
    contact_email: EmailStr
    contact_name: Optional[str] = Field(None, max_length=255, description="Custom name for non-CronPost users")

class ContactResponse(BaseModel):
    contact_email: EmailStr
    display_name: str # Tên cuối cùng sẽ được hiển thị cho user
    is_cronpost_user: bool
    contact_user_id: Optional[uuid.UUID] = None

class ContactDeleteRequest(BaseModel):
    contact_email: EmailStr

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

@router.post("/block", status_code=status.HTTP_204_NO_CONTENT, summary="Block another user")
async def block_user(
    request_data: BlockUserRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Chặn một người dùng khác, không cho phép họ gửi tin nhắn In-App tới mình.
    Lưu ý: Thao tác này là một chiều, A chặn B không có nghĩa là B chặn A.
    """
    if current_user.email == request_data.blocked_user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="You cannot block yourself."
        )

    # Tìm người dùng cần chặn
    user_to_block_stmt = await db.execute(select(User).where(User.email == request_data.blocked_user_email))
    user_to_block = user_to_block_stmt.scalars().first()

    if not user_to_block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to block not found.")

    # Kiểm tra xem đã chặn trước đó chưa để tránh tạo bản ghi trùng lặp
    existing_block_stmt = await db.execute(
        select(UserBlock).where(
            UserBlock.blocker_user_id == current_user.id,
            UserBlock.blocked_user_id == user_to_block.id
        )
    )
    if existing_block_stmt.scalars().first():
        # Nếu đã chặn, không báo lỗi, coi như yêu cầu đã thành công
        logger.info(f"User {current_user.email} tried to block {user_to_block.email} again (already blocked).")
        return

    # Tạo bản ghi chặn mới
    new_block = UserBlock(
        blocker_user_id=current_user.id,
        blocked_user_id=user_to_block.id
    )
    db.add(new_block)
    await db.commit()
    
    logger.info(f"User {current_user.email} has blocked {user_to_block.email}.")
    return

@router.post("/unblock", status_code=status.HTTP_204_NO_CONTENT, summary="Unblock a user")
async def unblock_user(
    request_data: BlockUserRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Bỏ chặn một người dùng, cho phép họ gửi lại tin nhắn In-App.
    """
    # Tìm người dùng cần bỏ chặn
    user_to_unblock_stmt = await db.execute(select(User).where(User.email == request_data.blocked_user_email))
    user_to_unblock = user_to_unblock_stmt.scalars().first()

    if not user_to_unblock:
        # Không báo lỗi nếu người dùng không tồn tại để tránh lộ thông tin
        logger.warning(f"User {current_user.email} tried to unblock a non-existent user: {request_data.blocked_user_email}")
        return

    # Tìm và xóa bản ghi chặn
    delete_stmt = delete(UserBlock).where(
        UserBlock.blocker_user_id == current_user.id,
        UserBlock.blocked_user_id == user_to_unblock.id
    )
    await db.execute(delete_stmt)
    await db.commit()
    
    logger.info(f"User {current_user.email} has unblocked {user_to_unblock.email}.")
    return

# --- ADDED: CONTACTS API ENDPOINTS ---

@router.get("/contacts", response_model=List[ContactResponse], summary="List all user contacts")
async def list_contacts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Lấy danh bạ của người dùng, tự động điền tên chính xác nếu contact là user CronPost.
    """
    stmt = (
        select(Contact)
        .outerjoin(User, Contact.contact_user_id == User.id)
        .where(Contact.owner_user_id == current_user.id)
        .options(selectinload(Contact.contact_user)) # Tải trước thông tin user
        .order_by(Contact.contact_name, User.user_name)
    )
    result = await db.execute(stmt)
    contacts_db = result.scalars().all()
    
    response_list = []
    for contact in contacts_db:
        display_name = contact.contact_name
        if contact.is_cronpost_user and contact.contact_user and contact.contact_user.user_name:
            display_name = contact.contact_user.user_name
        elif not display_name:
            display_name = contact.contact_email

        response_list.append(
            ContactResponse(
                contact_email=contact.contact_email,
                display_name=display_name,
                is_cronpost_user=contact.is_cronpost_user,
                contact_user_id=contact.contact_user_id
            )
        )
    return response_list

@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED, summary="Add a new contact")
async def add_contact(
    contact_data: ContactCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Thêm một liên hệ mới vào danh bạ.
    """
    if current_user.email == contact_data.contact_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot add yourself to contacts.")

    # Kiểm tra xem contact đã tồn tại chưa
    existing_contact_stmt = await db.execute(select(Contact).where(Contact.owner_user_id == current_user.id, Contact.contact_email == contact_data.contact_email))
    if existing_contact_stmt.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contact already exists.")

    # Kiểm tra xem email của contact có phải là user của CronPost không
    contact_as_user_stmt = await db.execute(select(User).where(User.email == contact_data.contact_email))
    contact_as_user = contact_as_user_stmt.scalars().first()
    
    is_cp_user = True if contact_as_user else False
    contact_user_id_val = contact_as_user.id if contact_as_user else None
    
    # Theo logic đã thống nhất: chỉ lưu contact_name nếu không phải user CronPost
    contact_name_val = contact_data.contact_name if not is_cp_user else None

    new_contact = Contact(
        owner_user_id=current_user.id,
        contact_email=contact_data.contact_email,
        contact_name=contact_name_val,
        is_cronpost_user=is_cp_user,
        contact_user_id=contact_user_id_val
    )
    db.add(new_contact)
    await db.commit()
    await db.refresh(new_contact)

    # Chuẩn bị dữ liệu trả về
    display_name = contact_name_val
    if is_cp_user and contact_as_user and contact_as_user.user_name:
        display_name = contact_as_user.user_name
    elif not display_name:
        display_name = new_contact.contact_email
    
    return ContactResponse(
        contact_email=new_contact.contact_email,
        display_name=display_name,
        is_cronpost_user=new_contact.is_cronpost_user,
        contact_user_id=new_contact.contact_user_id
    )

@router.delete("/contacts", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a contact")
async def delete_contact(
    contact_data: ContactDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Xóa một liên hệ khỏi danh bạ dựa trên email.
    """
    stmt = delete(Contact).where(
        Contact.owner_user_id == current_user.id,
        Contact.contact_email == contact_data.contact_email
    )
    await db.execute(stmt)
    await db.commit()
    return