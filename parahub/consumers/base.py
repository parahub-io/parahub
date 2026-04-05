"""
Base WebSocket consumer with authentication and common functionality.
"""

import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)


class AuthenticatedJsonWebsocketConsumer(AsyncJsonWebsocketConsumer):
    """
    Base consumer with JWT authentication and JSON message handling.
    
    Features:
    - Automatic authentication check on connect
    - JSON encoding/decoding with Django serializers
    - Heartbeat support for connection monitoring
    - Error handling and logging
    """
    
    async def connect(self):
        """
        Handle WebSocket connection.
        Rejects connection if user is not authenticated.
        """
        self.user = self.scope.get("user")
        self.profile = self.scope.get("profile")
        
        if not self.user or not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt on {self.scope['path']}")
            await self.close(code=4001)  # Custom close code for authentication failure
            return
        
        # Set user-specific channel name
        self.user_channel_name = f"user_{self.user.id}"
        
        # Accept connection
        await self.accept()
        
        # Send connection confirmation
        await self.send_json({
            "type": "connection.established",
            "message": "WebSocket connection established",
            "user": {
                "id": self.user.id,
                "username": self.user.username,
                "profile_id": self.profile.id if self.profile else None,
            }
        })
        
        logger.info(f"WebSocket connected: {self.user.username} on {self.scope['path']}")
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        Override in subclasses to clean up resources.
        """
        if hasattr(self, 'user') and self.user.is_authenticated:
            logger.info(f"WebSocket disconnected: {self.user.username} (code: {close_code})")
    
    async def receive_json(self, content):
        """
        Handle incoming JSON messages.
        Routes messages based on 'type' field.
        """
        message_type = content.get("type")
        
        if not message_type:
            await self.send_error("Message type is required")
            return
        
        # Handle heartbeat
        if message_type == "heartbeat":
            await self.handle_heartbeat(content)
            return
        
        # Route to handler method based on message type
        handler_name = f"handle_{message_type.replace('.', '_')}"
        handler = getattr(self, handler_name, None)
        
        if handler:
            try:
                await handler(content)
            except Exception as e:
                logger.error(f"Error handling message {message_type}: {e}")
                await self.send_error(f"Error processing message: {str(e)}")
        else:
            await self.send_error(f"Unknown message type: {message_type}")
    
    async def handle_heartbeat(self, message):
        """
        Respond to heartbeat messages to keep connection alive.
        """
        await self.send_json({
            "type": "heartbeat.response",
            "timestamp": message.get("timestamp"),
        })
    
    async def send_error(self, error_message, error_code=None):
        """
        Send error message to client.
        """
        await self.send_json({
            "type": "error",
            "message": error_message,
            "code": error_code,
        })
    
    async def send_notification(self, title, message, notification_type="info", data=None):
        """
        Send notification to client.
        
        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification (info, success, warning, error)
            data: Additional data to include
        """
        await self.send_json({
            "type": "notification",
            "title": title,
            "message": message,
            "notification_type": notification_type,
            "data": data or {},
        })
    
    # Utility methods for database access
    
    @database_sync_to_async
    def get_user_profile(self):
        """Get the user's profile from database."""
        from identity.models import Profile
        try:
            return Profile.objects.get(account=self.user)
        except Profile.DoesNotExist:
            return None
    
    @database_sync_to_async
    def check_user_permission(self, permission_name):
        """Check if user has a specific permission."""
        return self.user.has_perm(permission_name)