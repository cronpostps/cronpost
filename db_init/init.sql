-- SQL KHỞI TẠO POSTGRES DATABASE DUY NHẤT
-- VERSION: 2.10.1
-- Mô tả: Sửa lỗi cú pháp trong câu lệnh INSERT...ON CONFLICT. Thêm bảng email_checkin_settings và pin_attempts.

-- KÍCH HOẠT EXTENSION CẦN THIẾT
CREATE EXTENSION IF NOT EXISTS moddatetime; 
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- TẠO CÁC KIỂU ENUM
CREATE TYPE public.user_account_status_enum AS ENUM ('INS','ANS_CLC','ANS_WCT','FNS');
CREATE TYPE public.user_membership_type_enum AS ENUM ('free','premium');
CREATE TYPE public.clc_type_enum AS ENUM ('every_day','specific_days','day_of_week','date_of_month','date_of_year','specific_date_in_year');
CREATE TYPE public.day_of_week_enum AS ENUM ('Mon','Tue','Wed','Thu','Fri','Sat','Sun');
CREATE TYPE public.wct_duration_unit_enum AS ENUM ('minutes','hours');
CREATE TYPE public.message_overall_status_enum AS ENUM ('pending','processing','partially_sent','sent','failed','cancelled');
CREATE TYPE public.sending_method_enum AS ENUM ('cronpost_email', 'in_app_messaging', 'user_email');
CREATE TYPE public.receiver_channel_enum AS ENUM ('email','telegram');
CREATE TYPE public.individual_send_status_enum AS ENUM ('pending','sent','failed','skipped');
CREATE TYPE public.fm_schedule_trigger_type_enum AS ENUM ('days_after_im_sent','day_of_week','date_of_month','date_of_year','specific_date');
CREATE TYPE public.sending_attempt_status_enum AS ENUM ('success','failed','retrying');
CREATE TYPE public.checkin_method_enum AS ENUM ('login_auto','manual_button','email_link','telegram_command','pin_input');
CREATE TYPE public.ott_opt_in_status_enum AS ENUM ('pending_verification','active','revoked_by_receiver','revoked_by_user','failed_verification','unlinked');
CREATE TYPE public.rating_points_enum AS ENUM ('_1','_2','_3','_4','_5');
CREATE TYPE public.scm_schedule_type_enum AS ENUM ('loop', 'unloop');
CREATE TYPE public.scm_status_enum AS ENUM ('active', 'inactive', 'paused');


-- TẠO CÁC BẢNG

CREATE TABLE public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    google_id TEXT UNIQUE,
    user_name TEXT,
    pin_code TEXT,
    pin_code_question TEXT,
    pin_recovery_code_hash TEXT,
    pin_recovery_code_used BOOLEAN DEFAULT FALSE NOT NULL,
    is_confirmed_by_email BOOLEAN DEFAULT FALSE NOT NULL,
    trust_verifier_email TEXT,
    use_pin_for_all_actions BOOLEAN DEFAULT FALSE NOT NULL,
    checkin_on_signin BOOLEAN DEFAULT FALSE NOT NULL,
    timezone TEXT DEFAULT 'Etc/UTC' NOT NULL,
    language TEXT DEFAULT 'en' NOT NULL,
    account_status public.user_account_status_enum DEFAULT 'INS' NOT NULL,
    membership_type public.user_membership_type_enum DEFAULT 'free' NOT NULL,
    membership_expires_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_successful_checkin_at TIMESTAMPTZ,
    failed_pin_attempts INT DEFAULT 0 NOT NULL,
    account_locked_until TIMESTAMPTZ,
    account_locked_reason TEXT,
    fns_stop_token_hash TEXT,
    fns_stop_token_generated_at TIMESTAMPTZ,
    fns_stop_token_expires_at TIMESTAMPTZ,
    is_fns_stop_token_used BOOLEAN DEFAULT FALSE NOT NULL,
    user_telegram_id TEXT UNIQUE,
    user_telegram_username TEXT,
    telegram_link_status public.ott_opt_in_status_enum DEFAULT 'unlinked' NOT NULL,
    provider TEXT,
    is_admin BOOLEAN DEFAULT FALSE NOT NULL,
    uploaded_storage_bytes BIGINT DEFAULT 0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.user_smtp_settings (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    smtp_server TEXT NOT NULL,
    smtp_port INT NOT NULL CHECK (smtp_port IN (465, 587)),
    smtp_sender_email TEXT NOT NULL,
    smtp_password_encrypted TEXT NOT NULL,
    is_active BOOLEAN DEFAULT FALSE NOT NULL,
    last_test_successful BOOLEAN,
    last_test_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.email_checkin_settings (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    use_checkin_token_email BOOLEAN NOT NULL DEFAULT FALSE,
    checkin_token TEXT UNIQUE,
    checkin_token_expires_at TIMESTAMPTZ,
    send_additional_reminder BOOLEAN NOT NULL DEFAULT FALSE,
    additional_reminder_minutes INT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.pin_attempts (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    attempt_time TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    is_successful BOOLEAN NOT NULL
);

CREATE TABLE public.email_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    confirmation_token TEXT UNIQUE NOT NULL,
    token_expires_at TIMESTAMPTZ NOT NULL,
    is_confirmed BOOLEAN DEFAULT FALSE NOT NULL,
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_email_confirmations_token UNIQUE (confirmation_token)
);

CREATE TABLE public.login_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    login_time TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    ip_address INET,
    user_agent TEXT,
    device_os TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.user_configurations (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    clc_type public.clc_type_enum NOT NULL DEFAULT 'every_day',
    clc_day_number_interval INT,
    clc_day_of_week public.day_of_week_enum,
    clc_date_of_month INT,
    clc_date_of_year TEXT,
    clc_specific_date DATE,
    clc_prompt_time TIME WITHOUT TIME ZONE NOT NULL DEFAULT '09:00:00',
    wct_duration_value INT NOT NULL DEFAULT 1,
    wct_duration_unit public.wct_duration_unit_enum NOT NULL DEFAULT 'hours',
    is_clc_enabled BOOLEAN DEFAULT FALSE NOT NULL,
    next_clc_prompt_at TIMESTAMPTZ,
    wct_active_ends_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.uploaded_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL UNIQUE,
    filesize_bytes BIGINT NOT NULL,
    mimetype TEXT,
    storage_location TEXT DEFAULT 'local' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    sending_method public.sending_method_enum NOT NULL DEFAULT 'cronpost_email',
    message_order INT NOT NULL DEFAULT 0,
    message_title TEXT,
    message_content TEXT NOT NULL,
    is_initial_message BOOLEAN DEFAULT FALSE NOT NULL,
    attachment_file_id UUID REFERENCES public.uploaded_files(id) ON DELETE SET NULL,
    overall_send_status public.message_overall_status_enum DEFAULT 'pending' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_user_message_order UNIQUE (user_id, message_order)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_user_unique_initial_message ON public.messages (user_id) WHERE (is_initial_message = TRUE);

CREATE TABLE public.message_receivers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
    receiver_channel public.receiver_channel_enum NOT NULL,
    receiver_address TEXT NOT NULL,
    individual_send_status public.individual_send_status_enum DEFAULT 'pending' NOT NULL,
    send_attempts INT DEFAULT 0 NOT NULL,
    last_attempt_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_message_receiver_channel_address UNIQUE (message_id, receiver_channel, receiver_address)
);

CREATE TABLE public.fm_schedules (
    message_id UUID PRIMARY KEY REFERENCES public.messages(id) ON DELETE CASCADE,
    trigger_type public.fm_schedule_trigger_type_enum NOT NULL,
    days_after_im_value INT,
    day_of_week_value public.day_of_week_enum,
    date_of_month_value INT,
    date_of_year_value TEXT, 
    specific_date_value DATE,
    sending_time_of_day TIME WITHOUT TIME ZONE NOT NULL DEFAULT '09:00:00',
    repeat_number INT DEFAULT 1 NOT NULL CHECK (repeat_number >= 0 AND repeat_number <= 99),
    next_send_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.sending_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
    receiver_id UUID NOT NULL REFERENCES public.message_receivers(id) ON DELETE CASCADE,
    sending_method_snapshot public.sending_method_enum NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    status public.sending_attempt_status_enum NOT NULL,
    status_details TEXT,
    receiver_address_snapshot TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.checkin_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    checkin_timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    method public.checkin_method_enum NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.receiver_ott_optins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    receiver_email_identifier TEXT NOT NULL,
    channel public.receiver_channel_enum NOT NULL,
    platform_specific_id TEXT,
    status public.ott_opt_in_status_enum NOT NULL DEFAULT 'pending_verification',
    opt_in_token TEXT UNIQUE,
    opt_in_token_expires_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_sender_receiver_email_channel UNIQUE (sender_user_id, receiver_email_identifier, channel)
);

CREATE TABLE public.password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    reset_token_hash TEXT UNIQUE NOT NULL, 
    token_expires_at TIMESTAMPTZ NOT NULL,
    is_used BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.message_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user1_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    user2_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    user1_last_read_at TIMESTAMPTZ,
    user2_last_read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT chk_message_thread_distinct_users CHECK (user1_id <> user2_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_message_thread_users ON public.message_threads (LEAST(user1_id, user2_id), GREATEST(user1_id, user2_id));

CREATE TABLE public.in_app_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES public.message_threads(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    receiver_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    read_at TIMESTAMPTZ,
    attachment_file_id UUID REFERENCES public.uploaded_files(id) ON DELETE SET NULL,
    is_deleted_by_sender BOOLEAN DEFAULT FALSE NOT NULL,
    is_deleted_by_receiver BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT chk_in_app_message_sender_receiver CHECK (sender_id <> receiver_id)
);

CREATE TABLE public.user_reviews (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    rating_points public.rating_points_enum NOT NULL,
    comment TEXT CHECK (char_length(comment) <= 300),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.system_settings (
    id INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    setting_key TEXT UNIQUE NOT NULL,
    setting_value TEXT,
    description TEXT,
    value_type TEXT DEFAULT 'string' NOT NULL CHECK (value_type IN ('string', 'integer', 'boolean', 'json', 'float')),
    admin_editable BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE public.user_blocks (
    blocker_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    blocked_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    PRIMARY KEY (blocker_user_id, blocked_user_id),
    CONSTRAINT chk_no_self_block CHECK (blocker_user_id <> blocked_user_id)
);

CREATE TABLE public.simple_cron_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    sending_method public.sending_method_enum NOT NULL DEFAULT 'cronpost_email',
    title TEXT,
    content TEXT NOT NULL,
    receiver_address TEXT NOT NULL,
    schedule_type public.scm_schedule_type_enum NOT NULL,
    loop_interval_minutes INT,
    unloop_send_at TIMESTAMPTZ,
    repeat_number INT NOT NULL DEFAULT 1,
    current_repetition INT NOT NULL DEFAULT 0,
    status public.scm_status_enum NOT NULL DEFAULT 'active',
    last_sent_at TIMESTAMPTZ,
    next_send_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);


-- TẠO CÁC TRIGGERS CHO `updated_at`
CREATE OR REPLACE FUNCTION public.check_fm_message_not_initial()
RETURNS TRIGGER AS $$
DECLARE is_im BOOLEAN;
BEGIN
    SELECT is_initial_message INTO is_im FROM public.messages WHERE id = NEW.message_id;
    IF is_im IS TRUE THEN
        RAISE EXCEPTION 'Constraint Violated: Cannot create FM schedule for an IM. Message ID % is IM.', NEW.message_id USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_before_insert_update_fm_schedules BEFORE INSERT OR UPDATE ON public.fm_schedules FOR EACH ROW EXECUTE FUNCTION public.check_fm_message_not_initial();
CREATE TRIGGER handle_updated_at_users BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_user_smtp_settings BEFORE UPDATE ON public.user_smtp_settings FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_email_checkin_settings BEFORE UPDATE ON public.email_checkin_settings FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_pin_attempts BEFORE UPDATE ON public.pin_attempts FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_email_confirmations BEFORE UPDATE ON public.email_confirmations FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_user_configurations BEFORE UPDATE ON public.user_configurations FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_messages BEFORE UPDATE ON public.messages FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_message_receivers BEFORE UPDATE ON public.message_receivers FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_fm_schedules BEFORE UPDATE ON public.fm_schedules FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_receiver_ott_optins BEFORE UPDATE ON public.receiver_ott_optins FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_user_reviews BEFORE UPDATE ON public.user_reviews FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_system_settings BEFORE UPDATE ON public.system_settings FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_password_reset_tokens BEFORE UPDATE ON public.password_reset_tokens FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_uploaded_files BEFORE UPDATE ON public.uploaded_files FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_message_threads BEFORE UPDATE ON public.message_threads FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_in_app_messages BEFORE UPDATE ON public.in_app_messages FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);
CREATE TRIGGER handle_updated_at_simple_cron_messages BEFORE UPDATE ON public.simple_cron_messages FOR EACH ROW EXECUTE PROCEDURE public.moddatetime (updated_at);


-- TẠO CÁC INDEXES
CREATE INDEX IF NOT EXISTS idx_pin_attempts_user_id_time ON public.pin_attempts(user_id, attempt_time DESC);
CREATE INDEX IF NOT EXISTS idx_email_checkin_settings_token ON public.email_checkin_settings(checkin_token);
CREATE INDEX IF NOT EXISTS idx_email_confirmations_user_id ON public.email_confirmations(user_id);
CREATE INDEX IF NOT EXISTS idx_email_confirmations_token ON public.email_confirmations(confirmation_token);
CREATE INDEX IF NOT EXISTS idx_login_history_user_id_time ON public.login_history(user_id, login_time DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON public.messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id_order ON public.messages(user_id, message_order);
CREATE INDEX IF NOT EXISTS idx_messages_attachment_file_id ON public.messages(attachment_file_id);
CREATE INDEX IF NOT EXISTS idx_message_receivers_message_id ON public.message_receivers(message_id);
CREATE INDEX IF NOT EXISTS idx_message_receivers_channel_address ON public.message_receivers(receiver_channel, receiver_address);
CREATE INDEX IF NOT EXISTS idx_sending_history_message_id ON public.sending_history(message_id);
CREATE INDEX IF NOT EXISTS idx_sending_history_receiver_id ON public.sending_history(receiver_id);
CREATE INDEX IF NOT EXISTS idx_sending_history_sent_at ON public.sending_history(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkin_log_user_id_timestamp ON public.checkin_log(user_id, checkin_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_receiver_ott_optins_sender_receiver_email_channel ON public.receiver_ott_optins(sender_user_id, receiver_email_identifier, channel);
CREATE INDEX IF NOT EXISTS idx_receiver_ott_optins_opt_in_token ON public.receiver_ott_optins(opt_in_token);
CREATE INDEX IF NOT EXISTS idx_system_settings_key ON public.system_settings(setting_key);
CREATE INDEX IF NOT EXISTS idx_users_user_telegram_id ON public.users(user_telegram_id) WHERE user_telegram_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON public.password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token_hash ON public.password_reset_tokens(reset_token_hash);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires_at ON public.password_reset_tokens(token_expires_at);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_user_id ON public.uploaded_files(user_id);
CREATE INDEX IF NOT EXISTS idx_message_threads_user1_id_user2_id ON public.message_threads(LEAST(user1_id, user2_id), GREATEST(user1_id, user2_id));
CREATE INDEX IF NOT EXISTS idx_message_threads_last_message_at ON public.message_threads(last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_in_app_messages_thread_id_sent_at ON public.in_app_messages(thread_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_in_app_messages_sender_id ON public.in_app_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_in_app_messages_receiver_id ON public.in_app_messages(receiver_id);
CREATE INDEX IF NOT EXISTS idx_in_app_messages_attachment_file_id ON public.in_app_messages(attachment_file_id);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked_id ON public.user_blocks(blocked_user_id);
CREATE INDEX IF NOT EXISTS idx_scm_user_id ON public.simple_cron_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_scm_next_send_at ON public.simple_cron_messages(next_send_at) WHERE status = 'active';


-- THÊM DỮ LIỆU MẶC ĐỊNH CHO system_settings
INSERT INTO public.system_settings (setting_key, setting_value, description, value_type, admin_editable) VALUES
    ('max_clc_start_offset_years', '100', 'Maximum years user can set CLC start time from now', 'integer', true),
    ('min_clc_start_offset_minutes', '30', 'Minimum minutes user must set CLC start time from now', 'integer', true),
    ('default_clc_type', 'every_day', 'Default CLC type for new users', 'string', true),
    ('default_clc_prompt_time', '09:00:00', 'Default time for CLC prompt (HH:MM:SS in user timezone)', 'string', true),
    ('default_wct_duration_hours', '1', 'Default WCT duration in hours', 'integer', true),
    ('min_wct_duration_minutes', '60', 'Minimum WCT duration in minutes (1 hour)', 'integer', true),
    ('max_wct_duration_minutes', '1440', 'Maximum WCT duration in minutes (24 hours)', 'integer', true),
    ('clc_specific_days_min', '2', 'Min days for "By a specific day number" CLC type', 'integer', true),
    ('clc_specific_days_max', '999', 'Max days for "By a specific day number" CLC type', 'integer', true),
    ('fm_days_after_im_min', '1', 'Min days for FM "By a specific days number after IM"', 'integer', true),
    ('fm_days_after_im_max', '999', 'Max days for FM "By a specific days number after IM"', 'integer', true),
    ('fm_repeat_count_max', '99', 'Max repeat count for FM', 'integer', true),
    ('max_ans_duration_years', '100', 'Admin setting: Maximum duration a user can be in ANS state (example)', 'integer', true),
    ('min_ans_duration_minutes', '30', 'Admin setting: Minimum duration a user must be in ANS before FNS can trigger (example)', 'integer', true),
    ('max_fns_duration_years', '100', 'Admin setting: Maximum duration an FNS process runs (example)', 'integer', true),
    ('max_message_content_length_free', '5000', 'Max message content length for free users (chars)', 'integer', true),
    ('max_message_content_length_premium', '50000', 'Max message content length for premium users (chars)', 'integer', true),
    ('max_total_messages_free', '10', 'Max total active messages for free users', 'integer', true),
    ('max_total_messages_premium', '1000', 'Max total active messages for premium users', 'integer', true),
    ('failed_pin_attempts_lockout_threshold', '5', 'Number of failed PIN attempts before account lockout', 'integer', true),
    ('pin_lockout_duration_minutes', '15', 'Duration in minutes for account lockout due to failed PIN attempts', 'integer', true),
    ('max_email_attachment_size_mb_premium', '49', 'Max email attachment size in MB for premium users', 'integer', true),
    ('max_total_upload_storage_gb_premium', '1', 'Max total upload storage in GB for premium users', 'integer', true),
    ('inactive_account_cleanup_years_free', '5', 'Years after which an inactive free account (INS) is cleaned up', 'integer', true),
    ('unused_file_cleanup_years_premium', '5', 'Years after which an unused uploaded file by a premium user is cleaned up', 'integer', true),
    ('scm_min_mins', '30', 'Minimum message sending time since submit (minutes) for SCM', 'integer', true),
    ('scm_max_mins', '10000', 'Maximum message sending time since submit (minutes) for SCM', 'integer', true),
    ('scm_repeat_number_max', '99', 'Max repeat number for Simple Cron Messages (SCM)', 'integer', true),
    ('max_stored_messages_free', '100', 'Maximum messages stored in free account', 'integer', true),
    ('max_stored_messages_premium', '10000', 'Maximum messages stored in premium account', 'integer', true),
    ('premium_lifetime_price_usd', '10', 'The lifetime price in USD for the Premium plan', 'float', true),
    ('email_sending_rate_per_hours', '50', 'System-wide email sending frequency to ensure compliance with SMTP server regulations', 'integer', true),
    ('wct_final_reminder_minutes', '3', 'Final WCT reminder time before it ends (minutes)', 'integer', true),
    ('receivers_limit_cronpost_email', '5', 'Limit the number of recipients in the cronpost-email sending method', 'integer', true),
    ('receivers_limit_in_app_messaging', '10', 'Limit the number of recipients in the In-App-Messaging sending method', 'integer', true),
    ('receivers_limit_user_email', '10', 'Limit the number of recipients in the user-email sending method', 'integer', true),
    ('max_pin_attempts_log_per_user', '50', 'Maximum number of PIN attempt logs to store per user', 'integer', true)
ON CONFLICT (setting_key) DO UPDATE SET 
    setting_value = EXCLUDED.setting_value,
    description = EXCLUDED.description,
    value_type = EXCLUDED.value_type,
    admin_editable = EXCLUDED.admin_editable,
    updated_at = NOW();