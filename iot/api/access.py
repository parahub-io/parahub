"""
Role-gated device fetch shared by every IoT endpoint module.

Effective role ladder (core.access): OWNER (the owner FK) > MANAGER > VIEWER.
Device capability mapping:
  VIEWER  — see the device, status, telemetry, positions/history
  MANAGER — everything a viewer can + device administration (rename, location,
            WiFi/VPN/network config, passwords, diagnostics)
  OWNER   — everything + delete, sharing grants, ownership transfer
"""

from django.http import Http404
from ninja.errors import HttpError

from core.access import ROLE_VIEWER, get_role, role_satisfies
from ..models import IoTDevice


def get_device_for(profile, device_id, min_role=ROLE_VIEWER, require_mesh=False):
    """Fetch a device enforcing ``min_role`` for ``profile``.

    404 when the device doesn't exist OR the profile has no access at all
    (existence is not leaked); 403 when access exists but the role is too low.
    """
    if not profile:
        raise HttpError(401, "Authentication required")
    try:
        device = IoTDevice.objects.get(id=device_id)
    except IoTDevice.DoesNotExist:
        raise Http404("Device not found")
    role = get_role(device, profile)
    if role is None:
        raise Http404("Device not found")
    if not role_satisfies(role, min_role):
        raise HttpError(403, "Insufficient device permissions")
    if require_mesh and device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    device.access_role = role
    return device
