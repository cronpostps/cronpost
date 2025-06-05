# backend/app/models/message_models.py
# Version: 1.3
# Description: Pydantic models for message operations, including IM and FM scheduling.
# Changelog:
# - Added Pydantic models for Follow Message (FM) creation, update, and scheduling.

from pydantic import BaseModel, Field, constr, validator
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
    FMScheduleTriggerTypeEnum # Thêm Enum cho FM
)

# --- Common Base Models (Giữ nguyên) ---
class MessageContentBase(BaseModel):
    title: Optional[str] = Field(None, max_length=255, examples=["Follow-up Note"])
    content: constr(min_length=1, max_length=5000) = Field(..., examples=["This is a follow-up message..."])

class CLCScheduleBase(BaseModel): # Dùng cho IM
    clc_type: CLCTypeEnum = Field(default=CLCTypeEnum.every_day, description="Type of CLC loop.")
    clc_prompt_time: time = Field(default=time(9,0,0), description="Time of day for CLC prompt in user's timezone.")
    clc_day_number_interval: Optional[int] = Field(None, ge=2, le=999, description="Interval in days for 'specific_days' CLC type (min 2).") 
    clc_day_of_week: Optional[DayOfWeekEnum] = Field(None, description="Day of the week for 'day_of_week' CLC type.")
    clc_date_of_month: Optional[int] = Field(None, ge=1, le=31, description="Date of the month for 'date_of_month' CLC type.")
    clc_date_of_year: Optional[constr(pattern=r"^(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[012])$")] = Field(None, description="Date of the year (dd/MM) for 'date_of_year' CLC type.", examples=["29/02"])
    clc_specific_date: Optional[date] = Field(None, description="Specific date for 'specific_date_in_year' (Unloop IM) CLC type.")

class WCTScheduleBase(BaseModel): # Dùng cho IM
    wct_duration_value: int = Field(default=1, ge=1, description="Duration value for WCT.")
    wct_duration_unit: WTCDurationUnitEnum = Field(default=WTCDurationUnitEnum.hours, description="Unit for WCT duration (minutes or hours).")

# --- Initial Message (IM) Models (Giữ nguyên) ---
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
        use_enum_values = True # Thêm use_enum_values

class MessageResponseBase(MessageContentBase):
    id: uuid.UUID
    user_id: uuid.UUID
    is_initial_message: bool
    overall_send_status: str 
    created_at: datetime
    updated_at: datetime
    # attachment_file_id: Optional[uuid.UUID] = None 

    class Config:
        from_attributes = True
        use_enum_values = True

class InitialMessageWithScheduleResponse(BaseModel):
    message: MessageResponseBase
    configuration: UserConfigurationResponse
    account_status_after_update: UserAccountStatusEnum

    class Config:
        use_enum_values = True

# --- Follow Message (FM) Models ---
class FmScheduleConfigBase(BaseModel):
    trigger_type: FMScheduleTriggerTypeEnum = Field(..., description="How the FM sending is triggered relative to IM or other events.")
    sending_time_of_day: time = Field(default=time(9,0,0), description="Time of day to send the FM in user's timezone.")
    repeat_count: int = Field(default=0, ge=0, le=99, description="Number of times to repeat sending this FM (0 means send once). Not applicable for 'specific_date'.") # 

    # For 'days_after_im_sent'
    days_after_im_value: Optional[int] = Field(None, ge=1, le=999, description="Number of days after IM is sent. Required if trigger_type is 'days_after_im_sent'.") # 
    
    # For 'day_of_week' (after IM)
    day_of_week_value: Optional[DayOfWeekEnum] = Field(None, description="Day of the week to send. Required if trigger_type is 'day_of_week'.") # 
    
    # For 'date_of_month' (after IM)
    date_of_month_value: Optional[int] = Field(None, ge=1, le=31, description="Date of the month to send. Required if trigger_type is 'date_of_month'.") # 
    
    # For 'date_of_year' (after IM, annually)
    date_of_year_value: Optional[constr(pattern=r"^(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[012])$")] = Field(None, description="Date of the year (dd/MM) to send annually. Required if trigger_type is 'date_of_year'.") # 
    
    # For 'specific_date' (one-time, specific dd/mm/yyyy)
    specific_date_value: Optional[date] = Field(None, description="Specific date (YYYY-MM-DD) to send. Required if trigger_type is 'specific_date'. Repeat_count must be 0.") # 

    @validator('repeat_count')
    def specific_date_no_repeat(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.specific_date and v != 0:
            raise ValueError("repeat_count must be 0 for 'specific_date' trigger type.") # 
        return v

    # Thêm các validator để đảm bảo các trường cần thiết được cung cấp dựa trên trigger_type
    @validator('days_after_im_value', always=True)
    def check_days_after_im(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.days_after_im_sent and v is None:
            raise ValueError("'days_after_im_value' is required for 'days_after_im_sent' trigger type.")
        return v

    @validator('day_of_week_value', always=True)
    def check_day_of_week(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.day_of_week and v is None:
            raise ValueError("'day_of_week_value' is required for 'day_of_week' trigger type.")
        return v

    @validator('date_of_month_value', always=True)
    def check_date_of_month(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.date_of_month and v is None:
            raise ValueError("'date_of_month_value' is required for 'date_of_month' trigger type.")
        return v
    
    @validator('date_of_year_value', always=True)
    def check_date_of_year(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.date_of_year and v is None:
            raise ValueError("'date_of_year_value' is required for 'date_of_year' trigger type.")
        return v

    @validator('specific_date_value', always=True)
    def check_specific_date(cls, v, values):
        if values.get('trigger_type') == FMScheduleTriggerTypeEnum.specific_date and v is None:
            raise ValueError("'specific_date_value' is required for 'specific_date' trigger type.")
        return v

class FollowMessageCreateRequest(BaseModel):
    message: MessageContentBase
    schedule: FmScheduleConfigBase
    # message_order: Optional[int] = Field(None, description="Order of this FM if multiple FMs are sent on the same day. Backend can auto-assign if None.")

class FollowMessageUpdateRequest(BaseModel): # Tương tự Create, nhưng mọi trường là Optional
    message: Optional[MessageContentBase] = None
    schedule: Optional[FmScheduleConfigBase] = None
    # message_order: Optional[int] = None

class FmScheduleResponse(FmScheduleConfigBase):
    message_id: uuid.UUID
    next_send_at: Optional[datetime] = None
    is_active: bool
    current_repetition: int

    class Config:
        from_attributes = True
        use_enum_values = True

class FollowMessageResponse(MessageResponseBase): # Kế thừa từ MessageResponseBase
    fm_schedule: Optional[FmScheduleResponse] = None # FM sẽ có lịch trình riêng
    message_order: int # FM cũng có message_order