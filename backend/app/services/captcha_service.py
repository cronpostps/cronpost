# backend/app/services/captcha_service.py
# Version: 1.0
# Mô tả: Chứa logic xác minh Cloudflare Turnstile CAPTCHA

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

async def verify_turnstile_captcha(token: str, client_ip: Optional[str] = None) -> bool:
    """
    Xác minh Cloudflare Turnstile CAPTCHA token.

    Args:
        token (str): Turnstile response token từ frontend.
        client_ip (Optional[str]): Địa chỉ IP của client (để tăng cường xác minh).

    Returns:
        bool: True nếu xác minh thành công, False nếu ngược lại.
    """
    turnstile_secret_key = os.environ.get("TURNSTILE_SECRET_KEY")

    if not turnstile_secret_key:
        # Trong môi trường development, có thể bỏ qua xác minh nếu không có key
        if os.environ.get("ENVIRONMENT", "production").lower() == "development":
            logger.warning("DEV MODE: TURNSTILE_SECRET_KEY is not set. CAPTCHA verification bypassed.")
            return True
        logger.error("TURNSTILE_SECRET_KEY is not set in production environment!")
        return False

    payload_data = {
        "secret": turnstile_secret_key,
        "response": token
    }
    if client_ip:
        payload_data["remoteip"] = client_ip

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data=payload_data,
                timeout=5.0
            )
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            
            result = response.json()
            
            if result.get("success"):
                logger.info("Turnstile CAPTCHA verification successful.")
                return True
            else:
                logger.warning(f"Turnstile CAPTCHA verification failed: {result.get('error-codes', 'N/A')}")
                return False
        except httpx.HTTPStatusError as e_http:
            logger.error(f"HTTP error during Turnstile CAPTCHA verification: {e_http.response.status_code} - {e_http.response.text}", exc_info=False)
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Turnstile CAPTCHA verification: {e}", exc_info=True)
            return False