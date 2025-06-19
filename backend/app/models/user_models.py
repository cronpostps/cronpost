# # backend/models/user_model.py
# version 1.3 (Add upload file settings models)

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional
import uuid
import enum

from ..db.models import UserAccountStatusEnum, UserMembershipTypeEnum

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=20) # Giữ nguyên min/max length như trong tài liệu
    # user_name: Optional[str] = None # Tên người dùng, tùy chọn khi đăng ký

class UserSignIn(BaseModel):
    email: EmailStr
    password: str

class TokenData(BaseModel): # Model cho dữ liệu token trong response
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class RatingPointsEnum(str, enum.Enum):
    _1 = "_1"
    _2 = "_2"
    _3 = "_3"
    _4 = "_4"
    _5 = "_5"

class UserResponse(BaseModel):
    # Các trường cơ bản
    id: uuid.UUID
    email: EmailStr
    user_name: Optional[str] = None

    # Các trường cấu hình và trạng thái mà frontend cần
    account_status: UserAccountStatusEnum
    membership_type: UserMembershipTypeEnum
    timezone: str
    language: str
    use_pin_for_all_actions: bool
    checkin_on_signin: bool
    is_confirmed_by_email: bool

    # Các trường về giới hạn và dung lượng
    uploaded_storage_bytes: int
    storage_limit_gb: int
    messages_remaining: int

    # Các trường về lịch trình (nếu có)
    next_clc_prompt_at: Optional[datetime] = None
    wct_active_ends_at: Optional[datetime] = None
    next_fns_send_at: Optional[datetime] = None

    # Các trường về giới hạn độ dài tin nhắn
    max_message_chars_free: int
    max_message_chars_premium: int

    class Config:
        from_attributes = True
        use_enum_values = True

# SMTP Settings Models
class UserSmtpSettingsResponse(BaseModel):
    """Schema for returning SMTP settings, excluding sensitive data."""
    smtp_server: str
    smtp_port: int
    smtp_sender_email: str
    is_active: bool

    class Config:
        from_attributes = True

class UserSmtpSettingsUpdate(BaseModel):
    """Schema for creating or updating SMTP settings."""
    smtp_server: str
    smtp_port: int
    smtp_sender_email: EmailStr
    smtp_password: str

class SmtpTestResponse(BaseModel):
    """Response model for SMTP test results."""
    success: bool
    message: str

class UploadedFileResponse(BaseModel):
    """Schema for returning uploaded file details."""
    id: uuid.UUID
    original_filename: str
    filesize_bytes: int
    mimetype: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True