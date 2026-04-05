# Contracts

Peer-to-peer digital contracts with cryptographic signatures and built-in dispute resolution.

## How It Works

1. **Creator** uploads a file (stays on their device), the system computes a SHA256 hash
2. **Partner** receives the contract, verifies the file hash matches, and co-signs
3. Both signatures are PGP-based (client-side) — the server never sees the file contents
4. Work happens according to the contract terms
5. Both parties independently mark the contract as complete and leave reviews
6. Contract is finalized only when both sides confirm

The platform stores only the file hash (64 characters), never the file itself. This means your contract documents remain private and under your control.

## Contract Lifecycle

`PENDING_PARTNER` → `SIGNED` → `COMPLETED` or `CANCELLED`

- **Pending**: Creator has signed, waiting for partner
- **Signed**: Both parties signed, work in progress
- **Completed**: Both parties confirmed completion and reviewed each other
- **Cancelled**: Either party cancelled before completion

## Linking Items and Property

Contracts can reference marketplace items (e.g., "this contract is about selling my bicycle"). When a contract is completed, linked items are automatically deactivated. Contracts can also reference a property (land, apartment, etc.) as the subject of the agreement.

## Arbitration

If a dispute arises, either party can initiate arbitration. The system supports three escalation levels:

### Level 1: P2P Arbitration
- Choose an arbiter during contract creation (optional) or when a dispute occurs
- An encrypted Matrix chat room is created with both parties and the arbiter
- Contract details are pinned in the room
- The arbiter reviews evidence and issues a verdict (favor_creator, favor_partner, partial, or dismissed)
- Typical timeline: 7-14 days
- Both parties rate the arbiter afterwards (1-5 stars)

### Level 2: Institutional (CAC)
- If P2P arbitration fails, escalate to a Commercial Arbitration Centre
- Formal institutional process

### Level 3: Court
- Final escalation to the Portuguese judicial system

### Arbiter Profiles

Users can register as arbiters with specializations, fee information, and a bio. Transparent statistics are publicly visible: verdict history, rating distribution, escalation rate, average resolution time.

### Clause Templates

The platform generates legally-informed arbitration clauses in 6 languages. Portuguese templates follow Lei n.º 63/2011 (Portuguese Arbitration Law). Three clause types available:

- **Ad hoc**: Custom arbiter, UNCITRAL rules
- **Institutional**: Commercial Arbitration Centre (CAC), Lisbon
- **Escalated**: Ad hoc first, then CAC if unresolved

## Proof Export

Every contract can be exported as a ZIP file containing:
- Contract metadata (JSON)
- PGP signatures from both parties
- OpenTimestamps proof (Bitcoin-anchored timestamp)
- Verification instructions

This package serves as court-ready evidence that the contract existed and was signed at a specific time.

## Buy Flow

From any marketplace item, clicking "Buy" takes you directly to contract creation with the seller pre-filled as the partner and the item pre-linked.
