"""
Set up Gitea orgs + repos + local clones for the CMS git mirror.

Creates:
  - Org `cms` (public) + repo `parahub-cms` (all published posts, federated)
  - Org `cms-editorial` (visible, repos private) + per-establishment private repos
  - Local clones at CMS_GIT_ROOT with Gitea remotes
  - Webhook on cms-editorial repos for comment snapshots

Usage:
  python3 manage.py setup_cms_git --admin-token <TOKEN>
  python3 manage.py setup_cms_git --admin-token <TOKEN> --establishment parahub-associacao
"""
import os

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

GITEA_URL = 'http://localhost:3003'


class Command(BaseCommand):
    help = 'Create Gitea orgs, repos, and local clones for CMS git mirror'

    def add_arguments(self, parser):
        parser.add_argument('--admin-token', required=True, help='Gitea admin API token')
        parser.add_argument('--establishment', help='Only set up this establishment (slug)')
        parser.add_argument('--skip-initial-sync', action='store_true',
                            help='Skip mirroring existing posts to git')

    def handle(self, *args, **options):
        token = options['admin_token']
        headers = {'Authorization': f'token {token}', 'Content-Type': 'application/json'}

        from cms.git_mirror import _cms_git_root
        git_root = _cms_git_root()

        with httpx.Client(base_url=GITEA_URL, headers=headers, timeout=15) as client:
            # 1. Create orgs
            self._create_org(client, 'cms', 'CMS Public',
                             'Published blog posts — federated to other nodes',
                             visibility='public')
            self._create_org(client, 'cms-editorial', 'CMS Editorial',
                             'Draft posts and editorial discussions (private repos)',
                             visibility='public')  # org visible, repos private

            # 2. Create public repo
            public_repo = self._create_repo(
                client, 'cms', 'parahub-cms',
                'All published posts for this node — federated',
                private=False,
            )

            # Clone public repo locally
            self._clone_or_update(
                git_root / 'public',
                f'{GITEA_URL}/cms/parahub-cms.git',
                token,
            )

            # 3. Create editorial repos per establishment
            from geo.models import Establishment
            qs = Establishment.objects.all()
            if options['establishment']:
                qs = qs.filter(slug=options['establishment'])

            for est in qs:
                if not est.slug:
                    continue
                self._create_repo(
                    client, 'cms-editorial', est.slug,
                    f'Editorial drafts and discussions for {est.name}',
                    private=True,
                )

                # Clone locally
                self._clone_or_update(
                    git_root / 'editorial' / est.slug,
                    f'{GITEA_URL}/cms-editorial/{est.slug}.git',
                    token,
                )

                # Set up webhook for comment snapshots
                self._setup_webhook(
                    client, f'cms-editorial/{est.slug}',
                    events=['issue_comment'],
                )

            # Also set up webhook on public repo for federation notifications
            self._setup_webhook(
                client, 'cms/parahub-cms',
                events=['push'],
            )

        # 4. Update node.json with cms_git URL
        self._update_node_manifest()

        # 5. Initial sync
        if not options['skip_initial_sync']:
            self.stdout.write('\nRunning initial sync...')
            from cms.git_mirror import CMSGitMirror
            mirror = CMSGitMirror()
            result = mirror.initial_sync(options.get('establishment'))
            self.stdout.write(
                f"Synced {result['drafts']} drafts + {result['published']} published"
            )

        self.stdout.write(self.style.SUCCESS('\nCMS git setup complete.'))

    def _create_org(self, client, name, full_name, description, visibility='public'):
        resp = client.post('/api/v1/orgs', json={
            'username': name,
            'full_name': full_name,
            'description': description,
            'visibility': visibility,
        })
        if resp.status_code == 201:
            self.stdout.write(f'  Org created: {name}')
        elif resp.status_code == 422:
            self.stdout.write(f'  Org exists: {name}')
        else:
            self.stderr.write(f'  Org {name} failed: {resp.status_code} {resp.text}')

    def _create_repo(self, client, org, name, description, private=False):
        resp = client.post(f'/api/v1/orgs/{org}/repos', json={
            'name': name,
            'description': description,
            'private': private,
            'auto_init': True,
            'default_branch': 'main',
        })
        if resp.status_code == 201:
            self.stdout.write(f'  Repo created: {org}/{name} (private={private})')
        elif resp.status_code == 409:
            self.stdout.write(f'  Repo exists: {org}/{name}')
        else:
            self.stderr.write(f'  Repo {org}/{name} failed: {resp.status_code} {resp.text}')

    def _clone_or_update(self, local_path, remote_url, token):
        """Clone repo locally or update remote URL if already cloned."""
        import git as gitlib

        # Inject token into URL for push
        auth_url = remote_url.replace('http://', f'http://admin:{token}@')

        if (local_path / '.git').exists():
            repo = gitlib.Repo(local_path)
            # Update remote URL
            if 'origin' in [r.name for r in repo.remotes]:
                repo.remotes.origin.set_url(auth_url)
            self.stdout.write(f'  Local repo updated: {local_path}')
        else:
            local_path.mkdir(parents=True, exist_ok=True)
            try:
                gitlib.Repo.clone_from(auth_url, local_path)
                self.stdout.write(f'  Cloned: {local_path}')
            except gitlib.GitCommandError as e:
                if 'already exists and is not an empty directory' in str(e):
                    # Init and add remote
                    repo = gitlib.Repo.init(local_path)
                    repo.create_remote('origin', auth_url)
                    try:
                        repo.remotes.origin.fetch()
                        # Reset to remote main if it exists
                        for ref in repo.remotes.origin.refs:
                            if ref.remote_head == 'main':
                                repo.head.reference = repo.create_head('main', ref)
                                repo.head.reset(index=True, working_tree=True)
                                break
                    except Exception:
                        pass
                    self.stdout.write(f'  Initialized + remote added: {local_path}')
                else:
                    raise

    def _setup_webhook(self, client, repo_path, events):
        """Create Gitea webhook on a repo for the CMS comment handler."""
        webhook_secret = os.environ.get('GITEA_WEBHOOK_SECRET', '')
        webhook_url = f'https://parahub.io/api/v1/cms/gitea-webhook/'

        # Check if webhook already exists
        resp = client.get(f'/api/v1/repos/{repo_path}/hooks')
        if resp.status_code == 200:
            for hook in resp.json():
                if hook.get('config', {}).get('url') == webhook_url:
                    self.stdout.write(f'  Webhook exists: {repo_path}')
                    return

        resp = client.post(f'/api/v1/repos/{repo_path}/hooks', json={
            'type': 'gitea',
            'active': True,
            'events': events,
            'config': {
                'url': webhook_url,
                'content_type': 'json',
                'secret': webhook_secret,
            },
        })
        if resp.status_code == 201:
            self.stdout.write(f'  Webhook created: {repo_path} → {events}')
        else:
            self.stderr.write(
                f'  Webhook {repo_path} failed: {resp.status_code} {resp.text}'
            )

    def _update_node_manifest(self):
        """Add cms_git field to node.json for federation discovery."""
        from audit_log.registry import RegistryService
        try:
            registry = RegistryService()
            manifest = registry.get_node_manifest()
            if manifest and 'cms_git' not in manifest:
                domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
                manifest['cms_git'] = f'https://gitea.{domain}/cms/parahub-cms.git'
                if 'cms' not in manifest.get('capabilities', []):
                    manifest.setdefault('capabilities', []).append('cms')
                registry.write_node_manifest(manifest)
                self.stdout.write('  Updated node.json with cms_git')
        except Exception as e:
            self.stderr.write(f'  Failed to update node.json: {e}')
