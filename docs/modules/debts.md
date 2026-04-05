# Debts

Peer-to-peer debt tracking with automatic clearing through barter cycles.

## How It Works

Record debts between users with mutual confirmation. Debts participate in the barter graph, so they can be automatically reduced through multi-party clearing.

### Creating a Debt

Two modes depending on who initiates:

- **"I owe you"** (debtor creates): Becomes active immediately — admitting a debt needs no confirmation
- **"You owe me"** (creditor creates): Requires debtor confirmation before becoming active

### Recording Repayments

The creditor records partial or full repayments. No confirmation needed from the debtor (a repayment benefits them). The remaining amount updates automatically.

### Debt Lifecycle

`PENDING_CONFIRMATION` → `ACTIVE` → `PARTIALLY_SETTLED` → `FULLY_SETTLED` or `CANCELLED`

Debtor-created debts skip confirmation and become `ACTIVE` immediately. Creditor-created debts start as `PENDING_CONFIRMATION`.

## Clearing via Barter Cycles

This is the powerful part. Debts are synced to the Neo4j graph database and participate in barter cycle detection alongside marketplace items.

**Example**: Bob owes Alice €1,000. Alice owes Carl €800. Carl owes Bob €600. The system detects this cycle and clears the minimum (€600) from all three debts simultaneously. Result: Bob owes Alice €400, Alice owes Carl €200, Carl's debt is fully settled.

Debts can also participate in mixed cycles with items: Bob owes Alice (debt) + Alice offers a bicycle (item) + Carl wants the bicycle and has what Bob needs → three-way exchange that reduces the debt.

## PGP Signatures

Debt creation and confirmation are PGP-signed when the user has a PGP key. This creates a cryptographic proof that both parties acknowledged the debt.

## Multi-Currency

Debts support any currency from the platform's currency system (EUR, USD, RUB, and more). The user's preferred currency is pre-selected.

## Where to Find It

Debts are accessible as a tab in the Lightning Wallet page (`/wallet/debts`). The interface shows three views:
- **Owed to Me**: Debts where you are the creditor
- **I Owe**: Debts where you are the debtor
- **Pending Confirmation**: Debts awaiting your confirmation (live badge counter)

Real-time updates via WebSocket keep all parties in sync.
