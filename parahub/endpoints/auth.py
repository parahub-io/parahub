"""
Authentication endpoints for Parahub API
Handles user login, registration, token management
"""

from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel, EmailStr, field_validator
from django.contrib.auth import authenticate, login as django_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse
from identity.models import Account, Profile
from core.models import Instance
from parahub.auth import create_tokens_for_user, GlobalAuth
from parahub.ratelimit import ratelimit, user_or_ip
from ninja_jwt.tokens import RefreshToken
from typing import Optional
import hashlib
import logging
import secrets

logger = logging.getLogger(__name__)

# Create router for auth endpoints
auth_router = Router(tags=["Authentication"])


# Pydantic schemas
class LoginRequest(BaseModel):
    username: str
    password: str


class PoWProof(BaseModel):
    challenge: str
    hash: str  # hex-encoded scrypt output


class RegisterRequest(BaseModel):
    username: str
    email: Optional[EmailStr] = None  # if omitted, defaults to username@domain (HNA)
    password: str
    password_confirm: str
    local_name: str
    display_name: Optional[str] = None
    pow_proof: Optional[PoWProof] = None

    @field_validator('password_confirm')
    @classmethod
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: str
    username: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfoResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    date_joined: str
    profile: Optional[dict] = None


@auth_router.post("/token/", response={200: TokenResponse, 400: dict, 401: dict}, auth=None)
@ratelimit(group='auth:login', key=user_or_ip, rate='5/m', method='POST')
def login(request, data: LoginRequest):
    """
    Authenticate user and return JWT tokens

    **Rate Limit:** 5 attempts per minute per IP/user

    **Requirements:**
    - Valid username and password

    **Returns:**
    - Access token (JWT)
    - Refresh token
    - Token metadata
    """
    # Authenticate user
    user = authenticate(request, username=data.username, password=data.password)

    if user is None:
        raise HttpError(401, "invalid_credentials")

    if not user.is_active:
        raise HttpError(401, "account_disabled")

    # Create Django session for the user
    # This allows session-based auth to work alongside JWT
    django_login(request, user)

    # Create tokens
    tokens = create_tokens_for_user(user)

    logger.info(f"User {user.username} authenticated successfully")

    return TokenResponse(
        **tokens,
        user_id=str(user.id),
        username=user.username
    )


@auth_router.post("/refresh/", response={200: TokenResponse, 401: dict}, auth=None)
@ratelimit(group='auth:refresh', key=user_or_ip, rate='10/m', method='POST')
def refresh_token(request, data: RefreshRequest):
    """
    Refresh JWT access token using refresh token

    **Rate Limit:** 10 attempts per minute per IP/user

    **Requirements:**
    - Valid refresh token

    **Returns:**
    - New access token
    - Same refresh token (or new one)
    """
    try:
        # Validate and decode refresh token
        refresh = RefreshToken(data.refresh_token)
        user_id = refresh.get('user_id')
    except Exception:
        raise HttpError(401, "Invalid refresh token")

    try:
        user = Account.objects.get(id=user_id)
    except Account.DoesNotExist:
        raise HttpError(401, "Invalid refresh token")

    if not user.is_active:
        raise HttpError(401, "Account is disabled")

    # Create new tokens
    tokens = create_tokens_for_user(user)

    return TokenResponse(
        **tokens,
        user_id=str(user.id),
        username=user.username
    )


# scrypt params: N=65536 → ~1-2s on phone, GPU only ~10-20x faster (memory-hard)
# Server verification: one hashlib.scrypt call ~50-100ms — acceptable at 3/h rate limit
_POW_SCRYPT_N = 262144
_POW_SCRYPT_R = 8
_POW_SCRYPT_P = 1
_POW_SCRYPT_DKLEN = 32
_POW_CACHE_PREFIX = "pow_challenge:"
_POW_TTL = 300  # 5 minutes


@auth_router.get("/pow/challenge/", auth=None)
@ratelimit(group='auth:pow_challenge', key='ip', rate='10/m', method='GET')
def get_pow_challenge(request):
    """Return a one-time scrypt PoW challenge for registration anti-bot verification."""
    from constance import config
    if not config.REGISTRATION_ENABLED:
        raise HttpError(403, "Registration is disabled")
    challenge = secrets.token_hex(32)
    cache.set(f"{_POW_CACHE_PREFIX}{challenge}", True, timeout=_POW_TTL)
    return {
        "challenge": challenge,
        "params": {"N": _POW_SCRYPT_N, "r": _POW_SCRYPT_R, "p": _POW_SCRYPT_P, "dkLen": _POW_SCRYPT_DKLEN},
    }


def _get_client_ip(request) -> str:
    """Extract client IP from X-Forwarded-For or REMOTE_ADDR."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _verify_pow(proof: PoWProof) -> tuple[bool, str]:
    """Verify scrypt PoW proof. Returns (is_valid, error_message)."""
    cache_key = f"{_POW_CACHE_PREFIX}{proof.challenge}"
    if not cache.get(cache_key):
        return False, "Challenge expired or not found"

    # Server recomputes — params are fixed server-side, client can't downgrade
    # maxmem: N=65536, r=8 requires 128*N*r = 64MB; set 128MB to be safe
    data = proof.challenge.encode()
    salt = b"parahub-pow-v1"
    expected = hashlib.scrypt(
        data, salt=salt,
        n=_POW_SCRYPT_N, r=_POW_SCRYPT_R, p=_POW_SCRYPT_P, dklen=_POW_SCRYPT_DKLEN,
        maxmem=320 * 1024 * 1024
    ).hex()

    if expected != proof.hash:
        logger.warning(f"PoW failed (hash mismatch): challenge={proof.challenge[:8]}...")
        return False, "Hash mismatch"

    cache.delete(cache_key)  # one-time use
    logger.info(f"PoW verified: challenge={proof.challenge[:8]}...")
    return True, ""


@auth_router.post("/register/", response={200: TokenResponse, 400: dict, 403: dict, 500: dict}, auth=None)
@ratelimit(group='auth:register', key='ip', rate='3/h', method='POST')
def register(request, data: RegisterRequest):
    """
    Register new user account with profile

    **Rate Limit:** 3 registrations per hour per IP (anti-spam)

    **Requirements:**
    - Unique username and email
    - Valid password
    - Profile information

    **Returns:**
    - JWT tokens for immediate login
    """
    try:
        from constance import config
        if not config.REGISTRATION_ENABLED:
            raise HttpError(403, "Registration is disabled")

        # Verify PoW proof
        if not data.pow_proof:
            raise HttpError(400, "Proof of work required")
        is_valid, pow_error = _verify_pow(data.pow_proof)
        if not is_valid:
            raise HttpError(400, f"PoW verification failed: {pow_error}")

        # Validate username format and reserved words
        username = data.username.lower().strip()
        is_valid, error_msg = _is_username_valid(username)
        if not is_valid:
            raise HttpError(400, error_msg)

        # Validate password
        try:
            validate_password(data.password)
        except ValidationError as e:
            raise HttpError(400, f"Password validation failed: {'; '.join(e.messages)}")

        # Check if username exists
        if Account.objects.filter(username=username).exists():
            raise HttpError(400, "Username already exists")

        # Get default instance (assuming single instance for now)
        try:
            instance = Instance.objects.first()
            if not instance:
                raise HttpError(500, "No instance configured")
        except Exception:
            raise HttpError(500, "Instance configuration error")

        from django.contrib.sites.shortcuts import get_current_site
        domain = get_current_site(request).domain
        hna_email = f"{username}@{domain}"

        # Use provided email or fall back to HNA
        email = data.email if data.email else hna_email
        if data.email and Account.objects.filter(email=data.email).exists():
            raise HttpError(400, "Email already in use")

        # Create user and profile in transaction
        with transaction.atomic():
            # Create user account
            user = Account.objects.create_user(
                username=username,
                email=email,
                password=data.password,
                instance=instance,
                registration_ip=_get_client_ip(request),
            )
            
            # Create profile
            profile = Profile.objects.create(
                account=user,
                instance=instance,
                local_name=data.local_name,
                display_name=data.display_name or data.local_name
            )
            
            logger.info(f"New user registered: {user.username} with profile: {profile.hna}")
        
        # Create tokens for immediate login
        tokens = create_tokens_for_user(user)
        
        return TokenResponse(
            **tokens,
            user_id=str(user.id),
            username=user.username
        )
        
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HttpError(400, "Registration failed")


@auth_router.get("/me/", response={200: UserInfoResponse, 400: dict}, auth=GlobalAuth())
@ratelimit(group='auth:me', key=user_or_ip, rate='60/m')
def get_current_user(request):
    """
    Get current authenticated user information
    
    **Requirements:**
    - Valid JWT token
    
    **Returns:**
    - User account information
    - Primary profile information
    """
    try:
        user = request.auth
        
        # Get user's primary profile
        profile = user.profiles.first()
        profile_data = None
        
        if profile:
            profile_data = {
                "id": str(profile.id),
                "local_name": profile.local_name,
                "display_name": profile.display_name,
                "hna": profile.hna,
                "reputation_score": float(profile.reputation_score),
                "is_verified_wot": profile.is_verified_wot,
                "is_foundation_member": profile.is_foundation_member(),
                "avatar_url": profile.avatar.url if profile.avatar else None,
                "profile_type": profile.profile_type,
                "is_primary": profile.is_primary,
            }
        
        return UserInfoResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            date_joined=user.date_joined.isoformat(),
            profile=profile_data
        )
        
    except Exception as e:
        logger.error(f"Get user info error: {e}")
        raise HttpError(400, "Failed to get user information")


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


@auth_router.post("/logout/", auth=None)
@ratelimit(group='auth:logout', key=user_or_ip, rate='30/m', method='POST')
def logout(request, data: LogoutRequest = None):
    """
    Logout user and blacklist JWT refresh token

    **Requirements:**
    - Optional refresh_token in request body for JWT blacklisting

    **Returns:**
    - Success message

    **Behavior:**
    - Destroys Django session if authenticated
    - Blacklists refresh token if provided (prevents token reuse)
    - Client must still discard access token from memory
    """
    from django.contrib.auth import logout as django_logout

    # Logout from Django session if authenticated
    if request.user.is_authenticated:
        django_logout(request)
        logger.info(f"User session logged out: {request.user.username}")

    # Blacklist refresh token if provided
    if data and data.refresh_token:
        try:
            from ninja_jwt.tokens import RefreshToken
            token = RefreshToken(data.refresh_token)
            token.blacklist()
            logger.info(f"Refresh token blacklisted: {token.get('jti')}")
            return {"message": "Logged out successfully, token blacklisted"}
        except Exception as e:
            logger.warning(f"Failed to blacklist token on logout: {e}")
            # Don't fail logout if blacklisting fails
            return {"message": "Logged out successfully (token blacklist failed)"}

    return {"message": "Logged out successfully"}


@auth_router.get("/session/", auth=None)
@ratelimit(group='auth:session', key=user_or_ip, rate='60/m')
def check_session(request):
    """
    Check if user is authenticated via session (OAuth/SSO)

    **Returns:**
    - User information if authenticated via session (includes active profile from session)
    - {"authenticated": false} if not authenticated (200 status)
    """
    if request.user.is_authenticated:
        from identity.models import Profile

        # Get primary profile
        primary_profile = request.user.profiles.filter(is_primary=True).first()
        profile = primary_profile  # Default to primary

        # Check if there's an active profile in session
        active_profile_id = request.session.get('active_profile_id')
        if active_profile_id and primary_profile:
            try:
                active_profile = Profile.objects.get(id=active_profile_id)
                # Verify user can manage this profile
                if primary_profile.can_manage_profile(active_profile):
                    profile = active_profile
            except Profile.DoesNotExist:
                pass  # Use primary profile

        profile_data = None
        if profile:
            profile_data = {
                "id": str(profile.id),
                "local_name": profile.local_name,
                "display_name": profile.display_name,
                "hna": profile.hna,
                "reputation_score": float(profile.reputation_score),
                "is_verified_wot": profile.is_verified_wot,
                "is_foundation_member": profile.is_foundation_member(),
                "avatar_url": profile.avatar.url if profile.avatar else None,
                "profile_type": profile.profile_type,
                "is_primary": profile.is_primary
            }

        # Check if new OAuth user needs to confirm username
        needs_username_confirmation = request.session.get('is_new_oauth_user', False)

        return {
            "authenticated": True,
            "needs_username_confirmation": needs_username_confirmation,
            "user": {
                "id": str(request.user.id),
                "username": request.user.username,
                "email": request.user.email,
                "is_active": request.user.is_active,
                "is_staff": request.user.is_staff,  # Admin flag for UI
                "date_joined": request.user.date_joined.isoformat(),
                "profile": profile_data
            }
        }

    # Return 200 with authenticated: false instead of 401
    return {"authenticated": False}


@auth_router.get("/generated-credentials/", auth=None)
@ratelimit(group='auth:generated_credentials', key=user_or_ip, rate='30/m')
def get_generated_credentials(request):
    """
    Get generated HNA and password after OAuth signup.
    Credentials are kept in session until explicitly cleared or expired.
    """
    logger.info(f"[Credentials] Request session_key: {request.session.session_key}, user: {request.user}, authenticated: {request.user.is_authenticated}")

    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")

    # Check if there are generated credentials in session (don't pop - may be read multiple times)
    hna = request.session.get('generated_hna', None)
    password = request.session.get('generated_password', None)
    is_new_user = request.session.get('is_new_oauth_user', False)

    logger.info(f"[Credentials] Found hna: {bool(hna)}, password: {bool(password)}, is_new_user: {is_new_user}")

    if not hna or not password:
        raise HttpError(404, "No generated credentials found")
    
    return {
        "hna": hna,
        "password": password,
        "is_new_user": is_new_user
    }


@auth_router.post("/confirm-username/", auth=None)
@ratelimit(group='auth:confirm_username', key=user_or_ip, rate='10/m', method='POST')
def confirm_username(request):
    """
    Confirm username selection and clear new user flag.
    Called after user confirms their username on /choose-username page.
    Also creates Matrix user now that username is finalized.
    """
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")

    # Clear the new OAuth user flags from session
    request.session.pop('is_new_oauth_user', None)
    request.session.pop('generated_hna', None)
    request.session.pop('generated_password', None)

    logger.info(f"[Credentials] Username confirmed for {request.user.username}, cleared session flags")

    # Now create Matrix user (username is finalized)
    from threading import Thread
    def create_matrix_user_background():
        try:
            from parahub.endpoints.matrix_auth import _get_or_create_matrix_token
            token = _get_or_create_matrix_token(request.user.id)
            if token:
                logger.info(f"[Credentials] Matrix user created for {request.user.username}")
            else:
                logger.warning(f"[Credentials] Failed to create Matrix user for {request.user.username}")
        except Exception as e:
            logger.error(f"[Credentials] Exception creating Matrix user: {e}")

    thread = Thread(target=create_matrix_user_background, daemon=True)
    thread.start()

    return {"success": True, "message": "Username confirmed"}


@auth_router.get("/user-credentials/", auth=None)
@ratelimit(group='auth:user_credentials', key=user_or_ip, rate='30/m')
def get_user_credentials(request):
    """
    Get user's credentials for display in profile.
    Password is only available in session right after generation.
    """
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    
    # Check if password is temporarily stored in session
    password = request.session.get('generated_password', None)
    
    # Get user's HNA
    hna = request.user.email  # Email field contains the HNA
    
    return {
        "hna": hna,
        "password": password  # Will be None for existing users
    }


class DeleteAccountRequest(BaseModel):
    confirmation: str  # Must be "DELETE" to confirm


def _deactivate_synapse_user(username: str):
    """Deactivate and erase user in Matrix/Synapse. Non-fatal on failure."""
    import requests
    from django.conf import settings

    token = getattr(settings, 'SYNAPSE_ADMIN_TOKEN', None)
    if not token:
        logger.warning("[DeleteAccount] SYNAPSE_ADMIN_TOKEN not configured, skipping Matrix deactivation")
        return

    mxid = f"@{username}:parahub.io"
    try:
        # Deactivate + erase: removes displayname/avatar, kicks from all rooms
        r = requests.post(
            f"http://localhost:8008/_synapse/admin/v1/deactivate/{mxid}",
            headers={"Authorization": f"Bearer {token}"},
            json={"erase": True},
            timeout=10,
        )
        if r.status_code == 200:
            logger.info(f"[DeleteAccount] Deactivated Synapse user {mxid}")
        elif r.status_code == 404:
            logger.info(f"[DeleteAccount] Synapse user {mxid} not found (never logged into Matrix)")
        else:
            logger.warning(f"[DeleteAccount] Synapse deactivate {mxid} returned {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[DeleteAccount] Failed to deactivate Synapse user {mxid}: {e}")


@auth_router.post("/delete-account/", auth=None)
@ratelimit(group='auth:delete_account', key=user_or_ip, rate='3/h', method='POST')
def delete_account(request, data: DeleteAccountRequest):
    """
    Permanently delete user account and all associated data.

    **Rate Limit:** 3 attempts per hour per IP/user

    **Requirements:**
    - User must be authenticated
    - Must send confirmation: "DELETE"

    **Deletes:**
    - All profiles owned by user
    - All social account connections
    - The account itself

    **Warning:** This action is irreversible!
    """
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")

    # Require explicit confirmation
    if data.confirmation != "DELETE":
        raise HttpError(400, "Invalid confirmation. Send confirmation: 'DELETE' to proceed.")

    user = request.user
    username = user.username

    try:
        from django.db import transaction
        from identity.models import Profile
        from allauth.socialaccount.models import SocialAccount

        with transaction.atomic():
            # Log the deletion attempt
            logger.warning(f"[DeleteAccount] User {username} ({user.id}) initiated account deletion")

            # Deactivate Matrix/Synapse user (before Django deletion)
            _deactivate_synapse_user(username)

            # Delete all social accounts
            social_deleted = SocialAccount.objects.filter(user=user).delete()
            logger.info(f"[DeleteAccount] Deleted social accounts: {social_deleted}")

            # Delete all profiles
            profiles_deleted = Profile.objects.filter(account=user).delete()
            logger.info(f"[DeleteAccount] Deleted profiles: {profiles_deleted}")

            # Logout user first (destroy session)
            from django.contrib.auth import logout as django_logout
            django_logout(request)

            # Delete the account
            user.delete()
            logger.warning(f"[DeleteAccount] Account {username} permanently deleted")

        return {"success": True, "message": "Account permanently deleted"}

    except Exception as e:
        logger.error(f"[DeleteAccount] Failed to delete account {username}: {e}")
        raise HttpError(500, "Failed to delete account. Please try again.")


@auth_router.get("/session/token/", response={200: TokenResponse, 401: dict, 500: dict}, auth=None)
@ratelimit(group='auth:session_token', key=user_or_ip, rate='20/m', method='GET')
def get_session_token(request):
    """
    Get JWT token for users authenticated via OAuth/SSO session

    **Rate Limit:** 20 requests per minute per IP/user

    **Requirements:**
    - Valid session authentication (OAuth/SSO)

    **Returns:**
    - JWT access and refresh tokens
    """
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated via session")
    
    try:
        # Create JWT tokens for session-authenticated user
        tokens = create_tokens_for_user(request.user)
        
        logger.info(f"JWT tokens created for OAuth user: {request.user.username}")
        
        return TokenResponse(
            **tokens,
            user_id=str(request.user.id),
            username=request.user.username
        )
    except Exception as e:
        logger.error(f"Failed to create JWT for OAuth user: {e}")
        raise HttpError(500, "Failed to create authentication token")


# ===== Mobile OAuth Flow =====
# WebView and system browser have separate cookie jars.
# Google blocks OAuth inside WebView. So we open OAuth in system browser,
# then transfer the authenticated session back to the app via one-time tokens.

_MOBILE_AUTH_PREFIX = "mobile_auth:"
_MOBILE_AUTH_TTL = 300  # 5 minutes for the whole flow


class MobileInitResponse(BaseModel):
    state: str


@auth_router.post("/mobile/init/", response=MobileInitResponse, auth=None)
@ratelimit(group='auth:mobile_init', key='ip', rate='10/m', method='POST')
def mobile_auth_init(request):
    """
    Initialize mobile OAuth flow. Returns a state token that links
    the system browser OAuth session to the app's polling request.
    """
    state = secrets.token_urlsafe(32)
    cache.set(f"{_MOBILE_AUTH_PREFIX}{state}", "pending", timeout=_MOBILE_AUTH_TTL)
    return MobileInitResponse(state=state)


@auth_router.get("/mobile/poll/", auth=None)
@ratelimit(group='auth:mobile_poll', key='ip', rate='60/m', method='GET')
def mobile_auth_poll(request, state: str):
    """
    Poll for mobile OAuth completion. Returns JWT tokens once the user
    finishes OAuth in the system browser and /auth/mobile-complete/ fires.
    """
    if not state:
        raise HttpError(400, "Missing state parameter")

    cache_key = f"{_MOBILE_AUTH_PREFIX}{state}"
    data = cache.get(cache_key)

    if data is None:
        raise HttpError(410, "State expired or not found")

    if data == "pending":
        return {"status": "pending"}

    # Auth completed — data is a dict with tokens
    cache.delete(cache_key)  # one-time use
    return data


@auth_router.post("/mobile/session/", auth=GlobalAuth())
def mobile_establish_session(request):
    """
    Exchange JWT token for a Django session cookie in the WebView.
    Called after mobile OAuth poll succeeds — the WebView has JWT tokens
    in memory but no session cookie (because OAuth completed in Chrome
    Custom Tab which has a separate cookie store).
    """
    from django.contrib.auth import login
    login(request, request.user, backend='django.contrib.auth.backends.ModelBackend')
    return {"ok": True}


class UsernameAvailabilityResponse(BaseModel):
    username: str
    available: bool
    reason: Optional[str] = None


def _check_username_available_in_matrix(username: str) -> bool:
    """
    Check if username is available in Matrix (user doesn't exist).
    Returns True if available, False if taken.
    """
    import httpx
    from django.conf import settings

    SYNAPSE_BASE_URL = "http://localhost:8008"
    SYNAPSE_ADMIN_TOKEN = getattr(settings, 'SYNAPSE_ADMIN_TOKEN', None)

    if not SYNAPSE_ADMIN_TOKEN:
        logger.warning("[Username Check] SYNAPSE_ADMIN_TOKEN not configured, skipping Matrix check")
        return True  # Assume available if we can't check

    matrix_user_id = f"@{username.lower()}:parahub.io"

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{SYNAPSE_BASE_URL}/_synapse/admin/v2/users/{matrix_user_id}",
                headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"}
            )

            if response.status_code == 404:
                # User not found = available
                return True
            elif response.status_code == 200:
                # User exists = not available
                return False
            else:
                logger.warning(f"[Username Check] Unexpected Matrix response: {response.status_code}")
                return True  # Assume available on error
    except Exception as e:
        logger.error(f"[Username Check] Matrix check failed: {e}")
        return True  # Assume available on error


def _is_username_valid(username: str) -> tuple[bool, str]:
    """
    Validate username format.
    Returns (is_valid, error_message).
    """
    import re

    if not username:
        return False, "Username cannot be empty"

    if len(username) < 3:
        return False, "Username must be at least 3 characters"

    if len(username) > 30:
        return False, "Username must be at most 30 characters"

    # Matrix localpart rules: lowercase letters, numbers, dots, underscores, hyphens
    # We allow hyphens for readability (adjective-noun pattern)
    if not re.match(r'^[a-z0-9][a-z0-9._-]*[a-z0-9]$|^[a-z0-9]$', username.lower()):
        return False, "Username can only contain letters, numbers, dots, underscores, and hyphens"

    # Reserved usernames — exact match
    reserved_exact = {
        # Platform identity
        'parahub', 'parahub.io', 'para-hub', 'para.hub',
        # Admin / authority
        'admin', 'administrator', 'root', 'superuser', 'sysadmin',
        'moderator', 'mod', 'operator',
        # System roles
        'system', 'daemon', 'service', 'server', 'localhost',
        'nobody', 'null', 'undefined', 'anonymous', 'anon',
        # Support / official
        'support', 'help', 'helpdesk', 'contact', 'feedback',
        'info', 'information', 'news', 'press', 'media',
        'team', 'staff', 'official', 'verified',
        # Common service accounts
        'bot', 'chatbot', 'autobot', 'noreply', 'no-reply',
        'mailer', 'postmaster', 'webmaster', 'hostmaster',
        'abuse', 'security', 'billing', 'sales',
        # Well-known paths / protocols
        'api', 'www', 'ftp', 'ssh', 'mail', 'smtp', 'imap',
        'dns', 'cdn', 'proxy', 'gateway', 'nginx', 'apache',
        # Testing
        'test', 'testing', 'debug', 'demo', 'example', 'sample',
        'dev', 'development', 'staging', 'production',
        # Generic authority / impersonation
        'ceo', 'founder', 'owner', 'manager', 'director',
        'president', 'chairman',
        # Matrix / chat
        'matrix', 'synapse', 'element', 'cinny',
        # Finance / wallet
        'wallet', 'bitcoin', 'lightning', 'satoshi',
        # Offensive / placeholder
        'fuck', 'shit', 'ass', 'dick', 'porn', 'sex',
        'nigger', 'nigga', 'faggot',
    }
    # Substrings that should never appear in a username
    reserved_substrings = [
        'parahub', 'admin', 'support', 'moderator', 'official',
    ]

    lower = username.lower()
    if lower in reserved_exact:
        return False, "This username is reserved"

    for sub in reserved_substrings:
        if sub in lower and lower != sub:  # exact already checked above
            return False, "This username contains a reserved word"

    return True, ""


@auth_router.get("/check-username/{username}/", response=UsernameAvailabilityResponse, auth=None)
@ratelimit(group='auth:check_username', key='ip', rate='30/m', method='GET')
def check_username_availability(request, username: str):
    """
    Check if a username is available for registration.

    Checks both Parahub database and Matrix server.

    **Rate Limit:** 30 requests per minute per IP

    **Returns:**
    - available: true if username can be used
    - reason: explanation if not available
    """
    # Normalize to lowercase
    username = username.lower().strip()

    # Validate format
    is_valid, error_msg = _is_username_valid(username)
    if not is_valid:
        return UsernameAvailabilityResponse(
            username=username,
            available=False,
            reason=error_msg
        )

    # Check Parahub database
    if Account.objects.filter(username=username).exists():
        return UsernameAvailabilityResponse(
            username=username,
            available=False,
            reason="Username already taken"
        )

    # Check Profile local_name (for same instance)
    try:
        instance = Instance.objects.get(domain='parahub.io')
        if Profile.objects.filter(instance=instance, local_name=username).exists():
            return UsernameAvailabilityResponse(
                username=username,
                available=False,
                reason="Username already taken"
            )
    except Instance.DoesNotExist:
        pass

    # Check Matrix
    if not _check_username_available_in_matrix(username):
        return UsernameAvailabilityResponse(
            username=username,
            available=False,
            reason="Username already taken in chat system"
        )

    return UsernameAvailabilityResponse(
        username=username,
        available=True
    )


class GeneratedUsernameResponse(BaseModel):
    username: str
    available: bool


@auth_router.get("/generate-username/", response=GeneratedUsernameResponse, auth=None)
@ratelimit(group='auth:generate_username', key='ip', rate='20/m', method='GET')
def generate_available_username(request):
    """
    Generate a random available username.

    Generates adjective-noun style usernames and verifies availability
    in both Parahub database and Matrix server.

    **Rate Limit:** 20 requests per minute per IP

    **Returns:**
    - username: generated available username
    - available: always true (guaranteed available)
    """
    from core.username_generator import ADJECTIVES, NOUNS
    import random

    max_attempts = 100

    for attempt in range(max_attempts):
        adj = random.choice(ADJECTIVES)
        noun = random.choice(NOUNS)

        if attempt < 50:
            username = f"{adj}-{noun}"
        else:
            number = random.randint(1, 9999)
            username = f"{adj}-{noun}-{number}"

        # Check Parahub
        if Account.objects.filter(username=username).exists():
            continue

        # Check Profile
        try:
            instance = Instance.objects.get(domain='parahub.io')
            if Profile.objects.filter(instance=instance, local_name=username).exists():
                continue
        except Instance.DoesNotExist:
            pass

        # Check Matrix
        if not _check_username_available_in_matrix(username):
            continue

        # Found available username
        return GeneratedUsernameResponse(
            username=username,
            available=True
        )

    # Fallback with timestamp
    import time
    timestamp = int(time.time() * 1000) % 1000000
    username = f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{timestamp}"

    return GeneratedUsernameResponse(
        username=username,
        available=True
    )


class SetUsernameRequest(BaseModel):
    username: str


class SetUsernameResponse(BaseModel):
    success: bool
    username: str
    hna: str
    message: str = ""


@auth_router.post("/set-username/", response={200: SetUsernameResponse, 400: dict, 403: dict}, auth=None)
@ratelimit(group='auth:set_username', key=user_or_ip, rate='5/m', method='POST')
def set_username(request, data: SetUsernameRequest):
    """
    Set username for newly registered OAuth user.

    This endpoint allows users who just signed up via OAuth to choose
    their username instead of keeping the auto-generated one.

    **Requirements:**
    - User must be authenticated (session or JWT)
    - User must be a new OAuth user (session flag or username_changed=False)
    - Matrix user must not exist yet (username change affects Matrix ID)

    **Rate Limit:** 5 requests per minute per user
    """
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    from identity.models import Profile
    from core.models import Instance
    import httpx
    import logging

    logger = logging.getLogger(__name__)
    user = request.user
    new_username = data.username.lower().strip()

    # Validate username format
    is_valid, reason = _is_username_valid(new_username)
    if not is_valid:
        return 400, {"error": reason}

    # Check if user can still change username
    # New OAuth users have this flag in session
    is_new_oauth = request.session.get('is_new_oauth_user', False)

    # Also check if username was never changed (username matches profile local_name)
    try:
        instance = Instance.objects.get(domain='parahub.io')
        profile = Profile.objects.filter(account=user, instance=instance).first()
    except Instance.DoesNotExist:
        return 400, {"error": "Instance not found"}

    if not profile:
        return 400, {"error": "Profile not found"}

    # Allow change if: new OAuth user OR username still matches auto-generated pattern
    # (This allows users who missed the choose-username page to still change later)
    can_change = is_new_oauth or (user.username == profile.local_name)

    if not can_change:
        return 403, {"error": "Username can only be changed once after registration"}

    # Check if Matrix user already exists (would make change complicated)
    matrix_user_id = f"@{profile.local_name}:parahub.io"
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"http://localhost:8008/_matrix/client/v3/profile/{matrix_user_id}",
                headers={"Accept": "application/json"}
            )
            if response.status_code == 200:
                # Matrix user exists - check if it's the same user or different
                # If user already used chat, we can't easily change their Matrix username
                logger.warning(f"[SetUsername] Matrix user {matrix_user_id} already exists")
                return 403, {"error": "Cannot change username after using chat. Matrix account already created."}
    except Exception as e:
        logger.debug(f"[SetUsername] Matrix check failed (probably user doesn't exist): {e}")
        # Matrix user doesn't exist - good, we can proceed

    # Check availability in Parahub
    if Account.objects.filter(username=new_username).exclude(id=user.id).exists():
        return 400, {"error": "Username already taken"}

    if Profile.objects.filter(instance=instance, local_name=new_username).exclude(id=profile.id).exists():
        return 400, {"error": "Username already taken"}

    # Check availability in Matrix
    if not _check_username_available_in_matrix(new_username):
        return 400, {"error": "Username already taken in chat system"}

    # All checks passed - update username
    old_username = user.username
    user.username = new_username
    user.email = f"{new_username}@{instance.domain}"  # Update HNA
    user.save()

    profile.local_name = new_username
    profile.save()

    # Clear the new OAuth user flag
    if 'is_new_oauth_user' in request.session:
        del request.session['is_new_oauth_user']

    # Update session with new HNA
    request.session['generated_hna'] = f"{new_username}@{instance.domain}"

    logger.info(f"[SetUsername] User {user.id} changed username from {old_username} to {new_username}")

    return SetUsernameResponse(
        success=True,
        username=new_username,
        hna=f"{new_username}@{instance.domain}",
        message="Username updated successfully"
    )