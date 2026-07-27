"""Poll AirGradient stations over the mesh and store readings.

Bridge mechanism for the "now" case: AirGradient exposes a local ``/measures/
current`` HTTP API but sits on a mesh node's private LAN (no inbound route from
the cloud). We SSH-hop through the node that holds its DHCP lease — the device
serial IS its WiFi MAC, so the lease lookup needs no per-station config — and
GET the live measurement.

Superseded once the device is switched to push (``httpDomain`` → wx.parahub.io);
delete this command and its timer then.
"""

import json
import logging

from django.core.management.base import BaseCommand

from iot.api.mesh import _mesh_ssh
from iot import env_service
from iot.models import EnvStation, IoTDevice

logger = logging.getLogger('iot.env_poll')


def _mac_from_serial(serial: str) -> str:
    """AirGradient serial 'd83bda1ac64c' → MAC 'd8:3b:da:1a:c6:4c'."""
    s = serial.strip().lower().replace(':', '')
    return ':'.join(s[i:i + 2] for i in range(0, len(s), 2))


def _haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, atan2, sqrt
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def _nearest_node_ygg(station):
    """Yggdrasil address of the mesh router nearest to the station, or None."""
    loc = station.location
    best, best_km = None, None
    for dev in IoTDevice.objects.filter(device_type='MESH_ROUTER',
                                        latitude__isnull=False, longitude__isnull=False):
        ygg = (dev.connection_info or {}).get('yggdrasil_address')
        if not ygg:
            continue
        km = _haversine_km(loc.y, loc.x, dev.latitude, dev.longitude)
        if best_km is None or km < best_km:
            best, best_km = ygg, km
    return best


class Command(BaseCommand):
    help = 'Poll AirGradient stations via their mesh node and store readings.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true',
                            help='(Compat flag — this command always runs one pass.)')

    def handle(self, *args, **opts):
        stations = EnvStation.objects.filter(
            source=EnvStation.Source.AIRGRADIENT).exclude(external_id='')
        if not stations:
            self.stdout.write('No AirGradient stations to poll.')
            return

        for st in stations:
            ygg = _nearest_node_ygg(st)
            if not ygg:
                logger.warning('poll %s: no mesh node with coordinates', st.name)
                continue
            mac = _mac_from_serial(st.external_id)
            # Lease file lives on tmpfs and is wiped by a router reboot while the
            # client keeps using its IP until renewal — fall back to the ARP/neigh
            # table (IPv4 only: the URL below has no brackets) so a reboot doesn't
            # blind the poll for hours.
            cmd = (
                f'IP=$(awk -v m={mac} \'tolower($2)==m{{print $3}}\' /tmp/dhcp.leases | head -1); '
                f'[ -z "$IP" ] && IP=$(ip neigh | awk -v m={mac} \'tolower($5)==m && $1 !~ /:/ {{print $1; exit}}\'); '
                f'[ -n "$IP" ] && curl -s -m 8 "http://$IP/measures/current" || echo NOLEASE'
            )
            try:
                res = _mesh_ssh(ygg, cmd, timeout=15)
            except Exception as e:  # noqa: BLE001 — network hop, log and move on
                logger.warning('poll %s: ssh failed: %s', st.name, e)
                continue

            out = (res.stdout or '').strip()
            if not out or out == 'NOLEASE':
                logger.warning('poll %s: device MAC %s not in leases on %s', st.name, mac, ygg)
                continue
            try:
                data = json.loads(out)
            except ValueError:
                logger.warning('poll %s: non-JSON response: %s', st.name, out[:200])
                continue

            values = env_service.from_airgradient(data)
            env_service.record_reading(st, values, raw=data)
            aqi = st.latest.get('aqi')
            self.stdout.write(self.style.SUCCESS(
                f'{st.name}: pm25={values.get("pm25")} co2={values.get("co2")} '
                f'temp={values.get("temperature")} aqi={aqi}'))
