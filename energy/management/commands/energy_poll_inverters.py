"""
Poll inverter APIs (Shelly EM first, then others) and update cell status in Redis.

Usage:
    python3 manage.py energy_poll_inverters          # one-shot
    python3 manage.py energy_poll_inverters --loop 30 # every 30s

Redis key per cell: energy:live:{cell_id} = JSON {total_production_w, producers_online, updated_at}
TTL: 120s (stale after 2 missed polls)

Status logic:
    total_production_w > 500  → GREEN (surplus)
    total_production_w > 0    → YELLOW (balanced)
    total_production_w == 0   → RED (no surplus)
    all producers offline     → keep current status (don't flap to OFFLINE on transient errors)
"""
import json
import time
import logging
from datetime import datetime, timezone as dt_tz

import redis
import requests
from django.core.management.base import BaseCommand

from energy.models import EnergyCell, EnergyProducer, EnergyConsumer, EnergyRelay
from energy import relay_service
from iot.models import HAEntity, HAHome
from iot import ha_service

logger = logging.getLogger('energy.poller')

# Surplus threshold in watts — above this, cell goes GREEN
SURPLUS_THRESHOLD_W = 500


class Command(BaseCommand):
    help = 'Poll inverter APIs and update energy cell live data in Redis'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loop', type=int, default=0,
            help='Poll interval in seconds (0 = one-shot)',
        )

    def handle(self, *args, **options):
        loop_interval = options['loop']
        r = redis.Redis(host='localhost', port=6379, db=0)

        if loop_interval:
            self.stdout.write(f'Polling inverters every {loop_interval}s...')
            while True:
                self._poll_all(r)
                time.sleep(loop_interval)
        else:
            self._poll_all(r)

    def _poll_all(self, r):
        """Poll all cells with active producers that have API URLs."""
        cells = EnergyCell.objects.exclude(status=EnergyCell.Status.OFFLINE)
        for cell in cells:
            producers = cell.producers.filter(is_active=True).exclude(inverter_api_url='')
            if not producers.exists():
                continue
            total_w = 0.0
            online = 0
            for producer in producers:
                power = self._poll_producer(producer)
                if power is not None:
                    total_w += power
                    online += 1

            # Write to Redis
            live_data = {
                'total_production_w': round(total_w, 1),
                'producers_online': online,
                'updated_at': datetime.now(dt_tz.utc).isoformat(),
            }
            r.setex(f'energy:live:{cell.id}', 120, json.dumps(live_data))

            # Update cell status based on production
            if online > 0:
                if total_w > SURPLUS_THRESHOLD_W:
                    new_status = EnergyCell.Status.GREEN
                elif total_w > 0:
                    new_status = EnergyCell.Status.YELLOW
                else:
                    new_status = EnergyCell.Status.RED

                if cell.status != new_status:
                    old = cell.status
                    cell.status = new_status
                    cell.save(update_fields=['status'])
                    logger.info(f'Cell {cell.name}: {old} → {new_status} ({total_w:.0f}W, {online} online)')
                    self._dispatch_ha_signals(cell, new_status, total_w)
                    self._dispatch_relay_signals(cell, new_status)

    def _dispatch_ha_signals(self, cell: EnergyCell, new_status: str, total_w: float):
        """Send energy signals to consumer HA entities on cell status change.

        Chain: Cell → active Consumers → Profile → online HAHomes → HAEntities with energy_signal_role.
        """
        consumer_profile_ids = list(
            EnergyConsumer.objects.filter(cell=cell, is_active=True)
            .values_list('profile_id', flat=True)
        )
        if not consumer_profile_ids:
            return

        entities = (
            HAEntity.objects.filter(
                energy_signal_role__isnull=False,
                is_imported=True,
                home__owner_id__in=consumer_profile_ids,
                home__status='online',
            )
            .select_related('home')
        )

        is_surplus = new_status == EnergyCell.Status.GREEN
        price = float(cell.current_price_eur) if cell.current_price_eur else 0.0

        for entity in entities:
            try:
                token = ha_service.decrypt_token(entity.home.access_token_encrypted)
                url = entity.home.url

                if entity.energy_signal_role == HAEntity.EnergySignalRole.SURPLUS_BOOL:
                    service = 'turn_on' if is_surplus else 'turn_off'
                    ha_service.call_service_sync(url, token, entity.domain, service, entity.entity_id)

                elif entity.energy_signal_role == HAEntity.EnergySignalRole.SURPLUS_POWER:
                    ha_service.call_service_sync(
                        url, token, 'input_number', 'set_value',
                        entity.entity_id, {'value': round(total_w, 1)},
                    )

                elif entity.energy_signal_role == HAEntity.EnergySignalRole.SURPLUS_PRICE:
                    ha_service.call_service_sync(
                        url, token, 'input_number', 'set_value',
                        entity.entity_id, {'value': price},
                    )

                logger.info(f'HA signal sent: {entity.entity_id} ({entity.energy_signal_role}) → {entity.home.name}')
            except Exception as e:
                logger.warning(f'HA signal failed: {entity.entity_id} → {entity.home.name}: {e}')

    def _dispatch_relay_signals(self, cell: EnergyCell, new_status: str):
        """Toggle direct smart relays (Shelly/Tasmota) on cell status change."""
        is_surplus = new_status == EnergyCell.Status.GREEN
        relays = EnergyRelay.objects.filter(
            consumer__cell=cell,
            consumer__is_active=True,
            is_active=True,
        )
        now = datetime.now(dt_tz.utc)
        for relay in relays:
            try:
                relay_service.switch_relay(relay.relay_type, relay.url, relay.channel, is_surplus)
                relay.last_triggered = now
                relay.last_error = ''
                relay.save(update_fields=['last_triggered', 'last_error'])
                logger.info(f'Relay {"ON" if is_surplus else "OFF"}: {relay.name} ({relay.relay_type}) → {relay.url}')
            except Exception as e:
                relay.last_error = str(e)[:500]
                relay.save(update_fields=['last_error'])
                logger.warning(f'Relay failed: {relay.name} → {relay.url}: {e}')

    def _poll_producer(self, producer: EnergyProducer) -> float | None:
        """Poll a single producer's inverter. Returns watts or None on error."""
        try:
            if producer.inverter_type == 'SHELLY':
                return self._poll_shelly(producer)
            # Other inverter types can be added here
            return None
        except Exception as e:
            logger.warning(f'Poll failed for producer {producer.profile_id} ({producer.inverter_type}): {e}')
            return None

    def _poll_shelly(self, producer: EnergyProducer) -> float | None:
        """
        Poll Shelly EM / Shelly Pro EM device.
        API: GET http://<host>/rpc/EM.GetStatus?id=0
        Response: {"id":0, "a_act_power": 1234.5, ...}

        For Gen1 Shelly EM: GET http://<host>/status
        Response: {"emeters": [{"power": 1234.5, ...}]}
        """
        url = producer.inverter_api_url.rstrip('/')
        headers = {}
        if producer.inverter_api_token:
            headers['Authorization'] = f'Bearer {producer.inverter_api_token}'

        # Try Gen2+ RPC first
        try:
            resp = requests.get(f'{url}/rpc/EM.GetStatus?id=0', headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # a_act_power = active power on phase A (watts)
                power = data.get('a_act_power', 0) + data.get('b_act_power', 0) + data.get('c_act_power', 0)
                return max(0, -power)  # Negative = export (production)
        except (requests.RequestException, ValueError):
            pass

        # Fallback to Gen1 API
        try:
            resp = requests.get(f'{url}/status', headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                emeters = data.get('emeters', [])
                if emeters:
                    power = sum(em.get('power', 0) for em in emeters)
                    return max(0, -power)  # Negative = export
        except (requests.RequestException, ValueError):
            pass

        return None
