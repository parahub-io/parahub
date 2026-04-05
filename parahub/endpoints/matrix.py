"""
Matrix integration endpoints for Parahub
Handles Matrix session creation and management
"""

from ninja import Router
from ninja.responses import Response
from django.contrib.auth.decorators import login_required
from typing import Dict, Any
import httpx
import json
import hashlib
import logging
from django.conf import settings
from parahub.endpoints.matrix_auth import get_matrix_user_id

from parahub.ratelimit import ratelimit

logger = logging.getLogger(__name__)

router = Router(tags=["matrix"])


@router.post("/session", response=Dict[str, Any])
@ratelimit(group='matrix:session', key='ip', rate='10/m', method='POST')
def create_matrix_session(request):
    """
    Create or retrieve a Matrix session for the authenticated user
    This endpoint handles the SSO flow programmatically
    """
    if not request.user.is_authenticated:
        return {"success": False, "error": "Authentication required"}
    
    user = request.user

    # Generate Matrix user ID from profile's local_name (human-readable)
    matrix_user_id = get_matrix_user_id(user.id)

    try:
        # For now, we'll use the OIDC flow
        # Generate a mock access token for development
        import uuid
        import time
        
        # Create mock Matrix session data
        access_token = f"mock_token_{uuid.uuid4().hex[:16]}"
        device_id = f"PARAHUB_{uuid.uuid4().hex[:8].upper()}"
        
        # Store session data (in production this would be from actual Matrix auth)
        return {
            "success": True,
            "user_id": matrix_user_id,
            "access_token": access_token,
            "device_id": device_id,
            "homeserver": "https://parahub.io",
            "message": "Matrix session created successfully"
        }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/status", response=Dict[str, Any])
@ratelimit(group='matrix:status', key='ip', rate='30/m')
def get_matrix_status(request):
    """
    Check Matrix server status and user's connection status
    """
    if not request.user.is_authenticated:
        return {"connected": False, "homeserver_online": False}
    
    try:
        # Check if Synapse is responding
        response = httpx.get("http://localhost:8008/health", timeout=5.0)
        homeserver_online = response.status_code == 200
    except Exception as e:
        logger.warning(f"Failed to check Matrix homeserver status: {e}")
        homeserver_online = False
    
    return {
        "connected": False,  # Would check actual Matrix session here
        "homeserver_online": homeserver_online,
        "homeserver_url": "https://parahub.io"
    }


@router.post("/room/create", response=Dict[str, Any])
@ratelimit(group='matrix:create_room', key='ip', rate='10/m', method='POST')
@login_required
def create_room(request, name: str, topic: str = "", is_public: bool = False):
    """
    Create a new Matrix room
    """
    # This would use the Matrix Admin API to create a room
    # For now, return a placeholder
    return {
        "success": False,
        "error": "Room creation requires Matrix session"
    }


@router.get("/rooms", response=Dict[str, Any])
@ratelimit(group='matrix:rooms', key='ip', rate='30/m')
@login_required
def list_rooms(request):
    """
    List user's Matrix rooms
    """
    # This would fetch rooms from Matrix
    return {
        "rooms": [],
        "total": 0
    }