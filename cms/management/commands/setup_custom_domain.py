"""
Issue SSL certificate and configure nginx for a custom domain.

Flow: write HTTP-only nginx → reload → certbot webroot → write HTTPS nginx → reload.

Usage:
    python manage.py setup_custom_domain cafe-central.pt
    python manage.py setup_custom_domain --check cafe-central.pt
    python manage.py setup_custom_domain --remove cafe-central.pt
"""
import re
import subprocess
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from cms.models import Site

logger = logging.getLogger(__name__)

NGINX_CUSTOM_DIR = Path('/etc/nginx/sites-enabled')
PARAHUB_SERVER_NAME = 'parahub.io'
ACME_WEBROOT = '/opt/parahub/static/'


class Command(BaseCommand):
    help = 'Setup SSL and nginx for a custom domain'

    def add_arguments(self, parser):
        parser.add_argument('domain', help='Custom domain (e.g. cafe-central.pt)')
        parser.add_argument('--check', action='store_true', help='Only verify CNAME, no cert/nginx')
        parser.add_argument('--remove', action='store_true', help='Remove cert and nginx config')

    # Same regex as API layer — only lowercase alphanumeric, hyphens, dots
    DOMAIN_RE = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')

    def handle(self, *args, **options):
        domain = options['domain'].strip().lower()

        if not self.DOMAIN_RE.match(domain):
            self.stderr.write(f"Invalid domain format: '{domain}'. Only lowercase alphanumeric, hyphens, and dots.")
            return

        if options['remove']:
            return self._remove(domain)

        # Find the site
        site = Site.objects.filter(custom_domain=domain).first()
        if not site:
            self.stderr.write(f"No site with custom_domain='{domain}' found.")
            return

        # Step 1: Verify CNAME
        if not self._verify_cname(domain):
            self.stderr.write(
                f"CNAME verification failed. '{domain}' must have a CNAME record "
                f"pointing to '{PARAHUB_SERVER_NAME}' or an A record to {settings.PARAHUB_SERVER_IP}."
            )
            site.custom_domain_verified = False
            site.save(update_fields=['custom_domain_verified'])
            return

        site.custom_domain_verified = True
        site.save(update_fields=['custom_domain_verified'])
        self.stdout.write(f"CNAME verified for {domain}")

        if options['check']:
            return

        # Step 2: Write temporary HTTP-only nginx config (for ACME challenge)
        if not self._write_nginx_http(domain):
            self.stderr.write("Failed to write HTTP nginx config — aborting")
            return
        if not self._reload_nginx():
            self.stderr.write("Failed to reload nginx after HTTP config — aborting")
            return

        # Step 3: Issue SSL certificate (certbot webroot via static/)
        if not self._issue_cert(domain):
            self.stderr.write(f"Failed to issue SSL certificate for {domain}")
            # Clean up temp config
            self._remove_nginx(domain)
            return

        # Step 4: Write full HTTPS nginx config
        if not self._write_nginx_https(domain):
            self.stderr.write("Failed to write HTTPS nginx config")
            return
        if not self._reload_nginx():
            self.stderr.write("Failed to reload nginx after HTTPS config")
            return

        site.custom_domain_ssl_ready = True
        site.save(update_fields=['custom_domain_ssl_ready'])
        self.stdout.write(self.style.SUCCESS(f"Custom domain {domain} is live!"))

    # Private/reserved IP prefixes — SSRF defense in depth
    PRIVATE_IP_PREFIXES = (
        '127.', '10.', '192.168.', '0.', '169.254.',
        '172.16.', '172.17.', '172.18.', '172.19.',
        '172.20.', '172.21.', '172.22.', '172.23.',
        '172.24.', '172.25.', '172.26.', '172.27.',
        '172.28.', '172.29.', '172.30.', '172.31.',
    )
    BLOCKED_SUFFIXES = (
        '.local', '.localhost', '.internal', '.test', '.example',
        '.invalid', '.onion', '.i2p',
    )

    def _verify_cname(self, domain: str) -> bool:
        """Check if domain points to parahub.io via CNAME or A record."""
        import socket

        # SSRF check: block reserved TLDs
        for suffix in self.BLOCKED_SUFFIXES:
            if domain.endswith(suffix):
                self.stderr.write(f"SSRF blocked: domain {domain} uses reserved suffix {suffix}")
                return False

        try:
            result = subprocess.run(
                ['dig', '+short', 'CNAME', domain],
                capture_output=True, text=True, timeout=10,
            )
            cname = result.stdout.strip().rstrip('.')
            if cname == PARAHUB_SERVER_NAME:
                return True

            try:
                ip = socket.gethostbyname(domain)
                # SSRF check: reject private/reserved IPs
                if any(ip.startswith(prefix) for prefix in self.PRIVATE_IP_PREFIXES):
                    self.stderr.write(f"SSRF blocked: domain {domain} resolves to private IP {ip}")
                    return False
                return ip == settings.PARAHUB_SERVER_IP
            except socket.gaierror:
                return False
        except Exception as e:
            logger.error(f"CNAME check failed for {domain}: {e}")
            return False

    def _issue_cert(self, domain: str) -> bool:
        """Issue Let's Encrypt cert via HTTP-01 challenge (webroot)."""
        try:
            result = subprocess.run([
                'sudo', 'certbot', 'certonly',
                '--webroot',
                '-w', ACME_WEBROOT,
                '-d', domain,
                '--non-interactive',
                '--agree-tos',
                '--email', 'admin@parahub.io',
            ], capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                self.stdout.write(f"SSL certificate issued for {domain}")
                return True
            else:
                self.stderr.write(f"certbot error: {result.stderr}")
                return False
        except Exception as e:
            self.stderr.write(f"certbot exception: {e}")
            return False

    def _write_nginx_http(self, domain: str) -> bool:
        """Write temporary HTTP-only config for ACME challenge."""
        config = f"""# Temporary HTTP-only config for ACME challenge: {domain}
# Auto-generated by: python manage.py setup_custom_domain
server {{
    listen 80;
    server_name {domain};

    location /.well-known/acme-challenge/ {{
        root {ACME_WEBROOT};
    }}

    location / {{
        return 503;
    }}
}}
"""
        config_path = NGINX_CUSTOM_DIR / f"custom-{domain}"
        if not self._write_root_file(config_path, config):
            return False
        self.stdout.write(f"HTTP-only nginx config written: {config_path}")
        return True

    def _write_nginx_https(self, domain: str) -> bool:
        """Write full HTTPS nginx config."""
        config = f"""# Custom domain: {domain}
# Auto-generated by: python manage.py setup_custom_domain
server {{
    listen 443 ssl;
    server_name {domain};

    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;

    client_max_body_size 20M;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https://*.parahub.io; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' blob: wss://parahub.io https://*.parahub.io https://api.coingecko.com https://mempool.space; worker-src 'self' blob:; child-src 'self' blob: https://video.parahub.io; frame-ancestors 'self'; base-uri 'self'; form-action 'self';" always;

    location /api/ {{
        proxy_pass http://parahub_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }}

    location /static/ {{
        alias /opt/parahub/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }}

    location /media/ {{
        alias /opt/parahub/media/;
        expires 7d;
        add_header Cache-Control "public";
        access_log off;
    }}

    location / {{
        proxy_pass http://parahub_frontend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }}
}}

server {{
    listen 80;
    server_name {domain};

    location /.well-known/acme-challenge/ {{
        root {ACME_WEBROOT};
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}
"""
        config_path = NGINX_CUSTOM_DIR / f"custom-{domain}"
        if not self._write_root_file(config_path, config):
            return False
        self.stdout.write(f"HTTPS nginx config written: {config_path}")
        return True

    def _write_root_file(self, path: Path, content: str) -> bool:
        """Write a file under root-owned NGINX_CUSTOM_DIR via sudo tee.

        The Django process (uvicorn, running as an unprivileged user) has no
        direct write access to /etc/nginx/sites-enabled — only the sudo'd
        subprocess calls already used for certbot/nginx-reload can reach it.
        """
        result = subprocess.run(
            ['sudo', 'tee', str(path)],
            input=content, text=True, capture_output=True,
        )
        if result.returncode != 0:
            self.stderr.write(f"Failed to write {path}: {result.stderr}")
            return False
        return True

    def _reload_nginx(self) -> bool:
        """Test and reload nginx. Returns True on success."""
        test = subprocess.run(['sudo', 'nginx', '-t'], capture_output=True, text=True)
        if test.returncode != 0:
            self.stderr.write(f"Nginx config test failed: {test.stderr}")
            return False
        subprocess.run(['sudo', 'systemctl', 'reload', 'nginx'], check=True)
        self.stdout.write("Nginx reloaded")
        return True

    def _remove_nginx(self, domain: str):
        """Remove nginx config file and reload."""
        config_path = NGINX_CUSTOM_DIR / f"custom-{domain}"
        if config_path.exists():
            result = subprocess.run(['sudo', 'rm', '-f', str(config_path)], capture_output=True, text=True)
            if result.returncode != 0:
                self.stderr.write(f"Failed to remove {config_path}: {result.stderr}")
                return
            self._reload_nginx()

    def _remove(self, domain: str):
        """Remove custom domain: nginx config + DB cleanup."""
        self._remove_nginx(domain)
        self.stdout.write(f"Removed nginx config for {domain}")

        site = Site.objects.filter(custom_domain=domain).first()
        if site:
            site.custom_domain = ''
            site.custom_domain_verified = False
            site.custom_domain_ssl_ready = False
            site.save(update_fields=['custom_domain', 'custom_domain_verified', 'custom_domain_ssl_ready'])
            self.stdout.write(f"Cleared custom_domain on site {site.id}")

        self.stdout.write(self.style.SUCCESS(f"Custom domain {domain} removed."))
