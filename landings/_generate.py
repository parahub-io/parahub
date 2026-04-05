#!/usr/bin/env python3
"""
Static landing page generator.

Reads config.yaml + i18n JSON files → generates static HTML per locale.
Also generates sitemap.xml and nginx config.

Usage:
    python3 landings/_generate.py              # generate all landings
    python3 landings/_generate.py condo        # generate specific landing
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
LOCALES_DIR = PROJECT_DIR / 'frontend' / 'locales'
STYLE_CSS = (BASE_DIR / 'style.css').read_text() if (BASE_DIR / 'style.css').exists() else ''

LOCALES = [
    {'code': 'en', 'lang': 'en-US', 'name': 'English'},
    {'code': 'pt', 'lang': 'pt-PT', 'name': 'Português'},
    {'code': 'es', 'lang': 'es-ES', 'name': 'Español'},
    {'code': 'fr', 'lang': 'fr-FR', 'name': 'Français'},
    {'code': 'de', 'lang': 'de-DE', 'name': 'Deutsch'},
    {'code': 'ru', 'lang': 'ru-RU', 'name': 'Русский'},
]

# Locales hidden from the footer language switcher (pages still generated, hreflang preserved)
HIDDEN_FOOTER_LOCALES = {'ru'}

FOOTER_TAGLINES = {
    'en': 'Open-source civic infrastructure',
    'pt': 'Infraestrutura cívica open-source',
    'es': 'Infraestructura cívica de código abierto',
    'fr': 'Infrastructure civique open-source',
    'de': 'Open-Source-Bürgerinfrastruktur',
    'ru': 'Гражданская инфраструктура с открытым кодом',
}

# Lucide SVG icons (24x24, stroke-width 2, no fill)
LUCIDE_ICONS = {
    'vote': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 12 2 2 4-4"/><path d="M5 7c0-1.1.9-2 2-2h10a2 2 0 0 1 2 2v12H5V7Z"/><path d="M22 19H2"/></svg>',
    'landmark': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" x2="21" y1="22" y2="22"/><line x1="6" x2="6" y1="18" y2="11"/><line x1="10" x2="10" y1="18" y2="11"/><line x1="14" x2="14" y1="18" y2="11"/><line x1="18" x2="18" y1="18" y2="11"/><polygon points="12 2 20 7 4 7"/></svg>',
    'receipt': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/></svg>',
    'message-circle': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg>',
    'link-2': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></svg>',
    'heart': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>',
    # Common icons for future landings
    'shield': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>',
    'zap': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/></svg>',
    'globe': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>',
    'users': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    'map-pin': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>',
    'truck': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>',
    'sun': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
    'calendar': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>',
    'handshake': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2"/><path d="M3 3 2 14h2"/><path d="m8 7-1.25-1.25A1 1 0 0 0 6 5.5L3 4"/></svg>',
    'package': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>',
    'clock': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    'eye': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>',
    'bell': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
    'lock': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    'activity': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/></svg>',
    'eye-off': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/></svg>',
    'volume-2': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/></svg>',
}


def load_translations(namespace: str, locale_code: str) -> dict:
    """Load translation keys for a namespace from locale JSON."""
    locale_file = LOCALES_DIR / locale_code / f'{namespace}.json'
    if not locale_file.exists():
        print(f'  WARNING: {locale_file} not found, skipping')
        return {}
    with open(locale_file) as f:
        data = json.load(f)
    # Namespace is the top-level key (e.g. {"condo": {...}})
    return data.get(namespace, data)


def get_locale_path(locale_code: str, default_locale: str) -> str:
    """Get URL path for a locale (default locale = /)."""
    if locale_code == default_locale:
        return '/'
    return f'/{locale_code}/'


def build_alternates(subdomain: str, default_locale: str, exclude: set = None) -> list:
    """Build hreflang alternate links for locales (optionally excluding some)."""
    alternates = []
    for loc in LOCALES:
        if exclude and loc['code'] in exclude:
            continue
        path = get_locale_path(loc['code'], default_locale)
        alternates.append({
            'code': loc['code'],
            'lang': loc['lang'],
            'name': loc['name'],
            'path': path,
        })
    return alternates


OG_LOCALE_MAP = {
    'en': 'en_US', 'pt': 'pt_PT', 'es': 'es_ES',
    'fr': 'fr_FR', 'de': 'de_DE', 'ru': 'ru_RU',
}


def discover_all_landings() -> list:
    """Discover all landings and return list of {name, subdomain, label} dicts."""
    landings = []
    for item in sorted(BASE_DIR.iterdir()):
        if item.is_dir() and (item / 'config.yaml').exists():
            with open(item / 'config.yaml') as f:
                cfg = yaml.safe_load(f)
            landings.append({
                'name': item.name,
                'subdomain': cfg['subdomain'],
            })
    return landings


def generate_landing(landing_name: str, all_landings: list = None):
    """Generate all locale variants for a landing page."""
    landing_dir = BASE_DIR / landing_name
    config_file = landing_dir / 'config.yaml'

    if not config_file.exists():
        print(f'ERROR: {config_file} not found')
        return False

    with open(config_file) as f:
        config = yaml.safe_load(f)

    subdomain = config['subdomain']
    default_locale = config['default_locale']
    namespace = config['i18n_namespace']
    cta_path = config['cta_path']
    from_param = config['from_param']
    problems_count = config.get('problems_count', 3)
    features_count = config.get('features_count', 6)
    steps_count = config.get('steps_count', 3)
    feature_icon_names = config.get('feature_icons', [])

    # Resolve feature icons
    feature_icons_svg = []
    for name in feature_icon_names:
        feature_icons_svg.append(LUCIDE_ICONS.get(name, ''))

    # Jinja2 environment
    env = Environment(
        loader=FileSystemLoader(str(BASE_DIR)),
        autoescape=False,
    )
    template = env.get_template('_template.html')

    # Cross-links to other landings (exclude self)
    cross_links = []
    if all_landings:
        for l in all_landings:
            if l['subdomain'] != subdomain:
                cross_links.append({
                    'url': f"https://{l['subdomain']}.parahub.io",
                    'label': l['subdomain'].capitalize(),
                })

    alternates = build_alternates(subdomain, default_locale, exclude=HIDDEN_FOOTER_LOCALES)
    output_dir = landing_dir / 'output'
    output_dir.mkdir(exist_ok=True)

    generated = []

    for loc in LOCALES:
        locale_code = loc['code']
        t = load_translations(namespace, locale_code)
        if not t:
            continue

        locale_path = get_locale_path(locale_code, default_locale)

        # Build locale-aware CTA URL
        if locale_code == 'en':
            cta_locale_path = cta_path
        else:
            cta_locale_path = f'/{locale_code}{cta_path}'
        cta_url = f'https://parahub.io{cta_locale_path}?from={from_param}'

        # Collect section data
        problems = [t.get(f'landing_problem_{i}', '') for i in range(1, problems_count + 1)]
        features = []
        for i in range(1, features_count + 1):
            features.append({
                'title': t.get(f'landing_feature_{i}_title', ''),
                'desc': t.get(f'landing_feature_{i}_desc', ''),
                'icon': feature_icons_svg[i - 1] if i - 1 < len(feature_icons_svg) else '',
            })
        steps = [t.get(f'landing_how_{i}', '') for i in range(1, steps_count + 1)]

        html = template.render(
            t=t,
            locale_code=locale_code,
            locale_lang=loc['lang'],
            locale_path=locale_path,
            subdomain=subdomain,
            og_locale=OG_LOCALE_MAP.get(locale_code, 'en_US'),
            alternates=alternates,
            cta_url=cta_url,
            problems=problems,
            features=features,
            steps=steps,
            year=datetime.now(timezone.utc).year,
            footer_tagline=FOOTER_TAGLINES.get(locale_code, FOOTER_TAGLINES['en']),
            cross_links=cross_links,
            inline_css=STYLE_CSS,
        )

        # Write locale-specific file
        if locale_code == default_locale:
            out_file = output_dir / 'index.html'
        else:
            locale_dir = output_dir / locale_code
            locale_dir.mkdir(exist_ok=True)
            out_file = locale_dir / 'index.html'

        out_file.write_text(html)
        generated.append(f'  {locale_code}: {out_file.relative_to(BASE_DIR)}')

    # Generate sitemap.xml
    sitemap = generate_sitemap(subdomain, default_locale)
    sitemap_file = output_dir / 'sitemap.xml'
    sitemap_file.write_text(sitemap)
    generated.append(f'  sitemap: {sitemap_file.relative_to(BASE_DIR)}')

    # Generate robots.txt
    robots = generate_robots(subdomain)
    robots_file = output_dir / 'robots.txt'
    robots_file.write_text(robots)
    generated.append(f'  robots: {robots_file.relative_to(BASE_DIR)}')

    # Generate nginx config
    nginx = generate_nginx(subdomain, default_locale, str(output_dir))
    nginx_file = landing_dir / 'nginx.conf'
    nginx_file.write_text(nginx)
    generated.append(f'  nginx: {nginx_file.relative_to(BASE_DIR)}')

    print(f'{landing_name} ({subdomain}.parahub.io):')
    for line in generated:
        print(line)
    return True


def generate_sitemap(subdomain: str, default_locale: str) -> str:
    """Generate sitemap.xml with all locale URLs."""
    base = f'https://{subdomain}.parahub.io'
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    urls = []
    for loc in LOCALES:
        path = get_locale_path(loc['code'], default_locale)
        urls.append(f'''  <url>
    <loc>{base}{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
  </url>''')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
'''


def generate_robots(subdomain: str) -> str:
    """Generate robots.txt pointing to the sitemap."""
    return f'''User-agent: *
Allow: /

Sitemap: https://{subdomain}.parahub.io/sitemap.xml
'''


def generate_nginx(subdomain: str, default_locale: str, output_path: str) -> str:
    """Generate nginx config for the landing subdomain."""
    domain = f'{subdomain}.parahub.io'

    # Build Accept-Language map entries
    lang_locations = ''
    for loc in LOCALES:
        if loc['code'] == default_locale:
            continue
        lang_locations += f'''
    # {loc['name']}
    location = /{loc['code']}/ {{
        root {output_path};
        try_files /{loc['code']}/index.html =404;
    }}
'''

    return f'''# {domain} — Static landing page (auto-generated, do not edit manually)
# Regenerate: python3 landings/_generate.py {subdomain.split(".")[0]}

server {{
    listen 80;
    server_name {domain};
    return 301 https://{domain}$request_uri;
}}

server {{
    listen 443 ssl;
    server_name {domain};
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;

    root {output_path};

    # Default locale ({default_locale})
    location = / {{
        try_files /index.html =404;
    }}
{lang_locations}
    # Sitemap, Robots & OG image
    location = /sitemap.xml {{
        try_files /sitemap.xml =404;
    }}

    location = /robots.txt {{
        try_files /robots.txt =404;
    }}

    location = /og.png {{
        try_files /og.png =404;
        add_header Cache-Control "public, max-age=604800";
    }}

    # Anything else → redirect to root
    location / {{
        return 301 /;
    }}
}}
'''


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    all_landings = discover_all_landings()

    if target:
        if not generate_landing(target, all_landings):
            sys.exit(1)
    else:
        # Generate all landings
        count = 0
        for l in all_landings:
            if generate_landing(l['name'], all_landings):
                count += 1
        if count == 0:
            print('No landing configs found')
        else:
            print(f'\nGenerated {count} landing(s)')


if __name__ == '__main__':
    main()
