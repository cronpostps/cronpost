# backend/app/routers/user_actions_router.py
# Version: 2.3.0
# Changelog:
# - Added GET /blocked-users endpoint to list blocked users.
# - Added helper function and Pydantic model for the block list response.

import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone as dt_timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, constr, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
from sqlalchemy import delete, update

from ..db.database import get_db_session
from ..db.models import User, CheckinLog, SystemSetting, UserAccountStatusEnum, CheckinMethodEnum, Contact, UserBlock
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

class ContactUpdateRequest(BaseModel):
    contact_name: str = Field(..., max_length=255)

class ContactResponse(BaseModel):
    contact_email: EmailStr
    display_name: str
    is_cronpost_user: bool
    contact_user_id: Optional[uuid.UUID] = None
    contact_name: Optional[str] = None
    is_blocked: bool # {* NEW FIELD *}

class ContactDeleteRequest(BaseModel):
    contact_email: EmailStr

class BlockedUserResponse(BaseModel):
    blocked_user_id: uuid.UUID
    email: EmailStr
    user_name: Optional[str] = None
    blocked_at: datetime

# --- Helper Function for Contact Response ---
def create_contact_response(contact: Contact, is_blocked: bool) -> ContactResponse:
    """Helper to consistently create a ContactResponse object."""
    display_name = contact.contact_name
    if not display_name:
        if contact.is_cronpost_user and contact.contact_user and contact.contact_user.user_name:
            display_name = contact.contact_user.user_name
        else:
            display_name = contact.contact_email.split('@')[0]
    
    return ContactResponse(
        contact_email=contact.contact_email,
        display_name=display_name,
        is_cronpost_user=contact.is_cronpost_user,
        contact_user_id=contact.contact_user_id,
        contact_name=contact.contact_name,
        is_blocked=is_blocked  # Pass the blocked status directly
    )

# --- Check-in and Stop FNS API Endpoints ---

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

# --- User Block and Unblock API Endpoints ---

@router.get("/blocked-users", response_model=List[BlockedUserResponse], summary="List all blocked users")
async def get_blocked_users(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    stmt = (
        select(UserBlock)
        .where(UserBlock.blocker_user_id == current_user.id)
        .options(selectinload(UserBlock.blocked_user_details))
        .order_by(UserBlock.created_at.desc())
    )
    result = await db.execute(stmt)
    blocked_records = result.scalars().all()

    return [
        BlockedUserResponse(
            blocked_user_id=record.blocked_user_id,
            email=record.blocked_user_details.email,
            user_name=record.blocked_user_details.user_name,
            blocked_at=record.created_at
        )
        for record in blocked_records
    ]


@router.post("/block", status_code=status.HTTP_204_NO_CONTENT, summary="Block another user")
async def block_user(
    request_data: BlockUserRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    if current_user.email == request_data.blocked_user_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot block yourself.")

    user_to_block_stmt = await db.execute(select(User).where(User.email == request_data.blocked_user_email))
    user_to_block = user_to_block_stmt.scalars().first()

    if not user_to_block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This email does not belong to a CronPost user.")

    existing_block_stmt = await db.execute(select(UserBlock).where(UserBlock.blocker_user_id == current_user.id, UserBlock.blocked_user_id == user_to_block.id))
    if existing_block_stmt.scalars().first():
        return # Already blocked, do nothing

    new_block = UserBlock(blocker_user_id=current_user.id, blocked_user_id=user_to_block.id)
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
    user_to_unblock_stmt = await db.execute(select(User).where(User.email == request_data.blocked_user_email))
    user_to_unblock = user_to_unblock_stmt.scalars().first()

    if not user_to_unblock:
        logger.warning(f"User {current_user.email} tried to unblock a non-existent user: {request_data.blocked_user_email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to unblock not found.")

    delete_stmt = delete(UserBlock).where(UserBlock.blocker_user_id == current_user.id, UserBlock.blocked_user_id == user_to_unblock.id)
    result = await db.execute(delete_stmt)
    await db.commit()
    
    if result.rowcount == 0:
        logger.warning(f"User {current_user.email} tried to unblock a user they had not blocked: {request_data.blocked_user_email}")
        # No error raised to client, request is idempotent
        
    logger.info(f"User {current_user.email} has unblocked {user_to_unblock.email}.")
    return

# --- CONTACTS API ENDPOINTS ---

# Replace the old list_contacts function with this new version
@router.get("/contacts", response_model=List[ContactResponse], summary="List all user contacts")
async def list_contacts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    stmt = (
        select(
            Contact,
            UserBlock.blocked_user_id
        )
        .outerjoin(
            UserBlock,
            (UserBlock.blocker_user_id == current_user.id) &
            (UserBlock.blocked_user_id == Contact.contact_user_id)
        )
        .where(Contact.owner_user_id == current_user.id)
        .options(selectinload(Contact.contact_user))
        .order_by(Contact.contact_name, Contact.contact_email)
    )

    result = await db.execute(stmt)
    
    # Process results in a cleaner way
    response_list = [
        create_contact_response(contact, bool(blocked_user_id))
        for contact, blocked_user_id in result.all()
    ]
            
    return response_list

@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED, summary="Add a new contact")
async def add_contact(
    contact_data: ContactCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    if current_user.email == contact_data.contact_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot add yourself to contacts.")

    existing_contact_stmt = await db.execute(select(Contact).where(Contact.owner_user_id == current_user.id, Contact.contact_email == contact_data.contact_email))
    if existing_contact_stmt. scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contact already exists.")

    contact_as_user_stmt = await db.execute(select(User).where(User.email == contact_data.contact_email))
    contact_as_user = contact_as_user_stmt.scalars().first()
    
    is_cp_user = bool(contact_as_user)
    contact_user_id_val = contact_as_user.id if contact_as_user else None
    
    contact_name_val = contact_data.contact_name
    if not contact_name_val and is_cp_user and contact_as_user:
        contact_name_val = contact_as_user.user_name

    new_contact = Contact(
        owner_user_id=current_user.id,
        contact_email=contact_data.contact_email,
        contact_name=contact_name_val,
        is_cronpost_user=is_cp_user,
        contact_user_id=contact_user_id_val
    )
    db.add(new_contact)
    await db.commit()
    await db.refresh(new_contact, attribute_names=['contact_user'])
    
    return create_contact_response(new_contact, is_blocked=False)

@router.delete("/contacts", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a contact")
async def delete_contact(
    contact_data: ContactDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    stmt = delete(Contact).where(
        Contact.owner_user_id == current_user.id,
        Contact.contact_email == contact_data.contact_email
    )
    result = await db.execute(stmt)
    
    if result.rowcount == 0:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")

    await db.commit()
    return

@router.put("/contacts/{contact_email}", response_model=ContactResponse, summary="Update a contact's name")
async def update_contact(
    contact_email: EmailStr,
    contact_data: ContactUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    # {* MODIFIED QUERY to also fetch block status *}
    stmt = (
        select(
            Contact,
            UserBlock.blocked_user_id
        )
        .outerjoin(
            UserBlock,
            (UserBlock.blocker_user_id == current_user.id) &
            (UserBlock.blocked_user_id == Contact.contact_user_id)
        )
        .where(
            Contact.owner_user_id == current_user.id,
            Contact.contact_email == contact_email
        )
        .options(selectinload(Contact.contact_user))
    )
    
    result = await db.execute(stmt)
    result_row = result.first() # Use .first() as we expect only one row

    if not result_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")

    contact_to_update, blocked_id = result_row
    
    contact_to_update.contact_name = contact_data.contact_name
    await db.commit()
    await db.refresh(contact_to_update, attribute_names=['contact_user'])

    # {* MODIFIED CALL *}
    # Pass the fetched block status to the helper function
    return create_contact_response(contact_to_update, is_blocked=bool(blocked_id))