# Condominium Management

Building management system implementing Portuguese Lei 8/2022. Condominiums are modeled as Establishments with `organization_type='CONDOMINIUM'`.

## Concept

Portuguese law requires condominium management with permilagem (‰) ownership shares, regular quota payments, and assembly voting weighted by ownership fraction. Parahub digitalizes this process while reusing existing subsystems.

## Models

- **CondominiumFraction** -- ownership unit within a condominium (FK to Establishment). Fields: identifier (max 20 chars, e.g., "1-A"), floor, fraction_type (APARTMENT/GARAGE/STORAGE/COMMERCIAL/OTHER), permilagem (‰), optional resident (FK to Profile), invite tokens
- **QuotaPayment** -- monthly quota payment record per fraction (month, amount, paid_at)

## Permilagem

Ownership shares expressed in permilagem (‰). Total across all fractions must equal 1000‰. Used for weighted assembly voting -- multi-fraction owners' weights sum.

## Assembly Voting

Polls created via CondominiumService:
- `PollEligibleVoter` populated with permilagem weights (owners only)
- Multi-fraction owners' weights automatically summed
- Reuses Governance system (Liquid Democracy polls with Merkle audit)

## Budget

6 default categories: quotas-ordinarias, fundo-reserva, seguros, limpeza, manutencao, outros. Monthly budget stored in `establishment.attributes`. Reuses Treasury system (median voting with sliders).

## Reused Systems

- **Treasury**: participatory budget with median voting
- **Governance**: weighted assembly voting
- **Matrix**: auto-created chat room for condominium communication
- **EstablishmentMembership**: access control for fraction owners

## Frontend

- `/condo/create` -- creation wizard
- `/condo/{slug}/fractions` -- fraction management
- `/condo/{slug}/quotas` -- quota payment tracking with resident info and delinquency alerts (overdue payments highlighted)
- `/condo/{slug}/assembly` -- weighted poll creation with assembly vote history
- Permilagem explanation section (visual breakdown of ownership shares)
- Budget display with inline editing for admins (per-category monthly amounts)
- i18n: `locales/{en,pt,es,fr,de,ru}/condo.json` (~80 keys)

## Seed Data

`python3 manage.py seed_test_condominium [--reset]` -- creates "Condomínio Rua Augusta 10" with 6 fractions.

## Landing Page

Static landing at `condominios.parahub.io` (Portuguese default).

## Technical Details

- **Models**: `geo/models.py` -- CondominiumFraction, QuotaPayment (geo app, migration 0046)
- **Service**: `geo/services/condominium.py` -- CondominiumService
- **API**: `geo/endpoints/condominium.py` -- `/api/v1/condominiums/`
- **Frontend**: `pages/condo/` (create, [slug]/)
