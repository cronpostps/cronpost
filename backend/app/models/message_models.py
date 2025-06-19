# /backend/app/models/message_models.py
# Version: 2.7.1

from pydantic import BaseModel, Field, constr, validator, EmailStr
from typing import Optional, List
from datetime import time, date, datetime
import uuid

# Import Enums từ db.models để đảm bảo tính nhất quán
from ..db.models import (
    CLCTypeEnum,
    DayOfWeekEnum,
    WTCDurationUnitEnum,
    UserAccountStatusEnum,
    MessageOverallStatusEnum,
    FMScheduleTriggerTypeEnum
)

from ..models.user_models import UploadedFileResponse

# --- Common Base Models ---
class MessageContentBase(BaseModel):
    title: Optional[str] = Field(None, max_length=255, examples=["Follow-up Note"])
    content: constr(min_length=1) = Field(..., examples=["This is a follow-up message..."])

class CLCScheduleBase(BaseModel):
    clc_type: CLCTypeEnum = Field(default=CLCTypeEnum.every_day, description="Type of CLC loop.")
    clc_prompt_time: time = Field(default=time(9,0,0), description="Time of day for CLC prompt in user's timezone.")
    clc_day_number_interval: Optional[int] = Field(None, ge=2, le=999, description="Interval in days for 'specific_days' CLC type (min 2).")
    clc_day_of_week: Optional[DayOfWeekEnum] = Field(None, description="Day of the week for 'day_of_week' CLC type.")
    clc_date_of_month: Optional[int] = Field(None, ge=1, le=31, description="Date of the month for 'date_of_month' CLC type.")
    clc_date_of_year: Optional[constr(pattern=r"^(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[012])$")] = Field(None, description="Date of the year (dd/MM) for 'date_of_year' CLC type.", examples=["29/02"])
    clc_specific_date: Optional[date] = Field(None, description="Specific date for 'specific_date_in_year' (Unloop IM) CLC type.")

class WCTScheduleBase(BaseModel):
    wct_duration_value: int = Field(default=1, ge=1, description="Duration value for WCT.")
    wct_duration_unit: WTCDurationUnitEnum = Field(default=WTCDurationUnitEnum.hours, description="Unit for WCT duration (minutes or hours).")

class InitialMessageScheduleConfig(CLCScheduleBase, WCTScheduleBase):
    pass

class InitialMessageCreateUpdateRequest(BaseModel):
    message: MessageContentBase
    schedule: InitialMessageScheduleConfig

class UserConfigurationResponse(InitialMessageScheduleConfig):
    user_id: uuid.UUID
    is_clc_enabled: bool
    next_clc_prompt_at: Optional[datetime] = None
    wct_active_ends_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        use_enum_values = True

class MessageResponseBase(MessageContentBase):
    id: uuid.UUID
    user_id: uuid.UUID
    is_initial_message: bool
    overall_send_status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        use_enum_values = True

class InitialMessageWithScheduleResponse(BaseModel):
    message: MessageResponseBase
    configuration: UserConfigurationResponse
    account_status_after_update: UserAccountStatusEnum

    class Config:
        use_enum_values = True

class FmScheduleConfigBase(BaseModel):
    trigger_type: FMScheduleTriggerTypeEnum = Field(..., description="How the FM sending is triggered.")
    sending_time_of_day: time = Field(default=time(9,0,0), description="Time of day to send the FM in user's timezone.")
    repeat_number: int = Field(default=1, ge=0, le=99, description="Total number of times to send this message. 1 means send once. 0 is inactive.")
    days_after_im_value: Optional[int] = Field(None, ge=1, le=999)
    day_of_week_value: Optional[DayOfWeekEnum] = Field(None)
    date_of_month_value: Optional[int] = Field(None, ge=1, le=31)
    date_of_year_value: Optional[constr(pattern=r"^(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[012])$")] = Field(None)
    specific_date_value: Optional[date] = Field(None)

    @validator('repeat_number')
    def specific_date_no_repeat(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.specific_date and v > 1:
            raise ValueError("repeat_number must be 1 for 'specific_date' trigger type.")
        return v

    @validator('days_after_im_value', always=True)
    def check_days_after_im(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.days_after_im_sent and v is None:
            raise ValueError("'days_after_im_value' is required for 'days_after_im_sent' trigger type.")
        return v

class FollowMessageCreateRequest(BaseModel):
    message: MessageContentBase
    schedule: FmScheduleConfigBase

class FollowMessageUpdateRequest(BaseModel):
    message: Optional[MessageContentBase] = None
    schedule: Optional[FmScheduleConfigBase] = None

class FmScheduleResponse(FmScheduleConfigBase):
    message_id: uuid.UUID
    next_send_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        use_enum_values = True

class FollowMessageResponse(MessageResponseBase):
    fm_schedule: Optional[FmScheduleResponse] = None
    message_order: int

# --- In-App Messaging Models ---

class InAppMessageCreate(BaseModel):
    receiver_emails: List[EmailStr]
    subject: Optional[str] = Field(None, max_length=255)
    content: str = Field(..., description="Nội dung tin nhắn.")
    attachment_file_ids: Optional[List[uuid.UUID]] = Field([], description="Danh sách các UUID của file muốn đính kèm.")

class MessageThreadParticipantResponse(BaseModel):
    id: uuid.UUID
    user_name: Optional[str] = None
    email: EmailStr
    class Config:
        from_attributes = True

class MessageThreadResponse(BaseModel):
    id: uuid.UUID
    other_participant: MessageThreadParticipantResponse
    last_message_content: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_messages_count: int = 0
    class Config:
        from_attributes = True

class UnreadCountResponse(BaseModel):
    unread_count: int

class InAppMessageResponse(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    subject: Optional[str] = None
    content: str
    sent_at: datetime
    read_at: Optional[datetime] = None
    attachments: List[UploadedFileResponse] = Field([], description="Danh sách các file được đính kèm.")
    sender: MessageThreadParticipantResponse
    receiver: MessageThreadParticipantResponse

    class Config:
        from_attributes = True