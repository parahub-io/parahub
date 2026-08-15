#!/usr/bin/env python3
"""
Matrix Database Reset Script

Resets ONLY the Matrix Synapse PostgreSQL database (and the MAS database when
Matrix Authentication Service is deployed) and recreates the admin user.
Does NOT touch other databases (main PostgreSQL, Neo4j, Redis).

Usage:
    python3 matrix_db_reset.py [--dry-run]

What it does (legacy mode, no MAS deployed):
1. Stops Synapse container
2. Drops and recreates Synapse database
3. Starts Synapse container
4. Creates admin user via shared-secret registration
5. Uploads SSO icon to Matrix media repository and updates homeserver.yaml
6. Updates SYNAPSE_ADMIN_TOKEN in settings.py
7. Clears Redis Matrix session cache (prevents 401 errors from stale tokens)
8. Restarts parahub-uvicorn service

What it does (MAS mode, auto-detected via compose service):
1. Stops Synapse + MAS containers
2. Drops and recreates Synapse AND MAS databases
3. Starts MAS (runs its own migrations + config sync), then Synapse
4. Creates admin user via MAS Admin API (shared-secret registration is
   disabled under MAS), sets the Synapse server-admin flag via SQL, and
   mints a non-expiring personal-session access token as the admin token
5. SSO icon step is skipped (idp_icon lived in the removed oidc_providers
   block; login branding is served by MAS itself)
6-8. Same as legacy mode

Environment overrides (for rehearsal against a dev copy; defaults = prod):
    COMPOSE_DIR, SYNAPSE_COMPOSE_SERVICE, MAS_COMPOSE_SERVICE,
    SYNAPSE_BASE_URL, MAS_BASE_URL, SYNAPSE_DB_PORT, SETTINGS_PATH,
    SKIP_REDIS_CLEAR=1, SKIP_BACKEND_RESTART=1

Requires: Docker, PostgreSQL client (psql)
MAS mode also requires: MAS_ADMIN_CLIENT_ID + MAS_ADMIN_CLIENT_SECRET in env
(an OAuth2 client listed in MAS config `clients` + `policy.data.admin_clients`).
"""

import os
import subprocess
import sys
import time
import httpx
import hmac
import hashlib
import re
from pathlib import Path

# Standard admin credentials (see PK/matrix-admin-credentials.md)
ADMIN_USERNAME = os.environ['SYNAPSE_ADMIN_USER']
ADMIN_PASSWORD = os.environ['SYNAPSE_ADMIN_PASSWORD']
SYNAPSE_SHARED_SECRET = os.environ['SYNAPSE_REGISTRATION_SHARED_SECRET']
SYNAPSE_BASE_URL = os.environ.get('SYNAPSE_BASE_URL', 'http://localhost:8008')
SERVER_NAME = "parahub.io"

# MAS (Matrix Authentication Service) — web listener mounted under /mas
MAS_BASE_URL = os.environ.get('MAS_BASE_URL', 'http://localhost:8081/mas')
MAS_ADMIN_CLIENT_ID = os.environ.get('MAS_ADMIN_CLIENT_ID')
MAS_ADMIN_CLIENT_SECRET = os.environ.get('MAS_ADMIN_CLIENT_SECRET')
MAS_DB_NAME = "mas"

# Database credentials (MAS shares the same PostgreSQL instance, separate DB)
SYNAPSE_DB_HOST = "localhost"
SYNAPSE_DB_PORT = os.environ.get('SYNAPSE_DB_PORT', '5434')
SYNAPSE_DB_NAME = "synapse"
SYNAPSE_DB_USER = "synapse"
SYNAPSE_DB_PASSWORD = os.environ['SYNAPSE_DB_PASSWORD']

# Paths / compose targets. The admin token lives in .env (settings.py reads it
# via django-environ); SETTINGS_PATH may point at either an .env-style or a
# settings.py-style file — update_settings handles both formats.
SETTINGS_PATH = Path(os.environ.get('SETTINGS_PATH', "/opt/parahub/.env"))
COMPOSE_DIR = Path(os.environ.get('COMPOSE_DIR', "/opt/parahub"))
SYNAPSE_SERVICE = os.environ.get('SYNAPSE_COMPOSE_SERVICE', 'synapse')
MAS_SERVICE = os.environ.get('MAS_COMPOSE_SERVICE', 'mas')


def run_command(cmd, check=True, capture_output=False):
    """Run shell command and return result"""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        check=check,
        capture_output=capture_output,
        text=True
    )
    if capture_output and result.stdout:
        print(f"    {result.stdout.strip()}")
    return result


def mas_deployed() -> bool:
    """MAS mode is active when the compose project defines the MAS service."""
    result = run_command(
        f"cd {COMPOSE_DIR} && docker compose config --services",
        capture_output=True
    )
    return MAS_SERVICE in result.stdout.split()


def psql(db: str, sql: str, capture_output=False):
    """Run a SQL statement against the Synapse PostgreSQL instance (no shell,
    so the statement may safely contain any quoting)."""
    print(f"  $ psql -p {SYNAPSE_DB_PORT} -d {db} -c {sql!r}")
    env = dict(os.environ, PGPASSWORD=SYNAPSE_DB_PASSWORD)
    result = subprocess.run(
        ["psql", "-h", SYNAPSE_DB_HOST, "-p", SYNAPSE_DB_PORT,
         "-U", SYNAPSE_DB_USER, "-d", db, "-c", sql],
        check=True, capture_output=capture_output, text=True, env=env
    )
    if capture_output and result.stdout:
        print(f"    {result.stdout.strip()}")
    return result


def stop_services(with_mas: bool):
    """Stop Synapse (and MAS) containers"""
    print("\n[1/8] Stopping Matrix containers...")
    services = f"{SYNAPSE_SERVICE} {MAS_SERVICE}" if with_mas else SYNAPSE_SERVICE
    run_command(f"cd {COMPOSE_DIR} && docker compose stop {services}")


def reset_database(with_mas: bool):
    """Drop and recreate Synapse (and MAS) databases"""
    print("\n[2/8] Resetting Matrix databases...")

    for db in ([SYNAPSE_DB_NAME, MAS_DB_NAME] if with_mas else [SYNAPSE_DB_NAME]):
        print(f"  Recreating database {db}...")
        psql("postgres", f'DROP DATABASE IF EXISTS {db};')
        psql("postgres",
             f'CREATE DATABASE {db} OWNER {SYNAPSE_DB_USER} ENCODING UTF8'
             f' LC_COLLATE "C" LC_CTYPE "C" TEMPLATE template0;')


def start_services(with_mas: bool):
    """Start MAS first (Synapse validates its connection to it), then Synapse"""
    print("\n[3/8] Starting Matrix containers...")

    if with_mas:
        run_command(f"cd {COMPOSE_DIR} && docker compose start {MAS_SERVICE}")
        print("  Waiting for MAS to be ready (runs DB migrations + config sync)...")
        _wait_http_ok(f"{MAS_BASE_URL}/.well-known/openid-configuration", "MAS")

    run_command(f"cd {COMPOSE_DIR} && docker compose start {SYNAPSE_SERVICE}")
    print("  Waiting for Synapse to be ready...")
    _wait_http_ok(f"{SYNAPSE_BASE_URL}/_matrix/client/versions", "Synapse")
    # Wait for DB schema creation (Synapse creates tables async after first start)
    print("  Waiting for database schema initialization...")
    time.sleep(8)


def _wait_http_ok(url: str, name: str, max_attempts: int = 30):
    for attempt in range(max_attempts):
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                print(f"  ✓ {name} is ready")
                return
        except Exception:
            pass
        print(f"  Waiting... ({attempt + 1}/{max_attempts})")
        time.sleep(2)
    print(f"  ✗ ERROR: {name} did not become ready in time")
    sys.exit(1)


def generate_mac(shared_secret, nonce, user, password, admin=False):
    """Generate HMAC for Matrix registration"""
    mac = hmac.new(key=shared_secret.encode('utf8'), digestmod=hashlib.sha1)
    mac.update(nonce.encode('utf8'))
    mac.update(b"\x00")
    mac.update(user.encode('utf8'))
    mac.update(b"\x00")
    mac.update(password.encode('utf8'))
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    return mac.hexdigest()


def create_admin_user_legacy():
    """Create admin user via shared-secret registration and return access token"""
    print("\n[4/8] Creating Matrix admin user (shared-secret registration)...")

    with httpx.Client() as client:
        # Get nonce
        print(f"  Creating admin user: {ADMIN_USERNAME}")
        response = client.get(f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/register")
        response.raise_for_status()
        nonce = response.json()["nonce"]

        # Generate MAC
        mac = generate_mac(SYNAPSE_SHARED_SECRET, nonce, ADMIN_USERNAME, ADMIN_PASSWORD, admin=True)

        # Register admin
        response = client.post(
            f"{SYNAPSE_BASE_URL}/_synapse/admin/v1/register",
            json={
                "nonce": nonce,
                "username": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD,
                "mac": mac,
                "admin": True
            }
        )
        response.raise_for_status()

        token = response.json()["access_token"]
        matrix_id = response.json()["user_id"]

        print(f"  ✓ Admin user created: {matrix_id}")
        print(f"  ✓ Access token: {token[:20]}...")

        return token


def create_admin_user_mas():
    """Create admin user via the MAS Admin API and return a personal-session token.

    Shared-secret registration is disabled under MAS. Instead:
    1. client_credentials grant with scope urn:mas:admin
    2. POST /api/admin/v1/users — MAS provisions the user into Synapse
    3. SQL: set the Synapse server-admin flag (separate from MAS can_request_admin)
    4. POST /api/admin/v1/personal-sessions — non-expiring Matrix access token
    """
    print("\n[4/8] Creating Matrix admin user (MAS Admin API)...")

    if not (MAS_ADMIN_CLIENT_ID and MAS_ADMIN_CLIENT_SECRET):
        print("  ✗ ERROR: MAS_ADMIN_CLIENT_ID / MAS_ADMIN_CLIENT_SECRET not set in env")
        sys.exit(1)

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{MAS_BASE_URL}/oauth2/token",
            auth=(MAS_ADMIN_CLIENT_ID, MAS_ADMIN_CLIENT_SECRET),
            data={"grant_type": "client_credentials", "scope": "urn:mas:admin"}
        )
        response.raise_for_status()
        mas_token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {mas_token}"}

        response = client.post(
            f"{MAS_BASE_URL}/api/admin/v1/users",
            headers=headers,
            json={"username": ADMIN_USERNAME}
        )
        response.raise_for_status()
        user_ulid = response.json()["data"]["id"]
        matrix_id = f"@{ADMIN_USERNAME}:{SERVER_NAME}"
        print(f"  ✓ Admin user created via MAS: {matrix_id} (MAS id {user_ulid})")

        # MAS-side admin attribute (can_request_admin)
        response = client.post(
            f"{MAS_BASE_URL}/api/admin/v1/users/{user_ulid}/set-admin",
            headers=headers,
            json={"admin": True}
        )
        response.raise_for_status()

        # Admin power on the Synapse admin API is granted by the
        # urn:synapse:admin:* scope on the token (OAuth-delegated mode), NOT by
        # the users.admin DB flag. The flag is still set for any code path that
        # reads it directly; Synapse caches user rows, hence the restart.
        psql(SYNAPSE_DB_NAME,
             f"UPDATE users SET admin = 1 WHERE name = '{matrix_id}';")
        run_command(f"cd {COMPOSE_DIR} && docker compose restart {SYNAPSE_SERVICE}")
        _wait_http_ok(f"{SYNAPSE_BASE_URL}/_matrix/client/versions", "Synapse")

        response = client.post(
            f"{MAS_BASE_URL}/api/admin/v1/personal-sessions",
            headers=headers,
            json={
                "actor_user_id": user_ulid,
                "human_name": "parahub-backend admin token (matrix_db_reset)",
                "scope": "urn:matrix:org.matrix.msc2967.client:api:*"
                         " urn:matrix:org.matrix.msc2967.client:device:PARAHUBADMIN"
                         " urn:synapse:admin:*",
                # no expires_in: token does not expire
            }
        )
        response.raise_for_status()
        token = response.json()["data"]["attributes"]["access_token"]
        print(f"  ✓ Personal-session token minted: {token[:20]}...")

        return token


def upload_sso_icon(admin_token):
    """Upload SSO icon to Matrix media repository and update homeserver.yaml"""
    print("\n[5/8] Uploading SSO icon to Matrix media repository...")

    logo_path = Path("/opt/parahub/frontend/public/logo.svg")

    if not logo_path.exists():
        print(f"  ✗ WARNING: Logo not found at {logo_path}, skipping icon upload")
        return None

    # Upload logo
    with open(logo_path, 'rb') as f:
        logo_data = f.read()

    with httpx.Client() as client:
        response = client.post(
            f"{SYNAPSE_BASE_URL}/_matrix/media/v3/upload",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "image/svg+xml"
            },
            content=logo_data
        )

        if response.status_code != 200:
            print(f"  ✗ WARNING: Failed to upload icon: {response.status_code}")
            return None

        mxc_uri = response.json()["content_uri"]
        print(f"  ✓ Logo uploaded: {mxc_uri}")

        # Update homeserver.yaml files
        homeserver_files = [
            Path("/opt/parahub/synapse/data/homeserver.yaml"),
            Path("/opt/parahub/synapse/config/homeserver.yaml")
        ]

        for yaml_file in homeserver_files:
            if yaml_file.exists():
                try:
                    # Use sed to update the icon URI
                    subprocess.run(
                        f"sudo sed -i 's|idp_icon: \"mxc://parahub.io/[^\"]*\"|idp_icon: \"{mxc_uri}\"|g' {yaml_file}",
                        shell=True,
                        check=True
                    )
                    print(f"  ✓ Updated {yaml_file.name}")
                except Exception as e:
                    print(f"  ✗ WARNING: Failed to update {yaml_file.name}: {e}")

        return mxc_uri


def update_settings(token):
    """Update SYNAPSE_ADMIN_TOKEN (in .env or a settings.py-style file)"""
    print(f"\n[6/8] Updating {SETTINGS_PATH}...")

    if not SETTINGS_PATH.exists():
        print(f"  ✗ ERROR: {SETTINGS_PATH} not found")
        sys.exit(1)

    content = SETTINGS_PATH.read_text()

    env_pattern = r"(?m)^SYNAPSE_ADMIN_TOKEN=.*$"
    py_pattern = r"SYNAPSE_ADMIN_TOKEN\s*=\s*['\"].*?['\"]"

    if re.search(env_pattern, content):
        new_content = re.sub(env_pattern, f"SYNAPSE_ADMIN_TOKEN={token}", content)
    elif re.search(py_pattern, content):
        new_content = re.sub(py_pattern, f"SYNAPSE_ADMIN_TOKEN = '{token}'", content)
    else:
        print(f"  ✗ ERROR: Could not find SYNAPSE_ADMIN_TOKEN in {SETTINGS_PATH}")
        sys.exit(1)

    SETTINGS_PATH.write_text(new_content)
    print(f"  ✓ Updated SYNAPSE_ADMIN_TOKEN in {SETTINGS_PATH}")


def clear_redis_cache():
    """Clear Matrix session cache from Redis DB 1"""
    print("\n[7/8] Clearing Redis Matrix session cache...")

    if os.environ.get('SKIP_REDIS_CLEAR'):
        print("  ⚠ Skipped (SKIP_REDIS_CLEAR set)")
        return

    # Get all Matrix session keys from Redis DB 1
    result = run_command('redis-cli -n 1 KEYS "parahub:1:matrix_session_*"', capture_output=True)

    if result.stdout and result.stdout.strip():
        keys = result.stdout.strip().split('\n')
        print(f"  Found {len(keys)} cached Matrix sessions")

        # Delete all Matrix session keys
        for key in keys:
            if key.strip():
                run_command(f'redis-cli -n 1 DEL "{key.strip()}"', capture_output=True)

        print(f"  ✓ Cleared {len(keys)} Matrix sessions from Redis")
    else:
        print("  ✓ No cached sessions found")


def restart_backend():
    """Restart parahub-uvicorn service"""
    print("\n[8/8] Restarting backend service...")
    if os.environ.get('SKIP_BACKEND_RESTART'):
        print("  ⚠ Skipped (SKIP_BACKEND_RESTART set)")
        return
    run_command("sudo systemctl restart parahub-uvicorn")
    print("  ✓ Backend restarted")


def main():
    dry_run = "--dry-run" in sys.argv
    with_mas = mas_deployed()
    mode = "MAS" if with_mas else "legacy (no MAS)"

    print("=" * 80)
    print(f"Matrix Database Reset Script — mode: {mode}")
    print("=" * 80)

    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made\n")
        print("Would perform:")
        print(f"  1. Stop containers: {SYNAPSE_SERVICE}" + (f" + {MAS_SERVICE}" if with_mas else ""))
        print("  2. Drop and recreate databases: synapse" + (" + mas" if with_mas else ""))
        print("  3. Start containers" + (" (MAS first, runs migrations + config sync)" if with_mas else ""))
        if with_mas:
            print("  4. Create admin user via MAS Admin API + SQL admin flag + personal-session token")
            print("  5. Skip SSO icon (MAS serves login branding)")
        else:
            print("  4. Create admin user via shared-secret registration")
            print("  5. Upload SSO icon and update homeserver.yaml")
        print("  6. Update SYNAPSE_ADMIN_TOKEN in settings.py")
        print("  7. Clear Redis Matrix session cache")
        print("  8. Restart parahub-uvicorn")
        return

    # Confirm with user
    print("\n⚠️  WARNING: This will DELETE all Matrix data!")
    print("  - All rooms, messages, and user registrations will be lost")
    if with_mas:
        print("  - MAS database (auth sessions, upstream links, devices) is reset too")
    print("  - This ONLY affects Matrix/Synapse" + ("/MAS" if with_mas else "") + " databases")
    print("  - Main PostgreSQL, Neo4j, and Redis are NOT affected")
    print()
    response = input("Type 'YES' to continue: ")

    if response != "YES":
        print("Aborted.")
        return

    try:
        stop_services(with_mas)
        reset_database(with_mas)
        start_services(with_mas)
        if with_mas:
            token = create_admin_user_mas()
            mxc_uri = None  # idp_icon lived in the removed oidc_providers block
        else:
            token = create_admin_user_legacy()
            mxc_uri = upload_sso_icon(token)
        update_settings(token)
        clear_redis_cache()
        restart_backend()

        print("\n" + "=" * 80)
        print("✓ Matrix database reset complete!")
        print("=" * 80)
        print(f"\nAdmin credentials (see PK/matrix-admin-credentials.md):")
        print(f"  Username: {ADMIN_USERNAME}")
        if not with_mas:
            print(f"  Password: {ADMIN_PASSWORD}")
        else:
            print("  Password: none (MAS mode — token-only admin; password login is disabled)")
        print(f"  Matrix ID: @{ADMIN_USERNAME}:{SERVER_NAME}")
        print(f"  Token: {token[:30]}...")
        if mxc_uri:
            print(f"\nSSO Icon: {mxc_uri}")
        print()

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
