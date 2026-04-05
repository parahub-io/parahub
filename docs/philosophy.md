# Philosophy and Core Principles

## Mission

Global P2P infrastructure for direct interaction without intermediaries. Fighting the "inefficiency tax" that platforms extract: Amazon 15-30%, Upwork 20%, banks 2-5%. Continuing the ideas of Gandhi and Tolstoy through modern technology -- local self-governance, direct democracy, mutual aid.

## Inviolable Constraints

These principles define the system's integrity. They are not negotiable.

### 1. System Never Holds Funds
Parahub is infrastructure, not a payment processor. No escrow, no custodial wallets, no fund management. All financial transactions are direct between parties. The Lightning wallet runs entirely in the user's browser (Breez SDK Spark, WASM).

### 2. Client-Side Cryptography Only
PGP keys **never** leave the client. The server stores only public keys. Critical operations (contracts, votes, debts) require client-side PGP signatures. Key generation, signing, and encryption happen in the browser via OpenPGP.js.

### 3. Web of Trust as Sybil Defense
Identity verification through human relationships, not government documents. Three or more confirmations from already-verified users required. If a verified account is proven fake, **all three verifiers** are automatically banned. This makes false verification personally costly.

### 4. CQRS for High-Frequency Data
Write operations go to PostgreSQL (source of truth). Real-time reads come from Redis. **Never** write high-frequency data (GPS positions, analytics, view counts) directly to PostgreSQL. Pipeline: API/Daemon -> Redis (live, ephemeral TTL) -> PostgreSQL (batch, downsampled).

### 5. Performance Targets
API response time < 50ms (p95). Designed for 100K users per node. N+1 queries are unacceptable. Denormalization is acceptable when it serves performance.

## Design Philosophy

### Decentralization First
Federation via Matrix protocol. P2P where possible. Self-hosting supported. No single point of failure. The system should work even if parahub.io goes down -- anyone can run their own instance.

### Privacy by Design
Location fuzzing (100m precision for public display). End-to-end encryption for all messaging (Matrix/Megolm). Minimal personally identifiable information collected. GDPR compliance by architecture, not by policy.

### Progressive Complexity
The core platform works without any cryptocurrency. Fiat currencies are first-class citizens. Bitcoin/Lightning is optional for those who want borderless micropayments. PGP is required only for critical operations (signing contracts, voting).

### Optimistic Locking
Version fields on critical models (Item, Exchange). Conflict detection and rollback for concurrent modifications. No pessimistic locking that would degrade performance.

## Economic Model

### No Platform Fees
P2P transactions with zero commissions. The platform is funded by:
- **Para-ads** -- ethical advertising where users are paid for attention
- **Premium logistics** -- optional value-added services
- **Association membership** -- voluntary contributions

### Barter-First Economy
Multi-party barter with 2-5 participants (configurable), powered by Neo4j graph cycle detection. Fiat and crypto serve as fallback, not primary. Reputation functions as currency -- it cannot be purchased, only earned through genuine interactions.

## Governance Model

- **Direct Democracy**: 1 user = 1 vote, with liquid democracy delegation. All votes are PGP-signed.
- **Arbitration**: Peer-based dispute resolution. Arbitrators selected by Web of Trust standing and specialization. Decisions affect reputation. Appeal mechanism available.
- **Community Moderation**: Content flagged and voted on by the community. Admin intervention only for clearly illegal content.

## Technical Principles

- **PostgreSQL = Source of Truth**: Neo4j (barter graph) and Redis (cache, real-time) are secondary stores. PostgreSQL always wins on conflicts.
- **API-First**: REST (Django Ninja) for mutations, WebSocket for real-time, SSR for SEO.

## Ethical Red Lines

1. **No mandatory government KYC** -- Web of Trust is sufficient for internal interactions
2. **No surveillance** -- not even "optional" tracking
3. **No protocol-level censorship** -- individual instances may moderate
4. **No rent-seeking** -- platform fees only for genuine value-added services
5. **No closed source** -- the core is MIT License, forever
6. **Focus on utility, not entertainment** -- infrastructure for real life, not infinite scrolling

## What Parahub Is NOT

- NOT a marketplace (it's infrastructure that enables marketplaces)
- NOT a payment processor (it never holds funds)
- NOT a social network (it's transactional, not attention-based)
- NOT a gig economy (no platform taking a cut of labor)
- NOT a blockchain (uses proven databases with optional Bitcoin anchoring)
