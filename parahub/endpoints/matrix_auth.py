"""
Matrix authentication and widget integration for Parahub
Handles real Matrix/Synapse integration with auto-provisioning
"""

from ninja import Router
from typing import Dict, Any, Optional
from pydantic import BaseModel
import httpx
import hashlib
import hmac
import logging
import time
from django.conf import settings
from django.core.cache import cache
from parahub.auth import GlobalAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["matrix"])

# Synapse admin credentials and endpoints
SYNAPSE_BASE_URL = "http://localhost:8008"
SYNAPSE_PUBLIC_URL = "https://parahub.io"
SYNAPSE_ADMIN_TOKEN = getattr(settings, 'SYNAPSE_ADMIN_TOKEN', None)
SYNAPSE_SHARED_SECRET = settings.SYNAPSE_REGISTRATION_SHARED_SECRET


def generate_mac(shared_secret: str, nonce: str, user: str, password: str, 
                  admin: bool = False, user_type: str = None) -> str:
    """Generate HMAC for Synapse shared secret registration"""
    mac = hmac.new(
        key=shared_secret.encode('utf8'),
        digestmod=hashlib.sha1,
    )
    
    mac.update(nonce.encode('utf8'))
    mac.update(b"\x00")
    mac.update(user.encode('utf8'))
    mac.update(b"\x00")
    mac.update(password.encode('utf8'))
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    if user_type:
        mac.update(b"\x00")
        mac.update(user_type.encode('utf8'))
    
    return mac.hexdigest()


def get_matrix_localpart_for_account(account_id: str) -> str:
    """
    Get Matrix localpart (username) for an account.

    Uses the primary Profile's local_name instead of Account ID (ULID).
    This makes Matrix usernames human-readable: @alice:parahub.io instead of @01k2sh48yz:parahub.io

    Args:
        account_id: Account ULID

    Returns:
        Matrix localpart (e.g., "alice" for @alice:parahub.io)
    """
    from identity.models import Profile
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Get primary profile for this account
        profile = Profile.objects.filter(
            account_id=account_id,
            is_primary=True
        ).first()

        if profile and profile.local_name:
            # Use local_name (human-readable, like "alice" or "happy-panda")
            return profile.local_name.lower()

        # Fallback: try any profile for this account
        profile = Profile.objects.filter(account_id=account_id).first()
        if profile and profile.local_name:
            return profile.local_name.lower()

        # Last resort fallback: use account ID (shouldn't happen for normal users)
        logger.warning(f"[Matrix] No profile found for account {account_id}, falling back to ULID")
        return account_id.lower().replace('-', '_')

    except Exception as e:
        logger.error(f"[Matrix] Error getting localpart for account {account_id}: {e}")
        return account_id.lower().replace('-', '_')


def get_matrix_user_id(account_id: str) -> str:
    """
    Get full Matrix user ID for an account.

    Args:
        account_id: Account ULID

    Returns:
        Full Matrix user ID (e.g., "@alice:parahub.io")
    """
    localpart = get_matrix_localpart_for_account(account_id)
    return f"@{localpart}:parahub.io"


def _ensure_matrix_user_exists(client: httpx.Client, account_id: str, matrix_user_id: str,
                                displayname: str = None) -> bool:
    """
    Ensure Matrix user exists via Admin API with OIDC identity link.

    This creates the user if it doesn't exist, and links it to the Parahub OIDC
    identity so that SSO login will use this user instead of creating a new one.

    Note: No password is set because Synapse has password_config.enabled: false.
    Users authenticate via OIDC SSO only.

    Args:
        client: httpx.Client instance
        account_id: Parahub Account ULID (used as OIDC external_id / sub claim)
        matrix_user_id: Full Matrix user ID (@alice:parahub.io)
        displayname: Optional display name

    Returns:
        True if user exists or was created, False on error
    """
    import logging
    logger = logging.getLogger(__name__)

    if not SYNAPSE_ADMIN_TOKEN:
        logger.error("[Matrix] SYNAPSE_ADMIN_TOKEN not configured")
        return False

    try:
        # OIDC provider ID from homeserver.yaml: idp_id: parahub_django
        # Synapse prefixes it with "oidc-" internally
        oidc_provider_id = "oidc-parahub_django"

        # NOTE: Do NOT include "password" field - Synapse has password_config.enabled: false
        # Including password causes 403 "Password change disabled" error
        user_data = {
            "admin": False,
            "deactivated": False,
            "external_ids": [
                {
                    "auth_provider": oidc_provider_id,
                    "external_id": account_id  # This is the 'sub' claim in ID token
                }
            ]
        }

        if displayname:
            user_data["displayname"] = displayname

        put_response = client.put(
            f"{SYNAPSE_BASE_URL}/_synapse/admin/v2/users/{matrix_user_id}",
            headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"},
            json=user_data
        )

        if put_response.status_code in (200, 201):
            logger.info(f"[Matrix] User {matrix_user_id} exists/created with OIDC link to {account_id}")
            return True
        else:
            logger.error(f"[Matrix] Failed to create user {matrix_user_id}: {put_response.status_code} - {put_response.text}")
            return False

    except Exception as e:
        logger.error(f"[Matrix] Exception creating user {matrix_user_id}: {e}")
        return False


@router.post("/login-token", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:login_token', key=user_or_ip, rate='10/m', method='POST')
def get_login_token(request):
    """
    Generate a Matrix login token for SSO auto-login
    Creates user if needed, then generates a one-time login token
    """
    user = request.user

    # Check if this is a new OAuth user who hasn't confirmed username yet
    # Matrix user should not be created until username is finalized
    is_new_oauth_user = request.session.get('is_new_oauth_user', False)
    if is_new_oauth_user:
        logger.warning(f"[Matrix] Blocking login-token for new OAuth user {user.username} - needs username confirmation")
        return {"success": False, "error": "Please confirm your username first", "needs_username_confirmation": True}

    # Generate Matrix user ID from profile's local_name (human-readable)
    matrix_user_id = get_matrix_user_id(user.id)

    try:
        with httpx.Client() as client:
            # Ensure user exists with OIDC link (so SSO will use same user)
            displayname = user.profile.hna if hasattr(user, 'profile') else user.username
            if not _ensure_matrix_user_exists(client, user.id, matrix_user_id, displayname):
                raise Exception("Failed to ensure Matrix user exists")

            # Now generate login token using admin API
            if not SYNAPSE_ADMIN_TOKEN:
                return {
                    "success": False,
                    "error": "SYNAPSE_ADMIN_TOKEN not configured"
                }

            # Generate login token
            login_token_response = client.post(
                f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/users/{matrix_user_id}/login",
                headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"},
                json={}
            )

            if login_token_response.status_code == 200:
                token_data = login_token_response.json()

                return {
                    "success": True,
                    "user_id": matrix_user_id,
                    "login_token": token_data.get("access_token"),
                    "homeserver": SYNAPSE_PUBLIC_URL
                }
            else:
                raise Exception(f"Failed to generate login token: {login_token_response.text}")

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/widget-token", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:widget_token', key=user_or_ip, rate='10/m', method='POST')
def get_widget_token(request):
    """
    Get or create a Matrix widget token for the authenticated user
    This creates a real Matrix user if needed and returns a widget-compatible token
    """
    user = request.user

    # Check if this is a new OAuth user who hasn't confirmed username yet
    is_new_oauth_user = request.session.get('is_new_oauth_user', False)
    if is_new_oauth_user:
        logger.warning(f"[Matrix] Blocking widget-token for new OAuth user {user.username} - needs username confirmation")
        return {"success": False, "error": "Please confirm your username first", "needs_username_confirmation": True}

    # Generate Matrix user ID from profile's local_name (human-readable)
    matrix_user_id = get_matrix_user_id(user.id)

    # Check if we have cached credentials for this user
    cache_key = f"matrix_session_{user.id}"
    cached_session = cache.get(cache_key)

    if cached_session:
        return {
            "success": True,
            **cached_session
        }
    
    try:
        with httpx.Client() as client:
            # Ensure user exists with OIDC link (so SSO will use same user)
            if SYNAPSE_ADMIN_TOKEN:
                displayname = user.profile.hna if hasattr(user, 'profile') else user.username
                if not _ensure_matrix_user_exists(client, user.id, matrix_user_id, displayname):
                    raise Exception("Failed to create/update Matrix user")

                # Generate admin login token
                admin_login_response = client.post(
                    f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/users/{matrix_user_id}/login",
                    headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"},
                    json={"valid_until_ms": int((time.time() + 86400 * 7) * 1000)}  # 7 days
                )

                if admin_login_response.status_code == 200:
                    admin_data = admin_login_response.json()
                    access_token = admin_data.get("access_token")
                    device_id = admin_data.get("device_id", "PARAHUB_WEB")
                else:
                    raise Exception(f"Failed to create session: {admin_login_response.text}")
            else:
                return {"success": False, "error": "SYNAPSE_ADMIN_TOKEN not configured"}
            
            widget_token = access_token
                
            session_data = {
                "user_id": matrix_user_id,
                "access_token": access_token,
                "device_id": device_id,
                "homeserver": SYNAPSE_PUBLIC_URL,
                "widget_token": widget_token,
                "widget_url": f"{SYNAPSE_PUBLIC_URL}/_matrix/client",
                "message": "Matrix session created successfully"
            }

            # Cache session for 6 hours
            cache.set(cache_key, session_data, 6 * 3600)

            return {
                "success": True,
                **session_data
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/rooms", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:rooms', key=user_or_ip, rate='30/m')
def get_user_rooms(request):
    """
    Get list of rooms for the authenticated user
    """
    # Get cached session
    cache_key = f"matrix_session_{request.user.id}"
    session = cache.get(cache_key)
    
    if not session:
        return {"success": False, "error": "No active Matrix session"}
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/joined_rooms",
                headers={"Authorization": f"Bearer {session['access_token']}"}
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "rooms": response.json().get("joined_rooms", [])
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to fetch rooms"
                }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/ensure-room", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:ensure_room', key=user_or_ip, rate='5/m', method='POST')
def ensure_direct_room(request, other_user_cri: str):
    """
    Ensure a direct message room exists between two users
    """
    cache_key = f"matrix_session_{request.user.id}"
    session = cache.get(cache_key)

    if not session:
        return {"success": False, "error": "No active Matrix session"}

    # Get Matrix user ID from profile's local_name
    other_matrix_user = get_matrix_user_id(other_user_cri)

    try:
        with httpx.Client() as client:
            # Create direct room
            response = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/createRoom",
                headers={"Authorization": f"Bearer {session['access_token']}"},
                json={
                    "preset": "trusted_private_chat",
                    "invite": [other_matrix_user],
                    "is_direct": True,
                    "initial_state": [
                        {
                            "type": "m.room.encryption",
                            "state_key": "",
                            "content": {
                                "algorithm": "m.megolm.v1.aes-sha2"
                            }
                        }
                    ]
                }
            )

            if response.status_code in (200, 201):
                room_data = response.json()
                return {
                    "success": True,
                    "room_id": room_data.get("room_id")
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to create room: {response.text}"
                }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


class UnreadCountPayload(BaseModel):
    count: int

@router.post("/notify-unread", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:notify_unread', key=user_or_ip, rate='20/m', method='POST')
def notify_unread_count(request, payload: UnreadCountPayload):
    """
    Send WebSocket notification about Matrix unread count update
    This broadcasts to all connected clients for the authenticated user
    """
    count = payload.count

    try:
        from parahub.services.ws_publish import ws_publish
        ws_publish(f"user:{request.user.id}", {
            "type": "matrix.unread_update",
            "count": count,
            "rooms": [],
        })

        return {
            "success": True,
            "message": "Unread count notification sent"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def _get_or_create_matrix_token(user_id: str) -> Optional[str]:
    """
    Internal helper: Get or create Matrix access token for a user by Account ID
    Returns access_token or None on failure

    Steps:
    1. Try to register new user via admin API (uses shared secret)
    2. If user exists, try password login with deterministic password
    3. If that fails and SYNAPSE_ADMIN_TOKEN exists, use admin login API
    """
    from identity.models import Account
    import logging
    logger = logging.getLogger(__name__)

    try:
        Account.objects.get(id=user_id)
    except Account.DoesNotExist:
        logger.error(f"[Matrix] Account {user_id} does not exist")
        return None

    # Generate Matrix user ID from profile's local_name (human-readable)
    matrix_localpart = get_matrix_localpart_for_account(user_id)
    matrix_user_id = f"@{matrix_localpart}:parahub.io"

    # Check cache first
    cache_key = f"matrix_session_{user_id}"
    cached_session = cache.get(cache_key)
    if cached_session:
        return cached_session.get('access_token')

    # Generate deterministic password
    password = hashlib.sha256(f"{user_id}:{SYNAPSE_SHARED_SECRET}".encode()).hexdigest()

    try:
        with httpx.Client() as client:
            # CRITICAL: DO NOT create users via backend API!
            # Users MUST be created via OIDC SSO to avoid localpart conflicts.
            # Backend only tries to login existing users or use admin API.

            # Step 2: User exists - try password login
            try:
                login_response = client.post(
                    f"{SYNAPSE_BASE_URL}/_matrix/client/r0/login",
                    json={
                        "type": "m.login.password",
                        "identifier": {
                            "type": "m.id.user",
                            "user": matrix_localpart
                        },
                        "password": password
                    }
                )

                if login_response.status_code == 200:
                    access_token = login_response.json().get("access_token")
                    logger.info(f"[Matrix] Successfully logged in user {matrix_user_id} via password")
                    cache.set(cache_key, {"access_token": access_token}, 6 * 3600)
                    return access_token
                else:
                    logger.warning(f"[Matrix] Password login failed for {matrix_user_id}: {login_response.status_code} - {login_response.text}")
            except Exception as e:
                logger.warning(f"[Matrix] Exception during password login for {matrix_user_id}: {e}")

            # Step 3: Try admin API to create user + login token (requires SYNAPSE_ADMIN_TOKEN)
            if SYNAPSE_ADMIN_TOKEN:
                try:
                    # Ensure user exists with OIDC link (so SSO will use same user)
                    if not _ensure_matrix_user_exists(client, user_id, matrix_user_id):
                        logger.warning(f"[Matrix] Failed to ensure user {matrix_user_id} exists")

                    # Then create login token
                    admin_response = client.post(
                        f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/users/{matrix_user_id}/login",
                        headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"},
                        json={"valid_until_ms": int((time.time() + 86400 * 7) * 1000)}
                    )

                    if admin_response.status_code == 200:
                        access_token = admin_response.json().get("access_token")
                        logger.info(f"[Matrix] Successfully created admin login token for {matrix_user_id}")
                        cache.set(cache_key, {"access_token": access_token}, 6 * 3600)
                        return access_token
                    else:
                        logger.error(f"[Matrix] Admin login API failed for {matrix_user_id}: {admin_response.status_code} - {admin_response.text}")
                except Exception as e:
                    logger.error(f"[Matrix] Exception during admin login for {matrix_user_id}: {e}")
            else:
                logger.warning(f"[Matrix] SYNAPSE_ADMIN_TOKEN not configured, cannot use admin login API for {matrix_user_id}")

            logger.error(f"[Matrix] All methods failed to create token for {matrix_user_id}")
            return None
    except Exception as e:
        logger.error(f"[Matrix] Unexpected error in _get_or_create_matrix_token for {user_id}: {e}")
        return None


def _get_or_create_matrix_token_for_dm(user_id: str) -> Optional[str]:
    """
    Get OR CREATE Matrix token for DM purposes.
    Unlike _get_or_create_matrix_token, this WILL create user via admin API if needed.

    Used ONLY for DM auto-join - ensures target user exists for room invitation.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Try normal flow first
    token = _get_or_create_matrix_token(user_id)

    # Validate token before returning
    if token:
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{SYNAPSE_BASE_URL}/_matrix/client/v3/account/whoami",
                    headers={"Authorization": f"Bearer {token}"}
                )

                if response.status_code == 200:
                    # Token is valid
                    return token
                else:
                    logger.warning(f"[Matrix DM] Cached token invalid for {user_id}, creating fresh user")
                    # Clear cache
                    cache_key = f"matrix_session_{user_id}"
                    cache.delete(cache_key)
        except Exception as e:
            logger.warning(f"[Matrix DM] Token validation failed: {e}")

    # User doesn't exist or token invalid - create via admin API
    if not SYNAPSE_ADMIN_TOKEN:
        logger.error(f"[Matrix DM] No admin token, cannot create user {user_id}")
        return None

    try:
        # Generate Matrix user ID from profile's local_name (human-readable)
        matrix_user_id = get_matrix_user_id(user_id)

        with httpx.Client() as client:
            # Step 1: Ensure user exists with OIDC link (so SSO will use same user)
            if not _ensure_matrix_user_exists(client, user_id, matrix_user_id):
                logger.error(f"[Matrix DM] Failed to create user {matrix_user_id}")
                return None

            logger.info(f"[Matrix DM] Created/verified Matrix user for DM: {matrix_user_id}")

            # Step 2: Get access token via admin login API (password login disabled)
            login_response = client.post(
                f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/users/{matrix_user_id}/login",
                headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"},
                json={}
            )

            if login_response.status_code == 200:
                access_token = login_response.json().get("access_token")
                logger.info(f"[Matrix DM] Got access token for {matrix_user_id}")

                # Cache it
                cache_key = f"matrix_session_{user_id}"
                cache.set(cache_key, {"access_token": access_token}, 6 * 3600)

                return access_token
            else:
                logger.error(f"[Matrix DM] Admin login failed: {login_response.status_code} - {login_response.text}")
                return None
    except Exception as e:
        logger.error(f"[Matrix DM] Exception creating user {user_id}: {e}")
        return None


@router.get("/get-login-token", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:get_login_token', key=user_or_ip, rate='10/m')
def get_matrix_login_token(request):
    """
    Get a one-time Matrix SSO login token for auto-login in Cinny/Element

    This token can be passed as ?loginToken=xxx to Matrix web clients for seamless authentication.
    The token is single-use and expires after being used or after a short time.

    Returns:
        {
            "success": true,
            "loginToken": "abc123..."
        }
    """
    user_id = request.user.id

    # Check if this is a new OAuth user who hasn't confirmed username yet
    # Matrix user should not be created until username is finalized
    is_new_oauth_user = request.session.get('is_new_oauth_user', False)
    if is_new_oauth_user:
        logger.warning(f"[Matrix] Blocking Matrix token for new OAuth user {request.user.username} - needs username confirmation")
        return {"success": False, "error": "Please confirm your username first", "needs_username_confirmation": True}

    try:
        # First ensure Matrix user exists
        access_token = _get_or_create_matrix_token(user_id)
        if not access_token:
            logger.error(f"[Matrix] Failed to get access token for user {user_id}")
            return {"success": False, "error": "Failed to create Matrix session"}

        # Generate Matrix user ID from profile's local_name (human-readable)
        matrix_user_id = get_matrix_user_id(user_id)

        # Request a login token from Synapse (requires admin API)
        with httpx.Client() as client:
            # Use the user's own access token to get a login token
            # This is the standard way: user authenticates with their access_token and gets a login_token
            login_token_response = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/v1/login/get_token",
                headers={"Authorization": f"Bearer {access_token}"},
                json={}  # MSC3882 requires JSON body
            )

            if login_token_response.status_code == 200:
                login_token_data = login_token_response.json()
                login_token = login_token_data.get("login_token")

                if login_token:
                    logger.info(f"[Matrix] Generated login token for {matrix_user_id}")
                    return {
                        "success": True,
                        "loginToken": login_token
                    }
                else:
                    logger.error(f"[Matrix] No login_token in response for {matrix_user_id}")
                    return {"success": False, "error": "Invalid response from Matrix server"}
            else:
                logger.error(f"[Matrix] Failed to get login token for {matrix_user_id}: {login_token_response.status_code} - {login_token_response.text}")

                # Fallback: return the access token directly (less secure but works)
                logger.warning(f"[Matrix] Falling back to access token for {matrix_user_id}")
                return {
                    "success": True,
                    "loginToken": access_token,
                    "fallback": True  # Indicate this is not a proper login token
                }

    except Exception as e:
        logger.error(f"[Matrix] Exception getting login token for {user_id}: {e}")
        return {"success": False, "error": str(e)}


def _find_existing_dm(client: httpx.Client, access_token: str, user_id: str, dm_partner_mxid: str, partner_token: str = None) -> Optional[str]:
    """
    Find existing DM room with specific user in m.direct account_data

    Args:
        client: httpx.Client instance
        access_token: Matrix access token for the user
        user_id: Account ID (for logging)
        dm_partner_mxid: Matrix user ID of the DM partner (@user:parahub.io)
        partner_token: Optional Matrix access token for partner (to verify they're also member)

    Returns:
        room_id if existing DM found, None otherwise
    """
    import logging
    logger = logging.getLogger(__name__)

    # Get Matrix user ID from profile's local_name
    matrix_user_id = get_matrix_user_id(user_id)

    try:
        # Get current m.direct account_data
        get_response = client.get(
            f"{SYNAPSE_BASE_URL}/_matrix/client/r0/user/{matrix_user_id}/account_data/m.direct",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if get_response.status_code == 200:
            direct_rooms = get_response.json()

            # Check if we have DM rooms with this partner
            if dm_partner_mxid in direct_rooms:
                rooms = direct_rooms[dm_partner_mxid]
                if rooms and len(rooms) > 0:
                    # Get the first (most recent) room
                    room_id = rooms[0] if isinstance(rooms, list) else rooms

                    # CRITICAL: Verify that the room actually exists and BOTH users are JOINED
                    # (After Matrix DB reset, ALL client APIs return stale cache - must use admin API)
                    try:
                        # ONLY admin API returns accurate data - client APIs cache stale data
                        # Use admin endpoint to get actual current members
                        if not SYNAPSE_ADMIN_TOKEN:
                            logger.error(f"[Matrix] SYNAPSE_ADMIN_TOKEN not configured, cannot verify room membership accurately")
                            # Fallback: assume room is valid (risky but better than nothing)
                            logger.info(f"[Matrix] Found existing DM for {user_id} with {dm_partner_mxid}: {room_id}")
                            return room_id

                        admin_response = client.get(
                            f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/rooms/{room_id}/members",
                            headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"}
                        )

                        if admin_response.status_code == 200:
                            members_data = admin_response.json()
                            total_members = members_data.get("total", 0)
                            members = members_data.get("members", [])

                            current_mxid = matrix_user_id

                            # Admin API returns members as list of user_id strings (not dicts)
                            # If user_id is in the list, they are joined to the room
                            current_joined = current_mxid in members
                            partner_joined = dm_partner_mxid in members

                            logger.info(f"[Matrix] Admin API: room {room_id} has {total_members} members, current_user joined: {current_joined}, partner joined: {partner_joined}")

                            if current_joined and partner_joined:
                                # Both users are actually joined
                                logger.info(f"[Matrix] Found existing DM for {user_id} with {dm_partner_mxid}: {room_id}")
                                return room_id
                            else:
                                # Room exists but one or both users not joined - treat as stale
                                logger.warning(f"[Matrix] Room {room_id} exists but users not both joined (current: {current_joined}, partner: {partner_joined}), removing stale entry")

                                # Remove stale room from m.direct
                                direct_rooms[dm_partner_mxid] = [r for r in direct_rooms[dm_partner_mxid] if r != room_id]
                                if not direct_rooms[dm_partner_mxid]:
                                    del direct_rooms[dm_partner_mxid]

                                # Update m.direct to clean up stale data
                                client.put(
                                    f"{SYNAPSE_BASE_URL}/_matrix/client/r0/user/{matrix_user_id}/account_data/m.direct",
                                    headers={"Authorization": f"Bearer {access_token}"},
                                    json=direct_rooms
                                )

                                return None
                        else:
                            # Admin API failed - log and treat as stale to be safe
                            logger.warning(f"[Matrix] Failed to get room members via admin API for {room_id}: {admin_response.status_code}, treating as stale")

                            # Remove stale room from m.direct
                            direct_rooms[dm_partner_mxid] = [r for r in direct_rooms[dm_partner_mxid] if r != room_id]
                            if not direct_rooms[dm_partner_mxid]:
                                del direct_rooms[dm_partner_mxid]

                            # Update m.direct to clean up stale data
                            client.put(
                                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/user/{matrix_user_id}/account_data/m.direct",
                                headers={"Authorization": f"Bearer {access_token}"},
                                json=direct_rooms
                            )

                            return None
                    except Exception as verify_error:
                        logger.error(f"[Matrix] Error verifying room {room_id}: {verify_error}")
                        return None

        return None

    except Exception as e:
        logger.error(f"[Matrix] Exception finding existing DM for {user_id}: {e}")
        return None


def _update_direct_rooms(client: httpx.Client, access_token: str, user_id: str, dm_partner_mxid: str, room_id: str):
    """
    Update m.direct account_data to mark room as DM with specific user

    Args:
        client: httpx.Client instance
        access_token: Matrix access token for the user
        user_id: Account ID (for logging)
        dm_partner_mxid: Matrix user ID of the DM partner (@user:parahub.io)
        room_id: Room ID to add to DM list
    """
    import logging
    logger = logging.getLogger(__name__)

    # Get Matrix user ID from profile's local_name
    matrix_user_id = get_matrix_user_id(user_id)

    try:
        # Get current m.direct account_data
        get_response = client.get(
            f"{SYNAPSE_BASE_URL}/_matrix/client/r0/user/{matrix_user_id}/account_data/m.direct",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if get_response.status_code == 200:
            direct_rooms = get_response.json()
        elif get_response.status_code == 404:
            # No m.direct data yet - create new
            direct_rooms = {}
        else:
            logger.error(f"[Matrix] Failed to get m.direct for {user_id}: {get_response.status_code}")
            return

        # Add room_id to list for dm_partner_mxid
        if dm_partner_mxid not in direct_rooms:
            direct_rooms[dm_partner_mxid] = []

        if room_id not in direct_rooms[dm_partner_mxid]:
            direct_rooms[dm_partner_mxid].append(room_id)
            was_new = True
        else:
            was_new = False

        # ALWAYS update m.direct account_data (even if room already in list)
        # This ensures Synapse sends updated account_data in next /sync response
        # which is critical for Cinny to see the room after fresh login
        put_response = client.put(
            f"{SYNAPSE_BASE_URL}/_matrix/client/r0/user/{matrix_user_id}/account_data/m.direct",
            headers={"Authorization": f"Bearer {access_token}"},
            json=direct_rooms
        )

        if put_response.status_code == 200:
            logger.info(f"[Matrix] Updated m.direct for {user_id}: {dm_partner_mxid} -> {room_id} (was_new: {was_new})")
        else:
            logger.error(f"[Matrix] Failed to update m.direct for {user_id}: {put_response.status_code} - {put_response.text}")

    except Exception as e:
        logger.error(f"[Matrix] Exception updating m.direct for {user_id}: {e}")


def create_dm_between_accounts(account_id_1: str, account_id_2: str, initial_message: str = None, initial_message_html: str = None) -> Optional[str]:
    """
    Create a Matrix DM room between two accounts (by Account ID).

    Reusable helper: gets/creates Matrix users, creates room, auto-accepts invite,
    updates m.direct for both users.

    Args:
        account_id_1: Account ULID of the first user (room creator)
        account_id_2: Account ULID of the second user (invitee)
        initial_message: Optional plaintext message to send in new rooms
        initial_message_html: Optional HTML version of the initial message

    Returns:
        room_id if successful, None on failure
    """
    import logging
    logger = logging.getLogger(__name__)

    if account_id_1 == account_id_2:
        logger.warning("[Matrix DM] Cannot create DM with yourself")
        return None

    try:
        # Get access tokens for both users
        token_1 = _get_or_create_matrix_token(account_id_1)
        if not token_1:
            logger.error(f"[Matrix DM] Failed to get token for account {account_id_1}")
            return None

        token_2 = _get_or_create_matrix_token_for_dm(account_id_2)

        # Generate Matrix user IDs
        matrix_user_1 = get_matrix_user_id(account_id_1)
        matrix_user_2 = get_matrix_user_id(account_id_2)

        with httpx.Client() as client:
            # Check if DM room already exists
            existing_room_id = _find_existing_dm(client, token_1, account_id_1, matrix_user_2, token_2)
            if existing_room_id:
                logger.info(f"[Matrix DM] Existing DM found between {account_id_1} and {account_id_2}: {existing_room_id}")

                # Send context message to existing room (e.g. item link when contacting seller again)
                if initial_message:
                    import uuid
                    txn_id = str(uuid.uuid4())
                    msg_content = {
                        "msgtype": "m.notice",
                        "body": initial_message,
                    }
                    if initial_message_html:
                        msg_content["format"] = "org.matrix.custom.html"
                        msg_content["formatted_body"] = initial_message_html
                    try:
                        msg_response = client.put(
                            f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{existing_room_id}/send/m.room.message/{txn_id}",
                            headers={"Authorization": f"Bearer {token_1}"},
                            json=msg_content
                        )
                        if msg_response.status_code not in (200, 201):
                            logger.warning(f"[Matrix DM] Failed to send message to existing room {existing_room_id}: {msg_response.text}")
                    except Exception as msg_err:
                        logger.warning(f"[Matrix DM] Exception sending message to existing room: {msg_err}")

                return existing_room_id

            # Create DM room (no explicit name - Matrix clients show the other participant's name)
            create_room_response = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/createRoom",
                headers={"Authorization": f"Bearer {token_1}"},
                json={
                    "preset": "trusted_private_chat",
                    "invite": [matrix_user_2],
                    "is_direct": True,
                    "initial_state": [
                        {
                            "type": "m.room.encryption",
                            "state_key": "",
                            "content": {
                                "algorithm": "m.megolm.v1.aes-sha2"
                            }
                        }
                    ]
                }
            )

            if create_room_response.status_code not in (200, 201):
                logger.error(f"[Matrix DM] Failed to create room: {create_room_response.text}")
                return None

            room_data = create_room_response.json()
            room_id = room_data.get("room_id")

            # Auto-accept invitation for second user
            time.sleep(0.5)

            if token_2:
                join_response = client.post(
                    f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{room_id}/join",
                    headers={"Authorization": f"Bearer {token_2}"},
                    json={}
                )

                if join_response.status_code not in (200, 201):
                    logger.warning(f"[Matrix DM] Auto-accept failed for {account_id_2} in room {room_id}")

                # Update m.direct for both users
                _update_direct_rooms(client, token_1, account_id_1, matrix_user_2, room_id)
                _update_direct_rooms(client, token_2, account_id_2, matrix_user_1, room_id)
            else:
                logger.warning(f"[Matrix DM] No token for {account_id_2}, skipping auto-join and m.direct")
                # Still update m.direct for the creator
                _update_direct_rooms(client, token_1, account_id_1, matrix_user_2, room_id)

            # Send initial message if provided (only for new rooms)
            if initial_message and room_id:
                import uuid
                txn_id = str(uuid.uuid4())
                msg_content = {
                    "msgtype": "m.notice",
                    "body": initial_message,
                }
                if initial_message_html:
                    msg_content["format"] = "org.matrix.custom.html"
                    msg_content["formatted_body"] = initial_message_html

                try:
                    msg_response = client.put(
                        f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{room_id}/send/m.room.message/{txn_id}",
                        headers={"Authorization": f"Bearer {token_1}"},
                        json=msg_content
                    )
                    if msg_response.status_code not in (200, 201):
                        logger.warning(f"[Matrix DM] Failed to send initial message in {room_id}: {msg_response.text}")
                except Exception as msg_err:
                    logger.warning(f"[Matrix DM] Exception sending initial message: {msg_err}")

            logger.info(f"[Matrix DM] Created DM room {room_id} between {account_id_1} and {account_id_2}")
            return room_id

    except Exception as e:
        logger.error(f"[Matrix DM] Exception creating DM between {account_id_1} and {account_id_2}: {e}")
        return None


class CreateDMRequest(BaseModel):
    target_account_id: str
    # Optional context for initial message (e.g. from market)
    item_id: Optional[str] = None
    item_title: Optional[str] = None
    # Custom initial message (overrides auto-generated message from item context)
    initial_message: Optional[str] = None


@router.post("/create-dm", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:create_dm', key=user_or_ip, rate='5/m', method='POST')
def create_dm_room(request, payload: CreateDMRequest):
    """
    Create a DM room with auto-accept for both users
    Creates Matrix users if needed, creates room, and auto-accepts invite

    Returns:
        {
            "success": true,
            "room_id": "!abc123:parahub.io"
        }
    """
    current_user_id = request.user.id
    target_user_id = payload.target_account_id

    if current_user_id == target_user_id:
        return {"success": False, "error": "Cannot create DM with yourself"}

    # Build initial message from context
    initial_message = None
    initial_message_html = None
    if payload.initial_message:
        # Custom message from Propose Deal modal
        initial_message = payload.initial_message
    elif payload.item_id and payload.item_title:
        from identity.models import Profile
        buyer_profile = Profile.objects.filter(account_id=current_user_id, is_primary=True).first()
        buyer_hna = buyer_profile.hna if buyer_profile else str(current_user_id)
        buyer_local_name = buyer_profile.local_name if buyer_profile else str(current_user_id)

        item_url = f"https://parahub.io/market/{payload.item_id}"
        profile_url = f"https://parahub.io/u/{buyer_local_name}"

        initial_message = f"\U0001f6d2 {payload.item_title}\n{item_url}\n\n\U0001f464 {buyer_hna}\n{profile_url}"
        initial_message_html = (
            f'<p>\U0001f6d2 <a href="{item_url}">{payload.item_title}</a></p>'
            f'<p>\U0001f464 <a href="{profile_url}">{buyer_hna}</a></p>'
        )

    room_id = create_dm_between_accounts(current_user_id, target_user_id, initial_message, initial_message_html)
    if room_id:
        return {"success": True, "room_id": room_id}
    else:
        return {"success": False, "error": "Failed to create DM room"}


class CreateGroupChatRequest(BaseModel):
    participant_account_ids: list[str]
    room_name: str = None


@router.post("/create-group-chat", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:create_group_chat', key=user_or_ip, rate='5/m', method='POST')
def create_group_chat_room(request, payload: CreateGroupChatRequest):
    """
    Create a group chat room with auto-accept for all participants
    Creates Matrix users if needed, creates room, and auto-accepts invites for all

    Args:
        participant_account_ids: List of Profile IDs to invite (excluding creator)
        room_name: Optional room name (defaults to "Barter Exchange")

    Returns:
        {
            "success": true,
            "room_id": "!abc123:parahub.io"
        }
    """
    current_user_id = request.user.id
    participant_profile_ids = payload.participant_account_ids  # Note: despite name, these are Profile IDs
    room_name = payload.room_name or "Barter Exchange"

    # Validate participants
    if not participant_profile_ids or len(participant_profile_ids) == 0:
        return {"success": False, "error": "At least one participant required"}

    # Don't allow duplicate participants
    unique_profile_ids = list(set(participant_profile_ids))

    try:
        from identity.models import Profile

        # Convert Profile IDs to Account IDs
        profile_to_account = {}
        for profile_id in unique_profile_ids:
            try:
                profile = Profile.objects.select_related('account').get(id=profile_id)
                profile_to_account[profile_id] = profile.account.id
            except Profile.DoesNotExist:
                return {"success": False, "error": f"Profile {profile_id} not found"}

        # Get current user's Account ID (request.user is Account)
        current_account_id = current_user_id

        # Remove current user's account from participants if present
        participant_account_ids = [acc_id for acc_id in profile_to_account.values() if acc_id != current_account_id]

        if len(participant_account_ids) == 0:
            return {"success": False, "error": "At least one other participant required"}

        # Get access tokens for all users (creator + participants)
        current_token = _get_or_create_matrix_token(current_account_id)
        if not current_token:
            return {"success": False, "error": "Failed to create Matrix session for current user"}

        participant_tokens = {}
        participant_matrix_ids = []

        for account_id in participant_account_ids:
            token = _get_or_create_matrix_token(account_id)
            if not token:
                return {"success": False, "error": f"Failed to create Matrix session for participant {account_id}"}

            participant_tokens[account_id] = token
            # Get Matrix user ID from profile's local_name (human-readable)
            participant_matrix_ids.append(get_matrix_user_id(account_id))

        with httpx.Client() as client:
            # Create group chat room
            create_room_response = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/createRoom",
                headers={"Authorization": f"Bearer {current_token}"},
                json={
                    "preset": "private_chat",  # Private room with invites
                    "invite": participant_matrix_ids,
                    "name": room_name,
                    "initial_state": [
                        {
                            "type": "m.room.encryption",
                            "state_key": "",
                            "content": {
                                "algorithm": "m.megolm.v1.aes-sha2"
                            }
                        }
                    ]
                }
            )

            if create_room_response.status_code not in (200, 201):
                return {
                    "success": False,
                    "error": f"Failed to create room: {create_room_response.text}"
                }

            room_data = create_room_response.json()
            room_id = room_data.get("room_id")

            # Auto-accept invitations for all participants
            time.sleep(0.5)  # Brief delay to ensure invites are propagated

            failed_joins = []
            for account_id in participant_account_ids:
                try:
                    join_response = client.post(
                        f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{room_id}/join",
                        headers={"Authorization": f"Bearer {participant_tokens[account_id]}"},
                        json={}
                    )

                    if join_response.status_code not in (200, 201):
                        failed_joins.append(account_id)
                except Exception:
                    failed_joins.append(account_id)

            if failed_joins:
                # Room created but some auto-accepts failed
                return {
                    "success": True,
                    "room_id": room_id,
                    "warning": f"Room created but auto-accept failed for {len(failed_joins)} participant(s). They need to manually accept."
                }

            return {
                "success": True,
                "room_id": room_id
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }