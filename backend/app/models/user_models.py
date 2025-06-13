# # backend/models/user_model.py
# version 1.2 (Add SMTP settings models)

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import uuid
import enum

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

class UserResponse(BaseModel): # Model cho thông tin user trả về sau khi đăng nhập/đăng ký
    id: uuid.UUID
    email: EmailStr
    rating_points: Optional[RatingPointsEnum] = None

    class Config:
        from_attributes = True

# SMTP Settings Models

class UserSmtpSettingsResponse(BaseModel):
    """Schema for returning SMTP settings, excluding sensitive data."""
    smtp_server: str
    smtp_port: int
    smtp_sender_email: str
    is_active: bool

    class Config:
        orm_mode = True

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