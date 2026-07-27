"""
TCP-probe mesh routers' Yggdrasil SSH port to catch the ygg-inbound-dead
wedge: outbound heartbeats keep flowing while inbound connections time out,
leaving the node unmanageable (no SSH, no mesh-pass bind, no wifi/mullvad
API). Results feed the heartbeat reply's ygg_inbound_dead flag so the node
self-heals (yggdrasil restart -> reboot ladder) and the /iot device card
shows the unreachable state.

Runs from parahub-mesh-probe.timer every 2 minutes. State lives in cache
with a short TTL on purpose: if this probe stops running the verdict
evaporates instead of going stale — a stale "dead" must never keep
rebooting healthy nodes.
"""

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from iot.models import IoTDevice
from iot.api.mesh import ygg_probe_key, YGG_PROBE_TTL, YGG_PROBE_DEAD_AFTER

# Only heartbeat-fresh nodes are probed: a fully offline node can't act on
# the flag anyway and already shows as offline. Matches _GUEST_GW_FRESH.
_FRESH = timedelta(minutes=15)
_TIMEOUT = 6


def _tcp_ok(addr: str) -> bool:
    try:
        with socket.create_connection((addr, 22), timeout=_TIMEOUT):
            return True
    except OSError:
        return False


class Command(BaseCommand):
    help = "Probe mesh routers' Yggdrasil SSH inbound (tcp/22); feeds the heartbeat self-heal flag"

    def handle(self, *args, **options):
        now = timezone.now()
        targets = {}
        for d in IoTDevice.objects.filter(
            device_type='MESH_ROUTER', last_seen__gte=now - _FRESH,
        ):
            addr = (d.connection_info or {}).get('yggdrasil_address')
            if addr and addr != 'unknown':
                targets[d.device_id] = addr

        down = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(_tcp_ok, addr): mac for mac, addr in targets.items()
            }
            for fut in as_completed(futures):
                mac = futures[fut]
                ok = fut.result()
                prev = cache.get(ygg_probe_key(mac)) or {}
                fails = 0 if ok else prev.get('fails', 0) + 1
                cache.set(ygg_probe_key(mac), {
                    'ok': ok,
                    'fails': fails,
                    'dead': fails >= YGG_PROBE_DEAD_AFTER,
                    'ts': now.isoformat(),
                }, YGG_PROBE_TTL)
                if not ok:
                    down.append(mac)

        suffix = f": {', '.join(sorted(down))}" if down else ""
        self.stdout.write(
            f"probed {len(targets)} nodes, {len(down)} inbound-down{suffix}"
        )
