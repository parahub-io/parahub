# Contributing to Parahub

Parahub is developed by PARAHUB — Associacao (Portuguese NPO). Contributions are welcome!

## Before You Start

### Sign the CLA

Before your first contribution can be merged, you must agree to the [Contributor License Agreement](CLA.md) by commenting on your pull request:

> I have read and agree to the [Contributor License Agreement](CLA.md).

This is required once and covers all future contributions.

### License

Parahub is licensed under [MIT](LICENSE). By contributing, your code will be distributed under the same license.

## Development Setup

### Prerequisites

- Python 3.12+ with pip
- Node.js 20+ with npm
- Docker with Compose plugin (`docker compose`)
- PostgreSQL 16+ with PostGIS and TimescaleDB extensions
- Redis 7+
- Neo4j 5+
- OpenSSL

### Installation

```bash
git clone https://github.com/YOUR-ORG/parahub.git /opt/parahub
cd /opt/parahub

pip install -r requirements.txt
cd frontend && npm install && cd ..

# Bootstrap: generates secrets, creates .env, starts services
./install.sh

# Flags:
#   --skip-docker    Skip docker compose up
#   --skip-frontend  Skip npm install and frontend build
#   --force          Overwrite existing .env
```

### Running Locally

```bash
# Development servers (hot-reload)
./0restart-dev

# Backend: http://localhost:8001
# Frontend: http://localhost:3001
```

### Test Data

```bash
python3 manage.py seed_test_users
python3 manage.py seed_test_items
python3 manage.py seed_test_establishments --location lisbon
```

Test user credentials are in `.test_users_password` after seeding.

## Coding Style

### Backend (Python / Django)

- **Framework**: Django 5 with [django-ninja](https://django-ninja.dev/) for API endpoints
- **IDs**: All models use ULID primary keys (26 chars, no prefix)
- **API responses**: Always include `object_type` field
- **Auth**: Dual auth — session cookie + JWT Bearer token
- **Performance**: API endpoints must be under 50ms (p95). Use raw SQL for bulk read-only endpoints if ORM is too slow
- **No high-frequency writes to PostgreSQL** — use Redis for real-time data (CQRS pattern)

### Frontend (TypeScript / Vue / Nuxt)

- **Framework**: Nuxt 4 with SSR
- **Icons**: `lucide-vue-next` only — no other icon libraries
- **Components**: Use `UiButton`, `UiTabs`, `UiBadge`, `UiAlert`, `UiConfirmModal` from the design system (see `PK/design-system.md`)
- **Colors**: CSS design tokens (`var(--color-primary)`, etc.) — never hardcode hex values
- **i18n**: All user-facing strings go in locale JSON files. Support all 6 languages (en, pt, ru, es, fr, de). Escape `@` as `{'@'}` in locale strings
- **Navigation**: Always wrap paths in `localePath()` for router calls
- **Page layouts**: Follow patterns in `PK/design-system.md` — use `PageHeader` component, standard container widths

### General

- Read `PK/philosophy.md` for non-negotiable constraints before making architectural decisions
- Read `PK/architecture.md` for API patterns, auth flow, and CQRS conventions
- Read `PK/design-system.md` before any frontend work

## Testing

### Backend

```bash
# Run all tests
python3 manage.py test --no-input

# Run specific app tests
python3 manage.py test parahub.crypto.tests --no-input
```

### Frontend (E2E)

```bash
cd frontend
npm run test:e2e        # Headless
npm run test:e2e:ui     # With Playwright UI
npm run test:e2e:debug  # Debug mode
```

## Pull Request Process

1. **Fork and branch** — Create a feature branch from `master`
2. **Keep it focused** — One feature or fix per PR. Don't mix unrelated changes
3. **Test your changes** — Run backend tests and relevant E2E tests
4. **i18n** — If you added user-facing strings, include translations for all 6 locales
5. **Commit messages** — Use conventional commits: `feat(scope):`, `fix(scope):`, `docs(scope):`, `perf(scope):`
6. **Commit only your files** — Use `git add <specific files>`, never `git add -A`
7. **Open a PR** — Fill out the PR template. Include screenshots for UI changes

### What We Look For in Reviews

- Follows existing patterns (check similar code in the codebase)
- No hardcoded secrets, IPs, or credentials
- No new dependencies without justification
- Accessible UI (keyboard navigation, ARIA labels where needed)
- No regressions in existing functionality

## Project Structure

The codebase is modular — each system is relatively self-contained:

| Directory | Contents |
|-----------|----------|
| `identity/`, `market/`, `geo/`, etc. | Django apps (models, endpoints, services) |
| `frontend/pages/` | Nuxt pages |
| `frontend/components/` | Vue components |
| `frontend/locales/` | i18n translation files |
| `PK/` | System documentation (AI-readable, concise) |
| `docs/` | Public-facing documentation pages |

See `PK/codebase.md` for a complete map.

## Communication

- **Matrix**: `#general:parahub.io`
- **Git**: Self-hosted Gitea at `git.parahub.io`
- **Issues**: Use GitHub issue templates for bugs and feature requests
