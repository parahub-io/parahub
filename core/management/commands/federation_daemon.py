"""
Long-running federation daemon.

Connects to known peer nodes via WebSocket, authenticates with PGP,
listens for registry updates, and sends periodic heartbeats.

Also subscribes to local feed:federation Redis channel to relay
local updates to connected peers.

Usage:
    python manage.py federation_daemon

Systemd:
    parahub-federation.service (Type=simple, Restart=always)
"""
import asyncio
import json
import logging
import signal

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run federation daemon: connect to peers, sync registries, relay updates'

    def handle(self, *args, **options):
        if not getattr(settings, 'FEDERATION_ENABLED', False):
            self.stderr.write("FEDERATION_ENABLED is False. Set it in .env to enable.")
            return

        domain = getattr(settings, 'FEDERATION_DOMAIN', '')
        fingerprint = getattr(settings, 'FEDERATION_NODE_PGP_FINGERPRINT', '')

        if not domain:
            self.stderr.write("FEDERATION_DOMAIN not set.")
            return

        if not fingerprint:
            self.stderr.write(
                "FEDERATION_NODE_PGP_FINGERPRINT not set. "
                "Run: python manage.py init_federation_node"
            )
            return

        self.stdout.write(f"Starting federation daemon for {domain}")
        self.stdout.write(f"PGP fingerprint: {fingerprint[:16]}...")

        from parahub.services.federation_client import FederationClient

        client = FederationClient(domain, fingerprint)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Graceful shutdown
        def shutdown():
            self.stdout.write("Shutting down federation daemon...")
            loop.create_task(client.stop())

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown)

        try:
            loop.run_until_complete(asyncio.gather(
                client.run(),
                self._relay_local_updates(client),
            ))
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()
            self.stdout.write("Federation daemon stopped.")

    async def _relay_local_updates(self, client):
        """
        Subscribe to local feed:federation Redis channel and relay
        updates to connected peers.
        """
        import redis.asyncio as aioredis

        r = aioredis.Redis(
            host=getattr(settings, 'REDIS_HOST', 'localhost'),
            port=getattr(settings, 'REDIS_PORT', 6379),
        )

        pubsub = r.pubsub()
        await pubsub.subscribe('feed:federation')

        domain = getattr(settings, 'FEDERATION_DOMAIN', '')

        try:
            async for message in pubsub.listen():
                if message['type'] != 'message':
                    continue

                try:
                    data = json.loads(message['data'])
                except (json.JSONDecodeError, TypeError):
                    continue

                # Only relay our own updates (not echoes from peers)
                if data.get('domain') == domain and data.get('source') != 'peer_sync':
                    await client.broadcast(data)

        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe('feed:federation')
            await r.close()
