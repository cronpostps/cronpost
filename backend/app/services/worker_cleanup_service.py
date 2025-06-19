# /backend/app/services/worker_cleanup_service.py
# NEW FILE
# Version: 1.0.0

import asyncio
import logging
from datetime import datetime, time, timedelta
import pytz

from .cleanup_service import cleanup_old_in_app_messages

logger = logging.getLogger(__name__)

# Múi giờ Việt Nam theo yêu cầu thiết kế
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

async def run_daily_cleanup_scheduler():
    """
    Chạy một vòng lặp vô tận để thực hiện các tác vụ dọn dẹp mỗi ngày
    vào lúc 03:00 giờ Việt Nam.
    """
    logger.info("Background scheduler for cleanup tasks has started.")
    while True:
        now_vn = datetime.now(VIETNAM_TZ)
        run_time = time(3, 0, 0) # 03:00 AM
        
        next_run_datetime = VIETNAM_TZ.localize(
            datetime.combine(now_vn.date(), run_time)
        )
        
        if now_vn.time() >= run_time:
            # Nếu bây giờ đã qua 03:00, lên lịch cho ngày mai
            next_run_datetime += timedelta(days=1)
            
        wait_seconds = (next_run_datetime - now_vn).total_seconds()
        
        logger.info(f"Next cleanup job scheduled at: {next_run_datetime}. Waiting for {wait_seconds:.0f} seconds.")
        
        await asyncio.sleep(wait_seconds)
        
        try:
            logger.info("WORKER: Woke up for scheduled cleanup. Running jobs...")
            await cleanup_old_in_app_messages()
            # Có thể thêm các job dọn dẹp khác ở đây trong tương lai (ví dụ: dọn dẹp file)
            logger.info("WORKER: Scheduled cleanup jobs finished.")
        except Exception as e:
            logger.error(f"WORKER: An error occurred in the scheduled cleanup task: {e}", exc_info=True)
            
        # Chờ 1 phút để tránh vòng lặp tức thì nếu có lỗi trong lúc tính toán thời gian
        await asyncio.sleep(60)