# Roadmap

This roadmap describes features that are designed and planned but not yet implemented. The core platform (30+ subsystems) is live at [parahub.io](https://parahub.io) -- see [Features](features.md) for what's already working.

---

## High Priority

### Mobile App Store Publishing
**Status**: Capacitor app shell works. APK available for download.
**Remaining**: App Store (iOS) and Google Play submission, app store assets and screenshots. Firebase push notifications are fully implemented.

### Federation (Server-to-Server)
**Status**: All 4 phases complete. Git-based registry with node PGP signatures, inter-node WebSocket, profile migrations with 4-signature OTS anchoring, cross-node WoT verifications, federated search, data import. See [Federation module](modules/federation.md).
**What's next**: Cross-node contracts, federated marketplace item propagation — waiting for second production instance.

---

## Medium Priority

### ParaTube (Decentralized Video)
**Status**: Not started.
**Design**: PeerTube-based decentralized video hosting. Federation with existing PeerTube instances. Monetization via Lightning micropayments. Community moderation. Integration with Parahub identity and reputation.
**Why it matters**: YouTube alternative without algorithmic manipulation and 30% revenue share.

### Auto-Translation for Marketplace
**Status**: Items have auto-detected language and country. Language filter exists in UI.
**Design**: AI-powered automatic translation of item titles and descriptions. Original text preserved, translations cached. Toggle to view original or translated.
**Why it matters**: Enables cross-language trade without manual translation effort.

---

## Lower Priority

### User Subdomains
`alice.parahub.io` as personal pages. Mini-sites for individuals and establishments with customizable content.

### HNA Marketplace
Transfer, sale, and auction of human-readable addresses (usernames). Address as a tradeable asset.

### AI-Assisted Item Listing
**Status**: Implemented. Upload a photo -> AI suggests category, title, description, and market price range -> user reviews and publishes. Voice-to-listing via speech recognition also available. Only tag suggestion remains unimplemented.

### LN Auto-Settlement for Carpool
Automatic Lightning payment upon ride completion. Currently, carpool payment is arranged between parties.

### Matrix Bot for Zenith
AI assistant accessible via Matrix chat, not just the web interface. Natural language queries about the platform.

### Route Alignment for Carpool
**Status**: Implemented. Valhalla-based corridor search shows passengers only to drivers whose route passes through their pickup/dropoff stops. Configurable corridor width and directional filtering.

### Desktop Client
Electron or Tauri desktop application (optional -- web app works on desktop already).

### Open Creative Ecosystem
Decentralized economy for content creators. Direct payments via Lightning, no platform cut. Reputation-based discovery.

### GovTech Pilot
Testing participatory budgets and digital governance tools in partnership with a municipality. The treasury system already supports this -- needs a real-world pilot.

### Kubernetes Deployment
Horizontal scaling, load testing, multi-node deployment. Currently runs on a single server -- architecture supports scaling but hasn't needed it yet.

### External Security Audit
Professional audit of cryptography, API security, PGP implementation, and WebSocket authentication.

---

## Architectural Decisions (Why Not X)

| Original Plan | What We Built Instead | Why |
|---|---|---|
| Flutter mobile app | Capacitor (WebView shell) | Rewriting 25+ subsystems in Dart was impractical. Capacitor: 95% code reuse, one codebase, native APIs (push, deep links, status bar) |
| Redpanda event bus + Turbomill | asyncio pipeline | Kafka/Redpanda is overkill for current load. asyncio: simpler, sufficient, full CQRS without Kafka |
| LND/Core Lightning (server) | Breez SDK Spark (client WASM) | Non-custodial is better: keys stay with user, no custodial risk, no server-side fund management |
| Celery (async tasks) | Management commands + asyncio daemons | Celery adds unnecessary complexity at current scale |
| channels_redis | Native Redis pub/sub | Direct Redis pub/sub: fewer dependencies, same functionality, less overhead |
| Organization model (identity app) | geo.Establishment | Simpler: unified model for businesses and organizations, profiles only for humans |
| OP_RETURN blockchain anchoring | OpenTimestamps via OTS calendar | OTS is battle-tested, costs nothing, and one anchor covers all events via Git Merkle tree |

These decisions follow the principle: **build what you need now, architect for what you'll need later**. Every component listed above can be replaced or upgraded without breaking the rest of the system.
