"""
URL configuration for parahub project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView, RedirectView
from parahub.api import api
from . import views
from iot.views import iot_devices_view
from core.views.traccar_redirect import traccar_redirect

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('profile/', views.profile_view, name='profile'),
    path('logout/', views.direct_logout, name='direct_logout'),
    path('iot/', iot_devices_view, name='iot_devices'),
    path('traccar/', traccar_redirect, name='traccar_redirect'),
    path('admin/', admin.site.urls),
    path('api/', api.urls),
    path('accounts/', include('allauth.urls')),
    # Direct Google OAuth login (skips intermediate page)
    path('login/google/', RedirectView.as_view(url='/accounts/google/login/?process=login'), name='google_login'),
    path('login/apple/', RedirectView.as_view(url='/accounts/apple/login/?process=login'), name='apple_login'),
    path('auth/mobile-complete/', views.mobile_oauth_complete, name='mobile_oauth_complete'),
    
    # OIDC endpoints for Matrix Synapse
    path('oauth/', include('identity.urls_oidc')),
    
    # OAuth2/OIDC Provider (standard endpoints)
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
