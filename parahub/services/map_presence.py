"""
Map Presence Service - Redis-based viewport position tracking

Architecture:
- Redis GEOHASH for spatial indexing (find users viewing nearby locations)
- TTL-based cleanup (inactive users auto-removed after 5 minutes)
- Per-user state: lat, lon, zoom, avatar_type, avatar_state, speech_bubble

Usage:
    from parahub.services.map_presence import MapPresenceService

    # Update user's viewport position
    MapPresenceService.set_position(
        profile_id='01K7M4MDWPFZ5WQ4A5GRPPVZR2',
        lat=38.7223,
        lon=-9.1393,
        zoom=14,
        avatar_type='p1',
        avatar_state='idle',
        speech_bubble='Hello!'
    )

    # Get users viewing nearby locations (within 5km at zoom 14)
    nearby = MapPresenceService.get_nearby_users(lat=38.7223, lon=-9.1393, radius_km=5)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import redis
from django.conf import settings

logger = logging.getLogger(__name__)


class MapPresenceService:
    """
    Map presence service using Redis GEOHASH for spatial queries
    """

    # Redis keys
    POSITIONS_KEY = 'map_presence:positions'  # GEOHASH sorted set (lat/lon)
    USER_DATA_KEY_PREFIX = 'map_presence:user:'  # Hash with user details

    # TTL for inactive users (5 minutes)
    USER_TTL = 300

    # Avatar types (LPC spritesheets p0-p4)
    AVATAR_TYPES = [
        'p0',  # Character variant 0
        'p1',  # Character variant 1 (default)
        'p2',  # Character variant 2
        'p3',  # Character variant 3
        'p4',  # Character variant 4
    ]

    # Avatar states (LPC animations)
    AVATAR_STATES = [
        'idle',     # Standing still
        'walking',  # Moving viewport
        'jumping',  # Jump action
        'sitting',  # Sit action (toggle)
        'emoting',  # Wave/emote action
    ]

    # Shared Redis connection
    _redis_client = None

    @classmethod
    def _get_redis(cls):
        """Get or create Redis connection"""
        if cls._redis_client is None:
            # Parse Redis URL from settings
            redis_url = settings.CACHES['default']['LOCATION']
            cls._redis_client = redis.from_url(redis_url, decode_responses=True)
        return cls._redis_client

    @classmethod
    def _get_user_data_key(cls, profile_id: str) -> str:
        """Get Redis key for user data"""
        return f"{cls.USER_DATA_KEY_PREFIX}{profile_id}"

    @classmethod
    def set_position(
        cls,
        profile_id: str,
        lat: float,
        lon: float,
        zoom: int,
        avatar_type: str = 'p1',
        avatar_state: str = 'idle',
        speech_bubble: Optional[str] = None,
        profile_hna: Optional[str] = None,
        profile_name: Optional[str] = None,
    ) -> bool:
        """
        Update user's viewport position and state

        Args:
            profile_id: Profile ULID
            lat: Latitude of viewport center
            lon: Longitude of viewport center
            zoom: Map zoom level
            avatar_type: Avatar appearance
            avatar_state: Current animation state
            speech_bubble: Text to display (optional)
            profile_hna: Human-readable name (cached for performance)
            profile_name: Display name (cached for performance)

        Returns:
            True if successful
        """
        try:
            r = cls._get_redis()

            # Validate inputs
            if avatar_type not in cls.AVATAR_TYPES:
                avatar_type = 'p1'
            if avatar_state not in cls.AVATAR_STATES:
                avatar_state = 'idle'

            # Add to GEOHASH (values must be a sequence: [lon, lat, member])
            r.geoadd(cls.POSITIONS_KEY, values=[lon, lat, profile_id])

            # Store user data
            user_data_key = cls._get_user_data_key(profile_id)
            user_data = {
                'profile_id': profile_id,
                'lat': lat,
                'lon': lon,
                'zoom': zoom,
                'avatar_type': avatar_type,
                'avatar_state': avatar_state,
                'speech_bubble': speech_bubble or '',
                'profile_hna': profile_hna or '',
                'profile_name': profile_name or '',
                'last_update': datetime.now(timezone.utc).isoformat(),
            }

            r.hset(user_data_key, mapping=user_data)
            r.expire(user_data_key, cls.USER_TTL)

            logger.debug(f"Updated map presence for {profile_id} at ({lat}, {lon})")
            return True

        except Exception as e:
            logger.error(f"Failed to set map presence: {e}")
            return False

    @classmethod
    def get_nearby_users(
        cls,
        lat: float,
        lon: float,
        radius_km: float = 5.0,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get users viewing locations near the given coordinates

        Args:
            lat: Center latitude
            lon: Center longitude
            radius_km: Search radius in kilometers
            limit: Max number of users to return

        Returns:
            List of user presence data dicts
        """
        try:
            r = cls._get_redis()

            # GEOSEARCH query; format: [[member, distance], ...]
            nearby_members = r.geosearch(
                cls.POSITIONS_KEY,
                longitude=lon,
                latitude=lat,
                radius=radius_km,
                unit='km',
                withdist=True,
                count=limit,
            )

            if not nearby_members:
                return []

            # Fetch all user hashes in one round-trip
            pipe = r.pipeline(transaction=False)
            for member, _distance in nearby_members:
                pipe.hgetall(cls._get_user_data_key(member))
            user_hashes = pipe.execute()

            users = []
            stale_members = []

            for (member, distance), user_data in zip(nearby_members, user_hashes):
                if not user_data:
                    # Hash expired (TTL) but member survived in the zset — clean up lazily
                    stale_members.append(member)
                    continue
                user_data['distance_km'] = round(float(distance), 2)
                user_data['lat'] = float(user_data.get('lat', 0))
                user_data['lon'] = float(user_data.get('lon', 0))
                users.append(user_data)

            if stale_members:
                r.zrem(cls.POSITIONS_KEY, *stale_members)

            return users

        except Exception as e:
            logger.error(f"Failed to get nearby users: {e}")
            return []

    @classmethod
    def get_user_data(cls, profile_id: str) -> Optional[Dict]:
        """
        Get user presence data

        Returns:
            User data dict or None if not found
        """
        try:
            r = cls._get_redis()
            user_data_key = cls._get_user_data_key(profile_id)

            data = r.hgetall(user_data_key)
            return data or None

        except Exception as e:
            logger.error(f"Failed to get user data: {e}")
            return None

    @classmethod
    def remove_user(cls, profile_id: str) -> bool:
        """
        Remove user from map presence (on disconnect or disable)

        Returns:
            True if successful
        """
        try:
            r = cls._get_redis()

            # Remove from GEOHASH
            r.zrem(cls.POSITIONS_KEY, profile_id)

            # Delete user data
            user_data_key = cls._get_user_data_key(profile_id)
            r.delete(user_data_key)

            logger.debug(f"Removed map presence for {profile_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove user: {e}")
            return False

    @classmethod
    def touch(cls, profile_id: str) -> bool:
        """
        Refresh presence TTL for a connected-but-idle user (heartbeat).

        Returns:
            True if the user's presence data exists and TTL was refreshed
        """
        try:
            r = cls._get_redis()
            return bool(r.expire(cls._get_user_data_key(profile_id), cls.USER_TTL))
        except Exception as e:
            logger.error(f"Failed to touch presence: {e}")
            return False

    @classmethod
    def set_avatar_state(
        cls,
        profile_id: str,
        avatar_state: str
    ) -> bool:
        """
        Update only the avatar state (for animations)

        Args:
            profile_id: Profile ULID
            avatar_state: New state (idle, walking, jumping, sitting, emoting)

        Returns:
            True if successful
        """
        try:
            if avatar_state not in cls.AVATAR_STATES:
                return False

            r = cls._get_redis()
            user_data_key = cls._get_user_data_key(profile_id)

            # Update only state field
            r.hset(user_data_key, 'avatar_state', avatar_state)
            r.hset(user_data_key, 'last_update', datetime.now(timezone.utc).isoformat())
            r.expire(user_data_key, cls.USER_TTL)

            return True

        except Exception as e:
            logger.error(f"Failed to set avatar state: {e}")
            return False

    @classmethod
    def set_speech_bubble(
        cls,
        profile_id: str,
        speech_bubble: str
    ) -> bool:
        """
        Update speech bubble text

        Args:
            profile_id: Profile ULID
            speech_bubble: Text to display (max 200 chars)

        Returns:
            True if successful
        """
        try:
            r = cls._get_redis()
            user_data_key = cls._get_user_data_key(profile_id)

            # Truncate to 200 chars
            speech_bubble = speech_bubble[:200] if speech_bubble else ''

            # Update speech bubble field
            r.hset(user_data_key, 'speech_bubble', speech_bubble)
            r.hset(user_data_key, 'last_update', datetime.now(timezone.utc).isoformat())
            r.expire(user_data_key, cls.USER_TTL)

            return True

        except Exception as e:
            logger.error(f"Failed to set speech bubble: {e}")
            return False

    @classmethod
    def get_active_users_count(cls) -> int:
        """
        Get count of active users on map

        Returns:
            Number of active users
        """
        try:
            r = cls._get_redis()
            return r.zcard(cls.POSITIONS_KEY)
        except Exception as e:
            logger.error(f"Failed to get active users count: {e}")
            return 0
