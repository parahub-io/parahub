"""
OIDC URL configuration for Matrix Synapse integration
"""

from django.urls import path
from oauth2_provider.views import RevokeTokenView
from .views_oidc import (
    ParahubAuthorizationView,
    ParahubTokenView,
    oidc_discovery,
    jwks_endpoint,
    userinfo_endpoint,
)

app_name = 'oidc'

urlpatterns = [
    # OIDC Discovery
    path('.well-known/openid-configuration', oidc_discovery, name='oidc-discovery'),
    path('.well-known/jwks.json', jwks_endpoint, name='jwks'),
    
    # OAuth2/OIDC endpoints
    path('authorize/', ParahubAuthorizationView.as_view(), name='authorize'),
    path('token/', ParahubTokenView.as_view(), name='token'),
    path('revoke/', RevokeTokenView.as_view(), name='revoke'),
    path('userinfo/', userinfo_endpoint, name='userinfo'),
]