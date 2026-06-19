"""
Federation WebSocket consumer for inter-node communication.

URL: ws/v1/federation/
Auth: PGP challenge-response (node signing, not user JWT)

Protocol:
  1. Node A connects to Node B's /ws/v1/federation/
  2. Node B sends challenge: {"type": "challenge", "nonce": "<hex>"}
  3. Node A responds: {"type": "auth", "domain": "nodeA.io", "signature": "<PGP sig of nonce>"}
  4. Node B verifies signature against known node PGP key → accept/reject
  5. After auth: bidirectional registry_update, profile_migration, heartbeat messages
"""
import json
import logging
import secrets
import subprocess
import tempfile
from pathlib import Path

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .feed_pubsub import FeedPubSubManager

logger = logging.getLogger(__name__)


class FederationConsumer(AsyncJsonWebsocketConsumer):
    """Inter-node WebSocket for federation signals."""

    async def connect(self):
        self._authenticated = False
        self._peer_domain = None
        self._nonce = secrets.token_hex(32)

        await self.accept()

        # Send challenge
        await self.send_json({
            'type': 'challenge',
            'nonce': self._nonce,
        })

    async def disconnect(self, close_code):
        if self._authenticated and hasattr(self, '_feed'):
            await self._feed.unsubscribe('feed:federation', self._on_federation)
        if self._peer_domain:
            logger.info(f"Federation peer disconnected: {self._peer_domain}")

    async def receive_json(self, content):
        msg_type = content.get('type', '')

        if not self._authenticated:
            if msg_type == 'auth':
                await self._handle_auth(content)
            else:
                await self.send_json({'type': 'error', 'message': 'Authentication required'})
            return

        handler = {
            'heartbeat': self._handle_heartbeat,
            'registry_update': self._handle_registry_update,
            'profile_migration': self._handle_profile_migration,
            'cms_update': self._handle_cms_update,
        }.get(msg_type)

        if handler:
            await handler(content)
        else:
            await self.send_json({'type': 'error', 'message': f'Unknown message type: {msg_type}'})

    # ── Authentication ─────────────────────────────────────────────────

    async def _handle_auth(self, content):
        """Verify PGP challenge-response from connecting node."""
        domain = content.get('domain', '')
        signature = content.get('signature', '')

        if not domain or not signature:
            await self.send_json({'type': 'auth_failed', 'reason': 'Missing domain or signature'})
            await self.close()
            return

        # Look up the peer's PGP public key
        from django.conf import settings as s
        registry_path = Path(s.AUDIT_LOG_GIT_PATH) / 'public-git' / 'nodes' / f'{domain}.json'

        if not registry_path.exists():
            await self.send_json({'type': 'auth_failed', 'reason': f'Unknown peer: {domain}'})
            await self.close()
            return

        try:
            peer_data = json.loads(registry_path.read_text(encoding='utf-8'))
            peer_pgp_key = peer_data.get('node_pgp_public_key', '')

            if not peer_pgp_key:
                await self.send_json({'type': 'auth_failed', 'reason': 'Peer has no PGP key'})
                await self.close()
                return

            # Verify the signature of the nonce
            verified = await self._verify_pgp_signature(
                peer_pgp_key, self._nonce, signature
            )

            if not verified:
                await self.send_json({'type': 'auth_failed', 'reason': 'Invalid signature'})
                await self.close()
                return

        except Exception as e:
            logger.error(f"Federation auth error for {domain}: {e}")
            await self.send_json({'type': 'auth_failed', 'reason': 'Internal error'})
            await self.close()
            return

        # Auth successful
        self._authenticated = True
        self._peer_domain = domain
        logger.info(f"Federation peer authenticated: {domain}")

        # Subscribe to federation feed to relay updates
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()
        await self._feed.subscribe('feed:federation', self._on_federation)

        await self.send_json({
            'type': 'auth_ok',
            'domain': getattr(s, 'FEDERATION_DOMAIN', 'parahub.io'),
        })

    async def _verify_pgp_signature(self, public_key: str, nonce: str, signature: str) -> bool:
        """Verify a PGP detached signature against a public key."""
        import asyncio

        def _verify():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmpdir = Path(tmpdir)
                    gpg_home = tmpdir / '.gnupg'
                    gpg_home.mkdir(mode=0o700)

                    # Import public key
                    key_file = tmpdir / 'peer.asc'
                    key_file.write_text(public_key)
                    subprocess.run(
                        ['gpg', '--homedir', str(gpg_home), '--batch', '--import', str(key_file)],
                        capture_output=True, timeout=5,
                    )

                    # Write nonce and signature
                    nonce_file = tmpdir / 'nonce.txt'
                    nonce_file.write_text(nonce)
                    sig_file = tmpdir / 'nonce.txt.asc'
                    sig_file.write_text(signature)

                    # Verify
                    result = subprocess.run(
                        [
                            'gpg', '--homedir', str(gpg_home), '--batch',
                            '--verify', str(sig_file), str(nonce_file),
                        ],
                        capture_output=True, text=True, timeout=5,
                    )
                    return result.returncode == 0
            except Exception as e:
                logger.error(f"PGP verification failed: {e}")
                return False

        return await asyncio.get_event_loop().run_in_executor(None, _verify)

    # ── Message Handlers ───────────────────────────────────────────────

    async def _handle_heartbeat(self, content):
        """Process heartbeat from peer — update last_seen, exchange peer lists."""
        from django.conf import settings as s

        peers = content.get('peers', [])
        registry_head = content.get('registry_head', '')

        # Update last_seen in DB (async-safe)
        if self._peer_domain:
            from core.models import Instance
            from asgiref.sync import sync_to_async
            await sync_to_async(
                Instance.objects.filter(domain=self._peer_domain).update
            )(last_seen=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))

        # Respond with our own heartbeat
        await self.send_json({
            'type': 'heartbeat.response',
            'domain': getattr(s, 'FEDERATION_DOMAIN', 'parahub.io'),
            'registry_head': self._get_git_head(),
        })

    async def _handle_registry_update(self, content):
        """
        Peer notifies us of new registry commits.

        We receive the summary and can git fetch to sync.
        """
        commit = content.get('commit', '')
        records = content.get('records', [])
        domain = content.get('domain', self._peer_domain)

        logger.info(
            f"Registry update from {domain}: commit {commit[:8]}, "
            f"{len(records)} records"
        )

        # Broadcast to local users
        from parahub.services.ws_publish import ws_publish
        from asgiref.sync import sync_to_async
        await sync_to_async(ws_publish)('feed:federation', {
            'type': 'registry_update',
            'domain': domain,
            'commit': commit,
            'records': records,
        })

    async def _handle_profile_migration(self, content):
        """Handle profile migration notification from peer."""
        logger.info(
            f"Profile migration from {content.get('from', '?')} "
            f"to {content.get('to', '?')}"
        )

        from parahub.services.ws_publish import ws_publish
        from asgiref.sync import sync_to_async
        await sync_to_async(ws_publish)('feed:federation', {
            'type': 'profile_migration',
            **content,
        })

    async def _handle_cms_update(self, content):
        """
        Peer notifies us of new published CMS posts.

        We can git pull their public CMS repo to sync content.
        """
        domain = content.get('domain', self._peer_domain)
        records = content.get('records', [])

        logger.info(
            f"CMS update from {domain}: {len(records)} post(s)"
        )

        # Broadcast to local users
        from parahub.services.ws_publish import ws_publish
        from asgiref.sync import sync_to_async
        await sync_to_async(ws_publish)('feed:federation', {
            'type': 'cms_update',
            'domain': domain,
            'commit': content.get('commit', ''),
            'records': records,
        })

    # ── Federation feed relay ──────────────────────────────────────────

    async def _on_federation(self, channel: str, data: dict):
        """Relay federation events to connected peer."""
        # Don't echo back messages from this peer
        if data.get('domain') == self._peer_domain:
            return
        await self.send_json(data)

    # ── Utilities ──────────────────────────────────────────────────────

    def _get_git_head(self) -> str:
        """Get current HEAD commit hash of the registry repo."""
        try:
            from django.conf import settings as s
            import git as gitlib
            repo = gitlib.Repo(Path(s.AUDIT_LOG_GIT_PATH) / 'public-git')
            return repo.head.commit.hexsha
        except Exception:
            return ''
