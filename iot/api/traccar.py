"""
Traccar integration: credentials, SSO redirect, webhook, tracker positions.
"""


from typing import List, Optional
from datetime import datetime, timezone as dt_tz
import logging
from ninja import Schema
from ninja.errors import HttpError
from django.utils.crypto import get_random_string
from django.http import HttpRequest
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from core.access import accessible_q
from django.conf import settings
from ..models import IoTDevice, TraccarUser
from ..services import TraccarService

from .base import router

logger = logging.getLogger(__name__)

class TraccarCredentialsOut(Schema):
    username: str  # Deprecated: use login_email instead
    login_email: str  # The actual email to use for Traccar login
    password: str
    traccar_url: str = "https://traccar.parahub.io"
    has_account: bool

class TraccarSSOTicketOut(Schema):
    url: str
    expires_in: int = 60  # seconds

@router.get("/traccar/credentials", response=TraccarCredentialsOut, auth=ProfileAuth())
@ratelimit(group='iot:traccar_credentials', key=user_or_ip, rate='10/m')
def get_traccar_credentials(request):
    """Get Traccar credentials — auto-creates the account if it doesn't exist."""
    # Get authenticated user's profile
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    # Check for an existing account, create one automatically if absent
    try:
        # Try to fetch the existing account
        traccar_account = profile.traccar_account
    except TraccarUser.DoesNotExist:
        # No account yet — try to create one automatically
        try:
            traccar_service = TraccarService()
            traccar_service.create_or_update_user(profile)
            # Refresh the profile from the DB to pick up the new relation
            profile.refresh_from_db()
            traccar_account = profile.traccar_account
        except Exception as e:
            logger.error(f"Failed to create Traccar user: {e}")
            raise HttpError(503, f"Failed to create Traccar account: {str(e)}")

    # Decrypt the password for display to the user
    try:
        decrypted_password = TraccarService.decrypt_password(traccar_account.traccar_password_encrypted)
    except Exception as e:
        logger.error(f"Failed to decrypt Traccar password: {e}")
        decrypted_password = "Failed to retrieve password"
    
    # Compute the login email from username + domain
    login_email = f"{traccar_account.traccar_username}@{settings.TRACCAR_EMAIL_DOMAIN}"
    
    return TraccarCredentialsOut(
        username=traccar_account.traccar_username,  # Deprecated
        login_email=login_email,  # Use this for Traccar login
        password=decrypted_password,
        has_account=True
    )

@router.get("/traccar/sso-redirect")
@ratelimit(group='iot:traccar_sso', key='ip', rate='30/m')
def traccar_sso_redirect(request):
    """Initiate the OAuth2 flow for Traccar via OIDC."""
    from django.http import HttpResponseRedirect
    from urllib.parse import urlencode
    import hashlib
    import time

    # Generate a state value for CSRF protection
    # Use a hash of the current time and a random string
    state_source = f"{time.time()}:{get_random_string(16)}"
    state = hashlib.sha256(state_source.encode()).hexdigest()[:32]

    # OAuth2 authorization parameters
    params = {
        'response_type': 'code',
        'client_id': 'traccar-sso-client',
        'redirect_uri': 'https://traccar.parahub.io/api/session/openid/callback',
        'scope': 'openid profile email groups',
        'state': state,
    }
    
    # Redirect to the OAuth2 authorize endpoint
    authorize_url = f"https://parahub.io/o/authorize/?{urlencode(params)}"
    return HttpResponseRedirect(authorize_url)

_TRACCAR_ALLOWED_NETS = ('127.', '::1', '172.', '10.', '192.168.')

@router.post("/webhook/traccar", auth=None)
@ratelimit(group='iot:webhook', key='ip', rate='600/m')
def traccar_webhook(request: HttpRequest):
    """Receive position updates from Traccar event forwarding.

    Configured in traccar.xml via event.forward.url.
    Only accessible from localhost / Docker internal network.
    """
    import json as _json

    # Restrict to localhost / internal networks only. Use REMOTE_ADDR (set by
    # uvicorn proxy-headers to the real client), NOT the raw X-Forwarded-For:
    # nginx appends to a client-sent value, so its left-most element is
    # attacker-controlled — forging "X-Forwarded-For: 127.0.0.1" would
    # otherwise pass this internal-only allowlist from the public internet.
    client_ip = request.META.get('REMOTE_ADDR', '')
    if not any(client_ip.startswith(prefix) for prefix in _TRACCAR_ALLOWED_NETS):
        raise HttpError(403, "Forbidden")

    try:
        data = _json.loads(request.body)
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid JSON")

    success = TraccarService.process_position_redis(data)
    return {"processed": success}

class TrackerPositionOut(Schema):
    device_id: str
    name: str
    latitude: float
    longitude: float
    speed: Optional[float] = None
    heading: Optional[float] = None
    battery_level: Optional[int] = None
    last_update: Optional[datetime] = None
    traccar_status: Optional[str] = None

@router.get("/tracker-positions", response=List[TrackerPositionOut], auth=ProfileAuth())
@ratelimit(group='iot:tracker_positions', key=user_or_ip, rate='60/m')
def get_tracker_positions(request):
    """Get all tracker positions for the authenticated user (from Redis)."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    # Own trackers + trackers shared via ObjectAccess grants
    devices = list(
        IoTDevice.objects.filter(
            accessible_q(profile),
            device_type='TRACKER',
        ).values_list('id', 'name')
    )

    if not devices:
        return []

    device_ids = [str(d[0]) for d in devices]
    device_names = {str(d[0]): d[1] for d in devices}

    # Read live positions from Redis
    positions = TraccarService.get_positions_from_redis(device_ids)

    import time as _time
    now_epoch = int(_time.time())

    result = []
    for dev_id, pos in positions.items():
        lat = pos.get('lat')
        lon = pos.get('lon')
        if lat and lon:
            t = pos.get('t')
            # Derive status from age: <120s = online, <600s = unknown, else offline
            age = (now_epoch - t) if t else 999999
            status = 'online' if age < 120 else ('unknown' if age < 600 else 'offline')
            result.append(TrackerPositionOut(
                device_id=dev_id,
                name=device_names.get(dev_id, pos.get('name', '')),
                latitude=lat,
                longitude=lon,
                speed=pos.get('spd'),
                heading=pos.get('hdg'),
                battery_level=pos.get('bat'),
                last_update=datetime.fromtimestamp(t, tz=dt_tz.utc) if t else None,
                traccar_status=status,
            ))

    return result
