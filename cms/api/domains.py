"""
Custom domains: validation, CNAME verify, SSL issue/removal triggers.
"""


import logging
import socket

from ninja import Schema
from ninja.errors import HttpError

from django.conf import settings

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile
from geo.permissions import get_establishment_for_action, SIGNING_ROLES
from ..models import Site

from .base import router
from .helpers import _require_profile_owner
from .sites import _get_site_for_est, _get_site_for_profile

logger = logging.getLogger(__name__)

class CustomDomainIn(Schema):
    domain: str

class CustomDomainStatus(Schema):
    custom_domain: str
    custom_domain_verified: bool
    custom_domain_ssl_ready: bool
    cname_target: str = 'parahub.io'
    message: str = ''

# Reserved TLDs and suffixes that should never be used as custom domains
_BLOCKED_DOMAIN_SUFFIXES = (
    '.local', '.localhost', '.internal', '.test', '.example',
    '.invalid', '.onion', '.i2p',
)

# Private/reserved IP prefixes for SSRF protection
_PRIVATE_IP_PREFIXES = (
    '127.', '10.', '192.168.', '0.',
    '169.254.',  # Link-local / cloud metadata
    '172.16.', '172.17.', '172.18.', '172.19.',
    '172.20.', '172.21.', '172.22.', '172.23.',
    '172.24.', '172.25.', '172.26.', '172.27.',
    '172.28.', '172.29.', '172.30.', '172.31.',
)

def _validate_custom_domain(domain: str):
    """Validate custom domain is not internal/reserved. Raises HttpError on failure."""
    import re
    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$', domain):
        raise HttpError(400, "Invalid domain format")

    # Block parahub.io subdomains
    if domain.endswith('.parahub.io') or domain == 'parahub.io':
        raise HttpError(400, "Cannot use parahub.io subdomains as custom domain")

    # Block reserved TLDs (SSRF protection)
    for suffix in _BLOCKED_DOMAIN_SUFFIXES:
        if domain.endswith(suffix) or domain == suffix.lstrip('.'):
            raise HttpError(400, f"Domain with '{suffix}' suffix is not allowed")

    # Block uniqueness collision
    existing = Site.objects.filter(custom_domain=domain).first()
    # (caller handles exclude for own site)

    # Proactive SSRF check: resolve the domain and reject private IPs
    try:
        ip = socket.gethostbyname(domain)
        if any(ip.startswith(prefix) for prefix in _PRIVATE_IP_PREFIXES) or ip == '::1':
            logger.warning(f"SSRF blocked: domain {domain} resolves to private IP {ip}")
            raise HttpError(400, "Domain resolves to a private/reserved IP address")
    except socket.gaierror:
        pass  # Domain doesn't resolve yet — OK, user may not have set DNS yet

def _trigger_ssl_setup(domain: str):
    """Run SSL cert issuance + nginx config in the background pool (with Redis-based concurrency guard)."""
    from django.core.management import call_command
    from django.core.cache import cache
    from parahub.background import spawn

    lock_key = f'ssl_setup:{domain}'
    if not cache.add(lock_key, '1', timeout=600):  # 10 min lock
        logger.info(f"SSL setup already running for {domain}, skipping")
        return

    def _run():
        try:
            call_command('setup_custom_domain', domain)
        except Exception:
            logger.exception(f"SSL setup failed for {domain}")
        finally:
            cache.delete(lock_key)

    spawn(_run, label=f'ssl_setup:{domain}')
    logger.info(f"SSL setup triggered in background for {domain}")

def _trigger_ssl_removal(domain: str):
    """Remove nginx config for a custom domain in background."""
    from pathlib import Path
    import subprocess
    from parahub.background import spawn

    def _run():
        try:
            config_path = Path(f'/etc/nginx/sites-enabled/custom-{domain}')
            if config_path.exists():
                config_path.unlink()
                subprocess.run(['sudo', 'nginx', '-t'], capture_output=True, text=True, check=True)
                subprocess.run(['sudo', 'systemctl', 'reload', 'nginx'], check=True)
                logger.info(f"Nginx config removed for {domain}")
        except Exception:
            logger.exception(f"SSL removal failed for {domain}")

    spawn(_run, label=f'ssl_removal:{domain}')

@router.post('/sites/by-establishment/{establishment_id}/domain/', response=CustomDomainStatus, auth=ProfileAuth())
@ratelimit(group='cms:set_domain', key=user_or_ip, rate='10/h')
def set_custom_domain(request, establishment_id: str, payload: CustomDomainIn):
    """Set a custom domain for a site. OWNER/ADMIN only."""
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    site = _get_site_for_est(establishment_id)
    domain = payload.domain.strip().lower()

    if not domain:
        # Clear custom domain — also remove nginx/SSL config
        old_domain = site.custom_domain
        site.custom_domain = ''
        site.custom_domain_verified = False
        site.custom_domain_ssl_ready = False
        site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])
        if old_domain:
            _trigger_ssl_removal(old_domain)
        return CustomDomainStatus(
            custom_domain='', custom_domain_verified=False,
            custom_domain_ssl_ready=False, message='Custom domain removed',
        )

    # Centralized validation: format, reserved TLDs, SSRF, parahub.io block
    _validate_custom_domain(domain)

    # Check not already taken by another site
    existing = Site.objects.filter(custom_domain=domain).exclude(id=site.id).first()
    if existing:
        raise HttpError(400, "Domain already in use by another site")

    site.custom_domain = domain
    site.custom_domain_verified = False
    site.custom_domain_ssl_ready = False
    site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])

    return CustomDomainStatus(
        custom_domain=domain, custom_domain_verified=False,
        custom_domain_ssl_ready=False,
        message=f'Set domain to {domain}. Create a CNAME record pointing to parahub.io, then verify.',
    )

@router.post('/sites/by-establishment/{establishment_id}/domain/verify/', response=CustomDomainStatus, auth=ProfileAuth())
def verify_custom_domain(request, establishment_id: str):
    """Verify CNAME for custom domain. OWNER/ADMIN only. Rate limited: 1 per 30s per profile."""
    import subprocess as sp
    from django.core.cache import cache
    profile: Profile = request.auth
    get_establishment_for_action(establishment_id, profile, SIGNING_ROLES)

    cache_key = f'cms:domain_verify:{profile.id}'
    if cache.get(cache_key):
        raise HttpError(429, "Please wait before verifying again")
    cache.set(cache_key, 1, timeout=30)

    site = _get_site_for_est(establishment_id)
    domain = site.custom_domain
    if not domain:
        raise HttpError(400, "No custom domain set")

    # Check CNAME or A record
    verified = False
    try:
        result = sp.run(['dig', '+short', 'CNAME', domain], capture_output=True, text=True, timeout=10)
        cname = result.stdout.strip().rstrip('.')
        if cname == 'parahub.io':
            verified = True
    except Exception:
        pass

    if not verified:
        try:
            ip = socket.gethostbyname(domain)
            if ip == settings.PARAHUB_SERVER_IP:
                verified = True
        except socket.gaierror:
            pass

    site.custom_domain_verified = verified
    site.save(update_fields=['custom_domain_verified'])

    msg = 'CNAME verified!' if verified else f'Verification failed. Point {domain} CNAME to parahub.io'

    # Auto-trigger SSL setup if verified and not yet SSL-ready
    if verified and not site.custom_domain_ssl_ready:
        _trigger_ssl_setup(domain)
        msg = 'CNAME verified! SSL certificate is being issued — this may take a minute.'

    return CustomDomainStatus(
        custom_domain=domain,
        custom_domain_verified=verified,
        custom_domain_ssl_ready=site.custom_domain_ssl_ready,
        message=msg,
    )

@router.post('/sites/by-profile/{profile_name}/domain/', response=CustomDomainStatus, auth=ProfileAuth())
@ratelimit(group='cms:set_domain', key=user_or_ip, rate='10/h')
def set_profile_custom_domain(request, profile_name: str, payload: CustomDomainIn):
    """Set a custom domain for a profile site. Owner only."""
    _require_profile_owner(request, profile_name)
    site = _get_site_for_profile(profile_name)
    domain = payload.domain.strip().lower()

    if not domain:
        old_domain = site.custom_domain
        site.custom_domain = ''
        site.custom_domain_verified = False
        site.custom_domain_ssl_ready = False
        site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])
        if old_domain:
            _trigger_ssl_removal(old_domain)
        return CustomDomainStatus(
            custom_domain='', custom_domain_verified=False,
            custom_domain_ssl_ready=False, message='Custom domain removed',
        )

    # Centralized validation: format, reserved TLDs, SSRF, parahub.io block
    _validate_custom_domain(domain)

    existing = Site.objects.filter(custom_domain=domain).exclude(id=site.id).first()
    if existing:
        raise HttpError(400, "Domain already in use by another site")

    site.custom_domain = domain
    site.custom_domain_verified = False
    site.custom_domain_ssl_ready = False
    site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])

    return CustomDomainStatus(
        custom_domain=domain, custom_domain_verified=False,
        custom_domain_ssl_ready=False,
        message=f'Set domain to {domain}. Create a CNAME record pointing to parahub.io, then verify.',
    )

@router.post('/sites/by-profile/{profile_name}/domain/verify/', response=CustomDomainStatus, auth=ProfileAuth())
def verify_profile_custom_domain(request, profile_name: str):
    """Verify CNAME for custom domain. Owner only. Rate limited: 1 per 30s per profile."""
    import subprocess as sp
    from django.core.cache import cache
    _require_profile_owner(request, profile_name)
    profile: Profile = request.auth

    cache_key = f'cms:domain_verify:{profile.id}'
    if cache.get(cache_key):
        raise HttpError(429, "Please wait before verifying again")
    cache.set(cache_key, 1, timeout=30)
    site = _get_site_for_profile(profile_name)
    domain = site.custom_domain
    if not domain:
        raise HttpError(400, "No custom domain set")

    verified = False
    try:
        result = sp.run(['dig', '+short', 'CNAME', domain], capture_output=True, text=True, timeout=10)
        cname = result.stdout.strip().rstrip('.')
        if cname == 'parahub.io':
            verified = True
    except Exception:
        pass

    if not verified:
        try:
            ip = socket.gethostbyname(domain)
            if ip == settings.PARAHUB_SERVER_IP:
                verified = True
        except socket.gaierror:
            pass

    site.custom_domain_verified = verified
    site.save(update_fields=['custom_domain_verified'])

    msg = 'CNAME verified!' if verified else f'Verification failed. Point {domain} CNAME to parahub.io'

    if verified and not site.custom_domain_ssl_ready:
        _trigger_ssl_setup(domain)
        msg = 'CNAME verified! SSL certificate is being issued — this may take a minute.'

    return CustomDomainStatus(
        custom_domain=domain,
        custom_domain_verified=verified,
        custom_domain_ssl_ready=site.custom_domain_ssl_ready,
        message=msg,
    )
