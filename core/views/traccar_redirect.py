"""
Traccar SSO redirect view for seamless authentication
"""

from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def traccar_redirect(request):
    """
    Redirect authenticated Parahub users directly to Traccar
    Since Traccar is configured with openid.force=true,
    it will automatically redirect to our OIDC provider
    and then authenticate the user without showing login page
    """
    traccar_url = getattr(settings, 'TRACCAR_URL', 'https://traccar.parahub.io')
    
    # Log the redirect for monitoring
    logger.info(f"Redirecting user {request.user.username} to Traccar SSO")
    
    # Redirect to Traccar, which will handle OIDC flow automatically
    return redirect(traccar_url)