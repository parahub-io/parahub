"""
URL patterns for OIDC Provider
"""

from django.urls import path
from . import views
from .userinfo_view import CustomUserInfoView

app_name = 'oidc_provider'

urlpatterns = [
    # OpenID Connect Discovery
    path('.well-known/openid-configuration', views.openid_configuration, name='openid-configuration'),
    
    # JSON Web Key Set
    path('.well-known/jwks.json', views.jwks, name='jwks'),
    
    # Custom UserInfo endpoint with groups support
    path('o/userinfo/', CustomUserInfoView.as_view(), name='userinfo'),
]