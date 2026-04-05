"""
WebSocket URL routing for Parahub.
Defines WebSocket endpoints and maps them to consumers.
"""

from django.urls import re_path
from parahub.consumers import (
    AgentVoiceConsumer, DriverConsumer, FederationConsumer, MapPresenceConsumer,
    PublicConsumer, RealtimeConsumer, SupportVoiceConsumer, TrackerConsumer,
    TransitConsumer,
)

# WebSocket URL patterns
websocket_urlpatterns = [
    # Map presence (MMORPG-style avatars) — separate due to geo-tile paradigm
    re_path(r'ws/v1/map/presence/$', MapPresenceConsumer.as_asgi()),

    # Unified real-time: notifications, object subscriptions, room updates
    re_path(r'ws/v1/realtime/$', RealtimeConsumer.as_asgi()),

    # Public broadcast: system events (new_version, maintenance) — no auth required
    re_path(r'ws/v1/public/$', PublicConsumer.as_asgi()),

    # Transit vehicle positions (public, no auth) — tile-based pub/sub
    re_path(r'ws/v1/transit/$', TransitConsumer.as_asgi()),

    # Driver Mode: driver GPS broadcasting (auth required)
    re_path(r'ws/v1/driver/$', DriverConsumer.as_asgi()),

    # GPS tracker positions (auth required, ownership-filtered)
    re_path(r'ws/v1/trackers/$', TrackerConsumer.as_asgi()),

    # Federation: inter-node communication (PGP challenge-response auth)
    re_path(r'ws/v1/federation/$', FederationConsumer.as_asgi()),

    # Agent Voice: real-time voice conversation with AI agents (staff only)
    re_path(r'ws/v1/agents/voice/(?P<agent_name>\w+)/$', AgentVoiceConsumer.as_asgi()),

    # Support Voice: public voice support bot (no auth required)
    re_path(r'ws/v1/support/voice/$', SupportVoiceConsumer.as_asgi()),
]
