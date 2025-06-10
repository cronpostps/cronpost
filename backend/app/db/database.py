# backend/app/db/database.py
# version 1.1

import os
import logging # Thêm import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base 

logger = logging.getLogger(__name__) # Tạo logger

# Lấy các biến môi trường cho kết nối DB của App
DB_USER = os.getenv("APP_DB_USER")
DB_PASSWORD = os.getenv("APP_DB_PASSWORD")
DB_HOST = os.getenv("APP_DB_HOST")
DB_PORT = os.getenv("APP_DB_PORT", "5432") 
DB_NAME = os.getenv("APP_DB_NAME")

# Log các giá trị đã đọc để kiểm tra
logger.info(f"DATABASE_PY (v1.1): APP_DB_USER='{DB_USER}'")
logger.info(f"DATABASE_PY (v1.1): APP_DB_PASSWORD='{'******' if DB_PASSWORD else None}'")
logger.info(f"DATABASE_PY (v1.1): APP_DB_HOST='{DB_HOST}'")
logger.info(f"DATABASE_PY (v1.1): APP_DB_PORT='{DB_PORT}'")
logger.info(f"DATABASE_PY (v1.1): APP_DB_NAME='{DB_NAME}'")


if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
    logger.error(
        f"DATABASE_PY (v1.1): Một hoặc nhiều biến môi trường APP_DB_... chưa được thiết lập. "
        f"User: '{DB_USER}', Host: '{DB_HOST}', Port: '{DB_PORT}', DBName: '{DB_NAME}'"
    )
    # Để dễ debug hơn, chúng ta sẽ không raise RuntimeError ở đây ngay,
    # mà để engine được tạo với URL có thể là None, lỗi sẽ xảy ra khi sử dụng.
    SQLALCHEMY_DATABASE_URL = None
else:
    # Xây dựng chuỗi kết nối
    SQLALCHEMY_DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    logger.info(f"DATABASE_PY (v1.1): Constructed SQLALCHEMY_DATABASE_URL='{SQLALCHEMY_DATABASE_URL.replace(DB_PASSWORD, '******') if DB_PASSWORD and SQLALCHEMY_DATABASE_URL else SQLALCHEMY_DATABASE_URL}'")

if SQLALCHEMY_DATABASE_URL:
    engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True) # Giữ lại echo=True để xem log SQL
    AsyncSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
else:
    logger.critical("DATABASE_PY (v1.1): SQLALCHEMY_DATABASE_URL is NOT SET. Engine and AsyncSessionLocal will NOT be created.")
    engine = None
    AsyncSessionLocal = None

Base = declarative_base() # Base cho các model

async def get_db_session():
    if AsyncSessionLocal is None:
        logger.error("DATABASE_PY (v1.1): AsyncSessionLocal is not initialized in get_db_session. Cannot get DB session.")
        raise HTTPException(status_code=503, detail="Database session factory not available. Check server logs.")
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()