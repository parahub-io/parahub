<p align="center">
  <img src="frontend/public/logo.svg" width="100" alt="Parahub">
</p>

<h1 align="center">Parahub</h1>

<p align="center">
  Self-hosted P2P infrastructure for communities to trade, govern, and communicate &mdash; without middlemen.
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12+-3776ab?logo=python&logoColor=white">
  <img alt="Django" src="https://img.shields.io/badge/django-5-092e20?logo=django&logoColor=white">
  <img alt="Nuxt" src="https://img.shields.io/badge/nuxt-4-00dc82?logo=nuxt.js&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/postgresql-16+-336791?logo=postgresql&logoColor=white">
</p>

---

## Why

Platforms extract 15-30% from every transaction (Amazon, Upwork, Uber). Parahub replaces them with direct P2P infrastructure that communities self-host. No platform fees, no escrow, no data harvesting.

## What's Inside

**Trade** &mdash; P2P marketplace, multilateral barter (2-7 party cycles via graph DB), P2P contracts with cryptographic audit trail, debt tracking with clearing

**Govern** &mdash; Liquid democracy with transitive delegation, participatory budgeting, Web of Trust identity (3+ verifications as Sybil defense)

**Communicate** &mdash; E2E encrypted messaging (Matrix/Synapse), video conferencing (Jitsi), email (Mailcow), git hosting (Gitea)

**Navigate** &mdash; Map with real-time presence, business directory, public transit schedules (GTFS/GTFS-RT), community events, carpool, geocoding

**Secure** &mdash; Client-side PGP (keys never leave the browser), non-custodial Lightning payments, OpenTimestamps audit anchoring, privacy by design

## Stack

| Layer | Tech |
|-------|------|
| Backend | Django 5 / Ninja, Python 3.12 |
| Frontend | Nuxt 4 (SSR), Vue 3 |
| Database | PostgreSQL 16 + PostGIS + TimescaleDB |
| Graph | Neo4j (barter cycle detection) |
| Cache | Redis |
| Chat | Matrix Synapse + Element/Cinny |
| Maps | MapLibre GL + Martin (vector tiles) + Pelias (geocoding) |
| Routing | MOTIS (transit) + Valhalla (car/bike/walk) |
| Video | Jitsi Meet |
| Tracking | Traccar (GPS fleet) |
| Email | Mailcow |
| Git | Gitea |
| Containers | Docker Compose |

## Quick Start

### Prerequisites

- Python 3.12+ with pip
- Node.js 20+ with npm
- Docker with Compose plugin (`docker compose`)
- PostgreSQL 16+ with PostGIS and TimescaleDB extensions
- Redis 7+
- Neo4j 5+
- OpenSSL

### Setup

```bash
git clone https://github.com/parahub-io/parahub.git /opt/parahub
cd /opt/parahub

# Install Python dependencies
pip install -r requirements.txt

# Bootstrap: generates secrets, creates .env, configures services
./install.sh

# Flags: --skip-docker (if services run externally)
#         --skip-frontend (backend-only dev)
#         --force (overwrite existing .env)
```

The install script will:
1. Generate all secrets and create `.env`
2. Generate OIDC and VAPID keys
3. Start Docker services (Neo4j, Synapse, Traccar, Jitsi, Gitea, etc.)
4. Run Django migrations and create admin user
5. Build the Nuxt frontend

### Run (Development)

```bash
# Start dev servers (keeps production running if deployed)
./0restart-dev

# Backend: http://localhost:8001
# Frontend: http://localhost:3001
# Set cookie parahub_dev=1 on your domain for nginx routing
```

### Run (Production)

Set up nginx and systemd services (see `nginx/` for example configs), then:

```bash
./0restart    # Build + restart all services
```

## Architecture

```
Browser ──► Nginx ──► Nuxt SSR (:3000)
                  └──► Django API (:8000) ──► PostgreSQL/PostGIS
                                          ├──► Redis (cache/sessions/CQRS)
                                          ├──► Neo4j (barter graph)
                                          └──► WebSocket (real-time)
              └──► Docker services
                    ├── Matrix Synapse (E2E chat)
                    ├── Jitsi Meet (video)
                    ├── Traccar (GPS tracking)
                    ├── Gitea (git hosting)
                    ├── Martin (vector tiles)
                    ├── Pelias (geocoding)
                    └── Mailcow (email)
```

**Key patterns:** ULID identifiers, CQRS (high-freq reads via Redis, writes to PostgreSQL), JWT + session dual auth, native Redis pub/sub for WebSocket messaging.

## Contributing

Contributions welcome. The project is large but modular &mdash; each system (barter, governance, transit, etc.) is relatively self-contained.

1. Run `./install.sh` to set up your environment
2. Use `./0restart-dev` for development (never touches production)
3. Test data: `python3 manage.py seed_test_users && python3 manage.py seed_test_items`

## License

[MIT](LICENSE)
