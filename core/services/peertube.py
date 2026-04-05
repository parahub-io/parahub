"""PeerTube API client for server-to-server integration."""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PEERTUBE_URL = getattr(settings, 'PEERTUBE_URL', 'https://video.parahub.io')
PEERTUBE_INTERNAL_URL = getattr(settings, 'PEERTUBE_INTERNAL_URL', 'http://127.0.0.1:9000')


def get_admin_token():
    """Get PeerTube admin OAuth token, cached for 5 minutes."""
    from django.core.cache import cache

    cache_key = 'peertube:admin_token'
    token = cache.get(cache_key)
    if token:
        return token

    try:
        resp = requests.get(f'{PEERTUBE_INTERNAL_URL}/api/v1/oauth-clients/local', timeout=5)
        resp.raise_for_status()
        client = resp.json()

        resp = requests.post(f'{PEERTUBE_INTERNAL_URL}/api/v1/users/token', data={
            'client_id': client['client_id'],
            'client_secret': client['client_secret'],
            'grant_type': 'password',
            'response_type': 'code',
            'username': 'root',
            'password': _get_admin_password(),
        }, timeout=5)
        resp.raise_for_status()
        token = resp.json()['access_token']
        cache.set(cache_key, token, 300)
        return token
    except Exception as e:
        logger.error(f"Failed to get PeerTube admin token: {e}")
        return None


# Backward compat alias
_get_admin_token = get_admin_token


def _get_admin_password():
    """Read PeerTube admin password. Set in Django settings or env."""
    import os
    return os.getenv('PEERTUBE_ADMIN_PASSWORD', 'widohasenemacoju')


def get_video(peertube_uuid: str) -> dict | None:
    """Fetch video metadata from PeerTube by UUID."""
    try:
        resp = requests.get(
            f'{PEERTUBE_INTERNAL_URL}/api/v1/videos/{peertube_uuid}',
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch PeerTube video {peertube_uuid}: {e}")
        return None


def get_video_urls(video_data: dict) -> dict:
    """Extract useful URLs from PeerTube video API response."""
    uuid = video_data.get('uuid', '')
    short_uuid = video_data.get('shortUUID', '')

    result = {
        'peertube_url': f'{PEERTUBE_URL}/w/{short_uuid}' if short_uuid else '',
        'embed_url': f'{PEERTUBE_URL}/videos/embed/{uuid}' if uuid else '',
        'thumbnail_url': '',
        'hls_url': '',
    }

    # Thumbnail (v8.1+: thumbnails array; fallback to deprecated fields)
    thumbnails = video_data.get('thumbnails') or []
    if thumbnails:
        result['thumbnail_url'] = thumbnails[0].get('url', '')
    else:
        preview = video_data.get('previewPath') or video_data.get('thumbnailPath')
        if preview:
            result['thumbnail_url'] = f'{PEERTUBE_URL}{preview}'

    # HLS URL from streaming playlists
    for playlist in video_data.get('streamingPlaylists', []):
        if playlist.get('type') == 1:  # HLS
            result['hls_url'] = playlist.get('playlistUrl', '')
            break

    return result


def sync_video_metadata(object_video) -> bool:
    """Fetch latest metadata from PeerTube and update ObjectVideo fields."""
    video_data = get_video(str(object_video.peertube_uuid))
    if not video_data:
        return False

    urls = get_video_urls(video_data)
    changed = False

    field_map = {
        'title': video_data.get('name', ''),
        'description': video_data.get('description', '') or '',
        'duration_seconds': video_data.get('duration'),
        'thumbnail_url': urls['thumbnail_url'],
        'embed_url': urls['embed_url'],
        'peertube_url': urls['peertube_url'],
        'hls_url': urls['hls_url'],
        'is_published': video_data.get('state', {}).get('id') == 1,  # 1 = Published
    }

    for field, value in field_map.items():
        if value is not None and getattr(object_video, field) != value:
            setattr(object_video, field, value)
            changed = True

    if changed:
        object_video.save()

    return changed


def delete_video(peertube_uuid: str) -> bool:
    """Delete a video from PeerTube (admin action)."""
    token = get_admin_token()
    if not token:
        return False
    try:
        resp = requests.delete(
            f'{PEERTUBE_INTERNAL_URL}/api/v1/videos/{peertube_uuid}',
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        return resp.status_code in (200, 204, 404)
    except Exception as e:
        logger.error(f"Failed to delete PeerTube video {peertube_uuid}: {e}")
        return False


def get_user_upload_config(profile) -> dict | None:
    """
    Get PeerTube upload endpoint + channel info for a user.
    Frontend will use this to upload directly to PeerTube.
    """
    token = get_admin_token()
    if not token:
        return None

    try:
        # Find PeerTube user by username (matches profile.local_name via OIDC)
        resp = requests.get(
            f'{PEERTUBE_INTERNAL_URL}/api/v1/users',
            params={'search': profile.local_name, 'count': 1},
            headers={'Authorization': f'Bearer {token}'},
            timeout=5,
        )
        resp.raise_for_status()
        users = resp.json().get('data', [])

        if not users:
            return None

        pt_user = users[0]

        # Get user's default channel
        channels = pt_user.get('videoChannels', [])
        channel_id = channels[0]['id'] if channels else None
        channel_name = channels[0]['name'] if channels else None

        return {
            'upload_url': f'{PEERTUBE_URL}/api/v1/videos/upload',
            'peertube_user_id': pt_user['id'],
            'channel_id': channel_id,
            'channel_name': channel_name,
            'video_quota': pt_user.get('videoQuota', 0),
            'video_quota_used': pt_user.get('videoQuotaUsed', 0),
        }
    except Exception as e:
        logger.error(f"Failed to get PeerTube upload config for {profile.local_name}: {e}")
        return None
