# backend/app/services/schedule_service.py
# Version: 1.2 (Improved logic for date_of_month and date_of_year in CLC calculation)

import logging
from typing import Optional
from datetime import datetime, timedelta, time, date, timezone as dt_timezone
import calendar
import pytz # Using pytz for broader compatibility

from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import UserConfiguration, CLCTypeEnum, DayOfWeekEnum

logger = logging.getLogger(__name__)

DAY_OF_WEEK_MAP = {
    DayOfWeekEnum.Mon.value: 0, DayOfWeekEnum.Tue.value: 1, DayOfWeekEnum.Wed.value: 2,
    DayOfWeekEnum.Thu.value: 3, DayOfWeekEnum.Fri.value: 4, DayOfWeekEnum.Sat.value: 5,
    DayOfWeekEnum.Sun.value: 6,
}

def get_last_day_of_month(year: int, month: int) -> int:
    """Returns the last day of the given month and year."""
    return calendar.monthrange(year, month)[1]

async def calculate_next_clc_prompt_at(
    user_config: UserConfiguration,
    user_timezone_str: str,
    reference_datetime_utc: datetime,
    db: AsyncSession # db might be used later for SystemSettings
) -> Optional[datetime]:
    logger.info(f"Calculating next CLC for user_id: {user_config.user_id}, type: {user_config.clc_type}, ref_utc: {reference_datetime_utc}, tz: {user_timezone_str}")

    if not user_config.is_clc_enabled:
        logger.info(f"CLC is not enabled for user {user_config.user_id}. Returning None.")
        return None
    
    if user_config.clc_type == CLCTypeEnum.specific_date_in_year:
        logger.warning(f"calculate_next_clc_prompt_at for 'specific_date_in_year' (unloop) user {user_config.user_id}. This type implies no repeating CLC after check-in. Returning None.")
        return None # Unloop type does not have a "next" CLC in the same way after check-in.

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
    
    # Start calculation from the reference date in user's timezone
    current_calc_date_user_tz = reference_datetime_user_tz.date()
    reference_prompt_on_ref_date_user_tz = user_tz.localize(datetime.combine(current_calc_date_user_tz, prompt_time_local), is_dst=None)

    # If reference time is already past today's prompt time, start calculations from tomorrow
    if reference_datetime_user_tz >= reference_prompt_on_ref_date_user_tz:
        current_calc_date_user_tz += timedelta(days=1)
    
    # --- Logic for each clc_type ---
    if user_config.clc_type == CLCTypeEnum.every_day:
        next_prompt_date_user_tz = current_calc_date_user_tz
        
    elif user_config.clc_type == CLCTypeEnum.specific_days:
        days_interval = user_config.clc_day_number_interval
        if days_interval and days_interval >= 1: # Allow 1 for "next day" essentially
            # Assuming the interval is from the last prompt time.
            # If last_successful_checkin_at or IM creation time is the reference,
            # the next prompt is 'days_interval' after that reference.
            # For simplicity, we calculate 'days_interval' from 'current_calc_date_user_tz'
            # This means if prompt was 9am, checkin at 10am, interval 2 days.
            # current_calc_date_user_tz is tomorrow. Next prompt = tomorrow + (2-1) days = 2 days after today.
            # More robust: establish an anchor date if this is a strict N-day cycle.
            # Current simple approach: find the Nth day from 'current_calc_date_user_tz'
            # If today is 1st, prompt 9am, checkin 10am. current_calc_date_user_tz is 2nd. Interval 2 days.
            # next prompt is 2nd + (2-1) = 3rd.
            # If checkin 8am. current_calc_date_user_tz is 1st. Next prompt is 1st + (2-1) = 2nd.
            # This calculation assumes interval is from the "next possible prompt day".
            next_prompt_date_user_tz = reference_datetime_user_tz.date() + timedelta(days=days_interval)
            # Ensure this calculated date is not before current_calc_date_user_tz (if prompt time is late)
            if datetime.combine(next_prompt_date_user_tz, prompt_time_local) < datetime.combine(current_calc_date_user_tz, prompt_time_local):
                 # This scenario might need more complex anchor date logic
                 # For now, if it falls behind, take the next interval from current_calc_date
                 temp_ref_date = datetime.combine(reference_datetime_user_tz.date(), prompt_time_local)
                 while temp_ref_date <= reference_datetime_user_tz:
                      temp_ref_date += timedelta(days=days_interval)
                 next_prompt_date_user_tz = temp_ref_date.date()

        else:
            logger.error(f"Invalid clc_day_number_interval for user {user_config.user_id}")
            return None

    elif user_config.clc_type == CLCTypeEnum.day_of_week:
        if user_config.clc_day_of_week and user_config.clc_day_of_week.value in DAY_OF_WEEK_MAP:
            target_weekday = DAY_OF_WEEK_MAP[user_config.clc_day_of_week.value]
            temp_date = current_calc_date_user_tz
            while temp_date.weekday() != target_weekday:
                temp_date += timedelta(days=1)
            next_prompt_date_user_tz = temp_date
        else:
            logger.error(f"Invalid clc_day_of_week for user {user_config.user_id}")
            return None

    elif user_config.clc_type == CLCTypeEnum.date_of_month:
        target_day = user_config.clc_date_of_month
        if target_day and 1 <= target_day <= 31:
            year = current_calc_date_user_tz.year
            month = current_calc_date_user_tz.month
            
            # Loop to find the next valid occurrence
            for _ in range(13): # Check current month + next 12 months
                last_day_current_month = get_last_day_of_month(year, month)
                actual_target_day = min(target_day, last_day_current_month)
                
                try:
                    prospective_date = date(year, month, actual_target_day)
                    if prospective_date >= current_calc_date_user_tz:
                        next_prompt_date_user_tz = prospective_date
                        break
                except ValueError: # Should not happen with min(target_day, last_day...)
                    pass 
                
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                current_calc_date_user_tz = date(year, month, 1) # Reset for next iteration's check
            else: # Loop finished without break
                logger.error(f"Could not find next valid date_of_month for day {target_day} for user {user_config.user_id}")
                return None
        else:
            logger.error(f"Invalid clc_date_of_month ({target_day}) for user {user_config.user_id}")
            return None

    elif user_config.clc_type == CLCTypeEnum.date_of_year:
        if user_config.clc_date_of_year: # Format "dd/MM"
            try:
                day_str, month_str = user_config.clc_date_of_year.split('/')
                target_day = int(day_str)
                target_month = int(month_str)
                
                year = current_calc_date_user_tz.year
                
                for i in range(3): # Check current year, next year, year after next
                    current_year_to_check = year + i
                    try:
                        # Handle target_day > days in month (e.g., 29/02 non-leap)
                        actual_target_day = min(target_day, get_last_day_of_month(current_year_to_check, target_month))
                        prospective_date = date(current_year_to_check, target_month, actual_target_day)
                        
                        if prospective_date >= current_calc_date_user_tz:
                            # Ensure we are using the user's intended day if it's valid for that month/year
                            if target_day <= get_last_day_of_month(current_year_to_check, target_month):
                                next_prompt_date_user_tz = date(current_year_to_check, target_month, target_day)
                            else: # e.g. user wanted 29/02 but it's not a leap year, take 28/02
                                next_prompt_date_user_tz = prospective_date # which is last valid day
                            break 
                    except ValueError: # Invalid date, e.g., month out of range (should be caught by parsing)
                        pass
                else: # Loop finished without break
                    logger.error(f"Could not find next valid date_of_year for {user_config.clc_date_of_year} for user {user_config.user_id}")
                    return None
            except Exception as e: # Catch parsing errors or other issues
                logger.error(f"Error processing clc_date_of_year ('{user_config.clc_date_of_year}') for user {user_config.user_id}: {e}")
                return None
        else:
            logger.error(f"Missing clc_date_of_year for user {user_config.user_id}")
            return None
            
    else:
        logger.error(f"Unsupported clc_type: {user_config.clc_type} for user {user_config.user_id}")
        return None

    if next_prompt_date_user_tz:
        next_prompt_datetime_user_tz_naive = datetime.combine(next_prompt_date_user_tz, prompt_time_local)
        next_prompt_datetime_user_tz_aware = user_tz.localize(next_prompt_datetime_user_tz_naive, is_dst=None)
        next_prompt_utc = next_prompt_datetime_user_tz_aware.astimezone(pytz.utc)
        logger.info(f"Calculated next CLC prompt for user {user_config.user_id}: {next_prompt_utc} (UTC)")
        return next_prompt_utc
    
    logger.warning(f"Failed to calculate next_clc_prompt_at for user {user_config.user_id} (config_id: {user_config.user_id}) with type {user_config.clc_type}")
    return None