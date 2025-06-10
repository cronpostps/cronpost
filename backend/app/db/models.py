# /backend/app/db/models.py
# Version: 2.8.0
# Changelog:
# - Added UserBlock and SimpleCronMessage models to match init.sql v2.8.0.
# - Added corresponding relationships to the User model.
# - Added new Enum types for SCM.

import enum
import uuid
from datetime import datetime, timezone as dt_timezone

from sqlalchemy import (
    Column, Text, Boolean, DateTime, Integer, ForeignKey,
    Enum as SQLAlchemyEnum, Time, Date, String, BigInteger, PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from .database import Base

# --- Định nghĩa các lớp Python Enum ---
class UserAccountStatusEnum(str, enum.Enum): INS='INS'; ANS_CLC='ANS_CLC'; ANS_WCT='ANS_WCT'; FNS='FNS'
class UserMembershipTypeEnum(str, enum.Enum): free='free'; premium='premium'
class CLCTypeEnum(str, enum.Enum): every_day='every_day'; specific_days='specific_days'; day_of_week='day_of_week'; date_of_month='date_of_month'; date_of_year='date_of_year'; specific_date_in_year='specific_date_in_year'
class DayOfWeekEnum(str, enum.Enum): Mon='Mon'; Tue='Tue'; Wed='Wed'; Thu='Thu'; Fri='Fri'; Sat='Sat'; Sun='Sun'
class WTCDurationUnitEnum(str, enum.Enum): minutes='minutes'; hours='hours'
class MessageOverallStatusEnum(str, enum.Enum): pending='pending'; processing='processing'; partially_sent='partially_sent'; sent='sent'; failed='failed'; cancelled='cancelled'
class ReceiverChannelEnum(str, enum.Enum): email='email'; telegram='telegram'
class IndividualSendStatusEnum(str, enum.Enum): pending='pending'; sent='sent'; failed='failed'; skipped='skipped'
class FMScheduleTriggerTypeEnum(str, enum.Enum): days_after_im_sent='days_after_im_sent'; day_of_week='day_of_week'; date_of_month='date_of_month'; date_of_year='date_of_year'; specific_date='specific_date'
class SendingAttemptStatusEnum(str, enum.Enum): success='success'; failed='failed'; retrying='retrying'
class CheckinMethodEnum(str, enum.Enum): login_auto='login_auto'; manual_button='manual_button'; email_link='email_link'; telegram_command='telegram_command'; pin_input='pin_input'
class OttOptInStatusEnum(str, enum.Enum): pending_verification='pending_verification'; active='active'; revoked_by_receiver='revoked_by_receiver'; revoked_by_user='revoked_by_user'; failed_verification='failed_verification'; unlinked='unlinked'
class RatingPointsEnum(str, enum.Enum): _1='_1'; _2='_2'; _3='_3'; _4='_4'; _5='_5'
# ENUMs mới
class SCMScheduleTypeEnum(str, enum.Enum): loop='loop'; unloop='unloop'
class SCMStatusEnum(str, enum.Enum): active='active'; inactive='inactive'; paused='paused'


# --- Định nghĩa các Model Bảng ---

class User(Base):
    __tablename__ = 'users'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text)
    google_id = Column(Text, unique=True)
    user_name = Column(Text)
    pin_code = Column(Text)
    pin_code_question = Column(Text)
    pin_recovery_code_hash = Column(Text)
    pin_recovery_code_used = Column(Boolean, default=False, nullable=False)
    is_confirmed_by_email = Column(Boolean, default=False, nullable=False)
    trust_verifier_email = Column(Text)
    use_pin_for_all_actions = Column(Boolean, default=False, nullable=False)
    checkin_on_signin = Column(Boolean, default=False, nullable=False)
    timezone = Column(Text, default='Etc/UTC', nullable=False)
    language = Column(Text, default='en', nullable=False)
    account_status = Column(SQLAlchemyEnum(UserAccountStatusEnum, name='user_account_status_enum', create_type=False), default=UserAccountStatusEnum.INS, nullable=False)
    membership_type = Column(SQLAlchemyEnum(UserMembershipTypeEnum, name='user_membership_type_enum', create_type=False), default=UserMembershipTypeEnum.free, nullable=False)
    membership_expires_at = Column(DateTime(timezone=True))
    last_activity_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    last_successful_checkin_at = Column(DateTime(timezone=True))
    failed_pin_attempts = Column(Integer, default=0, nullable=False)
    account_locked_until = Column(DateTime(timezone=True))
    account_locked_reason = Column(Text)
    fns_stop_token_hash = Column(Text)
    fns_stop_token_generated_at = Column(DateTime(timezone=True))
    fns_stop_token_expires_at = Column(DateTime(timezone=True))
    is_fns_stop_token_used = Column(Boolean, default=False, nullable=False)
    user_telegram_id = Column(Text, unique=True)
    user_telegram_username = Column(Text)
    telegram_link_status = Column(SQLAlchemyEnum(OttOptInStatusEnum, name='ott_opt_in_status_enum', create_type=False), default=OttOptInStatusEnum.unlinked, nullable=False)
    provider = Column(Text, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    uploaded_storage_bytes = Column(BigInteger, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)

    # Relationships
    email_confirmations = relationship("EmailConfirmation", back_populates="user", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan")
    configuration = relationship("UserConfiguration", uselist=False, back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    checkin_logs = relationship("CheckinLog", back_populates="user", cascade="all, delete-orphan")
    ott_optins = relationship("ReceiverOttOptin", back_populates="user", cascade="all, delete-orphan")
    review = relationship("UserReview", uselist=False, back_populates="user", cascade="all, delete-orphan")
    uploaded_files = relationship("UploadedFile", back_populates="user", cascade="all, delete-orphan")
    message_threads_as_user1 = relationship("MessageThread", foreign_keys="[MessageThread.user1_id]", back_populates="user1", cascade="all, delete-orphan")
    message_threads_as_user2 = relationship("MessageThread", foreign_keys="[MessageThread.user2_id]", back_populates="user2", cascade="all, delete-orphan")
    sent_in_app_messages = relationship("InAppMessage", foreign_keys="[InAppMessage.sender_id]", back_populates="sender", cascade="all, delete-orphan")
    received_in_app_messages = relationship("InAppMessage", foreign_keys="[InAppMessage.receiver_id]", back_populates="receiver", cascade="all, delete-orphan")
    # Relationships cho bảng mới
    simple_cron_messages = relationship("SimpleCronMessage", back_populates="user", cascade="all, delete-orphan")
    user_blocks = relationship("UserBlock", foreign_keys="[UserBlock.blocker_user_id]", back_populates="blocker", cascade="all, delete-orphan")

class EmailConfirmation(Base):
    __tablename__ = 'email_confirmations'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    email = Column(Text, nullable=False)
    confirmation_token = Column(Text, unique=True, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=False)
    is_confirmed = Column(Boolean, default=False, nullable=False)
    confirmed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="email_confirmations")

class PasswordResetToken(Base):
    __tablename__ = 'password_reset_tokens'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    reset_token_hash = Column(Text, unique=True, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="password_reset_tokens")

class LoginHistory(Base):
    __tablename__ = 'login_history'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    login_time = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    ip_address = Column(INET)
    user_agent = Column(Text)
    device_os = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="login_history")

class UserConfiguration(Base):
    __tablename__ = 'user_configurations'
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), primary_key=True)
    clc_type = Column(SQLAlchemyEnum(CLCTypeEnum, name='clc_type_enum', create_type=False), default=CLCTypeEnum.every_day, nullable=False)
    clc_day_number_interval = Column(Integer); clc_day_of_week = Column(SQLAlchemyEnum(DayOfWeekEnum, name='day_of_week_enum', create_type=False))
    clc_date_of_month = Column(Integer); clc_date_of_year = Column(Text); clc_specific_date = Column(Date)
    clc_prompt_time = Column(Time, default='09:00:00', nullable=False)
    wct_duration_value = Column(Integer, default=1, nullable=False)
    wct_duration_unit = Column(SQLAlchemyEnum(WTCDurationUnitEnum, name='wct_duration_unit_enum', create_type=False), default=WTCDurationUnitEnum.hours, nullable=False)
    is_clc_enabled = Column(Boolean, default=False, nullable=False)
    next_clc_prompt_at = Column(DateTime(timezone=True)); wct_active_ends_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="configuration")

class UploadedFile(Base):
    __tablename__ = 'uploaded_files'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    original_filename = Column(Text, nullable=False)
    stored_filename = Column(Text, nullable=False, unique=True)
    filesize_bytes = Column(BigInteger, nullable=False)
    mimetype = Column(Text)
    storage_location = Column(Text, default='local', nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="uploaded_files")
    messages_attached_to = relationship("Message", back_populates="attachment_file")
    in_app_messages_attached_to = relationship("InAppMessage", back_populates="attachment_file")


class Message(Base):
    __tablename__ = 'messages'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    message_order = Column(Integer, default=0, nullable=False)
    message_title = Column(Text)
    message_content = Column(Text, nullable=False)
    is_initial_message = Column(Boolean, default=False, nullable=False)
    attachment_file_id = Column(UUID(as_uuid=True), ForeignKey('uploaded_files.id', ondelete="SET NULL"), nullable=True)
    overall_send_status = Column(SQLAlchemyEnum(MessageOverallStatusEnum, name='message_overall_status_enum', create_type=False), default=MessageOverallStatusEnum.pending, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="messages")
    receivers = relationship("MessageReceiver", back_populates="message", cascade="all, delete-orphan")
    fm_schedule = relationship("FmSchedule", uselist=False, back_populates="message", cascade="all, delete-orphan")
    attachment_file = relationship("UploadedFile", back_populates="messages_attached_to")

class MessageReceiver(Base):
    __tablename__ = 'message_receivers'; id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    message_id = Column(UUID(as_uuid=True), ForeignKey('messages.id', ondelete="CASCADE"), nullable=False)
    receiver_channel = Column(SQLAlchemyEnum(ReceiverChannelEnum, name='receiver_channel_enum', create_type=False), nullable=False)
    receiver_address = Column(Text, nullable=False); individual_send_status = Column(SQLAlchemyEnum(IndividualSendStatusEnum, name='individual_send_status_enum', create_type=False), default=IndividualSendStatusEnum.pending, nullable=False)
    send_attempts = Column(Integer, default=0, nullable=False); last_attempt_at = Column(DateTime(timezone=True)); failure_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False); updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    message = relationship("Message", back_populates="receivers")

class FmSchedule(Base):
    __tablename__ = 'fm_schedules'
    message_id = Column(UUID(as_uuid=True), ForeignKey('messages.id', ondelete="CASCADE"), primary_key=True)
    trigger_type = Column(SQLAlchemyEnum(FMScheduleTriggerTypeEnum, name='fm_schedule_trigger_type_enum', create_type=False), nullable=False)
    days_after_im_value = Column(Integer)
    day_of_week_value = Column(SQLAlchemyEnum(DayOfWeekEnum, name='day_of_week_enum', create_type=False))
    date_of_month_value = Column(Integer)
    date_of_year_value = Column(Text)
    specific_date_value = Column(Date)
    sending_time_of_day = Column(Time, default='09:00:00', nullable=False)
    repeat_number = Column(Integer, default=1, nullable=False)
    next_send_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    message = relationship("Message", back_populates="fm_schedule")

class SendingHistory(Base):
    __tablename__ = 'sending_history'; id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    message_id = Column(UUID(as_uuid=True), ForeignKey('messages.id', ondelete="CASCADE"), nullable=False); receiver_id = Column(UUID(as_uuid=True), ForeignKey('message_receivers.id', ondelete="CASCADE"), nullable=False)
    sending_method = Column(SQLAlchemyEnum(ReceiverChannelEnum, name='receiver_channel_enum', create_type=False), nullable=False); sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    status = Column(SQLAlchemyEnum(SendingAttemptStatusEnum, name='sending_attempt_status_enum', create_type=False), nullable=False); status_details = Column(Text); receiver_address_snapshot = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)

class CheckinLog(Base):
    __tablename__ = 'checkin_log'; id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False); checkin_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    method = Column(SQLAlchemyEnum(CheckinMethodEnum, name='checkin_method_enum', create_type=False), nullable=False); created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="checkin_logs")

class ReceiverOttOptin(Base):
    __tablename__ = 'receiver_ott_optins'; id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    sender_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False); receiver_email_identifier = Column(Text, nullable=False)
    channel = Column(SQLAlchemyEnum(ReceiverChannelEnum, name='receiver_channel_enum', create_type=False), nullable=False); platform_specific_id = Column(Text)
    status = Column(SQLAlchemyEnum(OttOptInStatusEnum, name='ott_opt_in_status_enum', create_type=False), default=OttOptInStatusEnum.pending_verification, nullable=False)
    opt_in_token = Column(Text, unique=True); opt_in_token_expires_at = Column(DateTime(timezone=True)); verified_at = Column(DateTime(timezone=True)); revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False); updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="ott_optins")

class UserReview(Base):
    __tablename__ = 'user_reviews'; user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), primary_key=True)
    rating_points = Column(SQLAlchemyEnum(RatingPointsEnum, name='rating_points_enum', create_type=False), nullable=False); comment = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False); updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    user = relationship("User", back_populates="review")


class SystemSetting(Base):
    __tablename__ = 'system_settings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(Text, unique=True, nullable=False)
    setting_value = Column(Text); description = Column(Text)
    value_type = Column(Text, default='string', nullable=False)
    admin_editable = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)

class MessageThread(Base):
    __tablename__ = 'message_threads'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user1_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    user2_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    last_message_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc))
    user1_last_read_at = Column(DateTime(timezone=True))
    user2_last_read_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)

    user1 = relationship("User", foreign_keys=[user1_id], back_populates="message_threads_as_user1")
    user2 = relationship("User", foreign_keys=[user2_id], back_populates="message_threads_as_user2")
    messages = relationship("InAppMessage", back_populates="thread", cascade="all, delete-orphan", order_by="InAppMessage.sent_at")


class InAppMessage(Base):
    __tablename__ = 'in_app_messages'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    thread_id = Column(UUID(as_uuid=True), ForeignKey('message_threads.id', ondelete="CASCADE"), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    receiver_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    read_at = Column(DateTime(timezone=True))
    attachment_file_id = Column(UUID(as_uuid=True), ForeignKey('uploaded_files.id', ondelete="SET NULL"), nullable=True)
    is_deleted_by_sender = Column(Boolean, default=False, nullable=False)
    is_deleted_by_receiver = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    
    thread = relationship("MessageThread", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_in_app_messages")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_in_app_messages")
    attachment_file = relationship("UploadedFile", back_populates="in_app_messages_attached_to")

class UserBlock(Base):
    __tablename__ = 'user_blocks'
    blocker_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), primary_key=True)
    blocked_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    
    blocker = relationship("User", foreign_keys=[blocker_user_id], back_populates="user_blocks")

class SimpleCronMessage(Base):
    __tablename__ = 'simple_cron_messages'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    title = Column(Text)
    content = Column(Text, nullable=False)
    receiver_address = Column(Text, nullable=False)
    schedule_type = Column(SQLAlchemyEnum(SCMScheduleTypeEnum, name='scm_schedule_type_enum', create_type=False), nullable=False)
    loop_interval_minutes = Column(Integer)
    unloop_send_at = Column(DateTime(timezone=True))
    repeat_number = Column(Integer, default=1, nullable=False)
    current_repetition = Column(Integer, default=0, nullable=False)
    status = Column(SQLAlchemyEnum(SCMStatusEnum, name='scm_status_enum', create_type=False), default=SCMStatusEnum.active, nullable=False)
    last_sent_at = Column(DateTime(timezone=True))
    next_send_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(dt_timezone.utc), nullable=False)

    user = relationship("User", back_populates="simple_cron_messages")