# # backend/models/user_model.py
# version 1.0

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import uuid # Dùng cho id người dùng từ Supabase

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
    # user_id: Optional[uuid.UUID] = None # Có thể thêm ID user nếu cần

class UserResponse(BaseModel): # Model cho thông tin user trả về sau khi đăng nhập/đăng ký
    id: uuid.UUID
    email: EmailStr
    # user_name: Optional[str] = None
    # Thêm các trường khác bạn muốn trả về sau khi user đăng nhập/đăng ký thành công
    # Ví dụ: account_status, membership_type

    class Config:
        from_attributes = True # Cho phép Pydantic đọc dữ liệu từ ORM models (nếu sau này dùng)
                               # Hoặc từ đối tượng User của Supabase