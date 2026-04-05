"""
Helper for broadcasting poll updates via Redis pub/sub.
"""
import logging
from parahub.services.ws_publish import ws_publish

logger = logging.getLogger(__name__)


async def broadcast_poll_update(poll_id, event_type, data):
    """
    Broadcast an update to all clients connected to a poll room.

    Usage:
        await broadcast_poll_update(
            poll_id='01K9...',
            event_type='poll.vote_cast',
            data={...}
        )
    """
    ws_publish(f'poll:{poll_id}', {'type': event_type, **data})
