# Lightning Wallet

Non-custodial Bitcoin wallet running entirely in the user's browser. Built with Breez SDK Spark (WASM).

## Architecture

The wallet is **client-side only**. Parahub's server never holds funds, keys, or wallet state. Everything runs in the browser via WebAssembly.

### Key Properties
- **Non-custodial**: user holds their own keys
- **Browser-based**: Breez SDK Spark compiled to WASM
- **Lightning Network**: instant, low-fee payments
- **On-chain**: standard Bitcoin transactions also supported
- **Spark addresses**: for receiving payments (in addition to standard Lightning invoices)

## Seed Management

### Generation
BIP39 mnemonic (12 words) generated client-side. Same seed can derive both the Lightning wallet and PGP keypair.

### Storage
Seed encrypted with user's PIN via PBKDF2 + AES-256-GCM. Encrypted blob stored in browser localStorage. Never sent to server.

### Backup
4-step process: Generate -> Verify (confirm words) -> PIN (set encryption) -> Confirm.

### Restore
12-word restore with autocomplete suggestions.

## Features

- **Receive**: Lightning invoices, Spark address, QR code
- **Send**: Lightning invoice payment, on-chain transactions
- **History**: transaction list with fiat equivalents
- **QR Scanner**: scan invoices from camera
- **Fiat Display**: amounts shown in user's preferred currency (real-time exchange rates)

## Integration with Parahub

- **Debts**: P2P debt tracking as a wallet tab (`/wallet/debts`). Create, confirm, repay debts. Clearing via barter cycles
- **Tickets**: purchase event and transit tickets via Lightning (no escrow -- direct buyer to operator)
- **Para-Ads**: micropayments for ad views
- **Mesh WiFi**: paid internet access via Lightning
- **Marketplace**: optional payment method for items
- **Profile**: Lightning address and Spark address displayed on public profile (auto-synced from SDK)
- **Donations**: voluntary 0%/0.1%/1% on wallet sends and ad campaigns

## Technical Details

- **Frontend**: `pages/wallet.vue`, `pages/seed-setup.vue`, `pages/seed-restore.vue`
- **Composables**: `composables/useSeed.ts` (BIP39, PIN encryption), `composables/useLightning.ts` (Breez SDK)
- **Exchange rates**: `currency/models.py` (ExchangeRate), cached in Redis (25h TTL)
- **Domain**: `breez.tips` (Breez SDK Spark endpoint)
