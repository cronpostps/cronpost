# /backend/app/services/cleanup_service.py
# Version 1.1.0 - Added check to not delete unread messages.

import logging
from sqlalchemy import select, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from ..db.database import AsyncSessionLocal
from ..db.models import InAppMessage, User, SystemSetting

logger = logging.getLogger(__name__)

async def cleanup_old_in_app_messages():
    """
    Finds and deletes In-App messages that are both read and past their retention period,
    based on rules in system_settings.
    """
    logger.info("CLEANUP JOB: Starting daily cleanup for old In-App messages...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Get storage retention settings from DB
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

            now = datetime.now(timezone.utc)
            free_cutoff_date = now - timedelta(days=retention_free_days)
            premium_cutoff_date = now - timedelta(days=retention_premium_days)

            # Get IDs of all premium users
            premium_users_stmt = select(User.id).where(User.membership_type == 'premium')
            premium_users_result = await db.execute(premium_users_stmt)
            premium_user_ids = {uid for uid in premium_users_result.scalars().all()}
            
            # Subquery to find messages to delete
            # MODIFIED: Added a top-level AND to ensure messages are read
            delete_candidates_stmt = select(InAppMessage.id).where(
                and_(
                    # NEW CONDITION: Message must be read (read_at is not NULL)
                    InAppMessage.read_at.is_not(None),

                    # ORIGINAL CONDITIONS for retention period
                    or_(
                        # Case 1: Both users are free AND message is older than free cutoff
                        and_(
                            InAppMessage.sender_id.notin_(premium_user_ids),
                            InAppMessage.receiver_id.notin_(premium_user_ids),
                            InAppMessage.created_at < free_cutoff_date
                        ),
                        # Case 2: At least one user is premium AND message is older than premium cutoff
                        and_(
                            or_(
                                InAppMessage.sender_id.in_(premium_user_ids),
                                InAppMessage.receiver_id.in_(premium_user_ids)
                            ),
                            InAppMessage.created_at < premium_cutoff_date
                        )
                    )
                )
            )

            message_ids_to_delete = (await db.execute(delete_candidates_stmt)).scalars().all()

            if not message_ids_to_delete:
                logger.info("CLEANUP JOB: No old, read In-App messages found to delete.")
                return

            # Perform DELETE
            delete_stmt = delete(InAppMessage).where(InAppMessage.id.in_(message_ids_to_delete))
            result = await db.execute(delete_stmt)
            await db.commit()

            logger.info(f"CLEANUP JOB: Successfully deleted {result.rowcount} old, read In-App messages.")

        except Exception as e:
            await db.rollback()
            logger.error(f"CLEANUP JOB: An error occurred during In-App message cleanup: {e}", exc_info=True)