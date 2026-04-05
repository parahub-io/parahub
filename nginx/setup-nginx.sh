#!/bin/bash
set -euo pipefail

# =============================================================================
# Nginx Configuration Generator for Parahub
# Generates configs from templates and creates symlinks in sites-enabled
#
# Usage:
#   ./nginx/setup-nginx.sh                    # reads DOMAIN from .env
#   ./nginx/setup-nginx.sh --domain my.tld    # explicit domain
#   ./nginx/setup-nginx.sh --list             # show what would be generated
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATES_DIR="$SCRIPT_DIR/templates"
OUTPUT_DIR="$SCRIPT_DIR/sites-available"
ENABLED_DIR="/etc/nginx/sites-enabled"

# Parse args
DOMAIN=""
LIST_ONLY=false
KUMA_SLUG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)    DOMAIN="$2"; shift 2 ;;
        --kuma-slug) KUMA_SLUG="$2"; shift 2 ;;
        --list)      LIST_ONLY=true; shift ;;
        *)           err "Unknown arg: $1"; exit 1 ;;
    esac
done

# Read domain from .env if not provided
if [[ -z "$DOMAIN" ]]; then
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        DOMAIN=$(grep -oP '^SITE_URL=https?://\K[^/]+' "$PROJECT_DIR/.env" 2>/dev/null || true)
    fi
    if [[ -z "$DOMAIN" ]]; then
        err "Domain not found. Use --domain or set SITE_URL in .env"
        exit 1
    fi
fi

# Default kuma slug from domain (first part before .)
if [[ -z "$KUMA_SLUG" ]]; then
    KUMA_SLUG="${DOMAIN%%.*}"
fi

# Template → output mapping
# Format: template_name:output_filename
CONFIGS=(
    "main.conf.template:${DOMAIN}"
    "status.conf.template:status.${DOMAIN}"
    "git.conf.template:git.${DOMAIN}"
    "jitsi.conf.template:jitsi.${DOMAIN}"
    "tiles.conf.template:tiles.${DOMAIN}"
    "video.conf.template:video.${DOMAIN}"
    "netdata.conf.template:netdata.${DOMAIN}"
    "plausible.conf.template:plausible.${DOMAIN}"
    "mail.conf.template:mail.${DOMAIN}"
    "sites.conf.template:sites.${DOMAIN}"
)

echo -e "${BOLD}Parahub Nginx Setup${NC}"
echo -e "  Domain:      ${CYAN}${DOMAIN}${NC}"
echo -e "  Project:     ${CYAN}${PROJECT_DIR}${NC}"
echo -e "  Kuma slug:   ${CYAN}${KUMA_SLUG}${NC}"
echo ""

if $LIST_ONLY; then
    echo -e "${BOLD}Would generate:${NC}"
    for entry in "${CONFIGS[@]}"; do
        template="${entry%%:*}"
        output="${entry##*:}"
        if [[ -f "$TEMPLATES_DIR/$template" ]]; then
            echo -e "  ${GREEN}✓${NC} $template → $OUTPUT_DIR/$output"
        else
            echo -e "  ${RED}✗${NC} $template (template not found)"
        fi
    done
    exit 0
fi

# Generate configs
mkdir -p "$OUTPUT_DIR"

echo -e "${BOLD}Generating configs from templates...${NC}"
for entry in "${CONFIGS[@]}"; do
    template="${entry%%:*}"
    output="${entry##*:}"

    if [[ ! -f "$TEMPLATES_DIR/$template" ]]; then
        warn "Template not found: $template — skipping"
        continue
    fi

    sed \
        -e "s|__DOMAIN__|${DOMAIN}|g" \
        -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
        -e "s|__KUMA_SLUG__|${KUMA_SLUG}|g" \
        "$TEMPLATES_DIR/$template" > "$OUTPUT_DIR/$output"

    ok "$output"
done

# Create symlinks
echo ""
echo -e "${BOLD}Creating symlinks in $ENABLED_DIR...${NC}"

if [[ ! -d "$ENABLED_DIR" ]]; then
    err "$ENABLED_DIR does not exist. Is nginx installed?"
    exit 1
fi

NEED_SUDO=false
if [[ ! -w "$ENABLED_DIR" ]]; then
    NEED_SUDO=true
fi

link_cmd() {
    if $NEED_SUDO; then
        sudo "$@"
    else
        "$@"
    fi
}

for entry in "${CONFIGS[@]}"; do
    output="${entry##*:}"
    target="$OUTPUT_DIR/$output"
    link="$ENABLED_DIR/$output"

    if [[ ! -f "$target" ]]; then
        continue
    fi

    # Skip if already correctly linked
    if [[ -L "$link" ]] && [[ "$(readlink -f "$link")" == "$(readlink -f "$target")" ]]; then
        info "$output — already linked"
        continue
    fi

    # Remove existing file/link
    if [[ -e "$link" ]] || [[ -L "$link" ]]; then
        link_cmd rm -f "$link"
    fi

    link_cmd ln -s "$target" "$link"
    ok "$output → $target"
done

# Also link landing page configs if they exist
echo ""
echo -e "${BOLD}Linking landing page configs...${NC}"
for nginx_conf in "$PROJECT_DIR"/landings/*/nginx.conf; do
    if [[ ! -f "$nginx_conf" ]]; then
        continue
    fi

    # Extract domain from server_name in the config
    landing_domain=$(grep -m1 'server_name' "$nginx_conf" | awk '{print $2}' | tr -d ';')
    if [[ -z "$landing_domain" ]]; then
        warn "No server_name in $nginx_conf — skipping"
        continue
    fi

    link="$ENABLED_DIR/$landing_domain"

    if [[ -L "$link" ]] && [[ "$(readlink -f "$link")" == "$(readlink -f "$nginx_conf")" ]]; then
        info "$landing_domain — already linked"
        continue
    fi

    if [[ -e "$link" ]] || [[ -L "$link" ]]; then
        link_cmd rm -f "$link"
    fi

    link_cmd ln -s "$nginx_conf" "$link"
    ok "$landing_domain → $nginx_conf"
done

# Test nginx
echo ""
echo -e "${BOLD}Testing nginx configuration...${NC}"
if sudo nginx -t 2>&1; then
    ok "nginx config test passed"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo -e "  1. Get SSL certificates:  ${CYAN}sudo certbot --nginx -d ${DOMAIN} -d www.${DOMAIN}${NC}"
    echo -e "     Then for each subdomain: ${CYAN}sudo certbot --nginx -d status.${DOMAIN}${NC}"
    echo -e "  2. Reload nginx:          ${CYAN}sudo systemctl reload nginx${NC}"
    echo -e "  3. Verify:                ${CYAN}curl -sI https://${DOMAIN}${NC}"
else
    err "nginx config test FAILED — check the output above"
    exit 1
fi
