"""
Base WebSocket consumer with authentication and common functionality.
"""

import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)


async def refuse_connection(consumer, code, reason, message):
    """Turn a socket away with a code the client can actually read.

    Closing a socket that was never accepted answers the HTTP upgrade with a
    403 instead. The close code is lost that way — the browser reports 1006,
    indistinguishable from a dropped network — and the Android WebView paints
    the 403 as a full-page system error over the running app (issue #465, then
    fixed only in the agent-voice consumer). Accepting first costs one frame
    and leaves the client something to branch on, which is how a native client
    knows to retry with the token in the query string.

    Written with `send` rather than `send_json` so the plain
    `AsyncWebsocketConsumer` subclasses can use it too.

    Note the cost of accepting: the socket now really opens, so Channels
    delivers `websocket.disconnect` and runs the consumer's `disconnect()` —
    which an unaccepted socket never did. That handler runs on a `connect()`
    that returned early, so anything it touches may not exist yet. Consumers
    whose teardown assumes its own setup ran must start with

        if getattr(self, '_connection_refused', False):
            return
    """
    consumer._connection_refused = True
    await consumer.accept()
    await consumer.send(text_data=json.dumps({
        'type': 'error', 'code': reason, 'message': message,
    }))
    await consumer.close(code=code)


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

        Returns True when the socket is open and usable. A subclass that
        overrides `connect` must branch on that: after a refusal the socket is
        already closed, and anything it does next runs on a dead connection.
        """
        self.user = self.scope.get("user")
        self.profile = self.scope.get("profile")

        if not self.user or not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt on {self.scope['path']}")
            await refuse_connection(
                self, 4001, 'unauthenticated', "Sign in to open this connection")
            return False

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
        return True
    
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