"""
Server health endpoint and Netdata/Kuma monitor SSO redirects.
"""


import logging
import os
import subprocess
from ninja import Schema
from ninja.errors import HttpError
from django.core import signing
from django.http import HttpResponse
from django.core.cache import cache
from parahub.auth import GlobalAuth
from parahub.ratelimit import ratelimit, user_or_ip

from .base import router

logger = logging.getLogger(__name__)

class ServerHealthOut(Schema):
    cpu_percent: float
    ram_percent: float
    disk_percent: float
    containers_running: int
    containers_total: int
    uptime_seconds: int
    netdata_url: str = "https://netdata.parahub.io"
    uptime_kuma_url: str = "https://status.parahub.io"

@router.get("/server/health", response=ServerHealthOut, auth=GlobalAuth())
@ratelimit(group='iot:server_health', key=user_or_ip, rate='30/m')
def server_health(request):
    """Server health metrics for IoT dashboard (staff only)."""
    if not request.auth.is_staff:
        raise HttpError(403, "Staff only")

    cached = cache.get("iot:server:health")
    if cached is not None:
        return cached

    result = {
        'cpu_percent': 0, 'ram_percent': 0, 'disk_percent': 0,
        'containers_running': 0, 'containers_total': 0, 'uptime_seconds': 0,
        'netdata_url': 'https://netdata.parahub.io',
        'uptime_kuma_url': 'https://status.parahub.io',
    }

    # CPU from /proc/loadavg (1-min avg / cores)
    try:
        with open('/proc/loadavg') as f:
            load1 = float(f.read().split()[0])
        result['cpu_percent'] = round(load1 / os.cpu_count() * 100, 1)
    except Exception:
        pass

    # RAM from /proc/meminfo
    try:
        with open('/proc/meminfo') as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                meminfo[parts[0].rstrip(':')] = int(parts[1])
        total = meminfo.get('MemTotal', 1)
        available = meminfo.get('MemAvailable', 0)
        result['ram_percent'] = round((1 - available / total) * 100, 1)
    except Exception:
        pass

    # Disk from os.statvfs
    try:
        st = os.statvfs('/')
        result['disk_percent'] = round((1 - st.f_bavail / st.f_blocks) * 100, 1)
    except Exception:
        pass

    # Uptime from /proc/uptime
    try:
        with open('/proc/uptime') as f:
            result['uptime_seconds'] = int(float(f.read().split()[0]))
    except Exception:
        pass

    # Docker containers
    try:
        out = subprocess.check_output(
            ['docker', 'ps', '-a', '--format', '{{.State}}'],
            timeout=5, text=True
        )
        states = out.strip().split('\n') if out.strip() else []
        result['containers_total'] = len(states)
        result['containers_running'] = sum(1 for s in states if s == 'running')
    except Exception:
        pass

    cache.set("iot:server:health", result, 15)  # 15s TTL
    return result

MONITOR_SERVICES = {
    'netdata': 'https://netdata.parahub.io',
    'status': 'https://status.parahub.io',
}

MONITOR_SALT = 'monitor-auth'

@router.get("/monitor/{service}/", auth=None)
@ratelimit(group='iot:monitor_redirect', key='ip', rate='30/m')
def monitor_redirect(request, service: str):
    """Generate signed token and redirect to monitoring dashboard (staff only).
    Accepts JWT via Authorization header or ?token= query param (for window.open)."""
    if service not in MONITOR_SERVICES:
        raise HttpError(404, "Unknown service")

    # Authenticate: try header first, then query param
    from parahub.auth import GlobalAuth
    auth = GlobalAuth()
    account = None
    try:
        account = auth.authenticate(request, request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', ''))
    except Exception:
        pass
    if not account:
        jwt_param = request.GET.get('token', '')
        if jwt_param:
            try:
                account = auth.authenticate(request, jwt_param)
            except Exception:
                pass
    if not account or not account.is_staff:
        raise HttpError(403, "Staff only")

    signed = signing.dumps({'s': service, 'u': account.id}, salt=MONITOR_SALT)
    base = MONITOR_SERVICES[service]
    # Status dashboard lives at /dashboard (root is public status page)
    path = "/dashboard" if service == "status" else ""
    url = f"{base}{path}?_t={signed}"
    return HttpResponse(status=302, headers={'Location': url})

@router.get("/monitor-auth/", auth=None)
@ratelimit(group='iot:monitor_auth', key='ip', rate='120/m')
def monitor_auth(request):
    """Validate monitoring token or cookie (called by nginx auth_request)."""
    # Extract _t from X-Original-URI header (nginx auth_request passes original URI)
    token = request.GET.get('_t', '')
    if not token:
        original_uri = request.META.get('HTTP_X_ORIGINAL_URI', '')
        if '_t=' in original_uri:
            from urllib.parse import urlparse, parse_qs
            parsed = parse_qs(urlparse(original_uri).query)
            token = parsed.get('_t', [''])[0]
    if token:
        try:
            data = signing.loads(token, salt=MONITOR_SALT, max_age=300)
            # Valid token — return 200 with Set-Cookie for subsequent requests
            session_val = signing.dumps({'s': data['s'], 'u': data['u']}, salt=MONITOR_SALT)
            resp = HttpResponse(status=200)
            resp.set_cookie(
                '_monitor', session_val,
                max_age=3600, httponly=True, secure=True, samesite='Strict',
            )
            return resp
        except (signing.BadSignature, KeyError):
            pass

    # Check existing cookie
    cookie = request.COOKIES.get('_monitor', '')
    if cookie:
        try:
            signing.loads(cookie, salt=MONITOR_SALT, max_age=3600)
            return HttpResponse(status=200)
        except signing.BadSignature:
            pass

    return HttpResponse(status=401)
