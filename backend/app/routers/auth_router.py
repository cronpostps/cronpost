# backend/app/routers/auth_router.py
# Version: 3.0.2
# Changelog:
# - Added py-user-agents to parse device_os from user-agent string on login.
# - Added login history logging for Google OAuth sign-ins.

import os
import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from user_agents import parse
from typing import Optional, Dict, Any
import secrets
import string
import pytz

from fastapi import APIRouter, HTTPException, Depends, status, Request as FastAPIRequest, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr, Field

import httpx
import bcrypt
from jose import jwt as python_jose_jwt, JWTError as JoseJWTError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from authlib.oidc.core import CodeIDToken
from authlib.jose import JsonWebKey
from authlib.jose import jwt as authlib_jwt
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..db.database import get_db_session
from ..db.models import User, EmailConfirmation, UserAccountStatusEnum, LoginHistory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from ..services.captcha_service import verify_turnstile_captcha
from ..services.email_service import send_email_async

logger = logging.getLogger(__name__)

# --- Rate Limiter ---
limiter = Limiter(key_func=get_remote_address, default_limits=["5000/day", "300/hour", "60/minute"])
SIGNUP_RATE_LIMIT = "3/hour"
RESEND_CONFIRMATION_EMAIL_INTERVAL_MINUTES_INT = int(os.environ.get("RESEND_CONFIRMATION_EMAIL_INTERVAL_MINUTES", "30"))
RESEND_CONFIRMATION_RATE_LIMIT = f"1/{RESEND_CONFIRMATION_EMAIL_INTERVAL_MINUTES_INT}minute"

router = APIRouter(tags=["Authentication"])

# --- Cấu hình từ Biến Môi trường ---
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost")
APP_JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
APP_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
EMAIL_CONFIRMATION_SECRET_KEY = os.environ.get("EMAIL_CONFIRMATION_SECRET_KEY", APP_JWT_SECRET_KEY)
EMAIL_CONFIRMATION_SALT = os.environ.get("EMAIL_CONFIRMATION_SALT", "email-confirmation-salt")
EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS = int(os.environ.get("EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS", "24"))
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI_FROM_ENV = os.environ.get("GOOGLE_REDIRECT_URI")

confirmation_serializer = URLSafeTimedSerializer(EMAIL_CONFIRMATION_SECRET_KEY)

# --- Pydantic Models ---
class UserCreateRequest(BaseModel): 
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=20) 
    captchaToken: str
    timezone: Optional[str] = None

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    message: Optional[str] = None
    class Config: from_attributes = True
class ResendConfirmationRequest(BaseModel): email: EmailStr
class TokenResponse(BaseModel): access_token: str; refresh_token: Optional[str] = None; token_type: str = "bearer"

# --- Hàm tiện ích ---
def hash_password(p: str) -> str: return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
def verify_password(p: str, h: str) -> bool: return bcrypt.checkpw(p.encode('utf-8'),h.encode('utf-8')) if p and h else False
def create_access_token(data: dict, exp_delta: Optional[timedelta]=None) -> str:
    to_encode = data.copy()
    expire = datetime.now(dt_timezone.utc) + (exp_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(dt_timezone.utc)})
    return python_jose_jwt.encode(to_encode, APP_JWT_SECRET_KEY, algorithm=APP_JWT_ALGORITHM)
def generate_random_password(l: int=12) -> str: return ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(l))


# --- Hàm gửi email (đã sửa để dùng service mới) ---
async def create_and_dispatch_confirmation_email_payload(db: AsyncSession,user:User,bg:BackgroundTasks,is_resend:bool=False):
    token_data={"user_id":str(user.id),"email":user.email}
    token=confirmation_serializer.dumps(token_data,salt=EMAIL_CONFIRMATION_SALT)
    expires=datetime.now(dt_timezone.utc)+timedelta(hours=EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS)
    
    conf_rec_stmt = await db.execute(select(EmailConfirmation).filter_by(user_id=user.id,email=user.email,is_confirmed=False))
    conf_rec = conf_rec_stmt.scalars().first()
    
    if conf_rec:
        conf_rec.confirmation_token = token
        conf_rec.token_expires_at = expires
        conf_rec.created_at = datetime.now(dt_timezone.utc)
    else:
        conf_rec = EmailConfirmation(user_id=user.id,email=user.email,confirmation_token=token,token_expires_at=expires)
        db.add(conf_rec)
        
    link=f"{FRONTEND_BASE_URL}/api/auth/confirm-email?token={token}"
    email_subject = "Confirm Your CronPost Account"
    template_body = { "user_name": user.user_name or user.email.split('@')[0], "confirmation_link": link, "token_lifespan_hours": EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS }
    
    bg.add_task(send_email_async, email_subject, user.email, template_body, "confirmation.html")
    logger.info(f"Dispatched 'signup_confirmation' for {user.email}.")

async def dispatch_send_google_welcome_email(email:str,name:Optional[str],pw:str,bg:BackgroundTasks):
    email_subject = "Welcome to CronPost!"
    template_body = { "user_name": name or email.split('@')[0], "random_password": pw }
    bg.add_task(send_email_async, email_subject, email, template_body, "google_welcome.html")
    logger.info(f"Dispatched 'welcome_google' for {email}.")


# --- Endpoints ---

@router.post("/signup",response_model=UserResponse,status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(SIGNUP_RATE_LIMIT)
async def signup_user_endpoint(ud:UserCreateRequest,request:FastAPIRequest,bg:BackgroundTasks,db:AsyncSession=Depends(get_db_session)):
    
    logger.info(f"Received signup payload: {ud.dict()}")
    
    if not await verify_turnstile_captcha(token=ud.captchaToken, client_ip=request.client.host if request.client else None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,"Invalid CAPTCHA.")
    
    user_for_response =(await db.execute(select(User).filter_by(email=ud.email))).scalars().first()
    transaction_message = ""

    if user_for_response and user_for_response.is_confirmed_by_email:
        raise HTTPException(status.HTTP_409_CONFLICT,"Email already registered and confirmed.")
    
    # --- KHỐI LOGIC ĐÃ ĐƯỢC SỬA ---
    if user_for_response:
        # User đã tồn tại nhưng chưa xác nhận, cập nhật timezone và gửi lại email
        logger.info(f"Account for {ud.email} exists but is unconfirmed. Updating timezone and resending confirmation.")
        
        valid_timezone = user_for_response.timezone # Giữ lại timezone cũ làm mặc định
        if ud.timezone:
            try:
                pytz.timezone(ud.timezone)
                valid_timezone = ud.timezone
                logger.info(f"Updating existing unconfirmed user with new timezone: {valid_timezone}")
            except pytz.UnknownTimeZoneError:
                logger.warning(f"Received unknown timezone '{ud.timezone}'. Keeping existing timezone '{valid_timezone}'.")
        
        user_for_response.timezone = valid_timezone # CẬP NHẬT TIMEZONE CHO USER HIỆN TẠI
        
        await create_and_dispatch_confirmation_email_payload(db,user_for_response,bg,is_resend=True)
        transaction_message="Account exists but unconfirmed. Timezone updated and a new confirmation email has been sent."
    # --- KẾT THÚC KHỐI LOGIC ĐÃ SỬA ---
    else:
        # Tạo user hoàn toàn mới
        valid_timezone = 'Etc/UTC'
        if ud.timezone:
            try:
                pytz.timezone(ud.timezone)
                valid_timezone = ud.timezone
                logger.info(f"Received and validated timezone '{valid_timezone}' for new user {ud.email}.")
            except pytz.UnknownTimeZoneError:
                logger.warning(f"Received unknown timezone '{ud.timezone}' for new user {ud.email}. Defaulting to UTC.")
        
        email_prefix = ud.email.split('@')[0]
        new_user_obj=User(
            email=ud.email, 
            password_hash=hash_password(ud.password), 
            user_name=email_prefix, 
            provider='email',
            timezone=valid_timezone
        )
        db.add(new_user_obj)
        try:
            await db.flush()
            await create_and_dispatch_confirmation_email_payload(db,new_user_obj,bg)
            user_for_response = new_user_obj
            transaction_message="Registration successful. Please check your email to verify your account."
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=500, detail="A server conflict occurred during registration. Please try again.")
    
    if not user_for_response:
        await db.rollback()
        raise HTTPException(status_code=500,detail="User processing error, user object is None before commit.")

    await db.commit()
    await db.refresh(user_for_response)
    
    return UserResponse(id=user_for_response.id,email=user_for_response.email,message=transaction_message)

@router.get("/confirm-email",include_in_schema=False)
async def confirm_email_endpoint(token: str, db_session: AsyncSession = Depends(get_db_session)):
    redirect_email_param = ""
    try:
        token_data = confirmation_serializer.loads(token, salt=EMAIL_CONFIRMATION_SALT, max_age=EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS * 3600)
        user_id = uuid.UUID(token_data["user_id"])
        redirect_email_param = token_data.get("email", "")
    except SignatureExpired:
        try:
            expired_token_data = confirmation_serializer.loads(token, salt=EMAIL_CONFIRMATION_SALT, max_age=-1)
            expired_email_for_redirect = expired_token_data.get('email','')
        except BadTimeSignature:
            expired_email_for_redirect = ""
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_expired&email={expired_email_for_redirect}")
    except BadTimeSignature:
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_invalid")
    
    confirmation_record = (await db_session.execute(select(EmailConfirmation).filter_by(confirmation_token=token, user_id=user_id, email=redirect_email_param))).scalars().first()
    if not confirmation_record or confirmation_record.is_confirmed:
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_invalid_or_used&email={redirect_email_param}")
    
    user = await db_session.get(User, confirmation_record.user_id)
    if not user:
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_user_not_found&email={redirect_email_param}")
    if user.is_confirmed_by_email:
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_already_confirmed&email={user.email}")
    
    user.is_confirmed_by_email = True
    user.updated_at = datetime.now(dt_timezone.utc)
    confirmation_record.is_confirmed = True
    confirmation_record.confirmed_at = datetime.now(dt_timezone.utc)
    await db_session.commit()
    return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmed_success&email={user.email}")

@router.post("/resend-confirmation",status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(RESEND_CONFIRMATION_RATE_LIMIT)
async def resend_confirmation_email_endpoint(request_data:ResendConfirmationRequest, request:FastAPIRequest, background_tasks:BackgroundTasks, db_session:AsyncSession=Depends(get_db_session)):
    user=(await db_session.execute(select(User).filter_by(email=request_data.email))).scalars().first()
    msg,http_stat="If an unconfirmed account with this email exists, a new confirmation email has been sent.",status.HTTP_202_ACCEPTED
    if user and not user.is_confirmed_by_email:
        await create_and_dispatch_confirmation_email_payload(db_session,user,background_tasks,is_resend=True)
        await db_session.commit()
    elif user and user.is_confirmed_by_email:
        msg,http_stat="This email address has already been confirmed.",status.HTTP_200_OK
    return JSONResponse(status_code=http_stat,content={"message":msg})

# --- GOOGLE OAUTH ENDPOINTS (LOGIC FROM V2.6.10) ---
@router.get("/google")
@limiter.limit("10/minute")
async def google_oauth_login(request: FastAPIRequest):
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI_FROM_ENV]):
        raise HTTPException(status_code=500, detail="Google OAuth is not configured on the server.")
        
    # Create OAuth2 client without server metadata loading
    oauth_client = AsyncOAuth2Client(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        redirect_uri=GOOGLE_REDIRECT_URI_FROM_ENV,
        scope='openid profile email'
    )

    # Use Google's authorization endpoint directly
    authorization_endpoint = 'https://accounts.google.com/o/oauth2/v2/auth'
    
    code_verifier = generate_token(48)
    request.session['google_oauth_code_verifier'] = code_verifier
    code_challenge = create_s256_code_challenge(code_verifier)
    request.session['google_oauth_state'] = secrets.token_urlsafe(32)
    
    auth_url, _ = oauth_client.create_authorization_url(
        url=authorization_endpoint,
        state=request.session['google_oauth_state'],
        code_challenge=code_challenge,
        code_challenge_method='S256',
        access_type="offline",
        prompt="consent"
    )
    return RedirectResponse(auth_url)

@router.get("/google/callback", include_in_schema=False)
async def google_oauth_callback(
    request: FastAPIRequest,
    background_tasks: BackgroundTasks,
    db_session: AsyncSession = Depends(get_db_session)
):
    if 'error' in request.query_params:
        return RedirectResponse(
            url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_error&detail={request.query_params.get('error_description','Unknown Error')}"
        )
    
    state = request.query_params.get('state')
    if not state or state != request.session.pop('google_oauth_state', None):
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_state_mismatch")

    oauth_client = AsyncOAuth2Client(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        redirect_uri=GOOGLE_REDIRECT_URI_FROM_ENV
    )

    try:
        code_verifier = request.session.pop('google_oauth_code_verifier', None)
        token_response = await oauth_client.fetch_token(
            'https://oauth2.googleapis.com/token',
            code=request.query_params.get('code'),
            code_verifier=code_verifier
        )
        
        async with httpx.AsyncClient() as client:
            jwks_response = await client.get('https://www.googleapis.com/oauth2/v3/certs')
            jwk_set = JsonWebKey.import_key_set(jwks_response.json())
        
        user_claims = authlib_jwt.decode(
            token_response['id_token'],
            jwk_set,
            claims_cls=CodeIDToken,
            claims_options={
                "iss": {"essential": True, "value": "https://accounts.google.com"},
                "aud": {"essential": True, "value": GOOGLE_CLIENT_ID}
            }
        )
        user_claims.validate()
    except Exception as e:
        logger.error(f"Error during Google token exchange or validation: {e}", exc_info=True)
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_token_error&detail={str(e)}")

    google_email = user_claims.get("email")
    if not google_email or not user_claims.get("email_verified"):
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_email_not_verified&email={google_email or ''}")

    user = (await db_session.execute(select(User).filter_by(email=google_email))).scalars().first()
    
    # Mặc định là đăng nhập thành công
    status_param = "google_signin_success"

    if not user:
        # User mới, tạo tài khoản và đặt status để chuyển hướng đến trang hoàn tất hồ sơ
        random_pw = generate_random_password(12)
        user = User(
            email=google_email, 
            password_hash=hash_password(random_pw), 
            google_id=user_claims.get("sub"),
            user_name=user_claims.get("name"), 
            is_confirmed_by_email=True, # Email từ Google được coi là đã xác thực
            provider='google',
            timezone='Etc/UTC' # Sẽ được cập nhật ở bước sau
        )
        db_session.add(user)
        status_param = "google_signup_success_new_user" # Status mới cho người dùng mới
        await dispatch_send_google_welcome_email(google_email, user.user_name, random_pw, background_tasks)
        
        # --- THÊM VÀO ĐỂ SỬA LỖI ---
        # Đẩy session vào DB để user mới nhận được ID trước khi tạo LoginHistory
        await db_session.flush()
        await db_session.refresh(user)
        # ---------------------------
        
    elif not user.google_id:
        # User đã tồn tại với email/password, liên kết tài khoản Google
        user.google_id = user_claims.get("sub")
        user.user_name = user_claims.get("name") or user.user_name
        status_param = "google_link_success"

    # Ghi lại lịch sử đăng nhập
    user.last_activity_at = datetime.now(dt_timezone.utc)
    user_agent_string = request.headers.get("user-agent")
    device_os_info = parse(user_agent_string).os.family if user_agent_string else None
    
    db_session.add(LoginHistory(
        user_id=user.id,
        ip_address=request.client.host,
        user_agent=user_agent_string,
        device_os=device_os_info
    ))
    
    await db_session.commit()
    await db_session.refresh(user)
    
    # Tạo access token
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "provider": "google"})
    
    # --- LOGIC CHUYỂN HƯỚNG MỚI ---
    # Nếu là người dùng mới, chuyển đến trang hoàn tất hồ sơ
    if status_param == "google_signup_success_new_user":
        logger.info(f"New Google user {user.email}. Redirecting to complete profile page.")
        redirect_url = f"{FRONTEND_BASE_URL}/complete-profile.html?token={access_token}"
    else:
        # Nếu là người dùng cũ, vào thẳng dashboard
        redirect_url = f"{FRONTEND_BASE_URL}/dashboard.html?token={access_token}&status={status_param}&email={user.email}"
    
    response = RedirectResponse(url=redirect_url)
    return response