# backend/app/main.py
# version 1.15.2 (Launch background cleanup task)

import asyncio # Thêm import asyncio
from dotenv import load_dotenv
load_dotenv()

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .routers.auth_router import limiter

from .services.worker_cleanup_service import run_daily_cleanup_scheduler

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from .routers import (
    auth_router, 
    signin_router, 
    password_reset_router, 
    user_router,
    message_router, 
    messaging_router,
    user_actions_router,
    admin_router,
    file_router,
    sse_router
)

from .db.database import engine 

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    logger.info("Database engine initialized.")
    
    # --- ADDED: Launch the background task ---
    logger.info("Launching background task for daily cleanup...")
    asyncio.create_task(run_daily_cleanup_scheduler())
    
    yield
    
    logger.info("Application shutting down...")
    if engine is not None:
        await engine.dispose()
    logger.info("Application shutdown complete.")

app = FastAPI(
    title="CronPost API", 
    version="1.0.0",
    description="Backend API for CronPost, handling user authentication, message scheduling, and delivery.",
    lifespan=lifespan,
    openapi_version="3.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={ 
        "url": "/api/openapi.json" 
    }
)

# --- MIDDLEWARE ---
TRUSTED_HOSTS_STR = os.environ.get("TRUSTED_HOSTS", "127.0.0.1")
TRUSTED_HOSTS_LIST = [h.strip() for h in TRUSTED_HOSTS_STR.split(',')]
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=TRUSTED_HOSTS_LIST
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "insecure-default-key")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

ALLOWED_ORIGINS_STR = os.environ.get("ALLOWED_ORIGINS", "*") 
allow_origins_list = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(',')]
app.add_middleware(
    CORSMiddleware, 
    allow_origins=allow_origins_list, 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- Include Routers ---
app.include_router(auth_router.router, prefix="/auth")
app.include_router(signin_router.router, prefix="/auth")
app.include_router(password_reset_router.router, prefix="/auth")
app.include_router(user_router.router, prefix="/users")
app.include_router(message_router.router, prefix="/messages")
app.include_router(messaging_router.router, prefix="/messaging")
app.include_router(user_actions_router.router, prefix="/users")
app.include_router(admin_router.router, prefix="/admin")
app.include_router(file_router.router, prefix="/files")
app.include_router(sse_router.router, prefix="")

# --- Root Endpoints ---
@app.get("/", tags=["App Root"], summary="Backend Root Status") 
async def read_root_server():
    return {"message": "CronPost Backend is running. API is accessed via Nginx at /api prefix."}