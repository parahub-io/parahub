"""Direct smart relay control (Shelly, Tasmota) — no Home Assistant required.

Used by energy poller to toggle relays when cell status changes.
All calls are synchronous (management command context).
"""
import logging

import requests

logger = logging.getLogger('energy.relay')

# Timeout for relay HTTP calls (local network devices)
RELAY_TIMEOUT = 5


def switch_relay(relay_type: str, url: str, channel: int, turn_on: bool) -> bool:
    """Toggle a relay on/off. Returns True on success."""
    url = url.rstrip('/')
    if relay_type == 'SHELLY_GEN2':
        return _switch_shelly_gen2(url, channel, turn_on)
    elif relay_type == 'SHELLY_GEN1':
        return _switch_shelly_gen1(url, channel, turn_on)
    elif relay_type == 'TASMOTA':
        return _switch_tasmota(url, channel, turn_on)
    else:
        raise ValueError(f'Unknown relay type: {relay_type}')


def test_relay(relay_type: str, url: str, channel: int) -> dict:
    """Test connection to a relay device. Returns {ok, info, error}."""
    url = url.rstrip('/')
    try:
        if relay_type == 'SHELLY_GEN2':
            r = requests.post(
                f'{url}/rpc/Switch.GetStatus',
                json={'id': channel},
                timeout=RELAY_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            return {'ok': True, 'info': f"output={data.get('output')}, source={data.get('source', '?')}"}

        elif relay_type == 'SHELLY_GEN1':
            r = requests.get(f'{url}/relay/{channel}', timeout=RELAY_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            return {'ok': True, 'info': f"ison={data.get('ison')}"}

        elif relay_type == 'TASMOTA':
            r = requests.get(f'{url}/cm?cmnd=Status%200', timeout=RELAY_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            name = data.get('Status', {}).get('DeviceName', '?')
            return {'ok': True, 'info': f"device={name}"}

        return {'ok': False, 'error': f'Unknown relay type: {relay_type}'}

    except requests.ConnectionError:
        return {'ok': False, 'error': 'Connection refused — is the device online?'}
    except requests.Timeout:
        return {'ok': False, 'error': 'Connection timed out'}
    except requests.HTTPError as e:
        return {'ok': False, 'error': f'HTTP {e.response.status_code}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _switch_shelly_gen2(url: str, channel: int, turn_on: bool) -> bool:
    """Shelly Gen2+ RPC: POST /rpc/Switch.Set {"id": 0, "on": true}"""
    r = requests.post(
        f'{url}/rpc/Switch.Set',
        json={'id': channel, 'on': turn_on},
        timeout=RELAY_TIMEOUT,
    )
    r.raise_for_status()
    return True


def _switch_shelly_gen1(url: str, channel: int, turn_on: bool) -> bool:
    """Shelly Gen1: GET /relay/<channel>?turn=on|off"""
    action = 'on' if turn_on else 'off'
    r = requests.get(f'{url}/relay/{channel}?turn={action}', timeout=RELAY_TIMEOUT)
    r.raise_for_status()
    return True


def _switch_tasmota(url: str, channel: int, turn_on: bool) -> bool:
    """Tasmota: GET /cm?cmnd=Power<N> ON|OFF (Power0 = all, Power1 = ch1)"""
    action = 'ON' if turn_on else 'OFF'
    power = f'Power{channel}' if channel > 0 else 'Power'
    r = requests.get(f'{url}/cm?cmnd={power}%20{action}', timeout=RELAY_TIMEOUT)
    r.raise_for_status()
    return True
