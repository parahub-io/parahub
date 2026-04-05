"""
Initialize this Parahub instance as a federation node.

Generates a server-level PGP key pair, creates node.json manifest,
and sets up the registry directory structure.

Usage:
    python manage.py init_federation_node [--domain parahub.io] [--name "Parahub"]
"""
import json
import subprocess
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Initialize federation node: generate PGP key, create manifest, set up registry dirs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--domain', type=str,
            default=getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io'),
            help='Domain of this node (default: FEDERATION_DOMAIN from settings)',
        )
        parser.add_argument(
            '--name', type=str, default='Parahub',
            help='Human-readable name of this node',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Regenerate PGP key even if one exists',
        )

    def handle(self, *args, **options):
        domain = options['domain']
        name = options['name']
        force = options['force']

        repo_path = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git'

        self.stdout.write(f"Initializing federation node: {domain}")

        # 1. Ensure directory structure
        for dirname in ('nodes', 'organizations', 'migrations'):
            (repo_path / dirname).mkdir(parents=True, exist_ok=True)
            gitkeep = repo_path / dirname / '.gitkeep'
            if not gitkeep.exists():
                gitkeep.touch()
        self.stdout.write(self.style.SUCCESS("  Directory structure created"))

        # 2. Generate node PGP key
        fingerprint, public_key = self._ensure_pgp_key(domain, name, force)
        if not fingerprint:
            self.stderr.write("Failed to generate/find PGP key")
            return

        self.stdout.write(self.style.SUCCESS(f"  PGP key: {fingerprint}"))

        # 3. Create node.json manifest
        site_url = getattr(settings, 'SITE_URL', f'https://{domain}')
        manifest = {
            'type': 'node',
            'domain': domain,
            'name': name,
            'url': site_url,
            'registry_git': f'https://gitea.{domain}/audit/parahub-registry.git',
            'ws_federation': f'wss://{domain}/ws/v1/federation/',
            'matrix_server': domain,
            'node_pgp_fingerprint': fingerprint,
            'node_pgp_public_key': public_key,
            'established': __import__('datetime').datetime.now(
                __import__('datetime').timezone.utc
            ).isoformat(),
            'version': '1.0',
            'capabilities': [
                'organizations', 'marketplace', 'contracts',
                'wot', 'treasury', 'governance',
            ],
            'peers': [],
        }

        from audit_log.registry import RegistryService
        registry = RegistryService()
        commit = registry.write_node_manifest(manifest)

        self.stdout.write(self.style.SUCCESS(
            f"  Node manifest written and committed: {commit[:8]}"
        ))

        # 4. Print settings to add
        self.stdout.write("\n" + self.style.WARNING("Add to .env or settings.py:"))
        self.stdout.write(f"  FEDERATION_ENABLED=True")
        self.stdout.write(f"  FEDERATION_DOMAIN={domain}")
        self.stdout.write(f"  FEDERATION_NODE_PGP_FINGERPRINT={fingerprint}")

    def _ensure_pgp_key(self, domain: str, name: str, force: bool):
        """Generate or find node PGP key. Returns (fingerprint, public_key_armor)."""
        key_email = f"node@{domain}"

        if not force:
            # Check if key already exists
            result = subprocess.run(
                ['gpg', '--list-keys', '--with-colons', key_email],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('fpr:'):
                        fingerprint = line.split(':')[9]
                        # Export public key
                        export = subprocess.run(
                            ['gpg', '--armor', '--export', fingerprint],
                            capture_output=True, text=True,
                        )
                        return fingerprint, export.stdout

        # Generate new key
        self.stdout.write("  Generating node PGP key...")
        key_params = f"""
%no-protection
Key-Type: eddsa
Key-Curve: Ed25519
Subkey-Type: ecdh
Subkey-Curve: Curve25519
Name-Real: {name} Federation Node
Name-Email: {key_email}
Expire-Date: 0
%commit
"""
        result = subprocess.run(
            ['gpg', '--batch', '--gen-key'],
            input=key_params,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            self.stderr.write(f"GPG key generation failed: {result.stderr}")
            return None, None

        # Get fingerprint
        list_result = subprocess.run(
            ['gpg', '--list-keys', '--with-colons', key_email],
            capture_output=True, text=True,
        )
        fingerprint = None
        for line in list_result.stdout.split('\n'):
            if line.startswith('fpr:'):
                fingerprint = line.split(':')[9]
                break

        if not fingerprint:
            self.stderr.write("Could not find generated key fingerprint")
            return None, None

        # Export public key
        export = subprocess.run(
            ['gpg', '--armor', '--export', fingerprint],
            capture_output=True, text=True,
        )

        return fingerprint, export.stdout
