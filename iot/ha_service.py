"""
Home Assistant integration service.

Communicates with user-owned HA instances via REST API.
Token encryption uses the same Fernet mechanism as TraccarService.
"""
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
import requests as sync_requests
from django.conf import settings
from django.utils import timezone

from iot.services import TraccarService

logger = logging.getLogger(__name__)

# Timeouts for HA API calls
HA_CONNECT_TIMEOUT = 5.0
HA_READ_TIMEOUT = 15.0

# Domains where entities can be controlled (turn_on/off, etc.)
CONTROLLABLE_DOMAINS = frozenset({
    'light', 'switch', 'fan', 'cover', 'lock', 'climate',
    'media_player', 'vacuum', 'humidifier', 'water_heater',
    'valve', 'siren', 'button', 'scene', 'script',
    'input_boolean', 'input_number',
})

# Mapping HA domain → IoTDevice.device_type
DOMAIN_TO_DEVICE_TYPE = {
    'sensor': 'SENSOR',
    'binary_sensor': 'SENSOR',
    'device_tracker': 'TRACKER',
    'switch': 'ACTUATOR',
    'light': 'ACTUATOR',
    'lock': 'ACTUATOR',
    'climate': 'ACTUATOR',
    'cover': 'ACTUATOR',
    'fan': 'ACTUATOR',
}

# Blocked URL patterns (SSRF protection)
_BLOCKED_HOSTS = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}


def _validate_url(url: str) -> str:
    """Validate HA URL and block SSRF to internal services."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError("URL must use http or https")
    host = parsed.hostname or ''
    if host in _BLOCKED_HOSTS:
        raise ValueError("URL must not point to localhost")
    # Block internal Parahub ports (LXC host from ALLOWED_HOSTS)
    internal_hosts = {h.strip() for h in getattr(settings, 'ALLOWED_HOSTS', []) if h.strip()}
    internal_ports = {8000, 8001, 8003, 8004, 8005, 5432, 6379}
    if host in internal_hosts and parsed.port in internal_ports:
        raise ValueError("URL must not point to internal Parahub services")
    return url.rstrip('/')


def encrypt_token(token: str) -> str:
    """Encrypt HA long-lived access token using shared Fernet key."""
    return TraccarService.encrypt_password(token)


def decrypt_token(encrypted: str) -> str:
    """Decrypt HA long-lived access token."""
    return TraccarService.decrypt_password(encrypted)


def _client(token: str, timeout_connect: float = HA_CONNECT_TIMEOUT,
            timeout_read: float = HA_READ_TIMEOUT) -> httpx.AsyncClient:
    """Create an httpx async client configured for HA API."""
    return httpx.AsyncClient(
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        timeout=httpx.Timeout(timeout_read, connect=timeout_connect),
        follow_redirects=True,
    )


async def test_connection(url: str, token: str) -> dict:
    """Test connection to a HA instance. Returns config or error."""
    url = _validate_url(url)
    try:
        async with _client(token) as client:
            # Check API is running
            r = await client.get(f'{url}/api/')
            if r.status_code == 401:
                return {'ok': False, 'error': 'Invalid access token'}
            r.raise_for_status()

            # Fetch config for metadata
            r2 = await client.get(f'{url}/api/config')
            r2.raise_for_status()
            config = r2.json()

            return {
                'ok': True,
                'ha_version': config.get('version', ''),
                'location_name': config.get('location_name', ''),
                'latitude': config.get('latitude'),
                'longitude': config.get('longitude'),
            }
    except httpx.ConnectError:
        return {'ok': False, 'error': 'Connection refused — is HA running at this URL?'}
    except httpx.TimeoutException:
        return {'ok': False, 'error': 'Connection timed out'}
    except httpx.HTTPStatusError as e:
        return {'ok': False, 'error': f'HTTP {e.response.status_code}'}
    except ValueError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        logger.exception("HA test_connection error")
        return {'ok': False, 'error': str(e)}


async def fetch_states(url: str, token: str) -> list[dict]:
    """Fetch all entity states from a HA instance."""
    url = _validate_url(url)
    async with _client(token) as client:
        r = await client.get(f'{url}/api/states')
        r.raise_for_status()
        return r.json()


async def get_entity_state(url: str, token: str, entity_id: str) -> dict:
    """Fetch current state of a single entity."""
    url = _validate_url(url)
    async with _client(token) as client:
        r = await client.get(f'{url}/api/states/{entity_id}')
        r.raise_for_status()
        return r.json()


async def call_service(url: str, token: str, domain: str, service: str,
                       entity_id: str, data: Optional[dict] = None) -> bool:
    """Call a HA service (turn_on, turn_off, set_temperature, etc.)."""
    url = _validate_url(url)
    body = {'entity_id': entity_id}
    if data:
        body.update(data)
    async with _client(token) as client:
        r = await client.post(f'{url}/api/services/{domain}/{service}', json=body)
        r.raise_for_status()
        return True


def call_service_sync(url: str, token: str, domain: str, service: str,
                      entity_id: str, data: Optional[dict] = None) -> bool:
    """Synchronous version of call_service for use in management commands."""
    url = _validate_url(url)
    body = {'entity_id': entity_id}
    if data:
        body.update(data)
    r = sync_requests.post(
        f'{url}/api/services/{domain}/{service}',
        json=body,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        timeout=10,
    )
    r.raise_for_status()
    return True


def determine_controllability(domain: str) -> bool:
    return domain in CONTROLLABLE_DOMAINS


def map_domain_to_device_type(domain: str) -> str:
    return DOMAIN_TO_DEVICE_TYPE.get(domain, 'HA_DEVICE')


async def sync_home_entities(home) -> dict:
    """Sync all imported entities for a HAHome. Returns {updated, errors, offline}."""
    from iot.models import HAEntity
    token = decrypt_token(home.access_token_encrypted)
    url = home.url.rstrip('/')

    imported = HAEntity.objects.filter(home=home, is_imported=True)
    updated = 0
    errors = 0
    offline_entities = []

    try:
        states = await fetch_states(url, token)
        state_map = {s['entity_id']: s for s in states}
    except Exception as e:
        logger.warning("HA sync failed for %s: %s", home.name, e)
        home.status = 'offline'
        home.last_error = str(e)[:500]
        home.save(update_fields=['status', 'last_error'])
        return {'updated': 0, 'errors': 1, 'offline': []}

    now = timezone.now()
    for entity in imported:
        ha_state = state_map.get(entity.entity_id)
        if ha_state is None:
            offline_entities.append(entity.entity_id)
            continue
        try:
            entity.state = str(ha_state.get('state', ''))[:255]
            entity.attributes_json = ha_state.get('attributes', {})
            entity.friendly_name = ha_state.get('attributes', {}).get('friendly_name', '')[:255]
            lc = ha_state.get('last_changed')
            if lc:
                entity.last_changed = datetime.fromisoformat(lc.replace('Z', '+00:00'))
            entity.last_synced = now
            entity.save(update_fields=[
                'state', 'attributes_json', 'friendly_name', 'last_changed', 'last_synced',
            ])
            updated += 1
        except Exception:
            logger.exception("Error syncing entity %s", entity.entity_id)
            errors += 1

    home.status = 'online'
    home.last_seen = now
    home.last_error = ''
    home.save(update_fields=['status', 'last_seen', 'last_error'])

    return {'updated': updated, 'errors': errors, 'offline': offline_entities}
