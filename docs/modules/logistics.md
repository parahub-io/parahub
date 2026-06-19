# P-Hub (Decentralized Logistics)

Peer-to-peer shipment network where any Establishment can become a drop-off/pick-up point. Hub is a **service role** (flag on Establishment), not a separate entity.

## Design Principles

- **Hub = Establishment + flag** -- reuses directory, map, reviews, membership, payments
- **Anyone can be a hub** -- WoT 3+ to activate hub mode
- **No escrow** -- system tracks shipments, never holds funds
- **Chain relay** -- shipment can travel through multiple hubs via carriers
- **Carrier = any trusted user** -- WoT 1+ minimum

## How It Works

### Hub Activation

Any Establishment owner enables hub mode and configures:
- **Capacity**: max parcels (or unlimited)
- **Accepted sizes**: S (envelope), M (shoebox), L (backpack), XL (suitcase)
- **Storage duration**: up to 14 days
- **Storage fee**: sats/day (0 = free)
- **Instructions**: "Enter from backyard, ring bell"

### Shipment Lifecycle

```
Sender creates shipment (origin hub → destination hub)
    → Status: CREATED
    → Deposits parcel at origin hub
    → Status: AT_ORIGIN
    → Carrier picks up (from competing offers)
    → Status: IN_TRANSIT
    → Arrives at destination hub
    → Status: READY (receiver notified)
    → Receiver picks up with 6-digit code
    → Status: DELIVERED
```

Multi-hop: shipments can relay through intermediate hubs (AT_HUB status).

Auto-expiry: `expire_shipments` management command cancels stale shipments (CREATED/AT_ORIGIN past max storage days). Runs via `parahub-expire-shipments.timer` (daily). System-generated events have `actor=None`.

### Hub Operator Panel

Establishment detail page includes a hub operator panel for managing incoming shipments. Hub operators receive notifications on shipment status changes (deposit, pickup, delivery).

### Carrying Tab

Carriers see a "Carrying" tab on the shipments page showing shipments they are currently transporting (accepted offers with IN_TRANSIT status).

### Carrier Offers

Any WoT 1+ user can offer to carry a shipment. Sender sees competing offers with price, route, and carrier reputation. Direct Lightning payment between parties.

### Tracking

- **8-character tracking code**: public status lookup without login
- **6-digit pickup code**: secure handoff at destination
- **QR codes**: carrier scanning for status transitions
- **Event timeline**: full history of status changes with timestamps

## API

Endpoints at `/api/v1/shipments/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/hubs/` | GET | List active hubs (with filters) |
| `/` | POST | Create shipment |
| `/{tracking_code}/` | GET | Track shipment (public) |
| `/{tracking_code}/deposit/` | POST | Mark deposited at hub |
| `/{tracking_code}/offers/` | GET/POST | Carrier offers |
| `/{tracking_code}/offers/{id}/accept/` | POST | Accept carrier offer |
| `/{tracking_code}/pickup/` | POST | Carrier picks up |
| `/{tracking_code}/arrive/` | POST | Carrier arrives at hub |
| `/{tracking_code}/deliver/` | POST | Receiver picks up (requires pickup code) |
| `/available/` | GET | Shipments available for carriers |

## Technical Details

- **Models**: `logistics/models.py` -- Shipment, ShipmentEvent, CarrierOffer
- **Establishment hub fields**: `geo/models.py` -- is_hub, hub_capacity, hub_max_days, hub_storage_fee_daily, hub_accepted_sizes, hub_instructions
- **API**: `parahub/endpoints/shipments.py`
- **Map layer**: P-Hub markers on the map for active hubs (capacity, accepted sizes, opening hours)
- **Frontend**: `/shipments` (tracking + carrying tab + create flow), hub operator panel in establishment detail
- **Timer**: `parahub-expire-shipments.timer` (daily auto-expiry)
