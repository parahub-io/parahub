"""
Authentication system for Parahub API using Django Ninja
Implements JWT-based authentication with profile resolution
"""

from ninja.security import HttpBearer
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from identity.models import Account, Profile
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class GlobalAuth(HttpBearer):
    """
    Global authentication class that handles JWT tokens and user resolution
    Extends HttpBearer to work with Authorization headers
    """
    
    def authenticate(self, request, token: str) -> Optional[Any]:
        """
        Authenticate the request using JWT token
        Returns the authenticated user or None
        """
        try:
            # Use ninja-jwt to validate token
            jwt_auth = JWTAuth()
            user = jwt_auth.authenticate(request, token)
            
            if user is None:
                return None
                
            # Ensure we have a valid Account instance
            if not isinstance(user, Account):
                logger.warning(f"Invalid user type: {type(user)}")
                return None
                
            # Attach user to request for easy access
            request.user = user
            
            return user
            
        except Exception as e:
            logger.warning(f"JWT authentication failed: {e}")
            return None
    
    def get_user_profile(self, request) -> Optional[Profile]:
        """
        Get the active profile for the authenticated user

        Priority:
        1. Active profile from session (if user can manage it)
        2. Primary profile (marked with is_primary=True)
        3. First profile (fallback)

        Creates primary profile automatically if it doesn't exist
        """
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return None

        try:
            # Get primary profile first (for fallback) with account preloaded
            primary_profile = request.user.profiles.filter(is_primary=True).select_related('account').first()

            # Auto-create primary profile if it doesn't exist
            if primary_profile is None:
                from core.models import Instance

                # Get default instance (parahub.io)
                instance = Instance.objects.filter(domain='parahub.io').first()
                if instance is None:
                    logger.error("Default instance not found, cannot create profile")
                    return None

                # Generate username if empty (can happen with OAuth if profile creation failed)
                if not request.user.username or request.user.username.strip() == '':
                    try:
                        from core.username_generator import generate_username
                        generated_username = generate_username()
                        request.user.username = generated_username
                        request.user.save(update_fields=['username'])
                        logger.warning(f"Generated missing username for user {request.user.id}: {generated_username}")
                    except Exception as e:
                        logger.error(f"Failed to generate username for user {request.user.id}: {e}")
                        return None

                # Create primary profile with username as local_name
                primary_profile = Profile.objects.create(
                    account=request.user,
                    instance=instance,
                    local_name=request.user.username,
                    display_name=f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                    is_publicly_linked=True,
                    profile_type=Profile.ProfileType.PERSONAL,
                    is_primary=True
                )
                logger.info(f"Auto-created primary profile for user {request.user.username}: {primary_profile.id}")

            # Check if there's an active profile in session
            active_profile_id = request.session.get('active_profile_id')
            if active_profile_id:
                try:
                    active_profile = Profile.objects.select_related('account').get(id=active_profile_id)

                    # Verify user can manage this profile
                    if primary_profile.can_manage_profile(active_profile):
                        logger.debug(f"Using active profile from session: {active_profile.hna}")
                        return active_profile
                    else:
                        # Clear invalid session data
                        logger.warning(f"User cannot manage profile {active_profile_id}, clearing session")
                        request.session.pop('active_profile_id', None)
                        request.session.modified = True
                except Profile.DoesNotExist:
                    # Clear invalid session data
                    logger.warning(f"Active profile {active_profile_id} not found, clearing session")
                    request.session.pop('active_profile_id', None)
                    request.session.modified = True

            # Return primary profile as default
            return primary_profile

        except Exception as e:
            logger.error(f"Error getting/creating profile for user {request.user}: {e}")
            return None


class ProfileAuth(GlobalAuth):
    """
    Authentication class that requires a valid user profile
    Useful for endpoints that need profile-specific data
    """

    def authenticate(self, request, token: str) -> Optional[Profile]:
        """
        Authenticate and return the user's primary profile
        """
        user = super().authenticate(request, token)
        if user is None:
            return None

        profile = self.get_user_profile(request)
        if profile is None:
            logger.warning(f"User {user} has no profile")
            return None

        # Attach profile to request for easy access in endpoints
        request.auth_profile = profile

        return profile


class OptionalProfileAuth(HttpBearer):
    """
    Optional authentication class that sets request.auth_profile if token is present,
    but doesn't require authentication (doesn't return 401 if missing).

    Useful for endpoints that need to behave differently for authenticated vs anonymous users.
    """

    def __call__(self, request):
        """
        Override parent __call__ to make authentication truly optional.
        HttpBearer.__call__ returns 401 if Authorization header is missing,
        but we want to allow anonymous access.
        """
        # Try to extract token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        token = None

        if auth_header.startswith('Bearer '):
            token = auth_header.replace('Bearer ', '').strip() or None

        # Authenticate (will attach request.auth_profile if token is valid)
        self.authenticate(request, token)

        # Always return truthy to prevent 401
        return True

    def authenticate(self, request, token: Optional[str]) -> Any:
        """
        Authenticate if token is present, but don't fail if missing.
        Falls back to Django session auth (for SSR requests that forward cookies).
        Always returns True to prevent 401 errors.
        """
        if token:
            try:
                # Use ProfileAuth to authenticate and get profile
                profile_auth_instance = ProfileAuth()
                profile = profile_auth_instance.authenticate(request, token)

                # Profile is already attached to request by ProfileAuth.authenticate()
                # But let's be explicit
                if profile:
                    request.auth_profile = profile
                    logger.debug(f"OptionalProfileAuth: Set auth_profile to {profile.hna}")
                else:
                    logger.debug("OptionalProfileAuth: No profile found")
            except Exception as e:
                logger.debug(f"OptionalProfileAuth failed (this is ok): {e}")

        # Fallback: try Django session auth (e.g. SSR forwarding cookies)
        if not hasattr(request, 'auth_profile') and hasattr(request, 'user') and request.user.is_authenticated:
            try:
                profile = GlobalAuth().get_user_profile(request)
                if profile:
                    request.auth_profile = profile
                    logger.debug(f"OptionalProfileAuth: Set auth_profile from session to {profile.hna}")
            except Exception as e:
                logger.debug(f"OptionalProfileAuth session fallback failed: {e}")

        # Always return something truthy to prevent 401
        # The endpoint will check hasattr(request, 'auth_profile') to know if user is authenticated
        return True


# Global authentication instances
global_auth = GlobalAuth()
profile_auth = ProfileAuth()
optional_profile_auth = OptionalProfileAuth()


def create_tokens_for_user(user: Account) -> dict:
    """
    Create JWT tokens for a user
    Returns access and refresh tokens
    """
    refresh = RefreshToken.for_user(user)
    
    return {
        'access_token': str(refresh.access_token),
        'refresh_token': str(refresh),
        'token_type': 'Bearer',
        'expires_in': refresh.access_token.lifetime.total_seconds()
    }


def get_user_from_token(token: str) -> Optional[Account]:
    """
    Get user from JWT token without Django request context
    Useful for background tasks or WebSocket authentication
    """
    try:
        from ninja_jwt.tokens import UntypedToken, AccessToken
        from ninja_jwt.exceptions import InvalidToken, TokenError

        # Validate token
        UntypedToken(token)

        # Decode token to get user ID
        access_token = AccessToken(token)
        user_id = access_token.get('user_id')

        if user_id is None:
            return None

        # Get user (use module-level User to avoid UnboundLocalError in except)
        return User.objects.get(id=user_id)

    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return None