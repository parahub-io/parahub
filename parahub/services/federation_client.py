"""
Federation WS client — outbound connections to peer nodes.

Connects to known peers' /ws/v1/federation/ endpoints,
authenticates via PGP challenge-response, and listens for
registry updates. Sends heartbeats and relays local updates.

Designed to run as a long-running daemon via management command.
"""
import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Set

import websockets

logger = logging.getLogger(__name__)


class FederationClient:
    """
    Manages outbound WS connections to federation peers.

    Usage:
        client = FederationClient(domain, fingerprint, peers)
        await client.run()  # blocks forever, reconnects on failure
    """

    HEARTBEAT_INTERVAL = 300  # 5 minutes
    RECONNECT_DELAY = 30     # seconds between reconnection attempts
    MAX_RECONNECT_DELAY = 600  # 10 min max backoff

    def __init__(self, domain: str, pgp_fingerprint: str):
        self.domain = domain
        self.pgp_fingerprint = pgp_fingerprint
        self._connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = True

    async def run(self):
        """Main loop: connect to all known peers, reconnect on failure."""
        logger.info(f"Federation client starting for {self.domain}")

        while self._running:
            peers = self._load_peers()

            for peer in peers:
                ws_url = peer.get('ws_federation', peer.get('ws_federation_url', ''))
                peer_domain = peer.get('domain', '')

                if not ws_url or not peer_domain:
                    continue
                if peer_domain == self.domain:
                    continue
                if peer_domain in self._tasks and not self._tasks[peer_domain].done():
                    continue

                # Start connection task for this peer
                self._tasks[peer_domain] = asyncio.create_task(
                    self._maintain_connection(peer_domain, ws_url, peer)
                )

            # Check every 60s for new peers
            await asyncio.sleep(60)

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        for domain, task in self._tasks.items():
            task.cancel()
        for domain, ws in self._connections.items():
            await ws.close()
        logger.info("Federation client stopped")

    async def broadcast(self, message: dict):
        """Send a message to all connected peers."""
        for domain, ws in list(self._connections.items()):
            try:
                await ws.send(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send to {domain}: {e}")

    # ── Connection Management ──────────────────────────────────────────

    async def _maintain_connection(self, peer_domain: str, ws_url: str, peer_data: dict):
        """Maintain a persistent connection to a peer, reconnecting on failure."""
        delay = self.RECONNECT_DELAY

        while self._running:
            try:
                await self._connect_and_listen(peer_domain, ws_url, peer_data)
                delay = self.RECONNECT_DELAY  # Reset on successful connection
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Connection to {peer_domain} failed: {e}. Retry in {delay}s")

            if not self._running:
                break

            await asyncio.sleep(delay)
            delay = min(delay * 2, self.MAX_RECONNECT_DELAY)

    async def _connect_and_listen(self, peer_domain: str, ws_url: str, peer_data: dict):
        """Connect to peer, authenticate, and listen for messages."""
        logger.info(f"Connecting to peer {peer_domain} at {ws_url}")

        async with websockets.connect(
            ws_url,
            additional_headers={'X-Federation-Domain': self.domain},
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            # 1. Receive challenge
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            challenge = json.loads(raw)

            if challenge.get('type') != 'challenge':
                raise ValueError(f"Expected challenge, got {challenge.get('type')}")

            nonce = challenge.get('nonce', '')

            # 2. Sign nonce with our node PGP key
            signature = self._sign_nonce(nonce)
            if not signature:
                raise ValueError("Failed to sign challenge nonce")

            await ws.send(json.dumps({
                'type': 'auth',
                'domain': self.domain,
                'signature': signature,
            }))

            # 3. Receive auth result
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            result = json.loads(raw)

            if result.get('type') != 'auth_ok':
                reason = result.get('reason', 'unknown')
                raise ValueError(f"Auth failed: {reason}")

            logger.info(f"Authenticated with peer {peer_domain}")
            self._connections[peer_domain] = ws

            # 4. Start listening + heartbeat
            try:
                await asyncio.gather(
                    self._listen(peer_domain, ws),
                    self._heartbeat_loop(peer_domain, ws),
                )
            finally:
                self._connections.pop(peer_domain, None)

    async def _listen(self, peer_domain: str, ws):
        """Listen for messages from peer."""
        async for raw in ws:
            try:
                data = json.loads(raw)
                await self._handle_message(peer_domain, data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from {peer_domain}")
            except Exception as e:
                logger.error(f"Error handling message from {peer_domain}: {e}")

    async def _heartbeat_loop(self, peer_domain: str, ws):
        """Send periodic heartbeats to peer."""
        while self._running:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            try:
                peers = [p.get('domain', '') for p in self._load_peers()]
                await ws.send(json.dumps({
                    'type': 'heartbeat',
                    'domain': self.domain,
                    'peers': peers,
                    'registry_head': self._get_registry_head(),
                }))
            except Exception as e:
                logger.warning(f"Heartbeat to {peer_domain} failed: {e}")
                break

    # ── Message Handling ───────────────────────────────────────────────

    async def _handle_message(self, peer_domain: str, data: dict):
        """Process incoming message from peer."""
        msg_type = data.get('type', '')

        if msg_type == 'registry_update':
            await self._on_registry_update(peer_domain, data)
        elif msg_type == 'profile_migration':
            await self._on_profile_migration(peer_domain, data)
        elif msg_type == 'heartbeat.response':
            logger.debug(f"Heartbeat response from {peer_domain}")
        elif msg_type == 'peer_registered':
            logger.info(f"New peer registered at {peer_domain}: {data.get('domain', '?')}")
        else:
            logger.debug(f"Unknown message type from {peer_domain}: {msg_type}")

    async def _on_registry_update(self, peer_domain: str, data: dict):
        """Handle registry update: sync git and broadcast locally."""
        commit = data.get('commit', '')
        records = data.get('records', [])

        logger.info(
            f"Registry update from {peer_domain}: "
            f"commit {commit[:8]}, {len(records)} records"
        )

        # Git fetch from peer (in thread to avoid blocking)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._git_sync_peer, peer_domain)

        # Broadcast to local users
        await loop.run_in_executor(None, self._local_broadcast, 'feed:federation', {
            'type': 'registry_update',
            'domain': peer_domain,
            'commit': commit,
            'records': records,
            'source': 'peer_sync',
        })

    async def _on_profile_migration(self, peer_domain: str, data: dict):
        """Handle profile migration notification."""
        logger.info(
            f"Profile migration via {peer_domain}: "
            f"{data.get('from', '?')} → {data.get('to', '?')}"
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._local_broadcast, 'feed:federation', {
            'type': 'profile_migration',
            **data,
            'source': 'peer_sync',
        })

    # ── Git Sync ───────────────────────────────────────────────────────

    def _git_sync_peer(self, peer_domain: str):
        """Fetch peer's registry via git and verify."""
        import git as gitlib
        from django.conf import settings

        repo_path = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git'
        repo = gitlib.Repo(repo_path)

        remote_name = f"peer/{peer_domain}"

        # Check if remote exists
        try:
            remote = repo.remote(remote_name)
        except ValueError:
            # Remote doesn't exist — look up URL from nodes/ dir
            node_file = repo_path / 'nodes' / f'{peer_domain}.json'
            if not node_file.exists():
                logger.warning(f"No node file for {peer_domain}, can't git sync")
                return

            node_data = json.loads(node_file.read_text(encoding='utf-8'))
            git_url = node_data.get('registry_git', '')
            if not git_url:
                logger.warning(f"No registry_git URL for {peer_domain}")
                return

            remote = repo.create_remote(remote_name, git_url)
            logger.info(f"Created git remote {remote_name} → {git_url}")

        # Fetch
        try:
            remote.fetch(timeout=30)
            logger.info(f"Git fetch from {peer_domain} successful")
        except Exception as e:
            logger.warning(f"Git fetch from {peer_domain} failed: {e}")

    # ── PGP Signing ───────────────────────────────────────────────────

    def _sign_nonce(self, nonce: str) -> Optional[str]:
        """Sign a nonce with this node's PGP key."""
        if not self.pgp_fingerprint:
            return None

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(nonce)
                f.flush()

                result = subprocess.run(
                    [
                        'gpg', '--batch', '--yes', '--armor',
                        '--local-user', self.pgp_fingerprint,
                        '--detach-sign', f.name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                sig_file = f.name + '.asc'
                if result.returncode == 0 and Path(sig_file).exists():
                    signature = Path(sig_file).read_text()
                    Path(sig_file).unlink(missing_ok=True)
                    Path(f.name).unlink(missing_ok=True)
                    return signature
                else:
                    logger.warning(f"GPG sign failed: {result.stderr}")
                    Path(f.name).unlink(missing_ok=True)
                    return None
        except Exception as e:
            logger.error(f"Nonce signing failed: {e}")
            return None

    # ── Utilities ──────────────────────────────────────────────────────

    def _load_peers(self):
        """Load known peers from registry git."""
        from django.conf import settings
        nodes_path = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git' / 'nodes'
        peers = []
        if not nodes_path.exists():
            return peers
        for f in nodes_path.glob('*.json'):
            try:
                peers.append(json.loads(f.read_text(encoding='utf-8')))
            except (json.JSONDecodeError, OSError):
                continue
        return peers

    def _get_registry_head(self) -> str:
        """Get HEAD commit hash."""
        try:
            from django.conf import settings
            import git as gitlib
            repo = gitlib.Repo(Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git')
            return repo.head.commit.hexsha
        except Exception:
            return ''

    def _local_broadcast(self, channel: str, data: dict):
        """Publish to local Redis for internal WS consumers."""
        try:
            from parahub.services.ws_publish import ws_publish
            ws_publish(channel, data)
        except Exception as e:
            logger.warning(f"Local broadcast failed: {e}")
