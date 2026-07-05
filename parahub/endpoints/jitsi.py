"""
Jitsi Meet integration for Parahub
Handles JWT token generation for authenticated video calls
"""

from ninja import Router
from typing import Dict, Any, Optional
from pydantic import BaseModel
import jwt
import time
import secrets
import logging
from django.conf import settings

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

router = Router(tags=["jitsi"])
logger = logging.getLogger(__name__)


def get_jitsi_jwt_secret() -> Optional[str]:
    """Get Jitsi JWT secret from settings"""
    return getattr(settings, 'JITSI_JWT_SECRET', None)


def generate_jitsi_jwt(
    room_name: str,
    profile_id: str,
    display_name: str,
    is_moderator: bool = True,
    expiry_seconds: int = 3600
) -> Optional[str]:
    """
    Generate a JWT token for Jitsi Meet authentication.

    JWT Payload format (Jitsi standard):
    {
        "aud": "parahub",
        "iss": "parahub.io",
        "sub": "jitsi.parahub.io",
        "room": room_name,
        "exp": timestamp,
        "context": {
            "user": {
                "id": profile_id,
                "name": display_name,
                "moderator": true/false
            }
        }
    }
    """
    secret = get_jitsi_jwt_secret()
    if not secret:
        logger.error("[Jitsi] JITSI_JWT_SECRET not configured")
        return None

    now = int(time.time())
    payload = {
        "aud": "parahub",
        "iss": "parahub.io",
        "sub": "jitsi.parahub.io",
        "room": room_name,
        "exp": now + expiry_seconds,
        "iat": now,
        "nbf": now,
        "context": {
            "user": {
                "id": profile_id,
                "name": display_name,
                "moderator": is_moderator
            }
        }
    }

    try:
        token = jwt.encode(payload, secret, algorithm="HS256")
        logger.info(f"[Jitsi] Generated JWT for room {room_name}, user {profile_id}")
        return token
    except Exception as e:
        logger.error(f"[Jitsi] Failed to generate JWT: {e}")
        return None


def generate_room_name(caller_id: str, callee_id: str = None) -> str:
    """
    Generate a unique room name for a call.

    Format: ph-{caller_id[:8]}-{callee_id[:8]}-{random_hex}
    """
    random_suffix = secrets.token_hex(4)
    if callee_id:
        return f"ph-{caller_id[:8]}-{callee_id[:8]}-{random_suffix}"
    else:
        return f"ph-{caller_id[:8]}-{random_suffix}"


class CreateRoomResponse(BaseModel):
    success: bool
    room_name: Optional[str] = None
    jwt_token: Optional[str] = None
    jitsi_url: Optional[str] = None
    error: Optional[str] = None


class JoinRoomResponse(BaseModel):
    success: bool
    jwt_token: Optional[str] = None
    jitsi_url: Optional[str] = None
    error: Optional[str] = None


class CreateRoomRequest(BaseModel):
    target_profile_id: Optional[str] = None


@router.post("/create-room", response=CreateRoomResponse, auth=ProfileAuth())
@ratelimit(group='jitsi:create_room', key=user_or_ip, rate='10/m', method='POST')
def create_room(request, payload: CreateRoomRequest = None):
    """
    Create a new Jitsi room and return JWT for the creator.

    - Requires authenticated user (ProfileAuth)
    - Generates unique room name
    - Returns JWT token for room access
    - Creator is always moderator
    """
    profile = request.auth_profile

    if not profile:
        return CreateRoomResponse(success=False, error="Profile not found")

    # Check if Jitsi is configured
    if not get_jitsi_jwt_secret():
        return CreateRoomResponse(success=False, error="Jitsi not configured")

    # Generate room name
    target_id = payload.target_profile_id if payload else None
    room_name = generate_room_name(profile.id, target_id)

    # Get display name
    display_name = (profile.display_name if profile.name_public else '') or profile.hna or profile.local_name or "User"

    # Generate JWT (creator is always moderator)
    jwt_token = generate_jitsi_jwt(
        room_name=room_name,
        profile_id=profile.id,
        display_name=display_name,
        is_moderator=True
    )

    if not jwt_token:
        return CreateRoomResponse(success=False, error="Failed to generate authentication token")

    # Build Jitsi URL
    jitsi_url = f"https://jitsi.parahub.io/{room_name}?jwt={jwt_token}"

    # Send notifications to target user if specified
    if target_id:
        try:
            from identity.models import Profile
            from notifications.services import notify_incoming_call
            from parahub.services.ws_publish import ws_publish

            target_profile = Profile.objects.filter(id=target_id).first()
            if target_profile and target_profile.account:
                ws_publish(f"user:{target_profile.account.id}", {
                    "type": "call.incoming",
                    "caller": {
                        "id": profile.id,
                        "display_name": display_name,
                        "local_name": profile.local_name,
                        "avatar_url": profile.avatar.url if profile.avatar else None,
                    },
                    "room_name": room_name,
                })
                logger.info(f"[Jitsi] Sent WebSocket call notification to {target_id}")

                # Send push notification
                notify_incoming_call(
                    user=target_profile.account,
                    caller_profile=profile,
                    room_name=room_name
                )
                logger.info(f"[Jitsi] Sent push call notification to {target_id}")
        except Exception as e:
            # Don't fail room creation if notification fails
            logger.warning(f"[Jitsi] Failed to send call notification: {e}")

    logger.info(f"[Jitsi] Room created: {room_name} by profile {profile.id}")

    return CreateRoomResponse(
        success=True,
        room_name=room_name,
        jwt_token=jwt_token,
        jitsi_url=jitsi_url
    )


@router.post("/join-room/{room_name}", response=JoinRoomResponse, auth=ProfileAuth())
@ratelimit(group='jitsi:join_room', key=user_or_ip, rate='20/m', method='POST')
def join_room(request, room_name: str):
    """
    Join an existing Jitsi room and return JWT.

    - Requires authenticated user (ProfileAuth)
    - Returns JWT token for room access
    - Joiners are not moderators by default
    """
    profile = request.auth_profile

    if not profile:
        return JoinRoomResponse(success=False, error="Profile not found")

    # Check if Jitsi is configured
    if not get_jitsi_jwt_secret():
        return JoinRoomResponse(success=False, error="Jitsi not configured")

    # Validate room name (basic sanitization)
    if not room_name or len(room_name) > 100 or not room_name.replace("-", "").replace("_", "").isalnum():
        return JoinRoomResponse(success=False, error="Invalid room name")

    # Get display name
    display_name = (profile.display_name if profile.name_public else '') or profile.hna or profile.local_name or "User"

    # Generate JWT (joiner is not moderator by default)
    jwt_token = generate_jitsi_jwt(
        room_name=room_name,
        profile_id=profile.id,
        display_name=display_name,
        is_moderator=False
    )

    if not jwt_token:
        return JoinRoomResponse(success=False, error="Failed to generate authentication token")

    # Build Jitsi URL
    jitsi_url = f"https://jitsi.parahub.io/{room_name}?jwt={jwt_token}"

    logger.info(f"[Jitsi] User {profile.id} joining room: {room_name}")

    return JoinRoomResponse(
        success=True,
        jwt_token=jwt_token,
        jitsi_url=jitsi_url
    )


@router.get("/status", response=Dict[str, Any])
@ratelimit(group='jitsi:status', key='ip', rate='30/m')
def jitsi_status(request):
    """
    Check Jitsi service status and configuration.

    Public endpoint - no auth required.
    """
    is_configured = get_jitsi_jwt_secret() is not None

    return {
        "configured": is_configured,
        "domain": "jitsi.parahub.io" if is_configured else None,
        "message": "Jitsi Meet is available" if is_configured else "Jitsi Meet is not configured"
    }
