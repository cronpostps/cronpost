# backend/app/dependencies.py
# Version: 1.0 (Refactored for self-hosted auth)

import os
import logging

from fastapi import HTTPException, status, Request as FastAPIRequest

logger = logging.getLogger(__name__)

if os.environ.get("DATABASE_URL") is None:
    logger.critical("CRITICAL (dependencies.py): DATABASE_URL is not set.")
    # Trong production, bạn có thể muốn raise một exception ở đây để ngăn ứng dụng khởi động.
if os.environ.get("JWT_SECRET_KEY") is None:
    logger.critical("CRITICAL (dependencies.py): JWT_SECRET_KEY is not set.")
    # Như trên.
if os.environ.get("GOOGLE_CLIENT_ID") is None or os.environ.get("GOOGLE_CLIENT_SECRET") is None:
    logger.warning("WARNING (dependencies.py): Google OAuth CLIENT_ID or CLIENT_SECRET missing. Google OAuth login may not function.")
if os.environ.get("TURNSTILE_SECRET_KEY") is None:
    logger.warning("WARNING (dependencies.py): TURNSTILE_SECRET_KEY (for CAPTCHA) not found. CAPTCHA verification will be skipped or fail if not configured.")