# /backend/app/routers/file_router.py
# Version: 1.0.1
# - Removed hardcoded prefix from APIRouter.

import os
import uuid
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..db.database import get_db_session
from ..db.models import User, UploadedFile, MessageAttachment, InAppMessage
from ..dependencies import get_current_active_user, get_system_settings_dep
from ..models.user_models import UploadedFileResponse

# --- CONFIGURATION ---
router = APIRouter(
    tags=["Files"],
    dependencies=[Depends(get_current_active_user)]
)
logger = logging.getLogger(__name__)

# Define the upload directory path relative to the backend app's root
UPLOAD_DIR = "/code/uploads"

# Ensure the upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)


# --- SECURITY & PERMISSION CHECK ---
def ensure_premium_user(user: User):
    """Dependency to check if the user is a premium member."""
    if user.membership_type != 'premium':
        logger.warning(f"Free user {user.email} attempted to access a premium file feature.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature is available for Premium members only."
        )

# --- ENDPOINTS ---

@router.post("/upload", response_model=UploadedFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
    settings: dict = Depends(get_system_settings_dep)
):
    """
    Handles file uploads for premium users.
    Performs server-side validation for permissions, file size, and total storage quota.
    """
    # 1. Permission Check (Premium only)
    ensure_premium_user(current_user)

    # 2. Server-side validation
    max_file_size_mb = int(settings.get('max_email_attachment_size_mb_premium', 49))
    max_total_storage_gb = int(settings.get('max_total_upload_storage_gb_premium', 1))
    
    max_file_size_bytes = max_file_size_mb * 1024 * 1024
    max_total_storage_bytes = max_total_storage_gb * 1024 * 1024 * 1024

    # Use a safer method to get file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    await file.seek(0)
    
    # 2a. Check individual file size
    if file_size > max_file_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File size exceeds the limit of {max_file_size_mb} MB.")

    # 2b. Check total storage quota
    if (current_user.uploaded_storage_bytes + file_size) > max_total_storage_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Uploading this file would exceed your total storage quota.")

    # 3. Save the file
    file_extension = os.path.splitext(file.filename)[1]
    stored_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        logger.error(f"Failed to save uploaded file {stored_filename} for user {current_user.email}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not save file.")

    # 4. Update database
    new_file_record = UploadedFile(
        user_id=current_user.id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        filesize_bytes=file_size,
        mimetype=file.content_type
    )
    db.add(new_file_record)
    
    current_user.uploaded_storage_bytes += file_size
    
    await db.commit()
    await db.refresh(new_file_record)
    
    logger.info(f"User {current_user.email} successfully uploaded file {new_file_record.id} ({file.filename}).")
    
    return new_file_record


@router.get("/", response_model=List[UploadedFileResponse])
async def get_uploaded_files(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Retrieves a list of all files uploaded by the current user.
    """
    ensure_premium_user(current_user)
    
    stmt = select(UploadedFile).where(UploadedFile.user_id == current_user.id).order_by(UploadedFile.created_at.desc())
    result = await db.execute(stmt)
    files = result.scalars().all()
    return files


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_uploaded_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Deletes a specific file uploaded by the user.
    """
    ensure_premium_user(current_user)

    stmt = select(UploadedFile).where(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id)
    result = await db.execute(stmt)
    file_to_delete = result.scalars().first()

    if not file_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found or you do not have permission to delete it.")

    # 1. Delete file from storage
    file_path = os.path.join(UPLOAD_DIR, file_to_delete.stored_filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # 2. Update database
    file_size = file_to_delete.filesize_bytes
    
    await db.delete(file_to_delete)
    
    current_user.uploaded_storage_bytes -= file_size
    if current_user.uploaded_storage_bytes < 0:
        current_user.uploaded_storage_bytes = 0 # Prevent negative values
        
    await db.commit()
    
    logger.info(f"User {current_user.email} deleted file {file_id}.")
    
    return

# Thêm vào cuối file file_router.py
from fastapi.responses import FileResponse
from ..db.models import MessageAttachment # Import model mới

@router.get("/download/{file_id}", summary="Download a file")
async def download_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    file_record_stmt = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    file_record = file_record_stmt.scalars().first()

    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    # --- KIỂM TRA QUYỀN TRUY CẬP ---
    # 1. Người dùng là chủ sở hữu file
    if file_record.user_id == current_user.id:
        pass # Cho phép download
    else:
        # 2. Hoặc, người dùng là người nhận của 1 tin nhắn có đính kèm file này
        permission_stmt = await db.execute(
            select(MessageAttachment)
            .join(InAppMessage, MessageAttachment.message_id == InAppMessage.id)
            .where(
                MessageAttachment.file_id == file_id,
                InAppMessage.receiver_id == current_user.id
            )
        )
        if not permission_stmt.scalars().first():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to download this file.")

    file_path = os.path.join(UPLOAD_DIR, file_record.stored_filename)
    if not os.path.exists(file_path):
        logger.error(f"File not found on disk but exists in DB: {file_path}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on server.")

    return FileResponse(path=file_path, filename=file_record.original_filename)