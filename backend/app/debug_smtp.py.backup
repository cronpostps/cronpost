# backend/app/debug_smtp.py
# Version: 1.0
# Mô tả: Script chẩn đoán kết nối SMTP trực tiếp bằng thư viện smtplib.

import smtplib
import os
import logging
from dotenv import load_dotenv

# Tải các biến môi trường từ file .env trong cùng thư mục gốc của docker-compose
# Điều này mô phỏng chính xác môi trường của ứng dụng FastAPI
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Cấu hình ---
SERVER = os.environ.get("MAIL_SERVER")
PORT = int(os.environ.get("MAIL_PORT", 465))
USERNAME = os.environ.get("MAIL_USERNAME")
PASSWORD = os.environ.get("MAIL_PASSWORD")

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - DEBUG_SMTP - %(levelname)s - %(message)s')

logging.info("--- SMTP Debug Script Starting ---")
logging.info(f"Server: {SERVER}")
logging.info(f"Port: {PORT}")
logging.info(f"Username: {USERNAME}")
logging.info(f"Password Loaded: {'Yes' if PASSWORD else 'No'}")

if not all([SERVER, PORT, USERNAME, PASSWORD]):
    logging.error("One or more environment variables are missing.")
else:
    try:
        # Sử dụng SMTP_SSL cho kết nối trực tiếp qua SSL trên cổng 465
        logging.info(f"Attempting to connect to {SERVER} on port {PORT} using SMTP_SSL...")
        server = smtplib.SMTP_SSL(SERVER, PORT, timeout=30)
        
        # Bật chế độ debug để xem toàn bộ giao tiếp với server
        server.set_debuglevel(2)
        
        logging.info("Connection successful. Attempting to login...")
        server.login(USERNAME, PASSWORD)
        
        logging.info("--- LOGIN SUCCESSFUL! ---")
        
        server.quit()
        logging.info("--- Connection closed. ---")
        
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"--- LOGIN FAILED: SMTP Authentication Error ---")
        logging.error(f"Error Code: {e.smtp_code}")
        logging.error(f"Error Message: {e.smtp_error}")
    except Exception as e:
        logging.error(f"--- AN UNEXPECTED ERROR OCCURRED ---")
        logging.error(f"Error type: {type(e).__name__}")
        logging.error(f"Error details: {e}")