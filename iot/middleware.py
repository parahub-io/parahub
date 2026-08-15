"""Device console journal.

Every mutating call on `/api/v1/iot/devices/{ulid}/...` — plus the two GETs that
hand out a secret — lands in `core.ObjectActionLog` with the actor's effective
role at that moment. Middleware rather than per-endpoint calls on purpose: the
device console is ~25 endpoints across three modules and grows, and a journal
that a new endpoint can forget to write is worse than none (it reads as
complete while missing exactly the action someone later asks about).

Never records values from a request body — only its keys. A `wifi-config` call
carries the WiFi password, and a journal the owner can read must not become a
second place secrets live.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# ULID: Crockford base32, no I/L/O/U
_DEVICE_PATH_RE = re.compile(
    r'^/api/v1/iot/devices/(?P<device_id>[0-9ABCDEFGHJKMNPQRSTVWXYZ]{26})(?P<rest>/.*)?$',
    re.IGNORECASE,
)
_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
# GETs worth a line: they disclose a credential rather than change state
_SECRET_READS = {'root-password', 'wifi-password'}
_MAX_BODY_BYTES = 64 * 1024


def _action_slug(rest: str) -> str:
    """First path segment after the device id ('' → the device itself)."""
    segments = [s for s in (rest or '').split('/') if s]
    return segments[0].lower() if segments else 'device'


def _body_keys(request):
    """Keys of a JSON body, never values. None when there is nothing useful."""
    raw = getattr(request, '_body', None)
    if not raw or len(raw) > _MAX_BODY_BYTES:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return sorted(data.keys())[:20] if isinstance(data, dict) else None


class DeviceActionLogMiddleware:
    """Writes one ObjectActionLog row per completed device-console action."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._record(request, response)
        except Exception:
            # A journal must never take down the action it journals
            logger.exception("Device action log failed")
        return response

    def _record(self, request, response):
        match = _DEVICE_PATH_RE.match(request.path)
        if not match:
            return

        method = request.method
        slug = _action_slug(match.group('rest'))
        is_secret_read = method == 'GET' and slug in _SECRET_READS
        if method not in _MUTATING_METHODS and not is_secret_read:
            return

        status = getattr(response, 'status_code', 0)
        # 2xx/3xx = it happened; 403 = someone with access reached past their
        # role, which is exactly what a journal exists to show. Anonymous 401s
        # and unknown-device 404s are noise (and have no actor to name).
        if not (status < 400 or status == 403):
            return

        profile = getattr(request, 'auth_profile', None)
        if profile is None:
            return

        from core.access import get_role
        from core.models import ObjectActionLog
        from .models import IoTDevice

        device_id = match.group('device_id')
        device = IoTDevice.objects.filter(id=device_id).only('id', 'owner_id').first()
        # Gone = this call deleted it (or transferred it away); the role that
        # allowed it is no longer resolvable, and inventing one would lie.
        role = get_role(device, profile) if device else ''

        detail = {'method': method, 'status': status}
        keys = _body_keys(request)
        if keys:
            detail['fields'] = keys

        ObjectActionLog.objects.create(
            object_id=device_id,
            actor=profile,
            role=role or '',
            action=f'{slug}:read' if is_secret_read else slug,
            detail=detail,
        )
