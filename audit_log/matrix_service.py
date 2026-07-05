"""
Matrix service for creating E2E encrypted rooms and sending proof backups.
"""
import httpx
import logging
from typing import List, Optional, Dict, Any
from django.conf import settings
from parahub.endpoints.matrix_auth import get_matrix_user_id

logger = logging.getLogger(__name__)


class MatrixService:
    """
    Service for Matrix Admin API operations.
    Used for creating E2E encrypted rooms for dispute resolution and proof backup.
    """

    def __init__(self):
        self.homeserver_url = "http://localhost:8008"  # Internal Synapse URL
        self.admin_token = settings.SYNAPSE_ADMIN_TOKEN
        self.server_name = "parahub.io"

    async def create_encrypted_room(
        self,
        creator_profile,
        participants: List,  # List of Profile objects
        name: str,
        topic: str = "",
        purpose: str = "dispute"
    ) -> Optional[str]:
        """
        Create E2E encrypted Matrix room for dispute resolution or proof backup.

        Args:
            creator_profile: Profile who creates the room
            participants: List of Profile objects to invite
            name: Room name
            topic: Room topic
            purpose: 'dispute' or 'proof_backup'

        Returns:
            Room ID (!xyz:parahub.io) or None if failed
        """
        try:
            # Create room using Admin API
            # Matrix user ID from profile's local_name (human-readable)
            creator_mxid = get_matrix_user_id(creator_profile.account_id)

            # Prepare invites (using account_id, deduplicated)
            invites = []
            seen_accounts = {creator_profile.account_id}
            for participant in participants:
                if participant.account_id not in seen_accounts:
                    invites.append(get_matrix_user_id(participant.account_id))
                    seen_accounts.add(participant.account_id)

            # Room creation request
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.homeserver_url}/_synapse/admin/v1/send_server_notice",
                    headers={
                        "Authorization": f"Bearer {self.admin_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "user_id": creator_mxid,
                        "content": {
                            "msgtype": "m.text",
                            "body": f"Room created for {purpose}: {name}"
                        }
                    },
                    timeout=10.0
                )

                # Alternative: Use client API with user impersonation
                # Create room with E2E encryption
                admin_mxid = "@parahub_sso_admin:parahub.io"

                room_response = await client.post(
                    f"{self.homeserver_url}/_matrix/client/r0/createRoom",
                    headers={
                        "Authorization": f"Bearer {self.admin_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "name": name,
                        "topic": topic,
                        "preset": "private_chat",  # Private, invite-only
                        "invite": invites,
                        "initial_state": [
                            {
                                "type": "m.room.encryption",
                                "state_key": "",
                                "content": {
                                    "algorithm": "m.megolm.v1.aes-sha2"
                                }
                            }
                        ],
                        "power_level_content_override": {
                            "users": {
                                admin_mxid: 100,  # Admin who creates the room
                                creator_mxid: 100,
                                **{invite: 50 for invite in invites}  # All participants can moderate
                            }
                        }
                    },
                    timeout=10.0
                )

                if room_response.status_code == 200:
                    room_data = room_response.json()
                    room_id = room_data.get('room_id')
                    logger.info(f"Created Matrix room {room_id} for {purpose}")
                    return room_id
                else:
                    logger.error(f"Failed to create Matrix room: {room_response.text}")
                    return None

        except Exception as e:
            logger.error(f"Error creating Matrix room: {e}")
            return None

    async def send_message(
        self,
        room_id: str,
        content: Dict[str, Any],
        sender_profile=None
    ) -> Optional[str]:
        """
        Send message to Matrix room.

        Args:
            room_id: Matrix room ID
            content: Message content (dict with msgtype, body, etc)
            sender_profile: Profile sending the message (for impersonation)

        Returns:
            Event ID or None if failed
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/send/m.room.message",
                    headers={
                        "Authorization": f"Bearer {self.admin_token}",
                        "Content-Type": "application/json"
                    },
                    json=content,
                    timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('event_id')
                else:
                    logger.error(f"Failed to send Matrix message: {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Error sending Matrix message: {e}")
            return None

    async def pin_message(self, room_id: str, event_id: str) -> bool:
        """
        Pin a message in a room (for important proof messages).

        Args:
            room_id: Matrix room ID
            event_id: Event ID to pin

        Returns:
            True if successful
        """
        try:
            async with httpx.AsyncClient() as client:
                # Get current pinned events
                state_response = await client.get(
                    f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/state/m.room.pinned_events/",
                    headers={
                        "Authorization": f"Bearer {self.admin_token}"
                    },
                    timeout=5.0
                )

                pinned = []
                if state_response.status_code == 200:
                    pinned = state_response.json().get('pinned', [])

                # Add new event to pinned
                if event_id not in pinned:
                    pinned.append(event_id)

                # Update pinned events
                response = await client.put(
                    f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/state/m.room.pinned_events/",
                    headers={
                        "Authorization": f"Bearer {self.admin_token}",
                        "Content-Type": "application/json"
                    },
                    json={"pinned": pinned},
                    timeout=5.0
                )

                return response.status_code == 200

        except Exception as e:
            logger.error(f"Error pinning Matrix message: {e}")
            return False

    async def ensure_user_exists(self, user_mxid: str, display_name: str = "", ulid: str = "") -> bool:
        """
        Ensure Matrix user exists, create if not with deterministic password.

        Args:
            user_mxid: Full Matrix user ID (@user:server)
            display_name: Display name for the user
            ulid: User's ULID for generating password

        Returns:
            True if user exists or was created
        """
        try:
            async with httpx.AsyncClient() as client:
                # Try to get user
                get_response = await client.get(
                    f"{self.homeserver_url}/_synapse/admin/v2/users/{user_mxid}",
                    headers={"Authorization": f"Bearer {self.admin_token}"},
                    timeout=5.0
                )

                if get_response.status_code == 200:
                    return True  # User exists

                # User doesn't exist, create it with deterministic password
                # This ensures SSO login will work with same user
                import hashlib
                SYNAPSE_SHARED_SECRET = settings.SYNAPSE_REGISTRATION_SHARED_SECRET
                password = hashlib.sha256(f"{ulid}:{SYNAPSE_SHARED_SECRET}".encode()).hexdigest()

                create_response = await client.put(
                    f"{self.homeserver_url}/_synapse/admin/v2/users/{user_mxid}",
                    headers={
                        "Authorization": f"Bearer {self.admin_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "displayname": display_name or user_mxid.split('@')[1].split(':')[0],
                        "password": password,  # Set deterministic password
                    },
                    timeout=10.0
                )

                if create_response.status_code in [200, 201]:
                    logger.info(f"Created Matrix user {user_mxid} with password")
                    return True
                else:
                    logger.error(f"Failed to create Matrix user {user_mxid}: {create_response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error ensuring Matrix user exists: {e}")
            return False

    async def invite_and_auto_join_users(self, room_id: str, participants: List, inviter_mxid: str) -> bool:
        """
        Invite users to a room and auto-accept invites using Admin API.
        Creates users if they don't exist.

        Args:
            room_id: Matrix room ID
            participants: List of Profile objects to invite
            inviter_mxid: Matrix user ID of the inviter (admin)

        Returns:
            True if all successful
        """
        try:
            async with httpx.AsyncClient() as client:
                # Deduplicate by account_id (multiple profiles may share same account)
                seen_accounts = set()

                for participant in participants:
                    # Skip if already processed this account
                    if participant.account_id in seen_accounts:
                        continue
                    seen_accounts.add(participant.account_id)

                    # Matrix user ID from profile's local_name (human-readable)
                    # One Matrix account per Parahub account, not per profile
                    user_mxid = get_matrix_user_id(participant.account_id)
                    display_name = (participant.display_name if participant.name_public else '') or participant.hna

                    # Ensure user exists first (with deterministic password using account_id)
                    if not await self.ensure_user_exists(user_mxid, display_name, participant.account_id):
                        logger.warning(f"Could not ensure user {user_mxid} exists, skipping")
                        continue

                    # Auto-join user to room via Admin API (no invite needed)
                    join_response = await client.post(
                        f"{self.homeserver_url}/_synapse/admin/v1/join/{room_id}",
                        headers={
                            "Authorization": f"Bearer {self.admin_token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "user_id": user_mxid
                        },
                        timeout=10.0
                    )

                    if join_response.status_code == 200:
                        logger.info(f"Auto-joined {user_mxid} to room {room_id}")
                    else:
                        logger.warning(f"Failed to auto-join {user_mxid} to room {room_id}: {join_response.text}")

                return True

        except Exception as e:
            logger.error(f"Error auto-joining users to Matrix room: {e}")
            return False

    async def invite_users(self, room_id: str, participants: List, inviter_mxid: str) -> bool:
        """
        Invite users to a room using Matrix Client API.
        Creates users if they don't exist.

        Args:
            room_id: Matrix room ID
            participants: List of Profile objects to invite
            inviter_mxid: Matrix user ID of the inviter (admin)

        Returns:
            True if all successful
        """
        try:
            async with httpx.AsyncClient() as client:
                for participant in participants:
                    # Matrix user ID from profile's local_name (human-readable)
                    user_mxid = get_matrix_user_id(participant.account_id)
                    display_name = (participant.display_name if participant.name_public else '') or participant.hna

                    # Ensure user exists first
                    if not await self.ensure_user_exists(user_mxid, display_name):
                        logger.warning(f"Could not ensure user {user_mxid} exists, skipping invite")
                        continue

                    # Invite user to room using admin token
                    response = await client.post(
                        f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/invite",
                        headers={
                            "Authorization": f"Bearer {self.admin_token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "user_id": user_mxid
                        },
                        timeout=10.0
                    )

                    if response.status_code == 200:
                        logger.info(f"Invited {user_mxid} to room {room_id}")
                    else:
                        logger.warning(f"Failed to invite {user_mxid} to room {room_id}: {response.text}")

                return True

        except Exception as e:
            logger.error(f"Error inviting users to Matrix room: {e}")
            return False

    async def send_to_system_room(self, profile, content: Dict[str, Any]) -> Optional[str]:
        """
        Send message to user's personal system notification room.

        Creates room if it doesn't exist.

        Args:
            profile: Profile to send to
            content: Message content

        Returns:
            Event ID or None if failed
        """
        from .models import MatrixRoomReference
        from django.contrib.contenttypes.models import ContentType

        # Check if system room exists
        content_type = ContentType.objects.get_for_model(profile)
        room_ref = MatrixRoomReference.objects.filter(
            content_type=content_type,
            object_id=profile.id,
            purpose='system_notifications'
        ).first()

        if not room_ref:
            # Create system room
            room_id = await self.create_encrypted_room(
                creator_profile=profile,
                participants=[profile],
                name=f"Parahub System Notifications ({profile.name})",
                topic="Система уведомлений Parahub",
                purpose='system_notifications'
            )

            if room_id:
                room_ref = MatrixRoomReference.objects.create(
                    content_type=content_type,
                    object_id=profile.id,
                    room_id=room_id,
                    purpose='system_notifications'
                )
            else:
                return None

        # Send message
        return await self.send_message(room_ref.room_id, content, sender_profile=profile)


# Singleton instance
matrix_service = MatrixService()
