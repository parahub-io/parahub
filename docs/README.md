# Parahub: Planetary Logistics

**Global Decentralized Infrastructure for Direct Cooperation and Efficient Economy**

[parahub.io](https://parahub.io) | [Status](https://status.parahub.io) | Open Source (MIT)

---

Parahub is a peer-to-peer platform that eliminates middlemen from everyday economic interactions. Instead of paying 15-30% to platforms like Amazon, Upwork, or Airbnb, people trade, barter, and cooperate directly -- with cryptographic trust, end-to-end encrypted communication, and zero platform fees.

Built as a registered Portuguese non-profit association (Associacao PARAHUB, Monção), the platform combines a marketplace, messaging, maps, governance tools, transit monitoring, mesh networking, and more into a single integrated system.

**Not** a marketplace (infrastructure). **Not** a payment processor (never holds funds). **Not** a social network (transactional). **Not** a blockchain.

## Documentation

| Document | Description |
|----------|-------------|
| [Vision](vision.md) | Why Parahub exists -- the problem, the solution, the long-term goal |
| [Philosophy](philosophy.md) | Core principles, ethical commitments, and red lines |
| [Features](features.md) | What the platform does today -- 30+ working subsystems |
| [Architecture](architecture.md) | Technical stack, patterns, and infrastructure |
| [Security](security.md) | Trust model, cryptography, audit trail, and threat mitigation |
| [Roadmap](roadmap.md) | What's planned -- mobile apps, auto-translation, ParaTube |
| [For Developers](for-developers.md) | API overview, self-hosting, contributing |
| [Modules](modules/) | Detailed documentation for individual subsystems |
| [Estatutos](estatutos.md) | NPO charter (Portuguese, legal document) |

## Quick Facts

- **Stack**: Django 5 / Ninja, Nuxt 4, PostgreSQL 16 / PostGIS / TimescaleDB, Redis, Neo4j
- **Identity**: ULID-based, multi-profile (up to 7 per account), Web of Trust verification
- **Crypto**: Client-side PGP (keys never leave the browser), Bitcoin/Lightning optional
- **Chat**: Matrix protocol (Synapse) with E2E encryption, three client options
- **Maps**: MapLibre + OpenStreetMap + self-hosted tiles, geocoding, routing
- **Transit**: 10 GTFS feeds, real-time vehicle tracking, multimodal routing
- **Mobile**: Capacitor (Android/iOS WebView shell), same codebase
- **Languages**: English, Portuguese, Spanish, French, German, Russian
- **License**: MIT

## Links

- **Live**: [parahub.io](https://parahub.io)
- **Status**: [status.parahub.io](https://status.parahub.io)
- **Source**: Self-hosted on [Gitea](https://gitea.parahub.io)
- **Chat**: Matrix at `#general:parahub.io`
