"""
WebSocket authentication middleware for Parahub.
Handles JWT authentication for WebSocket connections.
"""

import logging
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from ninja_jwt.tokens import AccessToken
from ninja_jwt.exceptions import TokenError
from identity.models import Profile

logger = logging.getLogger(__name__)


class JWTAuthMiddleware(BaseMiddleware):
    """
    JWT authentication middleware for WebSocket connections.

    Extracts JWT token from cookies (preferred) or query parameters (deprecated).

    Preferred method (secure):
        Set cookie 'ws_token' with JWT token value

    Deprecated method (query params - will be removed):
        ws://host/path/?token=<jwt_token>
        ⚠️ Query params are logged in server logs, exposing tokens
    """
    
    async def __call__(self, scope, receive, send):
        # Try to extract token from cookies first (secure method)
        token = self.get_token_from_cookies(scope)

        # Fallback to query params for backward compatibility (deprecated, will be removed)
        if not token:
            query_string = scope.get("query_string", b"").decode()
            query_params = parse_qs(query_string)
            token = query_params.get("token", [None])[0]

            if token:
                logger.warning(
                    f"WebSocket using deprecated query param auth for path: {scope['path']}. "
                    "Please migrate to cookie-based authentication."
                )

        # Authenticate user
        scope["user"] = await self.get_user_from_token(token)
        scope["profile"] = await self.get_profile_from_user(scope["user"])

        # Log authentication result
        if scope["user"].is_authenticated:
            logger.info(f"WebSocket authenticated: {scope['user'].username}")
        elif scope['path'] not in ('/ws/v1/public/', '/ws/v1/transit/', '/ws/v1/federation/'):
            # Suppress warning for public WS endpoints (no auth by design)
            logger.warning(f"WebSocket authentication failed for path: {scope['path']}")

        return await super().__call__(scope, receive, send)
    
    def get_token_from_cookies(self, scope):
        """
        Extract JWT token from cookies.

        Args:
            scope: ASGI scope dict containing headers

        Returns:
            Token string or None
        """
        headers = dict(scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode()

        if not cookie_header:
            return None

        # Parse cookies manually
        cookies = {}
        for cookie in cookie_header.split(";"):
            cookie = cookie.strip()
            if "=" in cookie:
                key, value = cookie.split("=", 1)
                cookies[key] = value

        # Look for ws_token cookie
        return cookies.get("ws_token")

    @database_sync_to_async
    def get_user_from_token(self, token_string):
        """
        Validate JWT token and return the associated user.
        
        Args:
            token_string: JWT token as string
            
        Returns:
            User object or AnonymousUser if authentication fails
        """
        if not token_string:
            return AnonymousUser()
        
        try:
            # Decode and validate token
            token = AccessToken(token_string)
            
            # Get user from token
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            user = User.objects.get(id=token["user_id"])
            
            # Check if user is active
            if not user.is_active:
                logger.warning(f"Inactive user attempted WebSocket connection: {user.username}")
                return AnonymousUser()
            
            return user
            
        except TokenError as e:
            logger.warning(f"Invalid token in WebSocket connection: {e}")
            return AnonymousUser()
        except User.DoesNotExist:
            logger.warning(f"User not found for token")
            return AnonymousUser()
        except Exception as e:
            logger.error(f"Unexpected error in WebSocket authentication: {e}")
            return AnonymousUser()
    
    @database_sync_to_async
    def get_profile_from_user(self, user):
        """
        Get the Profile object for an authenticated user.

        Args:
            user: Django User object (Account model)

        Returns:
            Profile object or None
        """
        if not user.is_authenticated:
            return None

        try:
            # Account IS the user model, so query directly (use primary profile)
            return Profile.objects.get(account=user, is_primary=True)
        except Profile.DoesNotExist:
            logger.warning(f"Profile not found for user: {user.username}")
            return None