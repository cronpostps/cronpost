# backend/app/main.py
# version 1.14.0 (load .env file on startup)

from dotenv import load_dotenv
load_dotenv()

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request as FastAPIRequest
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# Import cho Rate Limiting
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .routers.auth_router import limiter

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
    admin_router
)

from .db.database import engine 

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up with full features...")
    logger.info("Database engine initialized (schema assumed to be created by init.sql).")

    yield
    logger.info("Application shutting down: Disposing database engine...")
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

# 0. Proxy Headers Middleware (BẮT BUỘC đặt trước Rate Limiting)
TRUSTED_HOSTS_STR = os.environ.get("TRUSTED_HOSTS", "127.0.0.1")
TRUSTED_HOSTS_LIST = [h.strip() for h in TRUSTED_HOSTS_STR.split(',')]

logger.info(f"PROXY MIDDLEWARE INITIALIZED. TRUSTED HOSTS: {TRUSTED_HOSTS_LIST}")

app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=TRUSTED_HOSTS_LIST
)
logger.info(f"ProxyHeadersMiddleware configured for trusted hosts: {TRUSTED_HOSTS_LIST}")

# 1. Rate Limiting Middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
logger.info("SlowAPI Rate Limiting Middleware configured.")

# 2. Session Middleware
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY")
JWT_SECRET_KEY_FROM_ENV = os.environ.get("JWT_SECRET_KEY")

if not SESSION_SECRET_KEY:
    logger.warning("SESSION_SECRET_KEY is not set in .env. Falling back to JWT_SECRET_KEY for session secret.")
    SESSION_SECRET_KEY = JWT_SECRET_KEY_FROM_ENV
    if SESSION_SECRET_KEY == JWT_SECRET_KEY_FROM_ENV and JWT_SECRET_KEY_FROM_ENV is not None:
         logger.warning("Using JWT_SECRET_KEY (from env) as SESSION_SECRET_KEY. Strongly recommend a separate SESSION_SECRET_KEY for production.")

if not SESSION_SECRET_KEY: 
    SESSION_SECRET_KEY = "insecure-default-session-key-for-dev-only-change-me" 
    logger.error("CRITICAL: NEITHER SESSION_SECRET_KEY NOR JWT_SECRET_KEY are set in .env. Using an insecure default for session. THIS IS NOT SAFE FOR PRODUCTION.")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)
logger.info("Session Middleware configured.")

# 3. CORS Middleware
ALLOWED_ORIGINS_STR = os.environ.get("ALLOWED_ORIGINS", "*") 
if ALLOWED_ORIGINS_STR == "*":
    logger.warning("CORS allow_origins is set to '*' (allow all). This is suitable for development but NOT recommended for production.")
    allow_origins_list = ["*"]
else:
    allow_origins_list = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(',')]

app.add_middleware(
    CORSMiddleware, 
    allow_origins=allow_origins_list, 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)
logger.info(f"CORS Middleware configured with origins: {allow_origins_list}")

# --- Include Routers ---
app.include_router(auth_router.router, prefix="/auth")
app.include_router(signin_router.router, prefix="/auth")
app.include_router(password_reset_router.router, prefix="/auth")
app.include_router(user_router.router, prefix="/users")
app.include_router(message_router.router, prefix="/messages")
app.include_router(messaging_router.router, prefix="/messaging")
app.include_router(user_actions_router.router, prefix="/users")
app.include_router(admin_router.router, prefix="/admin")

logger.info("Auth, signin, password_reset, user, message, messaging, user_actions, admin routers included.")

# --- Root Endpoints ---
@app.get("/", tags=["App Root"], summary="Backend Root Status") 
async def read_root_server():
    return {"message": "CronPost Backend is running. API is accessed via Nginx at /api prefix."}