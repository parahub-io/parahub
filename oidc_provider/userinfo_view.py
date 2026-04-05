"""
Custom UserInfo endpoint for OIDC with groups support
"""
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from oauth2_provider.views.mixins import OAuthLibMixin
from oauth2_provider.views.generic import ProtectedResourceView
from .settings import oidc_userinfo
import logging

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class CustomUserInfoView(ProtectedResourceView):
    """
    Custom UserInfo endpoint that properly returns groups
    """
    required_scopes = ['openid']
    
    def get(self, request, *args, **kwargs):
        return self._handle_userinfo(request)
    
    def post(self, request, *args, **kwargs):
        return self._handle_userinfo(request)
    
    def _handle_userinfo(self, request):
        """
        Generate and return userinfo response with groups
        """
        # The ProtectedResourceView already validates the token and sets request.resource_owner
        user = request.resource_owner
        
        if not user:
            return JsonResponse({'error': 'invalid_token'}, status=401)
        
        # Generate claims using our custom function
        claims = {}
        try:
            claims = oidc_userinfo(claims, user)
            logger.info(f"Returning userinfo for {user.username}: {claims.keys()}")
        except Exception as e:
            logger.error(f"Error generating userinfo: {e}", exc_info=True)
            # Fallback
            claims = {
                'sub': getattr(user, 'cri', str(user.id)),
                'email': user.email,
                'preferred_username': user.username,
                'groups': ['parahub-users']
            }
        
        return JsonResponse(claims)