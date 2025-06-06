# backend/app/services/email_service.py
# Version: 1.1
# Mô tả: Sửa lỗi giá trị mặc định cho MAIL_STARTTLS.

import os
import logging
from typing import List, Dict, Any

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr, BaseModel

logger = logging.getLogger(__name__)

# Cấu hình từ biến môi trường
conf = ConnectionConfig(
    MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
    MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
    MAIL_FROM=os.environ.get("MAIL_FROM"),
    MAIL_PORT=int(os.environ.get("MAIL_PORT", 587)),
    MAIL_SERVER=os.environ.get("MAIL_SERVER"),
    MAIL_STARTTLS=os.environ.get("MAIL_STARTTLS", 'False').lower() in ('true', '1', 't'), # SỬA Ở ĐÂY
    MAIL_SSL_TLS=os.environ.get("MAIL_SSL_TLS", 'True').lower() in ('true', '1', 't'),
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=os.environ.get("TEMPLATE_FOLDER")
)

fm = FastMail(conf)

async def send_email_async(
    subject: str,
    email_to: EmailStr,
    body: Dict[str, Any],
    template_name: str
):
    """
    Hàm gửi email bất đồng bộ với template.
    """
    message = MessageSchema(
        subject=subject,
        recipients=[email_to],
        template_body=body,
        subtype=MessageType.html
    )
    
    try:
        logger.info(f"Attempting to send email to {email_to} with subject '{subject}' using template '{template_name}'")
        await fm.send_message(message, template_name=template_name)
        logger.info(f"Email successfully sent to {email_to}")
    except Exception as e:
        logger.error(f"Failed to send email to {email_to}. Error: {e}", exc_info=True)