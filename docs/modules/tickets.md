# Tickets

Unified ticketing for events and transit routes. Lightning payment goes directly from buyer to operator -- **no escrow**.

## How It Works

### Ticket Types
Operators (establishment owners/admins or staff) create ticket types linked to either an event or a transit route (mutually exclusive). Each type has a name, description, price in satoshis, and optional capacity limit.

### Purchase Flow
1. User selects a ticket type and clicks "Buy"
2. Server creates a PENDING ticket with a 15-minute expiry
3. User pays via Breez SDK (Spark address or Lightning invoice)
4. User submits payment preimage and hash to the server
5. Server verifies SHA256(preimage) == payment_hash, marks ticket ACTIVE
6. Optionally, user PGP-signs the QR token for cryptographic proof of ownership

### Validation
Operators scan QR codes via camera -- on the `/tickets/scan` page, or in the scanner embedded in the Driver Mode HUD, so a driver validates without ending the shift. Server verifies QR token and marks ticket USED. Only the ticket type operator or staff can validate.

### Offline Validation
Tickets carry a cryptographically signed QR. An operator can validate one with no connectivity -- the signature proves the ticket is genuine without a live server round-trip; the used-state syncs when back online.

The scanner also remembers what it has already seen during the shift: a single-use ticket scanned a second time on the same device is refused on the spot, and a time-limited ticket past its validity window is refused as ended. Refusals render in red, clearly distinct from the amber "authentic, queued for sync" advisory, so an inspector can tell "let them on" from "turn them away" at arm's length. The server remains the final authority once the queue syncs.

### Fares and Validity
Concession fares (student, senior, child) and validity windows -- single-use or time-limited. Network-wide agency tickets are valid across every route of a transit operator, not just one line. Prices can be set in EUR and shown with a live conversion to sats at the moment of purchase.

### Operator Tools
Establishment owners/admins act as operators (not only platform staff): they sell, validate, and manage their own ticket types. A sales dashboard shows tickets sold, revenue, and validations in real time. Refunds for unused tickets are issued directly back to the buyer.

## Access Control

| Action | Requirement |
|--------|------------|
| Create ticket type | WoT 3+ or staff |
| Purchase ticket | WoT 1+ (any authenticated) |
| Validate ticket | Ticket type operator or staff |

## Frontend

- **TicketPurchaseCard** -- shown on event detail and transit route pages
- **TicketBuyModal** -- payment flow with Breez SDK integration
- **TicketCard** -- ticket display in wallet "My Tickets" tab
- **TicketQRModal** -- full-screen QR code for validation
- **Scanner** -- `components/tickets/TicketScanner.vue` with camera QR reading (qr-scanner); hosted by the `/tickets/scan` page and as an overlay in the Driver Mode HUD

## Technical Details

- **Models**: `tickets/models.py` -- TicketType (event FK xor route FK), Ticket (PENDING/ACTIVE/USED, qr_token, ln_payment_hash, ln_preimage, pgp_signature)
- **API**: `tickets/api.py` -- CRUD for types, purchase, confirm, validate, sign, my tickets
- **Frontend**: `components/tickets/` (incl. `TicketScanner.vue`), `pages/tickets/scan.vue`, scanner overlay in `pages/driver.vue`
- **Seed**: `python3 manage.py seed_test_tickets [--reset]`
