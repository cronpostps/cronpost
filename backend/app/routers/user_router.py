# backend/app/routers/user_router.py
# Version: 1.0 (Handles user-specific endpoints like /users/me)

import logging
import uuid
from typing import Optional, List # Thêm List nếu trả về danh sách

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field # Import Field nếu cần cho Pydantic model

# Import các thành phần cần thiết
from ..db.database import get_db_session
from ..db.models import User, UserAccountStatusEnum, UserMembershipTypeEnum # Import các Enum cần thiết
from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select # Không cần select ở đây nếu chỉ get by id

# Import dependency để lấy user hiện tại
from ..core.security import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["Users"],  # Tag cho API docs
    dependencies=[Depends(get_current_active_user)] # Áp dụng cho tất cả các route trong router này
)

# --- Pydantic Models for User Data Response ---
# Chúng ta có thể định nghĩa một model riêng cho response của /users/me
# để chỉ trả về những thông tin cần thiết và an toàn.
# Hoặc tái sử dụng UserResponse từ auth_router nếu nó phù hợp (nhưng UserResponse có 'message')
# Tạo model mới UserProfileResponse sẽ tốt hơn.

class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    user_name: Optional[str] = None
    provider: Optional[str] = None
    is_confirmed_by_email: bool
    account_status: UserAccountStatusEnum 
    membership_type: UserMembershipTypeEnum
    timezone: Optional[str] = None
    language: Optional[str] = None
    # Thêm các trường khác bạn muốn trả về cho frontend dashboard
    # Ví dụ:
    # uploaded_storage_bytes: int
    # messages_remaining: Optional[int] = None 
    # (messages_remaining cần tính toán, có thể không trả về trực tiếp từ model User)

    class Config:
        from_attributes = True


@router.get("/me", response_model=UserProfileResponse, summary="Get current user profile")
async def read_users_me(
    current_user: User = Depends(get_current_active_user) # User đã được xác thực
):
    """
    Retrieve details for the currently authenticated user.
    """
    logger.info(f"Fetching profile for user: {current_user.email}")
    
    # Bạn có thể muốn tính toán messages_remaining ở đây nếu cần
    # Ví dụ: messages_remaining = MAX_MESSAGES_FOR_TYPE - current_message_count

    return current_user # FastAPI sẽ tự động chuyển đổi User ORM model sang UserProfileResponse

# Có thể thêm các endpoint khác liên quan đến user ở đây sau này, ví dụ:
# PUT /me (để cập nhật profile)
# POST /me/change-password