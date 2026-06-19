"""
CMS mirror support — federation WS broadcast helper.

The legacy post_save signal that spawned daemon threads for git mirror writes
was removed 2026-04-11 after days of lock-contention, dual-write races, and
intermediate-state corruption (see PK/cms-system.md).

Mirror writes are now drained single-threaded by `cms_mirror_drain` management
command, run on a systemd timer (`parahub-cms-mirror.timer`, every 2 min).
The drainer imports `_broadcast_cms_update` below to fire federation WS events
for posts it actually committed as published.
"""
from django.conf import settings


def _broadcast_cms_update(post, commit: str):
    """Broadcast cms_update to federation WS bus."""
    if not getattr(settings, 'FEDERATION_ENABLED', False):
        return

    from parahub.services.ws_publish import ws_publish

    ws_publish('feed:federation', {
        'type': 'cms_update',
        'domain': getattr(settings, 'FEDERATION_DOMAIN', 'parahub.io'),
        'commit': commit,
        'records': [{
            'action': 'published',
            'establishment': post.establishment.slug,
            'post': post.slug,
            'lang': post.language,
            'title': post.title,
        }],
    })
