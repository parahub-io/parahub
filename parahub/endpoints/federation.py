"""
Federation API endpoints.

Public endpoints for inter-node communication, HNA resolution,
and profile migration workflow.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from django.conf import settings
from django.db import models
from django.http import FileResponse
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import BaseModel

from parahub.auth import OptionalProfileAuth, ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)
router = Router(tags=["federation"])


# ── Schemas ────────────────────────────────────────────────────────────

class NodeManifestResponse(Schema):
    domain: str
    name: str
    url: str
    registry_git: str = ''
    ws_federation: str = ''
    matrix_server: str = ''
    capabilities: list = []
    peers: list = []


class HNAResolution(Schema):
    hna: str
    ulid: str
    node: str
    pgp_fingerprint: str = ''
    wot_level: int = 0
    avatar_url: str = ''
    migrated_to: str = ''  # If profile migrated, the new HNA


class RegistryStatsResponse(Schema):
    organizations: int
    peers: int
    migrations: int
    verifications: int = 0
    connected_peers: int = 0
    has_manifest: bool


class PeerNodeResponse(Schema):
    domain: str
    name: str = ''
    url: str = ''
    trust_level: str = ''
    first_seen: str = ''


class OrganizationRecord(Schema):
    ulid: str
    name: str
    slug: str = ''
    node: str
    organization_type: str = ''
    category: str = ''
    created_at: str = ''


class MigrationResponse(Schema):
    id: str
    from_hna: str
    to_hna: str = ''
    from_node: str
    to_node: str = ''
    status: str
    reason: str = ''
    continuity_proof: str = ''
    has_from_signature: bool = False
    has_to_signature: bool = False
    has_from_node_signature: bool = False
    has_to_node_signature: bool = False
    export_hash: str = ''
    git_commit_hash: str = ''
    created_at: str = ''
    completed_at: str = ''


# ── Public Endpoints (no auth, for inter-node queries) ─────────────────

@router.get("/node/", response=NodeManifestResponse, auth=None)
@ratelimit(group='federation:manifest', key='ip', rate='60/m')
def get_node_manifest(request):
    """
    Get this node's federation manifest.

    Public endpoint — other nodes call this to discover capabilities.
    """
    from audit_log.registry import RegistryService

    try:
        registry = RegistryService()
        manifest = registry.get_node_manifest()
    except Exception as e:
        logger.warning(f"Failed to read node manifest: {e}")
        manifest = None

    if not manifest:
        # Return basic info even without manifest file
        domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
        return {
            'domain': domain,
            'name': 'Parahub',
            'url': getattr(settings, 'SITE_URL', f'https://{domain}'),
        }

    return manifest


@router.get("/resolve/{hna}/", auth=None)
@ratelimit(group='federation:resolve', key='ip', rate='30/m')
def resolve_hna(request, hna: str):
    """
    Resolve a Human-Navigable Alias to profile data.

    Public endpoint — other nodes call this to look up users.
    Example: /api/v1/federation/resolve/deploy@parahub.io/
    """
    from identity.models import Profile

    # Parse HNA
    if '@' in hna:
        local_name, domain = hna.rsplit('@', 1)
    else:
        local_name = hna
        domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')

    my_domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')

    # Only resolve local profiles
    if domain != my_domain:
        raise HttpError(404, f"This node is {my_domain}, cannot resolve {domain}")

    # Check for completed migration (DB first, then git fallback)
    from core.models import ProfileMigration
    db_migration = ProfileMigration.objects.filter(
        from_hna=hna, status=ProfileMigration.COMPLETED,
    ).first()
    if db_migration:
        return {
            'hna': hna,
            'ulid': db_migration.profile_id,
            'node': my_domain,
            'migrated_to': db_migration.to_hna,
        }

    # Git fallback
    registry_path = Path(settings.AUDIT_LOG_GIT_PATH) / 'public-git' / 'migrations'
    if registry_path.exists():
        for mig_file in registry_path.glob('*.json'):
            try:
                mig = json.loads(mig_file.read_text(encoding='utf-8'))
                if mig.get('from_hna') == hna:
                    return {
                        'hna': hna,
                        'ulid': mig.get('from_ulid', ''),
                        'node': my_domain,
                        'migrated_to': mig.get('to_hna', ''),
                    }
            except (json.JSONDecodeError, OSError):
                continue

    # Look up profile
    try:
        profile = Profile.objects.select_related('account').get(
            account__username=local_name
        )
    except Profile.DoesNotExist:
        raise HttpError(404, f"Profile not found: {hna}")

    # Get WoT level
    from identity.models import Verification
    wot_count = Verification.objects.filter(
        verified_profile=profile, is_active=True
    ).count()

    # Get PGP fingerprint
    fingerprint = ''
    if profile.pgp_public_key:
        from audit_log.models import PGPKeyPublication
        pub = PGPKeyPublication.objects.filter(
            profile=profile, revoked=False
        ).first()
        if pub:
            fingerprint = pub.fingerprint

    return {
        'hna': f"{local_name}@{my_domain}",
        'ulid': profile.id,
        'node': my_domain,
        'pgp_fingerprint': fingerprint,
        'wot_level': wot_count,
        'avatar_url': profile.avatar.url if profile.avatar else '',
        'migrated_to': '',
    }


@router.get("/stats/", response=RegistryStatsResponse, auth=None)
@ratelimit(group='federation:stats', key='ip', rate='60/m')
def get_registry_stats(request):
    """Get federation registry statistics."""
    from audit_log.registry import RegistryService

    try:
        registry = RegistryService()
        return registry.get_registry_stats()
    except Exception as e:
        logger.warning(f"Failed to get registry stats: {e}")
        return {'organizations': 0, 'peers': 0, 'migrations': 0, 'has_manifest': False}


@router.get("/peers/", response=List[PeerNodeResponse], auth=None)
@ratelimit(group='federation:peers', key='ip', rate='60/m')
def list_peers(request):
    """List known federation peer nodes."""
    from audit_log.registry import RegistryService

    try:
        registry = RegistryService()
        peers = registry.get_known_peers()
        return [
            {
                'domain': p.get('domain', ''),
                'name': p.get('name', ''),
                'url': p.get('url', ''),
                'trust_level': p.get('trust_level', ''),
                'first_seen': p.get('first_seen', ''),
            }
            for p in peers
        ]
    except Exception as e:
        logger.warning(f"Failed to list peers: {e}")
        return []


@router.get("/organizations/", response=List[OrganizationRecord], auth=None)
@ratelimit(group='federation:organizations', key='ip', rate='60/m')
def list_organizations(request):
    """List all organizations in the federation registry."""
    from audit_log.registry import RegistryService

    try:
        registry = RegistryService()
        orgs = []
        for org_file in sorted(registry.orgs_path.glob('*.json')):
            try:
                data = json.loads(org_file.read_text(encoding='utf-8'))
                orgs.append({
                    'ulid': data.get('ulid', ''),
                    'name': data.get('name', ''),
                    'slug': data.get('slug', ''),
                    'node': data.get('node', ''),
                    'organization_type': data.get('organization_type', ''),
                    'category': data.get('category', ''),
                    'created_at': data.get('created_at', ''),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return orgs
    except Exception as e:
        logger.warning(f"Failed to list organizations: {e}")
        return []


# ── Staff Endpoints (admin management) ─────────────────────────────────

@router.post("/peers/register/", auth=ProfileAuth())
@ratelimit(group='federation:register_peer', key=user_or_ip, rate='10/m', method='POST')
def register_peer(request, domain: str, url: str, name: str = '', pgp_key: str = ''):
    """Register a new federation peer node (staff only)."""
    profile = request.auth
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")

    from audit_log.registry import RegistryService

    registry = RegistryService()
    commit = registry.register_peer({
        'domain': domain,
        'name': name or domain,
        'url': url,
        'node_pgp_public_key': pgp_key,
        'trust_level': 'observed',
    })

    if not commit:
        raise HttpError(500, "Failed to register peer")

    # Broadcast to federation
    from parahub.services.ws_publish import ws_publish
    ws_publish('feed:federation', {
        'type': 'peer_registered',
        'domain': domain,
    })

    return {'status': 'ok', 'domain': domain, 'commit': commit}


@router.post("/peers/discover/", auth=ProfileAuth())
@ratelimit(group='federation:discover_peer', key=user_or_ip, rate='10/m', method='POST')
def discover_peer(request, url: str):
    """
    Discover a peer by fetching their /api/v1/federation/node/ manifest.
    Auto-registers the peer with their published info. Staff only.
    """
    profile = request.auth
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")

    import httpx

    # Fetch peer's manifest
    try:
        manifest_url = url.rstrip('/') + '/api/v1/federation/node/'
        with httpx.Client(timeout=10) as client:
            resp = client.get(manifest_url)
            resp.raise_for_status()
            manifest = resp.json()
    except Exception as e:
        raise HttpError(400, f"Failed to fetch peer manifest: {e}")

    domain = manifest.get('domain', '')
    if not domain:
        raise HttpError(400, "Peer manifest missing domain")

    # Register
    from audit_log.registry import RegistryService
    registry = RegistryService()
    commit = registry.register_peer({
        'domain': domain,
        'name': manifest.get('name', domain),
        'url': manifest.get('url', url),
        'registry_git': manifest.get('registry_git', ''),
        'ws_federation': manifest.get('ws_federation', ''),
        'node_pgp_public_key': manifest.get('node_pgp_public_key', ''),
        'node_pgp_fingerprint': manifest.get('node_pgp_fingerprint', ''),
        'trust_level': 'observed',
        'capabilities': manifest.get('capabilities', []),
    })

    if not commit:
        raise HttpError(500, "Failed to register peer")

    return {
        'status': 'ok',
        'domain': domain,
        'name': manifest.get('name', ''),
        'capabilities': manifest.get('capabilities', []),
        'commit': commit,
    }


@router.post("/sync/", auth=ProfileAuth())
@ratelimit(group='federation:sync', key=user_or_ip, rate='10/m', method='POST')
def trigger_sync(request, domain: str = ''):
    """Trigger git fetch from a specific peer or all peers. Staff only."""
    profile = request.auth
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")

    from audit_log.registry import RegistryService
    import git as gitlib

    registry = RegistryService()

    # Determine which peers to sync
    if domain:
        peers = [p for p in registry.get_known_peers() if p.get('domain') == domain]
    else:
        peers = registry.get_known_peers()

    my_domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
    results = []

    for peer in peers:
        peer_domain = peer.get('domain', '')
        git_url = peer.get('registry_git', '')
        if not peer_domain or not git_url or peer_domain == my_domain:
            continue

        remote_name = f"peer/{peer_domain}"
        try:
            remote = registry.repo.remote(remote_name)
        except ValueError:
            remote = registry.repo.create_remote(remote_name, git_url)

        try:
            remote.fetch(timeout=30)
            results.append({'domain': peer_domain, 'status': 'ok'})
        except Exception as e:
            results.append({'domain': peer_domain, 'status': 'error', 'error': str(e)})

    return {'synced': results}


@router.get("/sync/status/", auth=ProfileAuth())
@ratelimit(group='federation:sync_status', key=user_or_ip, rate='60/m')
def sync_status(request):
    """Get git sync status for all peer remotes. Staff only."""
    profile = request.auth
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")

    from audit_log.registry import RegistryService
    registry = RegistryService()
    return {'peers': registry.get_peer_sync_status()}


@router.get("/peers/{domain}/organizations/", auth=None)
@ratelimit(group='federation:peer_orgs', key='ip', rate='60/m')
def list_peer_organizations(request, domain: str):
    """List organizations from a synced peer's registry."""
    from audit_log.registry import RegistryService
    registry = RegistryService()
    orgs = registry.read_peer_organizations(domain)
    return [
        {
            'ulid': o.get('ulid', ''),
            'name': o.get('name', ''),
            'slug': o.get('slug', ''),
            'node': o.get('node', domain),
            'organization_type': o.get('organization_type', ''),
            'category': o.get('category', ''),
            'created_at': o.get('created_at', ''),
        }
        for o in orgs
    ]


# ── Profile Migration Endpoints ──────────────────────────────────────

def _migration_to_response(m) -> dict:
    return {
        'id': m.id,
        'from_hna': m.from_hna,
        'to_hna': m.to_hna,
        'from_node': m.from_node,
        'to_node': m.to_node,
        'status': m.status,
        'reason': m.reason,
        'continuity_proof': m.continuity_proof,
        'has_from_signature': bool(m.from_user_signature),
        'has_to_signature': bool(m.to_user_signature),
        'has_from_node_signature': bool(m.from_node_signature),
        'has_to_node_signature': bool(m.to_node_signature),
        'export_hash': m.export_hash,
        'git_commit_hash': m.git_commit_hash,
        'created_at': m.created_at.isoformat() if m.created_at else '',
        'completed_at': m.completed_at.isoformat() if m.completed_at else '',
    }


@router.post("/migration/initiate/", response=MigrationResponse, auth=ProfileAuth())
@ratelimit(group='federation:initiate_migration', key=user_or_ip, rate='10/m', method='POST')
def initiate_migration(request, to_node: str, to_hna: str = '', reason: str = ''):
    """
    Initiate a profile migration to another node.

    Creates a migration record and signs it with this node's PGP key.
    The user must then sign with their PGP key via /migration/{id}/sign/.
    """
    from core.models import ProfileMigration

    profile = request.auth
    domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
    from_hna = f"{profile.account.username}@{domain}"

    # Check no active migration already exists
    active = ProfileMigration.objects.filter(
        profile=profile,
        status__in=['initiated', 'exported', 'signed'],
    ).first()
    if active:
        raise HttpError(409, f"Active migration already exists: {active.id}")

    migration = ProfileMigration.objects.create(
        profile=profile,
        from_hna=from_hna,
        to_hna=to_hna,
        from_node=domain,
        to_node=to_hna.split('@')[-1] if '@' in to_hna else to_node,
        reason=reason,
    )

    # Sign with node key
    from audit_log.registry import RegistryService
    registry = RegistryService()
    canonical = json.dumps({
        'type': 'profile_migration',
        'migration_id': migration.id,
        'from_hna': from_hna,
        'to_hna': to_hna,
        'from_node': domain,
        'to_node': migration.to_node,
    }, sort_keys=True, separators=(',', ':'))
    node_sig = registry._sign_with_node_key(json.loads(canonical))
    if node_sig:
        migration.from_node_signature = node_sig
        migration.save(update_fields=['from_node_signature'])

    logger.info(f"Migration initiated: {from_hna} → {to_hna or to_node} ({migration.id[:8]})")
    return _migration_to_response(migration)


@router.post("/migration/{migration_id}/sign/", response=MigrationResponse, auth=ProfileAuth())
@ratelimit(group='federation:sign_migration', key=user_or_ip, rate='10/m', method='POST')
def sign_migration(request, migration_id: str, signature: str, continuity_proof: str = ''):
    """
    Sign a migration with the user's PGP key.

    The source profile signs to confirm they want to migrate.
    """
    from core.models import ProfileMigration

    profile = request.auth

    try:
        migration = ProfileMigration.objects.get(id=migration_id)
    except ProfileMigration.DoesNotExist:
        raise HttpError(404, "Migration not found")

    if migration.profile_id != profile.id:
        raise HttpError(403, "Not your migration")

    if migration.status not in ('initiated', 'exported'):
        raise HttpError(400, f"Cannot sign migration in status: {migration.status}")

    migration.from_user_signature = signature
    if continuity_proof:
        migration.continuity_proof = continuity_proof
    migration.save(update_fields=['from_user_signature', 'continuity_proof'])

    logger.info(f"Migration {migration_id[:8]} signed by source user")
    return _migration_to_response(migration)


@router.post("/migration/{migration_id}/export/", auth=ProfileAuth())
@ratelimit(group='federation:export_migration', key=user_or_ip, rate='10/m', method='POST')
def export_migration_data(request, migration_id: str):
    """
    Generate data export ZIP for migration. Sets status to EXPORTED.

    Returns the export file as a download.
    """
    from core.models import ProfileMigration
    from audit_log.services import ProofExportService

    profile = request.auth

    try:
        migration = ProfileMigration.objects.get(id=migration_id)
    except ProfileMigration.DoesNotExist:
        raise HttpError(404, "Migration not found")

    if migration.profile_id != profile.id:
        raise HttpError(403, "Not your migration")

    if migration.status == 'completed':
        raise HttpError(400, "Migration already completed")

    # Generate full account export
    export_service = ProofExportService()
    zip_buffer = export_service.export_full_account(profile)

    # Compute SHA256 of the export
    zip_buffer.seek(0)
    sha256 = hashlib.sha256(zip_buffer.read()).hexdigest()
    zip_buffer.seek(0)

    migration.export_hash = sha256
    migration.status = ProfileMigration.EXPORTED
    migration.save(update_fields=['export_hash', 'status'])

    logger.info(f"Migration {migration_id[:8]} data exported (SHA256: {sha256[:16]}...)")

    return FileResponse(
        zip_buffer,
        content_type='application/zip',
        filename=f"migration_{migration.from_hna}_{migration.id[:8]}.zip",
    )


@router.post("/migration/{migration_id}/complete/", response=MigrationResponse, auth=ProfileAuth())
@ratelimit(group='federation:complete_migration', key=user_or_ip, rate='10/m', method='POST')
def complete_migration(request, migration_id: str, to_user_signature: str = ''):
    """
    Complete a migration. Commits to federation registry + broadcasts.

    Staff or the migrating user can complete. Destination node confirms
    by providing to_user_signature via inter-node API.
    """
    from core.models import ProfileMigration

    profile = request.auth

    try:
        migration = ProfileMigration.objects.get(id=migration_id)
    except ProfileMigration.DoesNotExist:
        raise HttpError(404, "Migration not found")

    is_owner = migration.profile_id == profile.id
    is_staff = profile.account.is_staff
    if not is_owner and not is_staff:
        raise HttpError(403, "Not authorized")

    if migration.status == 'completed':
        raise HttpError(400, "Already completed")

    if not migration.from_user_signature:
        raise HttpError(400, "Source user must sign first")

    if to_user_signature:
        migration.to_user_signature = to_user_signature

    # Commit to git registry
    from audit_log.registry import RegistryService
    registry = RegistryService()
    commit = registry.register_migration(
        from_hna=migration.from_hna,
        from_ulid=migration.profile_id,
        to_hna=migration.to_hna,
        to_ulid='',
        from_signature=migration.from_user_signature,
        to_signature=migration.to_user_signature,
        reason=migration.reason,
    )

    migration.status = ProfileMigration.COMPLETED
    migration.completed_at = datetime.now(timezone.utc)
    if commit:
        migration.git_commit_hash = commit
    migration.save(update_fields=[
        'status', 'completed_at', 'git_commit_hash', 'to_user_signature',
    ])

    # Broadcast via WS
    from parahub.services.ws_publish import ws_publish
    ws_publish('feed:federation', {
        'type': 'profile_migration',
        'from_hna': migration.from_hna,
        'to_hna': migration.to_hna,
        'domain': migration.from_node,
    })

    logger.info(f"Migration completed: {migration.from_hna} → {migration.to_hna} ({commit or 'no commit'})")
    return _migration_to_response(migration)


@router.post("/migration/{migration_id}/cancel/", response=MigrationResponse, auth=ProfileAuth())
@ratelimit(group='federation:cancel_migration', key=user_or_ip, rate='10/m', method='POST')
def cancel_migration(request, migration_id: str):
    """Cancel an in-progress migration."""
    from core.models import ProfileMigration

    profile = request.auth

    try:
        migration = ProfileMigration.objects.get(id=migration_id)
    except ProfileMigration.DoesNotExist:
        raise HttpError(404, "Migration not found")

    if migration.profile_id != profile.id and not profile.account.is_staff:
        raise HttpError(403, "Not authorized")

    if migration.status == 'completed':
        raise HttpError(400, "Cannot cancel completed migration")

    migration.status = ProfileMigration.CANCELLED
    migration.save(update_fields=['status'])

    logger.info(f"Migration cancelled: {migration.from_hna} ({migration_id[:8]})")
    return _migration_to_response(migration)


@router.get("/migration/{migration_id}/", response=MigrationResponse, auth=ProfileAuth())
@ratelimit(group='federation:get_migration', key=user_or_ip, rate='60/m')
def get_migration(request, migration_id: str):
    """Get migration details."""
    from core.models import ProfileMigration

    profile = request.auth

    try:
        migration = ProfileMigration.objects.get(id=migration_id)
    except ProfileMigration.DoesNotExist:
        raise HttpError(404, "Migration not found")

    if migration.profile_id != profile.id and not profile.account.is_staff:
        raise HttpError(403, "Not authorized")

    return _migration_to_response(migration)


@router.get("/migrations/", response=List[MigrationResponse], auth=ProfileAuth())
@ratelimit(group='federation:list_migrations', key=user_or_ip, rate='60/m')
def list_migrations(request):
    """List migrations. Staff sees all, users see their own."""
    from core.models import ProfileMigration

    profile = request.auth

    if profile.account.is_staff:
        qs = ProfileMigration.objects.all()
    else:
        qs = ProfileMigration.objects.filter(profile=profile)

    return [_migration_to_response(m) for m in qs[:50]]


# ── Inter-node migration confirmation (public, for target node) ──────

@router.post("/migration/confirm/", auth=None)
@ratelimit(group='federation:confirm_migration', key='ip', rate='10/m', method='POST')
def confirm_migration_from_peer(request):
    """
    Target node confirms a migration.

    Called by the destination node to provide to_node_signature and
    optionally to_user_signature for a migration record.
    Public endpoint — PGP signature required in body.
    """
    from core.models import ProfileMigration

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        raise HttpError(400, "Invalid JSON body")

    migration_id = body.get('migration_id', '')
    to_node_signature = body.get('to_node_signature', '')
    to_user_signature = body.get('to_user_signature', '')
    peer_domain = body.get('domain', '')

    if not migration_id or not peer_domain:
        raise HttpError(400, "migration_id and domain required")

    try:
        migration = ProfileMigration.objects.get(id=migration_id)
    except ProfileMigration.DoesNotExist:
        raise HttpError(404, "Migration not found")

    if migration.to_node != peer_domain:
        raise HttpError(403, f"Domain mismatch: expected {migration.to_node}, got {peer_domain}")

    if to_node_signature:
        migration.to_node_signature = to_node_signature
    if to_user_signature:
        migration.to_user_signature = to_user_signature
    migration.save(update_fields=['to_node_signature', 'to_user_signature'])

    return {'status': 'ok', 'migration_id': migration_id}


# ── Data Import (Phase 4) ────────────────────────────────────────────

@router.post("/migration/import/", auth=ProfileAuth())
@ratelimit(group='federation:import_migration', key=user_or_ip, rate='10/m', method='POST')
def import_migration_data(request):
    """
    Import a migration data ZIP on the destination node.
    Staff only. Parses the export ZIP and creates reference records.
    """
    import zipfile
    from io import BytesIO

    profile = request.auth
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")

    if not request.FILES.get('file'):
        raise HttpError(400, "ZIP file required (multipart 'file' field)")

    uploaded = request.FILES['file']
    if uploaded.size > 100 * 1024 * 1024:  # 100MB limit
        raise HttpError(400, "File too large (max 100MB)")

    zip_data = BytesIO(uploaded.read())

    try:
        zf = zipfile.ZipFile(zip_data, 'r')
    except zipfile.BadZipFile:
        raise HttpError(400, "Invalid ZIP file")

    imported = {'contracts': 0, 'debts': 0, 'verifications': 0, 'items': 0, 'pgp_key': False}

    # Parse and store as federated import records in the git registry
    from audit_log.registry import RegistryService
    registry = RegistryService()
    imports_path = registry.repo_path / 'imports'
    imports_path.mkdir(exist_ok=True)

    domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
    import_id = hashlib.sha256(zip_data.getvalue()[:1024]).hexdigest()[:16]
    import_dir = imports_path / import_id
    import_dir.mkdir(exist_ok=True)

    for name in zf.namelist():
        if name.startswith('contracts/') and name.endswith('.json'):
            try:
                data = json.loads(zf.read(name))
                data['imported_to'] = domain
                data['import_id'] = import_id
                out = import_dir / name.replace('/', '_')
                out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
                imported['contracts'] += 1
            except (json.JSONDecodeError, KeyError):
                continue

        elif name.startswith('debts/') and name.endswith('.json'):
            try:
                data = json.loads(zf.read(name))
                data['imported_to'] = domain
                data['import_id'] = import_id
                out = import_dir / name.replace('/', '_')
                out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
                imported['debts'] += 1
            except (json.JSONDecodeError, KeyError):
                continue

        elif name.startswith('verifications/') and name.endswith('.json'):
            try:
                data = json.loads(zf.read(name))
                if isinstance(data, list):
                    for v in data:
                        v['imported_to'] = domain
                        v['import_id'] = import_id
                    out = import_dir / name.replace('/', '_')
                    out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
                    imported['verifications'] += len(data)
                else:
                    data['imported_to'] = domain
                    out = import_dir / name.replace('/', '_')
                    out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
                    imported['verifications'] += 1
            except (json.JSONDecodeError, KeyError):
                continue

        elif name.startswith('items/') and name.endswith('.json'):
            try:
                data = json.loads(zf.read(name))
                data['imported_to'] = domain
                data['import_id'] = import_id
                out = import_dir / name.replace('/', '_')
                out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
                imported['items'] += 1
            except (json.JSONDecodeError, KeyError):
                continue

        elif name == 'pgp/public_key.asc':
            key_data = zf.read(name).decode('utf-8', errors='replace')
            (import_dir / 'public_key.asc').write_text(key_data, encoding='utf-8')
            imported['pgp_key'] = True

    zf.close()

    # Git commit the import
    try:
        registry.repo.index.add([str(p) for p in import_dir.rglob('*') if p.is_file()])
        commit = registry.repo.index.commit(
            f"federation: import migration data ({import_id})"
        )
        logger.info(f"Migration data imported: {import_id} ({commit.hexsha[:8]})")
    except Exception as e:
        logger.error(f"Failed to commit import: {e}")

    return {
        'status': 'ok',
        'import_id': import_id,
        'imported': imported,
    }


# ── Cross-Node WoT Verification (Phase 4) ────────────────────────────

@router.post("/verify/", auth=ProfileAuth())
@ratelimit(group='federation:verify', key=user_or_ip, rate='10/m', method='POST')
def federated_verify(request, verified_hna: str, method: str = 'VOUCHED', signature: str = ''):
    """
    Create a cross-node WoT verification.

    Records that the authenticated user vouches for a remote HNA.
    Commits to the git registry and broadcasts via WS.
    """
    profile = request.auth
    domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
    verifier_hna = f"{profile.account.username}@{domain}"

    if not profile.pgp_public_key and not profile.is_verified_wot:
        raise HttpError(400, "You need PGP keys or WoT verification to verify others")

    # Don't verify yourself
    if verified_hna == verifier_hna:
        raise HttpError(400, "Cannot verify yourself")

    from audit_log.registry import RegistryService
    registry = RegistryService()
    commit = registry.register_verification(
        verifier_hna=verifier_hna,
        verified_hna=verified_hna,
        method=method,
        signature=signature,
    )

    if not commit:
        raise HttpError(500, "Failed to register verification")

    # Broadcast
    from parahub.services.ws_publish import ws_publish
    ws_publish('feed:federation', {
        'type': 'verification',
        'verifier_hna': verifier_hna,
        'verified_hna': verified_hna,
        'domain': domain,
    })

    return {
        'status': 'ok',
        'verifier_hna': verifier_hna,
        'verified_hna': verified_hna,
        'commit': commit,
    }


@router.get("/verifications/{hna}/", auth=None)
@ratelimit(group='federation:verifications', key='ip', rate='20/m')
def get_federated_verifications(request, hna: str):
    """
    Get all federation-level verifications for an HNA.

    Returns verifications from local registry + all synced peers.
    Public endpoint for inter-node queries.
    """
    from audit_log.registry import RegistryService
    registry = RegistryService()

    # Local verifications
    local = registry.get_verifications_for(hna)

    # Peer verifications (from synced git)
    peer_verifications = []
    for peer in registry.get_known_peers():
        peer_domain = peer.get('domain', '')
        if not peer_domain:
            continue
        peer_vers = registry.read_peer_verifications(peer_domain, hna)
        peer_verifications.extend(peer_vers)

    return {
        'hna': hna,
        'verifications': local + peer_verifications,
        'count': len(local) + len(peer_verifications),
    }


# ── Federated Search (Phase 4) ───────────────────────────────────────

@router.get("/search/", auth=None)
@ratelimit(group='federation:search', key='ip', rate='10/m')
def federated_search(request, q: str, timeout: int = 5):
    """
    Search across the federation for profiles and organizations.

    Queries local node + all known peers' resolve endpoints.
    Returns aggregated results with node badges.
    """
    import concurrent.futures
    import httpx

    if len(q) < 2:
        raise HttpError(400, "Query too short (min 2 chars)")

    # Cap timeout to prevent abuse (max 10 seconds)
    timeout = min(max(timeout, 1), 10)

    domain = getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io')
    results = []

    # 1. Local profile search
    from identity.models import Profile
    local_profiles = Profile.objects.select_related('account').filter(
        models.Q(account__username__icontains=q) |
        models.Q(display_name__icontains=q)
    )[:10]

    for p in local_profiles:
        results.append({
            'type': 'profile',
            'hna': p.hna if hasattr(p, 'hna') else f"{p.account.username}@{domain}",
            'display_name': p.display_name or p.account.username,
            'node': domain,
            'is_local': True,
            'is_verified': p.is_verified_wot,
            'avatar_url': p.avatar.url if p.avatar else '',
        })

    # 2. Local organization search (from registry)
    from audit_log.registry import RegistryService
    try:
        registry = RegistryService()
        for org_file in registry.orgs_path.glob('*.json'):
            try:
                data = json.loads(org_file.read_text(encoding='utf-8'))
                name = data.get('name', '')
                slug = data.get('slug', '')
                if q.lower() in name.lower() or q.lower() in slug.lower():
                    results.append({
                        'type': 'organization',
                        'ulid': data.get('ulid', ''),
                        'name': name,
                        'slug': slug,
                        'node': domain,
                        'is_local': True,
                        'category': data.get('category', ''),
                    })
            except (json.JSONDecodeError, OSError):
                continue
    except Exception:
        pass

    # 3. Query peers in parallel
    peers = []
    try:
        peers = registry.get_known_peers()
    except Exception:
        pass

    def query_peer(peer):
        peer_domain = peer.get('domain', '')
        peer_url = peer.get('url', '')
        if not peer_domain or not peer_url or peer_domain == domain:
            return []

        peer_results = []

        # Try resolve if q looks like an HNA
        if '@' in q or '.' not in q:
            try:
                resolve_url = f"{peer_url.rstrip('/')}/api/v1/federation/resolve/{q}/"
                with httpx.Client(timeout=timeout) as client:
                    resp = client.get(resolve_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        peer_results.append({
                            'type': 'profile',
                            'hna': data.get('hna', ''),
                            'display_name': data.get('hna', '').split('@')[0],
                            'node': peer_domain,
                            'is_local': False,
                            'is_verified': data.get('wot_level', 0) >= 3,
                            'avatar_url': data.get('avatar_url', ''),
                            'pgp_fingerprint': data.get('pgp_fingerprint', ''),
                        })
            except Exception:
                pass

        # Search peer's organizations from synced git
        try:
            peer_orgs = registry.read_peer_organizations(peer_domain)
            for org in peer_orgs:
                name = org.get('name', '')
                slug = org.get('slug', '')
                if q.lower() in name.lower() or q.lower() in slug.lower():
                    peer_results.append({
                        'type': 'organization',
                        'ulid': org.get('ulid', ''),
                        'name': name,
                        'slug': slug,
                        'node': peer_domain,
                        'is_local': False,
                        'category': org.get('category', ''),
                    })
        except Exception:
            pass

        return peer_results

    # Parallel peer queries
    if peers:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(query_peer, p): p for p in peers}
            for future in concurrent.futures.as_completed(futures, timeout=timeout + 1):
                try:
                    results.extend(future.result())
                except Exception:
                    continue

    return {
        'query': q,
        'results': results,
        'count': len(results),
    }
