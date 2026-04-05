#!/usr/bin/env python3
"""
Matrix Database Reset Script

Resets ONLY the Matrix Synapse PostgreSQL database and recreates the admin user.
Does NOT touch other databases (main PostgreSQL, Neo4j, Redis).

Usage:
    python3 matrix_db_reset.py [--dry-run]

What it does:
1. Stops Synapse container
2. Drops and recreates Synapse database
3. Starts Synapse container
4. Creates admin user with standard credentials (see PK/matrix-admin-credentials.md)
5. Uploads SSO icon to Matrix media repository and updates homeserver.yaml
6. Updates SYNAPSE_ADMIN_TOKEN in settings.py
7. Clears Redis Matrix session cache (prevents 401 errors from stale tokens)
8. Restarts parahub-uvicorn service

Requires: Docker, PostgreSQL client (psql)
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
SYNAPSE_BASE_URL = "http://localhost:8008"

# Database credentials
SYNAPSE_DB_HOST = "localhost"
SYNAPSE_DB_PORT = "5434"  # Synapse PostgreSQL port
SYNAPSE_DB_NAME = "synapse"
SYNAPSE_DB_USER = "synapse"
SYNAPSE_DB_PASSWORD = os.environ['SYNAPSE_DB_PASSWORD']

# Paths
SETTINGS_PATH = Path("/opt/parahub/parahub/settings.py")
DOCKER_COMPOSE_PATH = Path("/opt/parahub")


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


def stop_synapse():
    """Stop Synapse container"""
    print("\n[1/6] Stopping Synapse container...")
    run_command("cd /opt/parahub && docker compose stop synapse")


def reset_database():
    """Drop and recreate Synapse database"""
    print("\n[2/6] Resetting Synapse database...")

    # Drop database
    print("  Dropping database...")
    drop_cmd = f"PGPASSWORD={SYNAPSE_DB_PASSWORD} psql -h {SYNAPSE_DB_HOST} -p {SYNAPSE_DB_PORT} -U {SYNAPSE_DB_USER} -d postgres -c 'DROP DATABASE IF EXISTS {SYNAPSE_DB_NAME};'"
    run_command(drop_cmd)

    # Recreate database
    print("  Creating database...")
    create_cmd = f"PGPASSWORD={SYNAPSE_DB_PASSWORD} psql -h {SYNAPSE_DB_HOST} -p {SYNAPSE_DB_PORT} -U {SYNAPSE_DB_USER} -d postgres -c 'CREATE DATABASE {SYNAPSE_DB_NAME} OWNER {SYNAPSE_DB_USER} ENCODING UTF8 LC_COLLATE \"C\" LC_CTYPE \"C\" TEMPLATE template0;'"
    run_command(create_cmd)


def start_synapse():
    """Start Synapse container and wait for it to be ready"""
    print("\n[3/6] Starting Synapse container...")
    run_command("cd /opt/parahub && docker compose start synapse")

    print("  Waiting for Synapse to be ready...")
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            response = httpx.get(f"{SYNAPSE_BASE_URL}/_matrix/client/versions", timeout=2.0)
            if response.status_code == 200:
                print("  ✓ Synapse is ready")
                # Wait for DB schema creation (Synapse creates tables async after first start)
                print("  Waiting for database schema initialization...")
                time.sleep(8)
                return
        except:
            pass

        print(f"  Waiting... ({attempt + 1}/{max_attempts})")
        time.sleep(2)

    print("  ✗ ERROR: Synapse did not become ready in time")
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


def create_admin_user():
    """Create admin user and return access token"""
    print("\n[4/7] Creating Matrix admin user...")

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


def upload_sso_icon(admin_token):
    """Upload SSO icon to Matrix media repository and update homeserver.yaml"""
    print("\n[5/7] Uploading SSO icon to Matrix media repository...")

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
    """Update SYNAPSE_ADMIN_TOKEN in settings.py"""
    print("\n[6/7] Updating settings.py...")

    if not SETTINGS_PATH.exists():
        print(f"  ✗ ERROR: {SETTINGS_PATH} not found")
        sys.exit(1)

    content = SETTINGS_PATH.read_text()

    # Replace token using regex
    pattern = r"SYNAPSE_ADMIN_TOKEN\s*=\s*['\"].*?['\"]"
    replacement = f"SYNAPSE_ADMIN_TOKEN = '{token}'"

    if re.search(pattern, content):
        new_content = re.sub(pattern, replacement, content)
        SETTINGS_PATH.write_text(new_content)
        print(f"  ✓ Updated SYNAPSE_ADMIN_TOKEN in {SETTINGS_PATH}")
    else:
        print(f"  ✗ ERROR: Could not find SYNAPSE_ADMIN_TOKEN in settings.py")
        sys.exit(1)


def clear_redis_cache():
    """Clear Matrix session cache from Redis DB 1"""
    print("\n[7/8] Clearing Redis Matrix session cache...")

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
    run_command("sudo systemctl restart parahub-uvicorn")
    print("  ✓ Backend restarted")


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 80)
    print("Matrix Database Reset Script")
    print("=" * 80)

    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made\n")
        print("Would perform:")
        print("  1. Stop Synapse container")
        print("  2. Drop and recreate Synapse database")
        print("  3. Start Synapse container")
        print("  4. Create admin user")
        print("  5. Upload SSO icon and update homeserver.yaml")
        print("  6. Update SYNAPSE_ADMIN_TOKEN in settings.py")
        print("  7. Restart parahub-uvicorn")
        return

    # Confirm with user
    print("\n⚠️  WARNING: This will DELETE all Matrix data!")
    print("  - All rooms, messages, and user registrations will be lost")
    print("  - This ONLY affects Matrix/Synapse database")
    print("  - Main PostgreSQL, Neo4j, and Redis are NOT affected")
    print()
    response = input("Type 'YES' to continue: ")

    if response != "YES":
        print("Aborted.")
        return

    try:
        stop_synapse()
        reset_database()
        start_synapse()
        token = create_admin_user()
        mxc_uri = upload_sso_icon(token)
        update_settings(token)
        clear_redis_cache()
        restart_backend()

        print("\n" + "=" * 80)
        print("✓ Matrix database reset complete!")
        print("=" * 80)
        print(f"\nAdmin credentials (see PK/matrix-admin-credentials.md):")
        print(f"  Username: {ADMIN_USERNAME}")
        print(f"  Password: {ADMIN_PASSWORD}")
        print(f"  Matrix ID: @{ADMIN_USERNAME}:parahub.io")
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
