"""
Matrix authentication and widget integration for Parahub
Handles real Matrix/Synapse integration with auto-provisioning
"""

from ninja import Router
from typing import Dict, Any, Optional
from pydantic import BaseModel
import hashlib
import html
import httpx
import logging
import mimetypes
import os
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

# Synapse is local; connect must be near-instant. The overall ceiling bounds
# how long a Synapse hiccup can hold a request slot (endpoints here are sync,
# and sync handlers share a single executor thread per worker).
SYNAPSE_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=2.0)

# MAS (Matrix Authentication Service). Synapse delegates auth to MAS: users are
# created through the MAS admin API (MAS provisions them into Synapse) and
# backend tokens are MAS personal sessions. The Synapse admin API is still used
# for room-level operations (members, purge) with SYNAPSE_ADMIN_TOKEN.
MAS_BASE_URL = getattr(settings, 'MAS_BASE_URL', 'http://localhost:8081/mas')
MAS_ADMIN_CLIENT_ID = getattr(settings, 'MAS_ADMIN_CLIENT_ID', None)
MAS_ADMIN_CLIENT_SECRET = getattr(settings, 'MAS_ADMIN_CLIENT_SECRET', None)
MAS_UPSTREAM_PROVIDER_ID = getattr(settings, 'MAS_UPSTREAM_PROVIDER_ID', None)

# client_credentials tokens are short-lived (MAS default 5 min); cache per
# worker process with a safety margin.
_mas_admin_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def _get_mas_admin_token(client: httpx.Client) -> Optional[str]:
    """Obtain (and cache) a MAS admin API token via client_credentials."""
    if not (MAS_ADMIN_CLIENT_ID and MAS_ADMIN_CLIENT_SECRET):
        logger.error("[MAS] MAS_ADMIN_CLIENT_ID / MAS_ADMIN_CLIENT_SECRET not configured")
        return None

    now = time.time()
    if _mas_admin_token_cache["token"] and _mas_admin_token_cache["expires_at"] > now:
        return _mas_admin_token_cache["token"]

    try:
        response = client.post(
            f"{MAS_BASE_URL}/oauth2/token",
            auth=(MAS_ADMIN_CLIENT_ID, MAS_ADMIN_CLIENT_SECRET),
            data={"grant_type": "client_credentials", "scope": "urn:mas:admin"},
        )
        if response.status_code != 200:
            logger.error(f"[MAS] client_credentials failed: {response.status_code} - {response.text}")
            return None
        payload = response.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in", 300)
        _mas_admin_token_cache["token"] = token
        _mas_admin_token_cache["expires_at"] = now + max(60, expires_in - 60)
        return token
    except Exception as e:
        logger.error(f"[MAS] Exception obtaining admin token: {e}")
        return None


def _mas_ensure_user(client: httpx.Client, account_id: str, matrix_user_id: str) -> Optional[str]:
    """Ensure the user exists in MAS with an upstream link to the Parahub
    account, so SSO logs into the same Matrix user the backend acts on.

    MAS provisions the user into Synapse on creation. Returns the MAS user
    ULID, or None on error.
    """
    admin_token = _get_mas_admin_token(client)
    if not admin_token:
        return None
    headers = {"Authorization": f"Bearer {admin_token}"}
    localpart = matrix_user_id.lstrip('@').split(':', 1)[0]

    try:
        response = client.get(
            f"{MAS_BASE_URL}/api/admin/v1/users/by-username/{localpart}", headers=headers
        )
        if response.status_code == 200:
            mas_user_id = response.json()["data"]["id"]
        elif response.status_code == 404:
            response = client.post(
                f"{MAS_BASE_URL}/api/admin/v1/users", headers=headers,
                json={"username": localpart},
            )
            if response.status_code not in (200, 201):
                logger.error(f"[MAS] Failed to create user {localpart}: {response.status_code} - {response.text}")
                return None
            mas_user_id = response.json()["data"]["id"]
            logger.info(f"[MAS] Created user {matrix_user_id} (MAS id {mas_user_id})")
        else:
            logger.error(f"[MAS] User lookup failed for {localpart}: {response.status_code} - {response.text}")
            return None

        # Upstream link: subject = Account ULID ('sub' claim of the Parahub IdP)
        if MAS_UPSTREAM_PROVIDER_ID:
            response = client.get(
                f"{MAS_BASE_URL}/api/admin/v1/upstream-oauth-links",
                headers=headers,
                params={"filter[user]": mas_user_id},
            )
            links = response.json().get("data", []) if response.status_code == 200 else []
            linked = any(
                l["attributes"].get("provider_id") == MAS_UPSTREAM_PROVIDER_ID
                and l["attributes"].get("subject") == account_id
                for l in links
            )
            if not linked:
                response = client.post(
                    f"{MAS_BASE_URL}/api/admin/v1/upstream-oauth-links",
                    headers=headers,
                    json={
                        "user_id": mas_user_id,
                        "provider_id": MAS_UPSTREAM_PROVIDER_ID,
                        "subject": account_id,
                    },
                )
                if response.status_code in (200, 201):
                    logger.info(f"[MAS] Linked {matrix_user_id} to account {account_id}")
                else:
                    # 409 = subject already linked (possibly to another user after
                    # a rename); SSO keeps working through the existing link.
                    logger.warning(f"[MAS] Upstream link for {matrix_user_id} not created: {response.status_code} - {response.text}")

        return mas_user_id
    except Exception as e:
        logger.error(f"[MAS] Exception ensuring user {matrix_user_id}: {e}")
        return None


def _mas_mint_user_token(client: httpx.Client, mas_user_id: str, matrix_user_id: str,
                          ttl_seconds: int = 7 * 86400) -> Optional[Dict[str, str]]:
    """Mint a Matrix access token for a user via a MAS personal session.

    Replaces the pre-MAS admin /login mint. Returns
    {'access_token': ..., 'device_id': ...} or None.
    """
    import secrets as _secrets

    admin_token = _get_mas_admin_token(client)
    if not admin_token:
        return None

    device_id = "PW" + _secrets.token_hex(4).upper()
    try:
        response = client.post(
            f"{MAS_BASE_URL}/api/admin/v1/personal-sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "actor_user_id": mas_user_id,
                "human_name": f"parahub-backend {matrix_user_id}",
                "scope": "urn:matrix:org.matrix.msc2967.client:api:*"
                         f" urn:matrix:org.matrix.msc2967.client:device:{device_id}",
                "expires_in": ttl_seconds,
            },
        )
        if response.status_code not in (200, 201):
            logger.error(f"[MAS] personal-session mint failed for {matrix_user_id}: {response.status_code} - {response.text}")
            return None
        access_token = response.json()["data"]["attributes"]["access_token"]
        return {"access_token": access_token, "device_id": device_id}
    except Exception as e:
        logger.error(f"[MAS] Exception minting token for {matrix_user_id}: {e}")
        return None


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


def get_account_id_for_matrix_user(matrix_user_id: str) -> Optional[str]:
    """Reverse of get_matrix_user_id: map @localpart:server to an Account ID.

    Matrix lowercases localparts, so local_name is matched case-insensitively.
    Primary profiles win when several profiles share a local_name.
    """
    from identity.models import Profile

    localpart = matrix_user_id.lstrip('@').split(':', 1)[0]
    account_id = (
        Profile.objects.filter(local_name__iexact=localpart)
        .order_by('-is_primary')
        .values_list('account_id', flat=True)
        .first()
    )
    return str(account_id) if account_id else None


def get_room_joined_members(room_id: str) -> Optional[list]:
    """Currently joined members of a room via the admin API (client APIs may
    serve stale cache after a Matrix DB reset).

    Returns [] when the room is gone or nobody is joined — positively dead:
    on a homeserver with no other server in the room such a room can never be
    joined again. Returns None when liveness cannot be determined; callers
    must treat None as "unknown" and never recreate a room because of it.
    """
    if not SYNAPSE_ADMIN_TOKEN:
        return None
    from urllib.parse import quote
    try:
        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
            resp = client.get(
                f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/rooms/{quote(room_id, safe='')}/members",
                headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"},
            )
        if resp.status_code == 200:
            return resp.json().get("members", [])
        if resp.status_code == 404:
            return []
        logger.warning(f"[Matrix] Members lookup for {room_id} returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"[Matrix] Members lookup for {room_id} failed: {e}")
    return None


def purge_matrix_room(room_id: str) -> None:
    """Delete a room server-side (admin API v2, asynchronous purge).

    Best effort — intended for rooms already verified dead via
    get_room_joined_members, or for a just-created duplicate abandoned after
    losing a heal race.
    """
    if not (room_id and SYNAPSE_ADMIN_TOKEN):
        return
    from urllib.parse import quote
    try:
        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
            client.request(
                "DELETE",
                f"{SYNAPSE_BASE_URL}/_synapse/admin/v2/rooms/{quote(room_id, safe='')}",
                headers={"Authorization": f"Bearer {SYNAPSE_ADMIN_TOKEN}"},
                json={"purge": True, "block": False},
            )
    except Exception as e:
        logger.warning(f"[Matrix] Purge of {room_id} failed: {e}")


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

    # Under MAS the Synapse admin PUT would create a Synapse-only phantom that
    # MAS (the authority on users) never sees — SSO would then collide on the
    # localpart. Users must be created through MAS, which provisions them into
    # Synapse. The displayname is applied later, once a user token exists
    # (MAS user creation takes no displayname).
    return _mas_ensure_user(client, account_id, matrix_user_id) is not None


# --- Matrix profile mirroring (display name + avatar) -----------------------
# MAS imports only localpart/displayname/email from our OIDC claims — it has no
# avatar claim — so the avatar is pushed straight to Synapse with the member's
# own token. The marker TTL only bounds Redis growth; losing a marker costs one
# redundant upload, nothing else.
MATRIX_AVATAR_MARKER_TTL = 90 * 86400


def _mas_user_exists(client: httpx.Client, matrix_user_id: str) -> bool:
    """True when MAS already knows this Matrix user.

    Profile mirroring must never provision: a member who uploads an avatar but
    has never opened the chat should not gain a Matrix account as a side effect
    of that upload.
    """
    admin_token = _get_mas_admin_token(client)
    if not admin_token:
        return False

    localpart = matrix_user_id.lstrip('@').split(':', 1)[0]
    try:
        response = client.get(
            f"{MAS_BASE_URL}/api/admin/v1/users/by-username/{localpart}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"[Matrix] MAS lookup failed for {localpart}: {e}")
        return False


def sync_matrix_profile(account_id: str, force: bool = False) -> bool:
    """Mirror the account's PRIMARY profile — display name and avatar — onto
    its Matrix user, so chat shows the same face as the rest of the site.

    Only the primary profile is mirrored. The Matrix identity is derived from
    it (see /whoami), so pushing a pseudonym's avatar would tie that pseudonym
    to the primary account for everyone in the room.

    Synapse stores every upload as its own media entry, so the avatar bytes are
    hashed and the hash cached: repeat calls upload nothing while the avatar is
    unchanged. Best-effort — returns False instead of raising.
    """
    from identity.models import Profile

    profile = (
        Profile.objects.filter(account_id=account_id, is_primary=True)
        .select_related('account', 'instance')
        .first()
    )
    if not profile:
        return False

    matrix_user_id = get_matrix_user_id(account_id)
    marker_key = f"matrix_avatar_{account_id}"

    avatar_bytes = None
    if profile.avatar:
        try:
            with profile.avatar.open('rb') as f:
                avatar_bytes = f.read()
        except Exception as e:
            logger.warning(f"[Matrix] Avatar unreadable for profile {profile.id}: {e}")
    digest = hashlib.sha256(avatar_bytes).hexdigest() if avatar_bytes else ''

    try:
        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
            if not _mas_user_exists(client, matrix_user_id):
                return False

            token = _get_or_create_matrix_token_for_dm(account_id)
            if not token:
                return False
            headers = {"Authorization": f"Bearer {token}"}

            # Synapse has no no-op guard: every profile PUT propagates a member
            # state event into every room the user is in. Read the current
            # profile first and write only what actually differs.
            response = client.get(
                f"{SYNAPSE_BASE_URL}/_matrix/client/v3/profile/{matrix_user_id}"
            )
            current = response.json() if response.status_code == 200 else {}

            ok = True
            # Bare local_name, not the hna: Matrix already renders the full
            # @name:parahub.io beside it, and the member's real name is behind
            # a visibility toggle that a room-wide display name would ignore.
            displayname = profile.local_name or profile.account.username
            if current.get('displayname') != displayname:
                response = client.put(
                    f"{SYNAPSE_BASE_URL}/_matrix/client/v3/profile/{matrix_user_id}/displayname",
                    headers=headers,
                    json={"displayname": displayname},
                )
                if response.status_code != 200:
                    ok = False
                    logger.warning(f"[Matrix] Displayname sync failed for {matrix_user_id}: {response.status_code} - {response.text}")

            # The marker alone cannot be trusted when Matrix disagrees about
            # whether an avatar exists at all (media purge, profile reset), so
            # presence is cross-checked and the mirror self-heals.
            in_sync = cache.get(marker_key) == digest and bool(current.get('avatar_url')) == bool(avatar_bytes)
            if in_sync and not force:
                return ok

            if avatar_bytes:
                filename = os.path.basename(profile.avatar.name)
                content_type = mimetypes.guess_type(filename)[0] or 'image/jpeg'
                response = client.post(
                    f"{SYNAPSE_BASE_URL}/_matrix/media/v3/upload",
                    params={"filename": filename},
                    headers={**headers, "Content-Type": content_type},
                    content=avatar_bytes,
                )
                if response.status_code != 200:
                    logger.warning(f"[Matrix] Avatar upload failed for {matrix_user_id}: {response.status_code} - {response.text}")
                    return False
                avatar_url = response.json().get("content_uri")
            elif current.get('avatar_url'):
                avatar_url = ""
            else:
                # Nothing to clear — record the empty state and leave Matrix alone.
                cache.set(marker_key, digest, MATRIX_AVATAR_MARKER_TTL)
                return ok

            response = client.put(
                f"{SYNAPSE_BASE_URL}/_matrix/client/v3/profile/{matrix_user_id}/avatar_url",
                headers=headers,
                json={"avatar_url": avatar_url},
            )
            if response.status_code != 200:
                logger.warning(f"[Matrix] Avatar sync failed for {matrix_user_id}: {response.status_code} - {response.text}")
                return False

            cache.set(marker_key, digest, MATRIX_AVATAR_MARKER_TTL)
            logger.info(f"[Matrix] Profile mirrored for {matrix_user_id} (avatar {'set' if avatar_bytes else 'cleared'})")
            return ok
    except Exception as e:
        logger.warning(f"[Matrix] Profile sync failed for {matrix_user_id}: {e}")
        return False


def spawn_matrix_profile_sync(profile) -> None:
    """Queue a background mirror of `profile` onto its Matrix user.

    No-op for pseudonym profiles (see sync_matrix_profile). Call sites are the
    avatar write paths, where the member is waiting on the response and must
    not pay for a Synapse round-trip.
    """
    if not profile.is_primary:
        return

    from parahub.background import spawn

    spawn(sync_matrix_profile, str(profile.account_id), label='matrix_profile_sync')


@router.get("/whoami", response=Dict[str, Any], auth=GlobalAuth())
@ratelimit(group='matrix:whoami', key=user_or_ip, rate='30/m', method='GET')
def get_expected_matrix_user(request):
    """
    Return the Matrix user ID this account maps to on SSO login.

    The chat page compares it against the Cinny session cached in the
    browser to detect a session left behind by another account
    (account switch / shared computer) and wipe it before mounting.
    """
    return {"user_id": get_matrix_user_id(request.user.id)}


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
        session = _get_or_create_matrix_session(user.id)
        if not session:
            return {"success": False, "error": "Failed to create Matrix session"}

        access_token = session["access_token"]
        device_id = session.get("device_id", "PARAHUB_WEB")

        # Best-effort profile mirror from the primary profile (MAS user creation
        # takes no displayname, and imports no avatar at all; backend-created
        # users would otherwise show as bare localparts with no face). This is
        # also the catch-up path for avatars changed before the feature existed
        # — it only runs on a cold session cache, so at most every 6h per user.
        from parahub.background import spawn
        spawn(sync_matrix_profile, str(user.id), label='matrix_profile_sync')

        session_data = {
            "user_id": matrix_user_id,
            "access_token": access_token,
            "device_id": device_id,
            "homeserver": SYNAPSE_PUBLIC_URL,
            "widget_token": access_token,
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
        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
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
        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
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


def _get_or_create_matrix_session(user_id: str) -> Optional[Dict[str, str]]:
    """Get or create a Matrix session for a user by Account ID.

    Ensures the user exists in MAS (provisioned into Synapse, upstream-linked
    to the Parahub account) and mints a MAS personal-session token. Returns
    {'access_token': ..., 'device_id': ...} or None. Cached for 6h; the minted
    token itself lives 7 days.
    """
    from identity.models import Account

    try:
        Account.objects.get(id=user_id)
    except Account.DoesNotExist:
        logger.error(f"[Matrix] Account {user_id} does not exist")
        return None

    cache_key = f"matrix_session_{user_id}"
    cached_session = cache.get(cache_key)
    if cached_session and cached_session.get('access_token'):
        return cached_session

    matrix_user_id = get_matrix_user_id(user_id)

    try:
        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
            mas_user_id = _mas_ensure_user(client, user_id, matrix_user_id)
            if not mas_user_id:
                logger.error(f"[Matrix] Failed to ensure MAS user for {matrix_user_id}")
                return None

            session = _mas_mint_user_token(client, mas_user_id, matrix_user_id)
            if not session:
                return None

            cache.set(cache_key, session, 6 * 3600)
            return session
    except Exception as e:
        logger.error(f"[Matrix] Unexpected error creating session for {user_id}: {e}")
        return None


def _get_or_create_matrix_token(user_id: str) -> Optional[str]:
    """Get or create a Matrix access token for a user by Account ID."""
    session = _get_or_create_matrix_session(user_id)
    return session.get('access_token') if session else None


def _get_or_create_matrix_token_for_dm(user_id: str) -> Optional[str]:
    """Like _get_or_create_matrix_token, but validates the (possibly cached)
    token against Synapse and re-mints once if it went stale (DB reset,
    revoked session)."""
    token = _get_or_create_matrix_token(user_id)
    if not token:
        return None

    try:
        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
            response = client.get(
                f"{SYNAPSE_BASE_URL}/_matrix/client/v3/account/whoami",
                headers={"Authorization": f"Bearer {token}"}
            )
        if response.status_code == 200:
            return token
        logger.warning(f"[Matrix DM] Cached token invalid for {user_id}, re-minting")
    except Exception as e:
        logger.warning(f"[Matrix DM] Token validation failed: {e}")

    cache.delete(f"matrix_session_{user_id}")
    return _get_or_create_matrix_token(user_id)


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

        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
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

    # Block enforcement (Play UGC policy). Direction-neutral error: the caller
    # is not told who blocked whom. System-initiated DMs (contract signing,
    # shipments, rides) bypass this — those follow explicit mutual engagement.
    from identity.services.blocks import dm_blocked_between_accounts
    from parahub.errors import LocalizedHttpError
    if dm_blocked_between_accounts(current_user_id, target_user_id):
        raise LocalizedHttpError(403, "dm_blocked", "Unable to start a chat with this user")

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
        profile_url = f"https://parahub.io/@{buyer_local_name}"

        initial_message = f"\U0001f6d2 {payload.item_title}\n{item_url}\n\n\U0001f464 {buyer_hna}\n{profile_url}"
        # Escape everything interpolated into formatted_body — item_id/item_title
        # come straight from the client (href attribute + element content).
        initial_message_html = (
            f'<p>\U0001f6d2 <a href="{html.escape(item_url)}">{html.escape(payload.item_title)}</a></p>'
            f'<p>\U0001f464 <a href="{html.escape(profile_url)}">{html.escape(buyer_hna)}</a></p>'
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

        with httpx.Client(timeout=SYNAPSE_HTTP_TIMEOUT) as client:
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