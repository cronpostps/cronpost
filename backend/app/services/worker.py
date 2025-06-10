import logging
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Message, FmSchedule, MessageOverallStatusEnum
from .schedule_service import calculate_next_fm_send_at # Giả sử hàm này cũng được cập nhật để xử lý lặp lại

logger = logging.getLogger(__name__)

async def process_scheduled_messages(db: AsyncSession):
    """
    Hàm này sẽ được gọi định kỳ (ví dụ: mỗi phút) bởi một trình lập lịch như cron hoặc Celery.
    """
    logger.info("Worker: Starting scheduled message processing run.")
    
    now_utc = datetime.now(timezone.utc)
    
    # 1. Lấy tất cả các FM có next_send_at <= thời gian hiện tại VÀ repeat_number > 0
    stmt = (
        select(FmSchedule)
        .join(Message)
        .where(
            FmSchedule.next_send_at <= now_utc,
            FmSchedule.repeat_number > 0,
            Message.overall_send_status != MessageOverallStatusEnum.processing # Tránh xử lý tin nhắn đang được gửi
        )
    )
    
    result = await db.execute(stmt)
    schedules_to_process = result.scalars().all()

    if not schedules_to_process:
        logger.info("Worker: No scheduled messages to process at this time.")
        return

    logger.info(f"Worker: Found {len(schedules_to_process)} message(s) to process.")

    for schedule in schedules_to_process:
        message = schedule.message
        
        # Đánh dấu là đang xử lý để tránh race condition
        message.overall_send_status = MessageOverallStatusEnum.processing
        await db.commit()

        try:
            # --- Logic gửi tin nhắn thực tế ở đây ---
            # (Ví dụ: gọi API của N8N hoặc dịch vụ email)
            logger.info(f"Worker: Sending message_id {message.id}, repeat number remaining: {schedule.repeat_number}")
            # send_email(message.content, ...)
            
            # --- Cập nhật sau khi gửi thành công ---
            new_repeat_number = schedule.repeat_number - 1
            
            # Cập nhật lại lịch trình
            schedule.repeat_number = new_repeat_number
            
            if new_repeat_number > 0:
                # Nếu vẫn còn lượt gửi, tính toán next_send_at tiếp theo
                # Lưu ý: cần có logic để lấy im_sent_at_utc
                im_sent_at = ... # Cần có logic để lấy thời gian gửi IM
                next_send = await calculate_next_fm_send_at(schedule, message.user.timezone, im_sent_at, db)
                schedule.next_send_at = next_send
                message.overall_send_status = MessageOverallStatusEnum.partially_sent # Hoặc một trạng thái phù hợp
                logger.info(f"Worker: Message {message.id} sent. Next send at {next_send}. Repeats remaining: {new_repeat_number}")
            else:
                # Nếu đã hết lượt gửi
                schedule.next_send_at = None
                message.overall_send_status = MessageOverallStatusEnum.sent # Đánh dấu là đã gửi xong hoàn toàn
                logger.info(f"Worker: Message {message.id} sent. All repetitions complete.")

        except Exception as e:
            logger.error(f"Worker: Failed to send message_id {message.id}. Error: {e}")
            message.overall_send_status = MessageOverallStatusEnum.failed
        
        finally:
            await db.commit()