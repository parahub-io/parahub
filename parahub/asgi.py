"""
ASGI config for Parahub project with WebSocket support.

This configuration supports both HTTP and WebSocket protocols
using Django Channels.
"""

import os
from django.core.asgi import get_asgi_application

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parahub.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import after Django initialization
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Import WebSocket routing and middleware
from parahub.routing import websocket_urlpatterns
from parahub.middleware.websocket import JWTAuthMiddleware

# Define the ASGI application
application = ProtocolTypeRouter({
    # HTTP protocol
    "http": django_asgi_app,
    
    # WebSocket protocol with authentication
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})