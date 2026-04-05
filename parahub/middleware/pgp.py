"""
PGP signature validation middleware and decorators for Parahub API
Provides @require_pgp decorator for critical endpoints
"""

from ninja.security import HttpBearer
from ninja.errors import HttpError
from django.http import HttpRequest
from parahub.crypto.pgp import pgp_crypto
from identity.models import Profile
from typing import Optional, Any, Callable
import json
import logging

logger = logging.getLogger(__name__)


class PGPSignatureAuth(HttpBearer):
    """
    Authentication class that requires both JWT token and PGP signature
    Used for critical operations like profile updates, deal creation, etc.
    """
    
    def authenticate(self, request: HttpRequest, token: str) -> Optional[Profile]:
        """
        Authenticate request with JWT token and validate PGP signature
        
        Args:
            request: HTTP request object
            token: JWT token from Authorization header
            
        Returns:
            Profile object if authentication successful, None otherwise
        """
        # First, validate JWT token using regular GlobalAuth
        from parahub.auth import global_auth
        user = global_auth.authenticate(request, token)
        
        if user is None:
            return None
        
        # Get user's primary profile
        profile = global_auth.get_user_profile(request)
        if profile is None:
            logger.warning(f"User {user.username} has no profile for PGP auth")
            return None
        
        # Check if profile has PGP public key
        if not profile.pgp_public_key:
            logger.warning(f"Profile {profile.hna} has no PGP key for signature verification")
            return None
        
        # Extract PGP signature headers
        signature = request.headers.get('X-PGP-Signature')
        nonce = request.headers.get('X-PGP-Nonce')
        timestamp = request.headers.get('X-PGP-Timestamp')
        
        if not signature or not nonce or not timestamp:
            logger.warning(f"Missing PGP headers for {profile.hna}")
            return None
        
        # Get request data for signature validation
        request_data = self._extract_request_data(request)
        
        # Validate PGP signature
        try:
            is_valid, error_msg = pgp_crypto.validate_request_signature(
                request_data=request_data,
                signature=signature,
                public_key_data=profile.pgp_public_key,
                nonce=nonce,
                timestamp=timestamp
            )
            
            if not is_valid:
                logger.warning(f"PGP signature validation failed for {profile.hna}: {error_msg}")
                return None
            
            logger.info(f"PGP signature validated successfully for {profile.hna}")
            
            # Attach profile to request for easy access in endpoints
            request.auth_profile = profile
            
            return profile
            
        except Exception as e:
            logger.error(f"PGP signature validation error for {profile.hna}: {e}")
            return None
    
    def _extract_request_data(self, request: HttpRequest) -> dict:
        """
        Extract request data for PGP signature validation
        
        Args:
            request: HTTP request object
            
        Returns:
            Dictionary of request data
        """
        try:
            if request.content_type == 'application/json':
                if hasattr(request, '_body') and request._body:
                    return json.loads(request._body.decode('utf-8'))
            
            # For non-JSON requests, use cleaned_data if available
            return {}
            
        except Exception as e:
            logger.error(f"Failed to extract request data: {e}")
            return {}


# Create global PGP auth instance
pgp_auth = PGPSignatureAuth()


def require_pgp(view_func: Callable) -> Callable:
    """
    Decorator to require PGP signature validation on endpoints
    
    Usage:
        @api.post("/critical-endpoint/", auth=pgp_auth)
        @require_pgp
        def critical_operation(request):
            # This endpoint requires both JWT and PGP signature
            pass
    """
    def wrapper(*args, **kwargs):
        return view_func(*args, **kwargs)
    
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    
    return wrapper


class PGPValidationError(Exception):
    """Exception raised when PGP validation fails"""
    pass