# backend/app/services/schedule_service.py
# Version: 1.4
# Changelog:
# - Refined CLCTypeEnum.specific_days logic for interval calculation.
# - Corrected CLCTypeEnum.date_of_year to skip invalid dates (e.g., 29/02 non-leap).
# - Added calculate_next_fm_send_at function for Follow Message scheduling.

import logging
from typing import Optional
from datetime import datetime, timedelta, time, date, timezone as dt_timezone
import calendar
import pytz

from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import (
    UserConfiguration, 
    CLCTypeEnum, 
    DayOfWeekEnum,
    FmSchedule, # Thêm FmSchedule
    FMScheduleTriggerTypeEnum # Thêm FMScheduleTriggerTypeEnum
)

logger = logging.getLogger(__name__)

DAY_OF_WEEK_MAP = {
    DayOfWeekEnum.Mon.value: 0, DayOfWeekEnum.Tue.value: 1, DayOfWeekEnum.Wed.value: 2,
    DayOfWeekEnum.Thu.value: 3, DayOfWeekEnum.Fri.value: 4, DayOfWeekEnum.Sat.value: 5,
    DayOfWeekEnum.Sun.value: 6,
}

def get_last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]

async def calculate_next_clc_prompt_at( # Giữ nguyên logic hiện tại của hàm này
    user_config: UserConfiguration,
    user_timezone_str: str,
    reference_datetime_utc: datetime,
    db: AsyncSession 
) -> Optional[datetime]:
    logger.info(f"Calculating next CLC for user_id: {user_config.user_id}, type: {user_config.clc_type}, ref_utc: {reference_datetime_utc}, tz: {user_timezone_str}")

    if not user_config.is_clc_enabled:
        logger.info(f"CLC is not enabled for user {user_config.user_id}. Returning None.")
        return None
    
    if user_config.clc_type == CLCTypeEnum.specific_date_in_year:
        logger.info(f"calculate_next_clc_prompt_at called for 'specific_date_in_year' (unloop) for user {user_config.user_id}. Unloop types do not have a 'next' CLC in this context. Returning None.")
        return None 

    try:
        user_tz = pytz.timezone(user_timezone_str)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone '{user_timezone_str}' for user {user_config.user_id}. Defaulting to UTC.")
        user_tz = pytz.utc

    reference_datetime_user_tz = reference_datetime_utc.astimezone(user_tz)
    prompt_time_local: time = user_config.clc_prompt_time
    if not prompt_time_local:
        prompt_time_local = time(9, 0, 0)
        logger.warning(f"clc_prompt_time is None for user {user_config.user_id}, defaulting to 09:00:00.")

    next_prompt_date_user_tz: Optional[date] = None
    current_day_of_reference_user_tz = reference_datetime_user_tz.date()
    prompt_on_ref_day_user_tz_naive = datetime.combine(current_day_of_reference_user_tz, prompt_time_local)
    
    try:
        prompt_on_ref_day_user_tz_aware = user_tz.localize(prompt_on_ref_day_user_tz_naive, is_dst=None)
    except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError) as e_tz:
        logger.warning(f"Timezone localization error for reference day prompt time for user {user_config.user_id}: {e_tz}.")
        effective_start_date_for_cycle = current_day_of_reference_user_tz + timedelta(days=1)
    else:
        if reference_datetime_user_tz >= prompt_on_ref_day_user_tz_aware:
            effective_start_date_for_cycle = current_day_of_reference_user_tz + timedelta(days=1)
        else:
            effective_start_date_for_cycle = current_day_of_reference_user_tz
    
    logger.debug(f"User {user_config.user_id}: ref_user_tz={reference_datetime_user_tz}, prompt_local={prompt_time_local}, effective_start_date_for_cycle={effective_start_date_for_cycle}")

    if user_config.clc_type == CLCTypeEnum.every_day:
        next_prompt_date_user_tz = effective_start_date_for_cycle
    elif user_config.clc_type == CLCTypeEnum.specific_days:
        days_interval = user_config.clc_day_number_interval
        if days_interval and days_interval >= 2:
            next_prompt_date_user_tz = effective_start_date_for_cycle + timedelta(days=days_interval)
        else: 
            logger.error(f"Invalid clc_day_number_interval ({days_interval}) for user {user_config.user_id} with specific_days type.")
            return None
    elif user_config.clc_type == CLCTypeEnum.day_of_week:
        if user_config.clc_day_of_week and user_config.clc_day_of_week.value in DAY_OF_WEEK_MAP:
            target_weekday = DAY_OF_WEEK_MAP[user_config.clc_day_of_week.value]
            temp_date = effective_start_date_for_cycle
            while temp_date.weekday() != target_weekday:
                temp_date += timedelta(days=1)
            next_prompt_date_user_tz = temp_date
        else:
            logger.error(f"Invalid clc_day_of_week for user {user_config.user_id}")
            return None
    elif user_config.clc_type == CLCTypeEnum.date_of_month:
        target_day_of_month = user_config.clc_date_of_month
        if target_day_of_month and 1 <= target_day_of_month <= 31:
            year = effective_start_date_for_cycle.year
            month = effective_start_date_for_cycle.month
            found_next_date = False
            for _ in range(13): 
                last_day_this_month = get_last_day_of_month(year, month)
                actual_target_day_this_month = min(target_day_of_month, last_day_this_month)
                try:
                    prospective_date = date(year, month, actual_target_day_this_month)
                    if prospective_date >= effective_start_date_for_cycle:
                        next_prompt_date_user_tz = prospective_date
                        found_next_date = True
                        break 
                except ValueError: pass 
                month += 1
                if month > 12: month = 1; year += 1
                effective_start_date_for_cycle = date(year, month, 1) 
            if not found_next_date:
                logger.error(f"Could not find next valid date_of_month for day {target_day_of_month} for user {user_config.user_id} within 13 months.")
                return None
        else:
            logger.error(f"Invalid clc_date_of_month ({target_day_of_month}) for user {user_config.user_id}")
            return None
    elif user_config.clc_type == CLCTypeEnum.date_of_year:
        if user_config.clc_date_of_year: 
            try:
                day_str, month_str = user_config.clc_date_of_year.split('/')
                target_day = int(day_str); target_month = int(month_str)
                if not (1 <= target_month <= 12 and 1 <= target_day <= 31): raise ValueError("Month or day out of valid range.")
                year_to_check = effective_start_date_for_cycle.year
                found_next_date = False
                for i in range(3): 
                    current_year_candidate = year_to_check + i
                    try:
                        prospective_date = date(current_year_candidate, target_month, target_day)
                        if prospective_date >= effective_start_date_for_cycle:
                            next_prompt_date_user_tz = prospective_date
                            found_next_date = True
                            break 
                    except ValueError: 
                        logger.debug(f"Skipping {target_day}/{target_month}/{current_year_candidate} for user {user_config.user_id} as it's an invalid date.")
                        effective_start_date_for_cycle = date(current_year_candidate + 1, 1, 1)
                        continue 
                if not found_next_date:
                    logger.error(f"Could not find next valid date_of_year for {user_config.clc_date_of_year} for user {user_config.user_id} within 3 years.")
                    return None
            except ValueError as e_val: 
                logger.error(f"Invalid format or value in clc_date_of_year ('{user_config.clc_date_of_year}') for user {user_config.user_id}: {e_val}")
                return None
            except Exception as e: 
                logger.error(f"Error processing clc_date_of_year ('{user_config.clc_date_of_year}') for user {user_config.user_id}: {e}", exc_info=True)
                return None
        else:
            logger.error(f"Missing clc_date_of_year for user {user_config.user_id}")
            return None
    else: 
        logger.error(f"Unsupported clc_type: {user_config.clc_type} for user {user_config.user_id}")
        return None

    if next_prompt_date_user_tz:
        next_prompt_datetime_user_tz_naive = datetime.combine(next_prompt_date_user_tz, prompt_time_local)
        try:
            next_prompt_datetime_user_tz_aware = user_tz.localize(next_prompt_datetime_user_tz_naive, is_dst=None)
        except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError) as e_tz:
            logger.error(f"Calculated next prompt time {next_prompt_datetime_user_tz_naive.strftime('%Y-%m-%d %H:%M:%S')} is invalid/ambiguous in timezone {user_timezone_str} for user {user_config.user_id}: {e_tz}. Returning None.")
            raise ValueError(f"The calculated next schedule time ({next_prompt_datetime_user_tz_naive.strftime('%H:%M')} on {next_prompt_date_user_tz.strftime('%Y-%m-%d')}) is invalid or ambiguous in your timezone ({user_timezone_str}). This can happen during Daylight Saving Time changes. Please adjust your prompt time or date.")
        next_prompt_utc = next_prompt_datetime_user_tz_aware.astimezone(pytz.utc)
        logger.info(f"Calculated next CLC prompt for user {user_config.user_id}: {next_prompt_utc} (UTC), from user-local: {next_prompt_datetime_user_tz_aware}")
        return next_prompt_utc
    
    logger.warning(f"Failed to calculate next_clc_prompt_at for user {user_config.user_id} with type {user_config.clc_type} (no valid date found).")
    return None

async def calculate_next_fm_send_at(
    fm_schedule: FmSchedule,
    user_timezone_str: str,
    im_sent_at_utc: Optional[datetime], # Thời điểm IM được gửi (UTC), nếu FM phụ thuộc IM
    # current_repetition: int, # Để xử lý lặp lại, cho lần tính đầu tiên có thể là 0
    # last_fm_sent_at_utc: Optional[datetime] # Thời điểm FM này được gửi lần cuối (cho việc lặp lại)
    db: AsyncSession # Có thể cần để lấy thông tin hệ thống hoặc IM
) -> Optional[datetime]:
    """
    Calculates the next send time for a Follow Message (FM).
    Returns datetime in UTC.
    """
    logger.info(f"Calculating next FM send for message_id: {fm_schedule.message_id}, trigger: {fm_schedule.trigger_type}, user_tz: {user_timezone_str}")

    if not fm_schedule.is_active:
        logger.info(f"FM {fm_schedule.message_id} is not active. No next send time.")
        return None

    try:
        user_tz = pytz.timezone(user_timezone_str)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone '{user_timezone_str}' for FM {fm_schedule.message_id}. Defaulting to UTC.")
        user_tz = pytz.utc

    fm_send_time_local: time = fm_schedule.sending_time_of_day
    if not fm_send_time_local: # Nên có default từ model, nhưng kiểm tra lại
        fm_send_time_local = time(9,0,0)
        logger.warning(f"FM {fm_schedule.message_id} has no sending_time_of_day, defaulting to 09:00.")

    # --- Xác định ngày tham chiếu (reference_date_user_tz) ---
    # Ngày này là ngày IM được gửi (cho các trigger phụ thuộc IM)
    # hoặc ngày hiện tại (cho specific_date không lặp lại, hoặc cho lần lặp đầu tiên của các trigger lặp lại mà không phụ thuộc IM chặt chẽ)
    
    # Thời điểm hiện tại để so sánh, đảm bảo FM được gửi trong tương lai
    now_utc = datetime.now(dt_timezone.utc)
    now_user_tz = now_utc.astimezone(user_tz)

    next_fm_send_date_user_tz: Optional[date] = None

    # Xử lý các trigger type phụ thuộc IM trước
    dependent_on_im = fm_schedule.trigger_type in [
        FMScheduleTriggerTypeEnum.days_after_im_sent,
        FMScheduleTriggerTypeEnum.day_of_week, # Tài liệu nói "sau khi IM được gửi" 
        FMScheduleTriggerTypeEnum.date_of_month, # Tài liệu nói "sau khi IM được gửi" 
        FMScheduleTriggerTypeEnum.date_of_year # Tài liệu nói "sau khi IM được gửi" 
    ]

    if dependent_on_im:
        if not im_sent_at_utc:
            logger.info(f"FM {fm_schedule.message_id} depends on IM send time, but IM not sent yet. Next send time is None for now.")
            return None # IM chưa gửi, không thể tính
        
        im_sent_at_user_tz = im_sent_at_utc.astimezone(user_tz)
        # effective_start_date là ngày IM được gửi, hoặc ngày hôm sau nếu thời gian gửi FM của ngày IM đã qua
        current_day_of_im_sent_user_tz = im_sent_at_user_tz.date()
        fm_send_on_im_day_user_tz_naive = datetime.combine(current_day_of_im_sent_user_tz, fm_send_time_local)
        
        try:
            fm_send_on_im_day_user_tz_aware = user_tz.localize(fm_send_on_im_day_user_tz_naive, is_dst=None)
        except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError):
            # If send time on IM day is invalid (DST), assume we start from next day relative to IM day
            base_date_for_calc = current_day_of_im_sent_user_tz + timedelta(days=1)
        else:
            if im_sent_at_user_tz >= fm_send_on_im_day_user_tz_aware: # Nếu IM gửi sau thời gian gửi FM của ngày đó
                base_date_for_calc = current_day_of_im_sent_user_tz + timedelta(days=1)
            else:
                base_date_for_calc = current_day_of_im_sent_user_tz
    else: # Cho 'specific_date' hoặc các loại lặp lại không phụ thuộc trực tiếp vào *thời điểm* IM gửi
        base_date_for_calc = now_user_tz.date() # Bắt đầu tính từ hôm nay (theo giờ user)
        # Nếu thời gian gửi của hôm nay đã qua, bắt đầu từ ngày mai
        today_fm_send_naive = datetime.combine(base_date_for_calc, fm_send_time_local)
        try:
            today_fm_send_aware = user_tz.localize(today_fm_send_naive, is_dst=None)
        except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError):
            base_date_for_calc += timedelta(days=1) # Nếu giờ gửi hôm nay lỗi DST, tính từ mai
        else:
            if now_user_tz >= today_fm_send_aware:
                base_date_for_calc += timedelta(days=1)

    logger.debug(f"FM {fm_schedule.message_id}: base_date_for_calc={base_date_for_calc}, fm_send_time_local={fm_send_time_local}")

    # --- Tính toán next_fm_send_date_user_tz dựa trên trigger_type ---
    if fm_schedule.trigger_type == FMScheduleTriggerTypeEnum.days_after_im_sent:
        if fm_schedule.days_after_im_value is not None:
            # Ngày gửi IM là ngày 0. "Sau X ngày" nghĩa là IM_date + X days.
            next_fm_send_date_user_tz = im_sent_at_user_tz.date() + timedelta(days=fm_schedule.days_after_im_value)
        else: return None # Cấu hình lỗi

    elif fm_schedule.trigger_type == FMScheduleTriggerTypeEnum.day_of_week: # Luôn là "tuần sau IM" hoặc "tuần này nếu còn kịp"
        if fm_schedule.day_of_week_value and fm_schedule.day_of_week_value.value in DAY_OF_WEEK_MAP:
            target_weekday = DAY_OF_WEEK_MAP[fm_schedule.day_of_week_value.value]
            temp_date = base_date_for_calc # Bắt đầu từ base_date_for_calc
            while temp_date.weekday() != target_weekday:
                temp_date += timedelta(days=1)
            next_fm_send_date_user_tz = temp_date
        else: return None

    elif fm_schedule.trigger_type == FMScheduleTriggerTypeEnum.date_of_month: # "tháng sau IM" hoặc "tháng này nếu còn kịp"
        target_day = fm_schedule.date_of_month_value
        if target_day and 1 <= target_day <= 31:
            year = base_date_for_calc.year
            month = base_date_for_calc.month
            found = False
            for _ in range(13): # Kiểm tra tháng hiện tại và 12 tháng tiếp theo
                last_day_current_month = get_last_day_of_month(year, month)
                actual_target_day = min(target_day, last_day_current_month)
                prospective_date = date(year, month, actual_target_day)
                if prospective_date >= base_date_for_calc:
                    next_fm_send_date_user_tz = prospective_date
                    found = True; break
                month += 1
                if month > 12: month = 1; year += 1
                base_date_for_calc = date(year, month, 1) # Reset base date cho vòng lặp sau
            if not found: return None
        else: return None

    elif fm_schedule.trigger_type == FMScheduleTriggerTypeEnum.date_of_year: # "năm sau IM" hoặc "năm nay nếu còn kịp"
        if fm_schedule.date_of_year_value:
            try:
                day_str, month_str = fm_schedule.date_of_year_value.split('/')
                target_d, target_m = int(day_str), int(month_str)
                if not (1 <= target_m <= 12 and 1 <= target_d <= 31): raise ValueError("Invalid dd/MM")
                
                year_to_check = base_date_for_calc.year
                found = False
                for i in range(fm_schedule.repeat_count + 2): # Check đủ số năm cho repeat + 1 năm dự phòng
                    current_year_candidate = year_to_check + i
                    try:
                        prospective_date = date(current_year_candidate, target_m, target_d)
                        if prospective_date >= base_date_for_calc:
                            next_fm_send_date_user_tz = prospective_date
                            found = True; break
                    except ValueError: # Ngày không hợp lệ (vd: 29/02)
                        base_date_for_calc = date(current_year_candidate + 1, 1, 1) # Bỏ qua năm này
                        continue
                if not found: return None
            except ValueError: return None # Lỗi parse dd/MM
        else: return None

    elif fm_schedule.trigger_type == FMScheduleTriggerTypeEnum.specific_date:
        if fm_schedule.specific_date_value:
            next_fm_send_date_user_tz = fm_schedule.specific_date_value
            # Kiểm tra điều kiện "chỉ được gửi nếu thời điểm này là sau thời điểm IM đã được gửi" 
            if im_sent_at_utc:
                # Tạo datetime UTC cho FM từ specific_date_value và sending_time_of_day
                fm_specific_send_naive = datetime.combine(fm_schedule.specific_date_value, fm_send_time_local)
                try:
                    fm_specific_send_user_tz = user_tz.localize(fm_specific_send_naive, is_dst=None)
                except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError) as e_tz:
                     logger.error(f"FM {fm_schedule.message_id} specific_date {fm_schedule.specific_date_value} at {fm_send_time_local} is invalid in timezone {user_timezone_str}: {e_tz}")
                     raise ValueError(f"The FM's specific send time is invalid or ambiguous in your timezone: {e_tz}")

                fm_specific_send_utc = fm_specific_send_user_tz.astimezone(pytz.utc)
                if fm_specific_send_utc <= im_sent_at_utc:
                    logger.info(f"FM {fm_schedule.message_id} with specific_date {fm_schedule.specific_date_value} is scheduled before or at IM send time {im_sent_at_utc}. It will be skipped or delayed until after IM.")
                    return None # Hoặc một logic khác để đánh dấu là "chờ IM"
            # Nếu IM chưa gửi, specific_date vẫn được giữ, việc gửi sẽ do worker kiểm tra sau
        else: return None
    else:
        logger.error(f"Unsupported FM trigger_type: {fm_schedule.trigger_type} for FM {fm_schedule.message_id}")
        return None

    if not next_fm_send_date_user_tz:
        logger.warning(f"Could not determine next_fm_send_date_user_tz for FM {fm_schedule.message_id}")
        return None
        
    # Kết hợp ngày đã tính với thời gian gửi
    final_fm_send_datetime_naive = datetime.combine(next_fm_send_date_user_tz, fm_send_time_local)
    try:
        final_fm_send_datetime_aware = user_tz.localize(final_fm_send_datetime_naive, is_dst=None)
    except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError) as e_tz:
        logger.error(f"Final calculated FM send time {final_fm_send_datetime_naive.strftime('%Y-%m-%d %H:%M:%S')} is invalid/ambiguous in timezone {user_timezone_str} for FM {fm_schedule.message_id}: {e_tz}.")
        # Xử lý lỗi này: có thể thử ngày hôm sau với cùng quy tắc, hoặc báo lỗi.
        # Hiện tại, raise ValueError để router xử lý.
        raise ValueError(f"The calculated send time for the Follow Message ({final_fm_send_datetime_naive.strftime('%H:%M')} on {next_fm_send_date_user_tz.strftime('%Y-%m-%d')}) is invalid or ambiguous in your timezone ({user_timezone_str}). This can occur during Daylight Saving Time changes. Please adjust the sending time or date.")

    final_fm_send_utc = final_fm_send_datetime_aware.astimezone(pytz.utc)

    # Đảm bảo thời gian gửi cuối cùng là trong tương lai so với thời điểm hiện tại
    # Ngoại trừ trường hợp specific_date có thể đã được set trong quá khứ (nhưng vẫn sau IM)
    if fm_schedule.trigger_type != FMScheduleTriggerTypeEnum.specific_date and final_fm_send_utc <= now_utc:
        # Điều này không nên xảy ra nếu base_date_for_calc được xử lý đúng
        logger.warning(f"Calculated FM send time {final_fm_send_utc} for FM {fm_schedule.message_id} is in the past or now. Base date: {base_date_for_calc}. This might indicate a logic issue or extremely short interval.")
        # Cần cơ chế tìm kiếm "lần hợp lệ tiếp theo" cho các loại lặp lại nếu lần tính đầu tiên bị rơi vào quá khứ.
        # Ví dụ: nếu FM "hàng ngày" và base_date_for_calc là hôm nay nhưng thời gian đã qua, nó nên là ngày mai.
        # Logic base_date_for_calc ở trên đã cố gắng xử lý việc này. Nếu vẫn vào đây, cần xem xét lại.
        # Tạm thời, coi đây là một trường hợp không thể lên lịch ngay.
        if fm_schedule.repeat_count > fm_schedule.current_repetition : # Nếu còn lượt lặp
             logger.info(f"Attempting to find next occurrence for past-scheduled repeating FM {fm_schedule.message_id}")
             # Đây là nơi logic tính toán cho lần lặp tiếp theo sẽ được áp dụng.
             # Ví dụ, nếu trigger là 'day_of_week', base_date_for_calc có thể là final_fm_send_date_user_tz + timedelta(days=1)
             # và chạy lại logic tìm kiếm.
             # Tạm thời return None để đơn giản hóa, logic lặp lại sẽ xử lý sau.
             return None
        return None


    logger.info(f"Calculated next FM send for {fm_schedule.message_id}: {final_fm_send_utc} (UTC), from user-local: {final_fm_send_datetime_aware}")
    return final_fm_send_utc