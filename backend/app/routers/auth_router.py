# backend/app/routers/auth_router.py
# Version: 2.7.0

import os
import logging
import uuid
import secrets
import httpx
import string
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, status, Request as FastAPIRequest, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr, Field

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
from ..db.models import User, EmailConfirmation, UserAccountStatusEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

# --- IMPORT MỚI ---
from ..services.captcha_service import verify_turnstile_captcha
from ..services.email_service import send_email_async # Import hàm gửi email mới

logger = logging.getLogger(__name__)

# --- Rate Limiter ---
limiter = Limiter(key_func=get_remote_address, default_limits=["1000/day", "100/hour", "10/minute"])
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
google_oauth_client: Optional[AsyncOAuth2Client] = None

# --- CÁC HÀM TIỆN ÍCH ( giữ nguyên) ---
async def get_google_oauth_client():
    # ... (giữ nguyên logic)
    global google_oauth_client
    if google_oauth_client is None:
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI_FROM_ENV:
            logger.error("Google OAuth Client ID, Secret OR Redirect URI are not configured in .env.")
            return None
        google_oauth_client = AsyncOAuth2Client(
            client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET,
            redirect_uri=GOOGLE_REDIRECT_URI_FROM_ENV, scope='openid profile email',
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
        )
    if not hasattr(google_oauth_client, 'metadata') or not google_oauth_client.metadata:
        try:
            if hasattr(google_oauth_client, 'load_server_metadata'):
                 await google_oauth_client.load_server_metadata()
            else:
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get(google_oauth_client.server_metadata_url, timeout=10.0)
                    response.raise_for_status(); fetched_metadata = response.json()
                    google_oauth_client.metadata = fetched_metadata
            logger.info("Google OAuth server metadata loaded/refreshed successfully in get_google_oauth_client.")
            if not google_oauth_client.metadata: raise Exception("Metadata still empty after load attempt.")
        except Exception as e:
            logger.error(f"Failed to load/refresh Google OAuth server metadata in get_google_oauth_client: {e}", exc_info=True)
            google_oauth_client = None; return None
    return google_oauth_client

class UserCreateRequest(BaseModel): email: EmailStr; password: str = Field(..., min_length=6, max_length=20); captchaToken: str
class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    message: Optional[str] = None
    class Config: from_attributes = True
class ResendConfirmationRequest(BaseModel): email: EmailStr
class TokenResponse(BaseModel): access_token: str; refresh_token: Optional[str] = None; token_type: str = "bearer"

def hash_password(p: str) -> str: return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
def verify_password(p: str, h: str) -> bool: return bcrypt.checkpw(p.encode('utf-8'),h.encode('utf-8')) if p and h else False
def create_access_token(data: dict, exp_delta: Optional[timedelta]=None) -> str:
    # ... (giữ nguyên logic)
    to_encode = data.copy()
    expire = datetime.now(dt_timezone.utc) + (exp_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(dt_timezone.utc)})
    return python_jose_jwt.encode(to_encode, APP_JWT_SECRET_KEY, algorithm=APP_JWT_ALGORITHM)
def generate_random_password(l: int=12) -> str: return ''.join(secrets.choice(string.ascii_letters + string.digits + string.punctuation) for i in range(l))

# --- CÁC HÀM DISPATCH EMAIL ĐƯỢC CẬP NHẬT ---
async def create_and_dispatch_confirmation_email_payload(db: AsyncSession,user:User,bg:BackgroundTasks,is_resend:bool=False):
    token_data={"user_id":str(user.id),"email":user.email}; token=confirmation_serializer.dumps(token_data,salt=EMAIL_CONFIRMATION_SALT)
    expires=datetime.now(dt_timezone.utc)+timedelta(hours=EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS)
    conf_rec_stmt = await db.execute(select(EmailConfirmation).filter_by(user_id=user.id,email=user.email,is_confirmed=False))
    conf_rec = conf_rec_stmt.scalars().first()
    if conf_rec:
        conf_rec.confirmation_token = token; conf_rec.token_expires_at = expires; conf_rec.created_at = datetime.now(dt_timezone.utc)
        logger.info(f"Updating EmailConfirmation for {user.email}")
    else:
        conf_rec = EmailConfirmation(user_id=user.id,email=user.email,confirmation_token=token,token_expires_at=expires)
        db.add(conf_rec); logger.info(f"Creating new EmailConfirmation for {user.email}")

    link=f"{FRONTEND_BASE_URL}/api/auth/confirm-email?token={token}"
    
    # --- THAY THẾ LOGIC GỬI ---
    email_subject = "Confirm Your CronPost Account"
    template_body = {
        "user_name": user.user_name or user.email.split('@')[0],
        "confirmation_link": link,
        "token_lifespan_hours": EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS,
    }
    bg.add_task(send_email_async, email_subject, user.email, template_body, "confirmation.html")
    # ---------------------------
    
    logger.info(f"Dispatched 'signup_confirmation' for {user.email}.")

async def dispatch_send_google_welcome_email(email:str,name:Optional[str],pw:str,bg:BackgroundTasks):
    # --- THAY THẾ LOGIC GỬI ---
    email_subject = "Welcome to CronPost!"
    template_body = {
        "user_name": name or email.split('@')[0],
        "random_password": pw,
    }
    bg.add_task(send_email_async, email_subject, email, template_body, "google_welcome.html")
    # ---------------------------

    logger.info(f"Dispatched 'welcome_google' for {email}.")


# --- CÁC ENDPOINT (giữ nguyên logic, chỉ thay đổi cách gọi hàm gửi mail) ---

@router.post("/signup",response_model=UserResponse,status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(SIGNUP_RATE_LIMIT)
async def signup_user_endpoint(ud:UserCreateRequest,request:FastAPIRequest,bg:BackgroundTasks,db:AsyncSession=Depends(get_db_session)):
    # ... (giữ nguyên logic)
    logger.info(f"Signup: {ud.email} from IP: {request.client.host if request.client else 'N/A'}");
    if db and db.bind: logger.info(f"Engine URL: {db.bind.sync_engine.url}")
    else: raise HTTPException(500,"DB session error.")
    if not await verify_turnstile_captcha(token=ud.captchaToken, client_ip=request.client.host if request.client else None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,"Invalid CAPTCHA.")
    user_for_response =(await db.execute(select(User).filter_by(email=ud.email))).scalars().first()
    transaction_message = ""
    if user_for_response and user_for_response.is_confirmed_by_email:
        raise HTTPException(status.HTTP_409_CONFLICT,"Email already registered and confirmed.")
    if user_for_response:
        await create_and_dispatch_confirmation_email_payload(db,user_for_response,bg,is_resend=True)
        transaction_message="Account exists but unconfirmed. A new confirmation email has been sent."
    else:
        email_prefix = ud.email.split('@')[0]
        new_user_obj=User(email=ud.email, password_hash=hash_password(ud.password), user_name=email_prefix, provider='email')
        db.add(new_user_obj);
        try:
            await db.flush()
            await create_and_dispatch_confirmation_email_payload(db,new_user_obj,bg)
            user_for_response = new_user_obj
            transaction_message="Registration successful. Please check your email to verify your account."
        except IntegrityError:
            await db.rollback()
            logger.warning(f"IntegrityError on new user {ud.email}, re-checking for race condition.")
            user_check_after_integrity_error =(await db.execute(select(User).filter_by(email=ud.email))).scalars().first()
            if user_check_after_integrity_error and user_check_after_integrity_error.is_confirmed_by_email:
                raise HTTPException(status.HTTP_409_CONFLICT,"Email confirmed in race.")
            if user_check_after_integrity_error:
                 logger.info(f"Race condition: User {ud.email} found unconfirmed. Resending email.")
                 if not user_check_after_integrity_error.user_name: user_check_after_integrity_error.user_name = ud.email.split('@')[0]
                 await create_and_dispatch_confirmation_email_payload(db,user_check_after_integrity_error,bg,is_resend=True)
                 transaction_message="Confirmation email resent due to a concurrent registration attempt."
                 user_for_response = user_check_after_integrity_error
            else:
                logger.error(f"IntegrityError for {ud.email} but user_check_after_integrity_error is None. This is unexpected.")
                transaction_message = "A server conflict occurred during registration. Please try again."
                raise HTTPException(status_code=500, detail=transaction_message)
    if not user_for_response:
        logger.error(f"User object is None before final commit for {ud.email}. Logic error in signup.")
        await db.rollback()
        raise HTTPException(status_code=500,detail="User processing error, user object is None before commit.")
    if not transaction_message :
        transaction_message = "Signup process completed with an unspecified message."
        logger.warning(f"Transaction message was empty for {ud.email}. Setting default.")
    await db.commit(); await db.refresh(user_for_response)
    return UserResponse(id=user_for_response.id,email=user_for_response.email,message=transaction_message)

@router.get("/confirm-email",include_in_schema=False)
async def confirm_email_endpoint(token: str, db_session: AsyncSession = Depends(get_db_session)):
    # ... (giữ nguyên logic)
    redirect_email_param = ""
    try:
        token_data = confirmation_serializer.loads(token, salt=EMAIL_CONFIRMATION_SALT, max_age=EMAIL_CONFIRMATION_TOKEN_LIFESPAN_HOURS * 3600)
        user_id = uuid.UUID(token_data["user_id"])
        redirect_email_param = token_data.get("email", "")
    except SignatureExpired:
        logger.warning(f"Email confirmation token expired: {token[:10]}...")
        expired_email_for_redirect = "";
        try:
            expired_token_data = confirmation_serializer.loads(token, salt=EMAIL_CONFIRMATION_SALT, max_age=-1)
            expired_email_for_redirect = expired_token_data.get('email','')
        except BadTimeSignature: logger.warning(f"Could not decode expired/invalid token {token[:10]}... for redirect (in SignatureExpired).")
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_expired&email={expired_email_for_redirect}", status_code=status.HTTP_302_FOUND)
    except BadTimeSignature:
        logger.warning(f"Invalid email confirmation token (BadTimeSignature): {token[:10]}...")
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_invalid", status_code=status.HTTP_302_FOUND)
    confirmation_record_stmt = await db_session.execute(select(EmailConfirmation).filter_by(confirmation_token=token, user_id=user_id, email=redirect_email_param))
    confirmation_record = confirmation_record_stmt.scalars().first()
    if not confirmation_record or confirmation_record.is_confirmed:
        logger.warning(f"Confirmation token invalid, already used, or payload mismatch for token {token[:10]}.")
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_invalid_or_used&email={redirect_email_param}", status_code=status.HTTP_302_FOUND)
    user = (await db_session.get(User, confirmation_record.user_id))
    if not user:
        logger.error(f"User {confirmation_record.user_id} not found for confirmed token.");
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmation_user_not_found&email={redirect_email_param}")
    if user.is_confirmed_by_email:
        logger.info(f"Email {user.email} was already confirmed for user {user.id} (user table).")
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_already_confirmed&email={user.email}")
    user.is_confirmed_by_email = True; user.updated_at = datetime.now(dt_timezone.utc)
    if user.account_status == UserAccountStatusEnum.INS: user.account_status = UserAccountStatusEnum.INS
    confirmation_record.is_confirmed = True; confirmation_record.confirmed_at = datetime.now(dt_timezone.utc)
    await db_session.commit()
    logger.info(f"Email {user.email} confirmed successfully for user {user.id}.")
    return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=email_confirmed_success&email={user.email}", status_code=status.HTTP_302_FOUND)

@router.post("/resend-confirmation",status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(RESEND_CONFIRMATION_RATE_LIMIT)
async def resend_confirmation_email_endpoint(
    request_data:ResendConfirmationRequest, request:FastAPIRequest,
    background_tasks:BackgroundTasks, db_session:AsyncSession=Depends(get_db_session)
):
    # ... (giữ nguyên logic)
    logger.info(f"Resend confirmation request for email: {request_data.email} from IP: {request.client.host if request.client else 'N/A'}")
    user=(await db_session.execute(select(User).filter_by(email=request_data.email))).scalars().first()
    msg,http_stat="If an unconfirmed account with this email exists, a new confirmation email has been sent.",status.HTTP_202_ACCEPTED
    if user and not user.is_confirmed_by_email: await create_and_dispatch_confirmation_email_payload(db_session,user,background_tasks,is_resend=True);await db_session.commit()
    elif user and user.is_confirmed_by_email: msg,http_stat="This email address has already been confirmed.",status.HTTP_200_OK
    return JSONResponse(status_code=http_stat,content={"message":msg})


# --- Google OAuth Endpoints (giữ nguyên logic) ---
@router.get("/google")
@limiter.limit("10/minute")
async def google_oauth_login(request: FastAPIRequest):
    # ... (giữ nguyên logic)
    oauth_client = await get_google_oauth_client()
    if not oauth_client: raise HTTPException(status_code=500, detail="Google OAuth client initialization failed. Check server logs.")
    authorization_endpoint = None
    if hasattr(oauth_client, 'metadata') and oauth_client.metadata: authorization_endpoint = oauth_client.metadata.get("authorization_endpoint")
    if not authorization_endpoint:
        logger.warning("Google OAuth authorization_endpoint not in client metadata. Attempting manual fetch...")
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get('https://accounts.google.com/.well-known/openid-configuration', timeout=10.0)
                response.raise_for_status(); fetched_metadata = response.json()
                oauth_client.metadata = fetched_metadata; authorization_endpoint = fetched_metadata.get("authorization_endpoint")
                logger.info("Successfully loaded Google OAuth metadata manually in /google endpoint.")
        except Exception as e:
            logger.error(f"Failed to load Google OAuth metadata manually in /google endpoint: {e}", exc_info=True)
            authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
            logger.warning(f"Using hardcoded fallback authorization_endpoint: {authorization_endpoint}")
            if not hasattr(oauth_client, 'metadata') or not oauth_client.metadata: oauth_client.metadata = {}
            oauth_client.metadata["authorization_endpoint"] = authorization_endpoint
    if not authorization_endpoint:
        logger.error("Google authorization_endpoint could not be determined even after manual fetch/fallback.")
        raise HTTPException(status_code=500, detail="Google OAuth configuration error (cannot determine auth endpoint).")
    code_verifier = generate_token(48); request.session['google_oauth_code_verifier'] = code_verifier
    code_challenge = create_s256_code_challenge(code_verifier); request.session['google_oauth_state'] = secrets.token_urlsafe(32)
    auth_url_response = oauth_client.create_authorization_url(
        url=authorization_endpoint, redirect_uri=GOOGLE_REDIRECT_URI_FROM_ENV, state=request.session['google_oauth_state'],
        code_challenge=code_challenge, code_challenge_method='S256', access_type="offline", prompt="consent"
    )
    auth_url = auth_url_response[0] if isinstance(auth_url_response, tuple) else auth_url_response
    logger.info(f"Redirecting for Google OAuth (URL generated)")
    return RedirectResponse(auth_url)

@router.get("/google/callback", include_in_schema=False)
async def google_oauth_callback(
    request: FastAPIRequest, background_tasks: BackgroundTasks, db_session: AsyncSession = Depends(get_db_session),
    code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None
):
    # ... (giữ nguyên logic)
    if error: return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_error&detail={request.query_params.get('error_description',error)}")
    if not code or not state or state != request.session.pop('google_oauth_state', None):
        logger.warning("Google OAuth callback: State mismatch or missing code/state."); return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_state_mismatch")
    code_verifier = request.session.pop('google_oauth_code_verifier', None)
    if not code_verifier: logger.warning("Google OAuth callback: Missing code_verifier."); return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_pkce_error")
    oauth_client = await get_google_oauth_client()
    if not oauth_client: logger.error("Google OAuth callback: Failed to get oauth_client."); return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_config_error_server")
    token_endpoint_url = None; jwks_uri = None; issuer = None
    if hasattr(oauth_client, 'metadata') and oauth_client.metadata:
        token_endpoint_url = oauth_client.metadata.get("token_endpoint")
        jwks_uri = oauth_client.metadata.get("jwks_uri")
        issuer = oauth_client.metadata.get("issuer")
    if not all([token_endpoint_url, jwks_uri, issuer]):
        logger.warning("Google OAuth metadata (token_endpoint, jwks_uri, or issuer) missing in callback. Attempting manual fetch...")
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get('https://accounts.google.com/.well-known/openid-configuration', timeout=10.0)
                response.raise_for_status(); fetched_metadata = response.json()
                oauth_client.metadata = fetched_metadata
                token_endpoint_url = fetched_metadata.get("token_endpoint"); jwks_uri = fetched_metadata.get("jwks_uri"); issuer = fetched_metadata.get("issuer")
                logger.info("Successfully re-loaded Google OAuth metadata manually in callback.")
        except Exception as e:
            logger.error(f"Failed to load Google OAuth metadata manually in callback: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Could not retrieve Google OAuth server configuration (metadata fetch failed for callback).")
    if not all([token_endpoint_url, jwks_uri, issuer]):
        logger.error("Essential Google OAuth metadata could not be determined for callback.")
        raise HTTPException(status_code=500, detail="Google OAuth configuration error (essential metadata missing).")
    try:
        token_response = await oauth_client.fetch_token(url=token_endpoint_url, code=code, redirect_uri=GOOGLE_REDIRECT_URI_FROM_ENV, code_verifier=code_verifier)
        id_token_str = token_response.get('id_token')
        if not id_token_str: logger.error("Missing 'id_token' string from Google."); raise Exception("Missing id_token string")
        async with httpx.AsyncClient() as http_client:
            jwks_response = await http_client.get(jwks_uri, timeout=5.0); jwks_response.raise_for_status(); jwk_set = JsonWebKey.import_key_set(jwks_response.json())
        claims_options = {"iss":{"essential": True, "value": issuer}, "aud": {"essential": True, "value": GOOGLE_CLIENT_ID}}
        user_claims = authlib_jwt.decode(id_token_str, jwk_set, claims_cls=CodeIDToken, claims_options=claims_options)
        user_claims.validate()
        logger.info("Successfully decoded and validated Google ID token using Authlib.")
    except JoseJWTError as e_jwt: logger.error(f"Error decoding/validating Google ID token: {e_jwt}", exc_info=True); return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_token_invalid")
    except Exception as e: logger.error(f"Error during Google token exchange or ID token processing: {e}", exc_info=True); return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_token_error")
    google_email, google_id = user_claims.get("email"), user_claims.get("sub")
    if not google_email or not google_id or not user_claims.get("email_verified"):
        logger.warning(f"Google OAuth: Missing info or email not verified for {google_email or ''}")
        return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_email_not_verified&email={google_email or ''}")
    user = (await db_session.execute(select(User).filter_by(email=google_email))).scalars().first()
    status_param = "google_signin_success"
    if not user or not user.is_confirmed_by_email:
        random_pw = generate_random_password(); hashed_pw = hash_password(random_pw)
        if not user:
            user = User(email=google_email, password_hash=hashed_pw, google_id=google_id, user_name=user_claims.get("name"), is_confirmed_by_email=True, account_status=UserAccountStatusEnum.INS, provider='google')
            db_session.add(user); status_param = "google_signup_success_check_email"
        else:
            user.password_hash, user.google_id, user.is_confirmed_by_email = hashed_pw, google_id, True
            user.user_name = user_claims.get("name") or user.user_name
            user.provider, user.account_status = 'google', UserAccountStatusEnum.INS
            status_param = "google_merge_success_check_email"
        try: await db_session.commit(); await db_session.refresh(user); await dispatch_send_google_welcome_email(google_email, user_claims.get("name"), random_pw, background_tasks)
        except IntegrityError: await db_session.rollback(); logger.error(f"IntegrityError Google OAuth user save: {google_email}", exc_info=True); return RedirectResponse(url=f"{FRONTEND_BASE_URL}/signin.html?status=google_oauth_db_error")
    elif not user.google_id:
        user.google_id = google_id; user.user_name = user_claims.get("name") or user.user_name
        await db_session.commit(); await db_session.refresh(user); status_param = "google_link_success"
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "provider": "google"})
    final_redirect_url = f"/dashboard.html?access_token={access_token}&status={status_param}" # Changed to redirect to dashboard directly
    logger.info(f"Google OAuth OK for {user.email}. Redirecting to dashboard.");
    response = RedirectResponse(url=f"{FRONTEND_BASE_URL}/dashboard.html")
    response.set_cookie(key="redirect_info", value=f'{{"access_token": "{access_token}", "status": "{status_param}"}}', max_age=10, path="/", httponly=False) # Not secure, just for simple redirect
    return response