# backend/app/services/email_service.py
# Version: 3.0 (Final)
# Mô tả: Viết lại hoàn toàn bằng smtplib tiêu chuẩn để đảm bảo hoạt động.

import os
import logging
import smtplib
from typing import Dict, Any
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi.concurrency import run_in_threadpool
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Đọc cấu hình từ biến môi trường
MAIL_SERVER = os.environ.get("MAIL_SERVER")
MAIL_PORT = int(os.environ.get("MAIL_PORT", 465))
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
MAIL_FROM = os.environ.get("MAIL_FROM")
TEMPLATE_FOLDER = os.environ.get("TEMPLATE_FOLDER", "app/templates/email")

# Thiết lập môi trường Jinja2
try:
    env = Environment(loader=FileSystemLoader(TEMPLATE_FOLDER))
except Exception as e:
    logger.error(f"Failed to initialize Jinja2 environment: {e}")
    env = None

def send_email_sync(subject: str, email_to: str, html_content: str):
    """
    Hàm đồng bộ để gửi email, sẽ được chạy trong một thread riêng.
    """
    if not all([MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM]):
        logger.error("Mail server settings are incomplete. Email not sent.")
        return

    msg = MIMEMultipart()
    msg['From'] = MAIL_FROM
    msg['To'] = email_to
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    try:
        logger.info(f"Connecting to SMTP server {MAIL_SERVER}:{MAIL_PORT}...")
        with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT, timeout=30) as server:
            # server.set_debuglevel(1) # Bỏ comment nếu cần debug chi tiết
            logger.info("Logging in...")
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            logger.info("Sending email...")
            server.send_message(msg)
            logger.info(f"Email successfully sent to {email_to}")
    except Exception as e:
        logger.error(f"Failed to send email using smtplib to {email_to}. Error: {e}", exc_info=True)
        # Ném lại lỗi để tác vụ nền có thể thấy (nếu cần)
        raise e

async def send_email_async(
    subject: str,
    email_to: str,
    body: Dict[str, Any],
    template_name: str
):
    """
    Hàm bất đồng bộ, render template và gọi hàm gửi email đồng bộ trong threadpool.
    """
    if not env:
        logger.error(f"Jinja2 environment not available. Cannot send email to {email_to}")
        return
        
    logger.info(f"Preparing to send email to {email_to} with subject '{subject}'")
    try:
        template = env.get_template(template_name)
        html_content = template.render(**body)
        # Chạy hàm send_email_sync trong một thread riêng để không block ứng dụng
        await run_in_threadpool(send_email_sync, subject=subject, email_to=email_to, html_content=html_content)
    except Exception as e:
        logger.error(f"Error in async email preparation for {email_to}. Error: {e}", exc_info=True)