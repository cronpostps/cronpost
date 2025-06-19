# backend/app/routers/messaging_router.py
# Version: 4.0.1

import logging
import uuid
import bleach 
from fastapi import APIRouter, Depends, Request, status, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, case, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from typing import List

from ..db.models import User, InAppMessage, MessageThread, UserBlock, UploadedFile, MessageAttachment
from ..db.database import get_db_session
from ..models.message_models import MessageThreadResponse, MessageThreadParticipantResponse, InAppMessageResponse, InAppMessageCreate
from ..core.security import get_current_active_user
from datetime import datetime, timezone as dt_timezone
from ..dependencies import get_system_settings_dep

from slowapi import Limiter
from slowapi.util import get_remote_address

ALLOWED_TAGS = ['p', 'b', 'strong', 'i', 'em', 'u', 'br', 'ul', 'ol', 'li', 'a', 'blockquote']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["In-App Messaging"],
    dependencies=[Depends(get_current_active_user)]
)
limiter = Limiter(key_func=get_remote_address)

class UnreadCountResponse(BaseModel):
    unread_count: int

@router.get("/unread-count", response_model=UnreadCountResponse, summary="Get unread in-app messages count")
async def get_unread_in_app_messages_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    unread_count_stmt = (
        select(func.count(InAppMessage.id))
        .where(InAppMessage.receiver_id == current_user.id)
        .where(InAppMessage.read_at == None)
        .where(InAppMessage.is_deleted_by_receiver == False)
    )
    unread_count_result = await db.execute(unread_count_stmt)
    count = unread_count_result.scalar_one_or_none() or 0
    return UnreadCountResponse(unread_count=count)

@router.get("/inbox", response_model=List[InAppMessageResponse], summary="Get all received messages (Inbox)")
async def get_inbox(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Lấy tất cả tin nhắn người dùng đã nhận, sắp xếp theo thời gian mới nhất.
    """
    stmt = (
        select(InAppMessage)
        .where(InAppMessage.receiver_id == current_user.id)
        .where(InAppMessage.is_deleted_by_receiver == False)
        .options(
            selectinload(InAppMessage.sender),
            selectinload(InAppMessage.receiver),
            selectinload(InAppMessage.attachments)
        )
        .order_by(InAppMessage.sent_at.desc())
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return messages

@router.get("/sent", response_model=List[InAppMessageResponse], summary="Get all sent messages")
async def get_sent_messages(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Lấy tất cả tin nhắn người dùng đã gửi, sắp xếp theo thời gian mới nhất.
    """
    stmt = (
        select(InAppMessage)
        .where(InAppMessage.sender_id == current_user.id)
        .where(InAppMessage.is_deleted_by_sender == False)
        .options(
            selectinload(InAppMessage.sender),
            selectinload(InAppMessage.receiver),
            selectinload(InAppMessage.attachments)
        )
        .order_by(InAppMessage.sent_at.desc())
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return messages

@router.get("/threads/{thread_id}", response_model=List[InAppMessageResponse], summary="Get all messages within a specific thread")
async def get_messages_in_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    thread_stmt = await db.execute(select(MessageThread).where(MessageThread.id == thread_id))
    thread = thread_stmt.scalars().first()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found.")
    if current_user.id not in [thread.user1_id, thread.user2_id]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to view this thread.")
    messages_stmt = await db.execute(
        select(InAppMessage)
        .where(InAppMessage.thread_id == thread_id)
        .options(
            selectinload(InAppMessage.sender),
            selectinload(InAppMessage.receiver),
            selectinload(InAppMessage.attachments) # <-- Thêm dòng này
        )
        .order_by(InAppMessage.sent_at.asc())
    )
    messages = messages_stmt.scalars().all()
    now_utc = datetime.now(dt_timezone.utc)
    if thread.user1_id == current_user.id:
        thread.user1_last_read_at = now_utc
    else:
        thread.user2_last_read_at = now_utc
    for msg in messages:
        if msg.receiver_id == current_user.id and not msg.read_at:
            msg.read_at = now_utc
    await db.commit()
    logger.info(f"User {current_user.email} viewed thread {thread_id} and marked it as read.")
    return messages


@router.post("/send", response_model=InAppMessageResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute, 200/hour")
async def send_new_message(
    message_data: InAppMessageCreate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    settings: dict = Depends(get_system_settings_dep),
    db: AsyncSession = Depends(get_db_session)
):
    # --- 1. Xác thực người nhận và các điều kiện cơ bản ---
    receiver_stmt = await db.execute(select(User).where(User.email == message_data.receiver_email))
    receiver = receiver_stmt.scalars().first()
    if not receiver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient user not found.")
    if receiver.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot send a message to yourself.")
    block_check_stmt = await db.execute(select(UserBlock).where(UserBlock.blocker_user_id == receiver.id, UserBlock.blocked_user_id == current_user.id))
    if block_check_stmt.scalars().first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are blocked from sending messages to this user.")

    # --- 2. Kiểm tra giới hạn nội dung (Dual Check) ---
    if current_user.membership_type == 'free':
        text_limit = int(settings.get('max_message_content_length_free', 5000))
    else:
        text_limit = int(settings.get('max_message_content_length_premium', 50000))

    html_hard_limit = text_limit * 4
    if len(message_data.content) > html_hard_limit:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Message data size is too large.")

    plain_text_content = bleach.clean(message_data.content, tags=[], strip=True)
    buffer_multiplier = float(settings.get('char_limit_buffer_multiplier', '2.0'))
    allowed_limit_with_buffer = text_limit * buffer_multiplier
    if len(plain_text_content) > allowed_limit_with_buffer:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Your message text ({len(plain_text_content)} characters) exceeds the allowed limit of {text_limit} characters.")

    # --- 3. Làm sạch nội dung HTML để lưu trữ ---
    sanitized_content = bleach.clean(message_data.content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES) # <== ĐÃ XÓA strip=True

    # --- 4. Tìm hoặc tạo Thread ---
    user1_id, user2_id = sorted([current_user.id, receiver.id])
    thread_stmt = await db.execute(select(MessageThread).where(MessageThread.user1_id == user1_id, MessageThread.user2_id == user2_id))
    thread = thread_stmt.scalars().first()
    now_utc = datetime.now(dt_timezone.utc)
    if not thread:
        thread = MessageThread(user1_id=user1_id, user2_id=user2_id, last_message_at=now_utc)
        db.add(thread)
        await db.flush()
    else:
        thread.last_message_at = now_utc

    # --- 5. Tạo tin nhắn và các bản ghi đính kèm ---
    new_message = InAppMessage(
        thread_id=thread.id,
        sender_id=current_user.id,
        receiver_id=receiver.id,
        subject=message_data.subject,
        content=sanitized_content,
        sent_at=now_utc
    )
    db.add(new_message)
    await db.flush() # Flush để new_message có ID

    if message_data.attachment_file_ids:
        if current_user.membership_type != 'premium':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Premium users can send attachments.")
        for file_id in message_data.attachment_file_ids:
            file_owner_stmt = await db.execute(select(UploadedFile.id).where(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id))
            if not file_owner_stmt.scalars().first():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Attachment file with ID {file_id} not found or you do not have permission to use it.")
            new_attachment = MessageAttachment(message_id=new_message.id, file_id=file_id)
            db.add(new_attachment)

    # --- 6. Commit và trả về kết quả ---
    await db.commit()

    # Tải lại message với đầy đủ thông tin để trả về response
    stmt_final = (
        select(InAppMessage).where(InAppMessage.id == new_message.id).options(
            selectinload(InAppMessage.sender),
            selectinload(InAppMessage.receiver),
            selectinload(InAppMessage.attachments) # Tải kèm attachments
        )
    )
    final_message_with_relations = (await db.execute(stmt_final)).scalars().first()

    logger.info(f"User {current_user.email} sent a message with subject '{message_data.subject}' to {receiver.email}")
    return final_message_with_relations

@router.get("/threads/search", response_model=List[MessageThreadResponse], summary="Search for message threads by participant name or email")
async def search_user_threads(
    q: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    if not q or len(q) < 2:
        return []
    user_id = current_user.id
    search_term = f"%{q.lower()}%"
    OtherUser = aliased(User)
    last_message_subquery = (select(InAppMessage.thread_id, func.max(InAppMessage.sent_at).label("last_sent_at")).group_by(InAppMessage.thread_id).subquery('last_message_subquery'))
    last_message_info = aliased(InAppMessage)
    stmt = (
        select(
            MessageThread, OtherUser,
            last_message_info.content.label("last_message_content"),
            func.count(case((InAppMessage.receiver_id == user_id, InAppMessage.read_at.is_(None)), else_=None)).label("unread_messages_count")
        )
        .join(OtherUser, case(
            (MessageThread.user1_id == user_id, MessageThread.user2_id == OtherUser.id),
            (MessageThread.user2_id == user_id, MessageThread.user1_id == OtherUser.id)
        ))
        .outerjoin(last_message_subquery, MessageThread.id == last_message_subquery.c.thread_id)
        .outerjoin(last_message_info, (last_message_info.thread_id == last_message_subquery.c.thread_id) & (last_message_info.sent_at == last_message_subquery.c.last_sent_at))
        # --- BUG FIX: Join on thread_id, not id ---
        .outerjoin(InAppMessage, MessageThread.id == InAppMessage.thread_id)
        .where(
            ((MessageThread.user1_id == user_id) | (MessageThread.user2_id == user_id)) &
            (func.lower(OtherUser.user_name).like(search_term) | func.lower(OtherUser.email).like(search_term))
        )
        .group_by(MessageThread.id, OtherUser.id, last_message_info.content)
        .order_by(MessageThread.last_message_at.desc().nullslast())
    )
    result = await db.execute(stmt)
    threads_data = []
    for thread, other_user, last_content, unread_count in result.all():
        participant = MessageThreadParticipantResponse.from_orm(other_user)
        thread_response = MessageThreadResponse(
            id=thread.id,
            other_participant=participant,
            last_message_content=last_content,
            last_message_at=thread.last_message_at,
            unread_messages_count=unread_count
        )
        threads_data.append(thread_response)
    return threads_data

@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a message from the user's view")
async def delete_message(
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Thực hiện soft delete một tin nhắn.
    Nếu người dùng là người gửi, set is_deleted_by_sender = true.
    Nếu người dùng là người nhận, set is_deleted_by_receiver = true.
    """
    stmt = select(InAppMessage).where(InAppMessage.id == message_id)
    result = await db.execute(stmt)
    message = result.scalars().first()

    if not message:
        # Không báo lỗi 404 để tránh lộ thông tin tin nhắn có tồn tại hay không
        return
    
    # Xác thực quyền
    if current_user.id == message.sender_id:
        if not message.is_deleted_by_sender:
            message.is_deleted_by_sender = True
            await db.commit()
            logger.info(f"Message {message_id} marked as deleted by sender {current_user.email}")
    elif current_user.id == message.receiver_id:
        if not message.is_deleted_by_receiver:
            message.is_deleted_by_receiver = True
            await db.commit()
            logger.info(f"Message {message_id} marked as deleted by receiver {current_user.email}")
    else:
        # Người dùng không phải người gửi cũng không phải người nhận
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this message."
        )
    return

@router.get("/search", response_model=List[InAppMessageResponse], summary="Search for messages by content, subject, or participant")
async def search_messages(
    q: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Tìm kiếm tin nhắn dựa trên một chuỗi truy vấn.
    Tìm kiếm trong các trường: Tên/Email người đối thoại, Tiêu đề và Nội dung tin nhắn.
    Chỉ trả về các tin nhắn mà người dùng hiện tại có quyền xem.
    """
    if not q or len(q) < 2:
        return []

    search_term = f"%{q.lower()}%"
    user_id = current_user.id

    # Alias để join đến thông tin của người đối thoại
    OtherUser = aliased(User)

    stmt = (
        select(InAppMessage)
        .join(MessageThread, InAppMessage.thread_id == MessageThread.id)
        # Join với User table để lấy thông tin của người đối thoại
        .join(OtherUser, or_(
            and_(MessageThread.user1_id == user_id, MessageThread.user2_id == OtherUser.id),
            and_(MessageThread.user2_id == user_id, MessageThread.user1_id == OtherUser.id)
        ))
        # Tải trước thông tin sender/receiver để tránh N+1 query
        .options(
            selectinload(InAppMessage.sender),
            selectinload(InAppMessage.receiver),
            selectinload(InAppMessage.attachments) # <-- Thêm dòng này
        )
        .where(
            # 1. User phải là một phần của cuộc trò chuyện
            or_(MessageThread.user1_id == user_id, MessageThread.user2_id == user_id),
            # 2. User phải có quyền xem tin nhắn này (chưa bị họ xóa)
            or_(
                and_(InAppMessage.sender_id == user_id, InAppMessage.is_deleted_by_sender == False),
                and_(InAppMessage.receiver_id == user_id, InAppMessage.is_deleted_by_receiver == False)
            ),
            # 3. Điều kiện tìm kiếm (case-insensitive)
            or_(
                func.lower(OtherUser.user_name).like(search_term),
                func.lower(OtherUser.email).like(search_term),
                func.lower(InAppMessage.subject).like(search_term),
                func.lower(InAppMessage.content).like(search_term)
            )
        )
        .order_by(InAppMessage.sent_at.desc())
    )

    result = await db.execute(stmt)
    messages = result.scalars().all()
    return messages

@router.post("/inbox/mark-all-as-read", status_code=status.HTTP_204_NO_CONTENT, summary="Mark all unread messages as read")
async def mark_all_messages_as_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Đánh dấu tất cả tin nhắn chưa đọc của người dùng hiện tại là đã đọc.
    """
    now_utc = datetime.now(dt_timezone.utc)
    
    stmt = (
        update(InAppMessage)
        .where(
            InAppMessage.receiver_id == current_user.id,
            InAppMessage.read_at == None
        )
        .values(read_at=now_utc)
    )
    
    result = await db.execute(stmt)
    await db.commit()
    
    logger.info(f"User {current_user.email} marked {result.rowcount} message(s) as read.")
    
    # Gửi sự kiện SSE để cập nhật UI ngay lập tức (quan trọng)
    from ..sse_manager import sse_manager
    await sse_manager.send_message(
        current_user.id,
        {"event": "unread_update", "unread_count": 0}
    )
    
    return