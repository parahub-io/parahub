"""
One-shot federation sync: git fetch from all known peers.

Usage:
    python manage.py federation_sync [--peer domain]
"""
import json
import logging
from pathlib import Path

import git as gitlib
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync federation registry from known peers via git fetch'

    def add_arguments(self, parser):
        parser.add_argument(
            '--peer', type=str, default='',
            help='Sync only from specific peer domain',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be synced without fetching',
        )

    def handle(self, *args, **options):
        repo_path = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git'
        nodes_path = repo_path / 'nodes'

        if not nodes_path.exists():
            self.stdout.write("No peers directory. Run init_federation_node first.")
            return

        # Load peers
        peers = []
        target_peer = options['peer']

        for node_file in sorted(nodes_path.glob('*.json')):
            try:
                data = json.loads(node_file.read_text(encoding='utf-8'))
                domain = data.get('domain', '')
                if target_peer and domain != target_peer:
                    continue
                if not domain or domain == getattr(settings, 'FEDERATION_DOMAIN', ''):
                    continue
                peers.append(data)
            except (json.JSONDecodeError, OSError):
                continue

        if not peers:
            self.stdout.write("No peers to sync from.")
            return

        repo = gitlib.Repo(repo_path)

        for peer in peers:
            domain = peer['domain']
            git_url = peer.get('registry_git', '')

            if not git_url:
                self.stdout.write(f"  {domain}: no registry_git URL, skipping")
                continue

            if options['dry_run']:
                self.stdout.write(f"  Would fetch from {domain} ({git_url})")
                continue

            remote_name = f"peer/{domain}"

            # Ensure remote exists
            try:
                remote = repo.remote(remote_name)
            except ValueError:
                remote = repo.create_remote(remote_name, git_url)
                self.stdout.write(f"  Created remote {remote_name} → {git_url}")

            # Fetch
            try:
                fetch_info = remote.fetch(timeout=30)
                ref_count = len(fetch_info)
                self.stdout.write(self.style.SUCCESS(
                    f"  {domain}: fetched {ref_count} ref(s)"
                ))

                # Show what's available on the peer's branch
                self._show_peer_records(repo, remote_name, domain)

            except Exception as e:
                self.stderr.write(f"  {domain}: fetch failed — {e}")

    def _show_peer_records(self, repo, remote_name: str, domain: str):
        """Show records available from a peer's fetched branch."""
        try:
            # Try to read their branch (usually master or main)
            for branch_name in ('master', 'main'):
                ref = f'{remote_name}/{branch_name}'
                try:
                    commit = repo.commit(ref)
                    break
                except Exception:
                    continue
            else:
                self.stdout.write(f"    Could not find master/main branch for {domain}")
                return

            # Count records by listing tree entries
            tree = commit.tree
            counts = {}
            for item in tree:
                if item.type == 'tree' and item.name in ('organizations', 'nodes', 'migrations'):
                    count = sum(1 for blob in item if blob.name.endswith('.json'))
                    counts[item.name] = count

            # Check for node.json
            has_manifest = any(item.name == 'node.json' for item in tree)

            parts = []
            if has_manifest:
                parts.append("manifest")
            for name, count in counts.items():
                if count > 0:
                    parts.append(f"{count} {name}")

            if parts:
                self.stdout.write(f"    Records: {', '.join(parts)}")

        except Exception as e:
            self.stdout.write(f"    Could not read peer records: {e}")
