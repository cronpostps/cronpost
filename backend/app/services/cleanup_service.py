# /backend/app/services/cleanup_service.py
# Version: 1.0.0

import logging
from sqlalchemy import select, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from ..db.database import AsyncSessionLocal
from ..db.models import InAppMessage, User, SystemSetting

logger = logging.getLogger(__name__)

async def cleanup_old_in_app_messages():
    """
    Tìm và xóa các tin nhắn In-App đã quá hạn lưu trữ
    dựa trên quy tắc trong system_settings.
    """
    logger.info("CLEANUP JOB: Starting daily cleanup for old In-App messages...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Lấy các thiết lập về thời gian lưu trữ từ DB
            settings_stmt = select(SystemSetting).where(
                or_(
                    SystemSetting.setting_key == 'time_storage_message_free',
                    SystemSetting.setting_key == 'time_storage_message_premium'
                )
            )
            settings_result = await db.execute(settings_stmt)
            settings = {s.setting_key: int(s.setting_value) for s in settings_result.scalars().all()}
            
            retention_free_days = settings.get('time_storage_message_free', 60)
            retention_premium_days = settings.get('time_storage_message_premium', 360)

            logger.info(f"CLEANUP JOB: Settings loaded: Free={retention_free_days}d, Premium={retention_premium_days}d.")

            now = datetime.utcnow()
            free_cutoff_date = now - timedelta(days=retention_free_days)
            premium_cutoff_date = now - timedelta(days=retention_premium_days)

            # Lấy ID của tất cả người dùng premium
            premium_users_stmt = select(User.id).where(User.membership_type == 'premium')
            premium_users_result = await db.execute(premium_users_stmt)
            premium_user_ids = [uid for uid in premium_users_result.scalars().all()]
            
            # Subquery để tìm các tin nhắn cần xóa
            delete_candidates_stmt = select(InAppMessage.id).where(
                or_(
                    # TH1: Cả 2 user là free VÀ tin nhắn cũ hơn ngưỡng free
                    and_(
                        InAppMessage.sender_id.notin_(premium_user_ids),
                        InAppMessage.receiver_id.notin_(premium_user_ids),
                        InAppMessage.created_at < free_cutoff_date
                    ),
                    # TH2: Có ít nhất 1 user là premium VÀ tin nhắn cũ hơn ngưỡng premium
                    and_(
                        or_(
                            InAppMessage.sender_id.in_(premium_user_ids),
                            InAppMessage.receiver_id.in_(premium_user_ids)
                        ),
                        InAppMessage.created_at < premium_cutoff_date
                    )
                )
            )

            message_ids_to_delete = (await db.execute(delete_candidates_stmt)).scalars().all()

            if not message_ids_to_delete:
                logger.info("CLEANUP JOB: No old In-App messages found to delete.")
                return

            # Thực hiện DELETE
            delete_stmt = delete(InAppMessage).where(InAppMessage.id.in_(message_ids_to_delete))
            result = await db.execute(delete_stmt)
            await db.commit()

            logger.info(f"CLEANUP JOB: Successfully deleted {result.rowcount} old In-App messages.")

        except Exception as e:
            await db.rollback()
            logger.error(f"CLEANUP JOB: An error occurred during In-App message cleanup: {e}", exc_info=True)