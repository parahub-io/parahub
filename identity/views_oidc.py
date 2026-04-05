"""
OIDC Views for Matrix Synapse integration
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from oauth2_provider.decorators import protected_resource
from oauth2_provider.views import AuthorizationView, TokenView, RevokeTokenView
from django.utils.decorators import method_decorator
from django.views import View
from .oidc import ParahubOIDCProvider, OIDC_DISCOVERY


class ParahubAuthorizationView(AuthorizationView):
    """
    Custom authorization view that auto-approves for Synapse
    """
    def form_valid(self, form):
        # Auto-approve for synapse client
        client_id = self.request.GET.get('client_id')
        if client_id == 'synapse-client':
            form.cleaned_data['allow'] = True
        return super().form_valid(form)


@require_http_methods(["GET"])
def oidc_discovery(request):
    """
    OpenID Connect Discovery endpoint
    Returns metadata about the OIDC provider
    """
    return JsonResponse(OIDC_DISCOVERY)


@require_http_methods(["GET"])
def jwks_endpoint(request):
    """
    JSON Web Key Set endpoint
    Returns the public keys used to verify tokens
    """
    # For now, return empty set as we're using HS256 (symmetric)
    # In production, should use RS256 with proper key management
    jwks = {
        "keys": []
    }
    return JsonResponse(jwks)


@protected_resource(scopes=['openid'])
@require_http_methods(["GET", "POST"])
def userinfo_endpoint(request):
    """
    UserInfo endpoint - returns claims about the authenticated user
    """
    user = request.user
    scope = request.GET.get('scope', 'openid profile email')
    
    claims = ParahubOIDCProvider.get_userinfo_claims(user, scope)
    
    return JsonResponse(claims)


@method_decorator(csrf_exempt, name='dispatch')
class ParahubTokenView(TokenView):
    """
    Custom token view with CORS support for Synapse
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        # Add CORS headers for Synapse
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        
        # If successful, add custom claims to ID token
        if response.status_code == 200:
            try:
                data = json.loads(response.content)
                if 'access_token' in data:
                    # Get user from access token
                    from oauth2_provider.models import AccessToken
                    try:
                        token = AccessToken.objects.get(token=data['access_token'])
                        user = token.user
                        
                        # Add custom claims
                        claims = ParahubOIDCProvider.get_oidc_claims(user)
                        data['id_token_claims'] = claims
                        
                        response.content = json.dumps(data)
                    except AccessToken.DoesNotExist:
                        pass
            except json.JSONDecodeError:
                pass
        
        return response