"""Plain Django views for environmental-station push ingest.

Served over the plaintext ``wx.parahub.io:80`` vhost — weather consoles and
air-quality monitors cannot do TLS. Devices are unauthenticated in the HTTP
sense; each is matched to its ``EnvStation`` by an unguessable token in the URL
path (Ecowitt) or its device serial in the body (AirGradient). No session, no
CSRF: these are machine-to-machine POSTs.
"""

import json
import logging

from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import env_service
from .models import EnvStation

logger = logging.getLogger('iot.ingest')


@csrf_exempt
@require_POST
def ecowitt_ingest(request, token):
    """Ecowitt "Customized upload" (protocol = Ecowitt). The console POSTs
    form-encoded readings to ``/ecowitt/<token>``; the console expects a bare
    200 with no body-parsing, so any 2xx keeps it uploading."""
    station = EnvStation.objects.filter(
        ingest_token=token, source=EnvStation.Source.ECOWITT,
    ).first()
    if not station:
        return HttpResponseForbidden('unknown station')

    post = request.POST
    # Learn the gateway's PASSKEY once, for reference/debugging.
    passkey = post.get('PASSKEY') or ''
    if passkey and station.external_id != passkey:
        station.external_id = passkey[:64]
        station.save(update_fields=['external_id'])

    values = env_service.from_ecowitt(post)
    env_service.record_reading(station, values, raw=dict(post.items()))
    return HttpResponse('success')


@csrf_exempt
def airgradient_ingest(request, path=''):
    """AirGradient custom-server push (``httpDomain`` set on the device).

    The device runs one cycle against its server: a GET firmware-update check
    (``.../generic/os/firmware.bin``), then a POST of measurements. If the
    firmware check errors it never posts, so GET must be answered "no update"
    (204). POST bodies are parsed best-effort and stored raw; refine the field
    map in ``env_service.from_airgradient`` from a captured payload."""
    if request.method == 'GET':
        # Firmware-update poll: we serve no firmware → "up to date, continue".
        return HttpResponse(status=204)
    if request.method != 'POST':
        return HttpResponse(status=405)

    body = request.body or b''
    logger.info('airgradient push path=%s len=%d body=%s',
                request.path, len(body), body[:600].decode('utf-8', 'replace'))

    try:
        data = json.loads(body or b'{}')
        if not isinstance(data, dict):
            data = {}
    except ValueError:
        data = {}

    serial = str(data.get('serialno') or data.get('serialNo') or '').lower()
    if not serial and 'airgradient:' in request.path:
        serial = request.path.split('airgradient:', 1)[1].split('/', 1)[0].lower()

    station = None
    if serial:
        station = EnvStation.objects.filter(
            external_id__iexact=serial, source=EnvStation.Source.AIRGRADIENT,
        ).first()
    if not station:
        # Accept but don't store: lets a freshly-pointed device confirm
        # connectivity while we read the captured shape from the log.
        logger.warning('airgradient push unmatched serial=%r', serial)
        return HttpResponse('ok')

    values = env_service.from_airgradient(data)
    env_service.record_reading(station, values, raw=data)
    return HttpResponse('ok')
