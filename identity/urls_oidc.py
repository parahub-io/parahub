"""
OIDC URL configuration for Matrix Synapse integration
"""

from django.urls import path
from oauth2_provider.views import RevokeTokenView
from oauth2_provider.views.oidc import JwksInfoView
from .views_oidc import (
    ParahubAuthorizationView,
    ParahubTokenView,
    oidc_discovery,
    userinfo_endpoint,
)

app_name = 'oidc'

urlpatterns = [
    # OIDC Discovery
    path('.well-known/openid-configuration', oidc_discovery, name='oidc-discovery'),
    # Same keyset as /o/.well-known/jwks.json — the key that actually signs
    # id_tokens (OIDC_RSA_PRIVATE_KEY). A hand-rolled endpoint here once
    # returned an empty keyset, breaking discovery-based clients.
    path('.well-known/jwks.json', JwksInfoView.as_view(), name='jwks'),
    
    # OAuth2/OIDC endpoints
    path('authorize/', ParahubAuthorizationView.as_view(), name='authorize'),
    path('token/', ParahubTokenView.as_view(), name='token'),
    path('revoke/', RevokeTokenView.as_view(), name='revoke'),
    path('userinfo/', userinfo_endpoint, name='userinfo'),
]