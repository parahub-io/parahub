"""
Federation Registry Service.

Manages the public git registry for federation: node manifests, organizations,
profile migrations, PGP keys. Extends the existing audit-log git repo with
federation-specific directories and record types.

Architecture:
  Git = state (persistent, verifiable, append-only)
  WebSocket = signals (ephemeral, real-time inter-node notifications)
  Matrix = communication (federated, E2E encrypted)
"""
import hashlib
import json
import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import git
from django.conf import settings

logger = logging.getLogger(__name__)


class RegistryService:
    """
    Manage federation registry in Git repository.

    Extends the existing audit-log/public-git/ repo with:
      - nodes/{domain}.json      — known federation peers
      - organizations/{ulid}.json — public organization/establishment records
      - migrations/{...}.json    — profile migration records
      - node.json                — this node's manifest
    """

    def __init__(self):
        self.repo_path = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git'
        self.nodes_path = self.repo_path / 'nodes'
        self.orgs_path = self.repo_path / 'organizations'
        self.migrations_path = self.repo_path / 'migrations'
        self.verifications_path = self.repo_path / 'verifications'

        # Ensure directories exist
        self.nodes_path.mkdir(parents=True, exist_ok=True)
        self.orgs_path.mkdir(parents=True, exist_ok=True)
        self.migrations_path.mkdir(parents=True, exist_ok=True)
        self.verifications_path.mkdir(parents=True, exist_ok=True)

        self.repo = git.Repo(self.repo_path)

    # ── Node manifest ──────────────────────────────────────────────────

    def get_node_manifest(self) -> Optional[Dict]:
        """Read this node's manifest from node.json."""
        manifest_path = self.repo_path / 'node.json'
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding='utf-8'))

    def write_node_manifest(self, manifest: Dict) -> str:
        """Write node.json and commit. Returns commit hash."""
        manifest_path = self.repo_path / 'node.json'
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        self.repo.index.add([str(manifest_path)])
        commit = self.repo.index.commit(
            f"federation: update node manifest for {manifest.get('domain', 'unknown')}"
        )
        logger.info(f"Node manifest committed: {commit.hexsha[:8]}")
        return commit.hexsha

    # ── Organizations ──────────────────────────────────────────────────

    def register_organization(self, establishment, creator_signature: str = '') -> Optional[str]:
        """
        Register an organization/establishment in the federation registry.

        Args:
            establishment: geo.Establishment instance
            creator_signature: PGP signature from the creator (optional, "mandatory if capable")

        Returns:
            Git commit hash, or None on failure.
        """
        domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')

        record = {
            'type': 'organization',
            'ulid': establishment.id,
            'name': establishment.name,
            'slug': establishment.slug or '',
            'node': domain,
            'organization_type': establishment.organization_type or '',
            'category': establishment.category.name if establishment.category else '',
            'is_online': establishment.is_online,
            'created_at': establishment.created_at.isoformat(),
            'created_by': establishment.owner.hna if establishment.owner else '',
            'creator_ulid': establishment.owner_id or '',
        }

        # Location (if physical)
        if establishment.location:
            record['location'] = {
                'lat': round(establishment.location.y, 6),
                'lon': round(establishment.location.x, 6),
            }
        elif establishment.world_object and establishment.world_object.location:
            record['location'] = {
                'lat': round(establishment.world_object.location.y, 6),
                'lon': round(establishment.world_object.location.x, 6),
            }

        # Signatures
        if creator_signature:
            record['creator_signature'] = creator_signature

        # Node signature (sign the canonical JSON with node key)
        node_sig = self._sign_with_node_key(record)
        if node_sig:
            record['node_signature'] = node_sig

        # Write file
        org_file = self.orgs_path / f"{establishment.id}.json"
        org_file.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )

        # Git commit
        try:
            self.repo.index.add([str(org_file)])
            commit = self.repo.index.commit(
                f"federation: register organization {establishment.name} ({establishment.id[:8]})"
            )
            logger.info(
                f"Registered organization {establishment.id[:8]} "
                f"({establishment.name}) in registry: {commit.hexsha[:8]}"
            )
            return commit.hexsha
        except Exception as e:
            logger.error(f"Failed to commit organization {establishment.id[:8]}: {e}")
            return None

    def update_organization(self, establishment) -> Optional[str]:
        """Update an existing organization record."""
        org_file = self.orgs_path / f"{establishment.id}.json"
        if not org_file.exists():
            # First time — register instead
            return self.register_organization(establishment)

        # Read existing, update mutable fields
        existing = json.loads(org_file.read_text(encoding='utf-8'))
        existing['name'] = establishment.name
        existing['slug'] = establishment.slug or ''
        existing['organization_type'] = establishment.organization_type or ''
        existing['is_online'] = establishment.is_online
        existing['updated_at'] = datetime.now(timezone.utc).isoformat()

        if establishment.category:
            existing['category'] = establishment.category.name

        org_file.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )

        try:
            self.repo.index.add([str(org_file)])
            commit = self.repo.index.commit(
                f"federation: update organization {establishment.name} ({establishment.id[:8]})"
            )
            return commit.hexsha
        except Exception as e:
            logger.error(f"Failed to update organization {establishment.id[:8]}: {e}")
            return None

    # ── Profile Migration ──────────────────────────────────────────────

    def register_migration(
        self,
        from_hna: str,
        from_ulid: str,
        to_hna: str,
        to_ulid: str,
        from_signature: str = '',
        to_signature: str = '',
        reason: str = '',
    ) -> Optional[str]:
        """
        Register a profile migration between nodes.

        Both old and new identities should sign the migration record.
        """
        domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
        from_node = from_hna.split('@')[-1] if '@' in from_hna else domain
        to_node = to_hna.split('@')[-1] if '@' in to_hna else domain
        timestamp = datetime.now(timezone.utc)

        record = {
            'type': 'profile_migration',
            'from_hna': from_hna,
            'from_ulid': from_ulid,
            'from_node': from_node,
            'to_hna': to_hna,
            'to_ulid': to_ulid,
            'to_node': to_node,
            'timestamp': timestamp.isoformat(),
            'reason': reason,
        }

        if from_signature:
            record['from_signature'] = from_signature
        if to_signature:
            record['to_signature'] = to_signature

        # Node signature
        node_sig = self._sign_with_node_key(record)
        if node_sig:
            record['from_node_signature'] = node_sig

        # Write file
        safe_hna = from_hna.replace('@', '_at_').replace('.', '_')
        filename = f"{timestamp.strftime('%Y-%m-%d')}_{safe_hna}.json"
        migration_file = self.migrations_path / filename
        migration_file.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )

        try:
            self.repo.index.add([str(migration_file)])
            commit = self.repo.index.commit(
                f"federation: profile migration {from_hna} → {to_hna}"
            )
            logger.info(f"Registered migration {from_hna} → {to_hna}: {commit.hexsha[:8]}")
            return commit.hexsha
        except Exception as e:
            logger.error(f"Failed to commit migration {from_hna} → {to_hna}: {e}")
            return None

    # ── Peer Nodes ─────────────────────────────────────────────────────

    def register_peer(self, peer_manifest: Dict) -> Optional[str]:
        """Register a known federation peer node."""
        domain = peer_manifest.get('domain', '')
        if not domain:
            return None

        record = {
            **peer_manifest,
            'first_seen': datetime.now(timezone.utc).isoformat(),
            'trust_level': peer_manifest.get('trust_level', 'observed'),
        }

        node_file = self.nodes_path / f"{domain}.json"
        node_file.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )

        try:
            self.repo.index.add([str(node_file)])
            commit = self.repo.index.commit(
                f"federation: register peer node {domain}"
            )
            logger.info(f"Registered peer {domain}: {commit.hexsha[:8]}")
            return commit.hexsha
        except Exception as e:
            logger.error(f"Failed to register peer {domain}: {e}")
            return None

    def get_known_peers(self) -> List[Dict]:
        """List all known peer nodes from the registry."""
        peers = []
        if not self.nodes_path.exists():
            return peers
        for node_file in sorted(self.nodes_path.glob('*.json')):
            try:
                peers.append(json.loads(node_file.read_text(encoding='utf-8')))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read peer file {node_file}: {e}")
        return peers

    # ── Cross-Node Verifications ────────────────────────────────────────

    def register_verification(
        self,
        verifier_hna: str,
        verified_hna: str,
        method: str,
        signature: str = '',
    ) -> Optional[str]:
        """
        Register a cross-node WoT verification in the registry.

        This records that verifier_hna vouches for verified_hna.
        Both may be on different nodes.
        """
        domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
        timestamp = datetime.now(timezone.utc)

        record = {
            'type': 'verification',
            'verifier_hna': verifier_hna,
            'verified_hna': verified_hna,
            'method': method,
            'node': domain,
            'timestamp': timestamp.isoformat(),
        }

        if signature:
            record['verifier_signature'] = signature

        node_sig = self._sign_with_node_key(record)
        if node_sig:
            record['node_signature'] = node_sig

        # Filename: verifier_verified.json
        safe_verifier = verifier_hna.replace('@', '_at_').replace('.', '_')
        safe_verified = verified_hna.replace('@', '_at_').replace('.', '_')
        filename = f"{safe_verifier}__{safe_verified}.json"
        ver_file = self.verifications_path / filename
        ver_file.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )

        try:
            self.repo.index.add([str(ver_file)])
            commit = self.repo.index.commit(
                f"federation: verification {verifier_hna} → {verified_hna}"
            )
            logger.info(f"Registered verification {verifier_hna} → {verified_hna}: {commit.hexsha[:8]}")
            return commit.hexsha
        except Exception as e:
            logger.error(f"Failed to commit verification: {e}")
            return None

    def get_verifications_for(self, hna: str) -> List[Dict]:
        """Get all verifications where hna is the verified party (local registry)."""
        results = []
        if not self.verifications_path.exists():
            return results
        for ver_file in self.verifications_path.glob('*.json'):
            try:
                data = json.loads(ver_file.read_text(encoding='utf-8'))
                if data.get('verified_hna') == hna:
                    results.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def read_peer_verifications(self, domain: str, hna: str = '') -> List[Dict]:
        """Read verifications from a peer's fetched branch, optionally filtered by HNA."""
        results = []
        remote_name = f"peer/{domain}"
        try:
            for branch in ('master', 'main'):
                ref = f'{remote_name}/{branch}'
                try:
                    commit = self.repo.commit(ref)
                    break
                except Exception:
                    continue
            else:
                return results

            for item in commit.tree:
                if item.type == 'tree' and item.name == 'verifications':
                    for blob in item:
                        if blob.name.endswith('.json'):
                            try:
                                data = json.loads(blob.data_stream.read().decode('utf-8'))
                                if not hna or data.get('verified_hna') == hna:
                                    results.append(data)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue
        except Exception as e:
            logger.warning(f"Failed to read peer verifications for {domain}: {e}")
        return results

    # ── Node PGP Signing ──────────────────────────────────────────────

    def _sign_with_node_key(self, data: Dict) -> Optional[str]:
        """Sign canonical JSON with the node's PGP private key."""
        fingerprint = getattr(settings, 'FEDERATION_NODE_PGP_FINGERPRINT', '')
        if not fingerprint:
            return None

        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(canonical)
                f.flush()
                result = subprocess.run(
                    [
                        'gpg', '--batch', '--yes', '--armor',
                        '--local-user', fingerprint,
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
            logger.warning(f"Node PGP signing failed: {e}")
            return None

    # ── Utilities ──────────────────────────────────────────────────────

    def get_registry_stats(self) -> Dict:
        """Get stats about the registry."""
        org_count = len(list(self.orgs_path.glob('*.json'))) if self.orgs_path.exists() else 0
        peer_count = len(list(self.nodes_path.glob('*.json'))) if self.nodes_path.exists() else 0
        migration_count = len(list(self.migrations_path.glob('*.json'))) if self.migrations_path.exists() else 0
        verification_count = len(list(self.verifications_path.glob('*.json'))) if self.verifications_path.exists() else 0

        # Count connected peers (git remotes with peer/ prefix)
        connected_peers = 0
        try:
            for remote in self.repo.remotes:
                if remote.name.startswith('peer/'):
                    connected_peers += 1
        except Exception:
            pass

        return {
            'organizations': org_count,
            'peers': peer_count,
            'migrations': migration_count,
            'verifications': verification_count,
            'connected_peers': connected_peers,
            'has_manifest': (self.repo_path / 'node.json').exists(),
        }

    def read_peer_organizations(self, domain: str) -> List[Dict]:
        """Read organizations from a peer's fetched branch."""
        orgs = []
        remote_name = f"peer/{domain}"

        try:
            # Find peer's branch
            for branch in ('master', 'main'):
                ref = f'{remote_name}/{branch}'
                try:
                    commit = self.repo.commit(ref)
                    break
                except Exception:
                    continue
            else:
                return orgs

            # Read organizations/ tree
            tree = commit.tree
            for item in tree:
                if item.type == 'tree' and item.name == 'organizations':
                    for blob in item:
                        if blob.name.endswith('.json'):
                            try:
                                data = json.loads(blob.data_stream.read().decode('utf-8'))
                                orgs.append(data)
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                continue
        except Exception as e:
            logger.warning(f"Failed to read peer orgs for {domain}: {e}")

        return orgs

    def read_peer_manifest(self, domain: str) -> Optional[Dict]:
        """Read a peer's node.json from their fetched branch."""
        remote_name = f"peer/{domain}"
        try:
            for branch in ('master', 'main'):
                ref = f'{remote_name}/{branch}'
                try:
                    commit = self.repo.commit(ref)
                    break
                except Exception:
                    continue
            else:
                return None

            for item in commit.tree:
                if item.name == 'node.json':
                    return json.loads(item.data_stream.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f"Failed to read peer manifest for {domain}: {e}")

        return None

    def get_peer_sync_status(self) -> List[Dict]:
        """Get sync status for all peer git remotes."""
        statuses = []
        try:
            for remote in self.repo.remotes:
                if not remote.name.startswith('peer/'):
                    continue
                domain = remote.name.replace('peer/', '')
                status = {
                    'domain': domain,
                    'url': remote.url,
                    'last_fetch': None,
                    'head': None,
                }
                # Try to get latest commit from peer's branch
                for branch in ('master', 'main'):
                    ref = f'{remote.name}/{branch}'
                    try:
                        commit = self.repo.commit(ref)
                        status['head'] = commit.hexsha[:8]
                        status['last_fetch'] = commit.committed_datetime.isoformat()
                        break
                    except Exception:
                        continue
                statuses.append(status)
        except Exception as e:
            logger.warning(f"Failed to get peer sync status: {e}")
        return statuses
