# Features

Everything listed here is implemented and running in production at [parahub.io](https://parahub.io).

---

## Identity and Trust

### Multi-Profile Identity
One account, up to 7 profiles (1 primary + 6 additional). Profile types: personal and pseudonymous. Each profile has its own reputation, items, contracts, and activity. ULID-based identifiers (26-character, globally unique, time-sortable). Human-readable addresses: `username@parahub.io`.

### Web of Trust (WoT)
Decentralized identity verification. 3+ confirmations from verified users required. 10 hierarchical trust levels (Anonymous → Authenticated → Has Profile → Personal/Pseudonymous → Verified → Apoiante → Efetivo → Fundador → Administrator) with a granular permission matrix. Fake account verified = all 3 verifiers auto-banned.

### PGP Cryptography
Client-side key generation and signing via OpenPGP.js. Server stores only public keys. Critical operations require PGP signatures: contracts, governance votes, debt records, treasury allocations. PGP key history tracked. Optional: derive PGP keypair from BIP39 seed phrase.

### Social Recovery
Account recovery through trusted contacts (M-of-N scheme). No reliance on email or phone number.

---

## Marketplace

### Items (Credit/Debit)
Universal listing model. **Credit** = "I'm offering" (goods, services, skills). **Debit** = "I'm looking for" (requests, needs). Flexible pricing: sale, rent, or free. Multi-currency support. Geolocation with map placement. AI-assisted image analysis for item validation. Auto-detected language and country for localization filtering.

### Category-Based Matching
850 categories in 5 languages across 17 root groups. Domain filtering (`applicable_to`: market/directory/events). Automatic matching: "I can offer X" shows items requesting X, and vice versa. Category tree with hierarchical navigation.

### Multi-Party Barter
Neo4j graph database for cycle detection. Automatic discovery of barter chains with 2-5 participants (configurable). A needs what B has, B needs what C has, C needs what A has -- the system finds these cycles automatically.

### Per-Item Visibility
Each listing chooses its audience: **public** (visible to everyone, including search engines) or **registered-only** (visible only to signed-in members). Sensitive offers can stay inside the community while public ones reach the whole web.

### Self-Made Mark
A listing can be marked **made by hand** to signal it is the seller's own craft, produce, or work -- not resale. A badge highlights it and a filter surfaces local makers and "your own and nearby" offers.

### Rentals and Booking
Any item listed for rent can be made bookable, with a live availability calendar and database-enforced no-double-booking. Two modes: a date range (pickup/return) or fixed time slots generated from opening hours (split shifts supported). Instant-confirm or approve-each-request, recurring weekly/monthly bookings, owner-entered walk-in bookings for offline clients, and a live manager inbox. A lightweight layer beneath the signed-contract system -- a booking can be formalized into a PGP-signed rental contract when needed. See [Rentals & Booking](modules/rental.md).

---

## Communication

### Matrix E2E Messaging
Synapse homeserver with OIDC single sign-on. Three client options: Element Web (full-featured), Cinny (lightweight), FluffyChat (mobile-first). End-to-end encryption via Megolm/Olm. Automatic DM room creation between users. Context messages with item/profile links. Instant switching between clients via KeepAlive.

### Video Calls
Jitsi Meet integration with JWT authentication. TURN server (coturn) for NAT traversal. One-click calling from user profiles.

### Web Push Notifications
Dual-channel: WebSocket (real-time, browser open) + Web Push (browser closed). Push notifications in 6 languages. Supported: Chrome, Firefox, Edge, Safari 16.4+.

---

## Maps and Geography

### Interactive Map
MapLibre GL JS with self-hosted OpenStreetMap vector tiles (Martin). Self-hosted font glyphs (no external CDN). KeepAlive for instant tab switching without tile reload. Canvas snapshot restore for instant map redraw. Live local weather overlay (temperature and conditions) in the map corner.

### Geocoding
Pelias with 213M documents, planet-wide coverage. Geographic bias via focus.point. Reverse geocoding for coordinates to addresses.

### Routing
Valhalla for street routing (car, walk, bike) with turn-by-turn maneuvers. MOTIS for multimodal transit routing (RAPTOR algorithm).

### Business Directory
Organization and business directory. WorldObject/Establishment model. Address search, map integration, photo galleries. Membership management with roles (Owner/Admin/Member). Public Board (Direção) section showing governance structure: president, board members, treasurer, auditor with role badges. Act-as-establishment: post items, events, and ads on behalf of an organization. Organization detail page features: open/closed status badge (based on opening hours), directions button (external map link), share button, map mini-view.

### Map Presence
Real-time MMORPG-style avatars on the map. Redis GEOHASH for spatial indexing. WebSocket tile-based pub/sub for efficient updates.

---

## Transit

### GTFS Import
Multiple transit feeds across cities worldwide, each with real-time vehicle tracking. Thousands of routes and stops. Auto-updated weekly via systemd timer with SHA256 hash caching. gtfstidy preprocessing for feed normalization. Multi-URL support for agencies with split feeds.

### Real-Time Vehicle Tracking
GTFS-RT feeds processed via asyncio pipeline. 30-second refresh cycle. Live vehicle positions on map. WebSocket broadcast by zoom-14 tiles. TimescaleDB for position history (1-day chunks, 7-day retention). Driver Mode vehicles injected into the same pipeline.

### ETA Engine
Segment travel time tracking with rolling observations. Schedule-based arrival predictions. Direction detection and zombie vehicle filtering. Route visualization with stop markers. SEO-friendly slug URLs for routes and stops.

### GTFS Relay
Public endpoints serve cached GTFS static ZIPs and GTFS-RT protobuf/JSON by feed slug. Third-party apps can consume Parahub's transit data without accessing upstream feeds directly.

---

## Governance

### Liquid Democracy
Multiple-choice polls with PGP-signed votes. Transitive delegation chains (delegate your vote to someone who delegates to someone else). Merkle tree audit log for verifiability. Security-audited (TOCTOU race conditions fixed). Real-time updates via WebSocket.

### Treasury
Per-establishment participatory budgets. Median voting with interactive sliders. Monthly budget epochs with freeze mechanism. Merkle audit chain. Real-time updates via WebSocket.

---

## Contracts and Debts

### P2P Contracts
Digital contracts with PGP signatures. Client-side SHA256 hash verification. Dual-completion (both parties must confirm). Optional subject property (FK to Property). Matrix DM auto-created for communication.

### Arbitration
Optional arbiter selection during contract creation. ArbiterProfile for qualified arbitrators. ArbitrationVerdict with typed outcomes (favor_creator/favor_partner/partial/dismissed). Three-level escalation: P2P resolution -> Consumer arbitration center (CAC/CICAP) -> Court. Clause template generator with Portuguese law context (Lei references).

### Debt Tracking
P2P debt records with debtor confirmation. Partial and full settlement tracking. Clearing via barter cycles (debt becomes a node in the Neo4j graph). Accessible as a tab in the Lightning Wallet page.

---

## Audit Trail

### Cryptographic Proofs
PGP keyring (public Git repository). OpenTimestamps batch Bitcoin anchoring (one anchor covers all events via Git Merkle tree). Matrix E2E message backup. Merkle audit for governance polls. ZIP export for court proceedings.

---

## Dashboard

### Home Page
Activity feed showing recent items, events, and community updates. Community pulse with live statistics (members, items, events, transit routes). Smart onboarding checklist for new users (verify identity, add first item, join chat, explore map).

---

## Events

Community events and meetups. Online, offline, or hybrid. Auto-created Matrix chat rooms. Map integration for venue selection. Establishment-hosted events supported. WoT level 2+ required. Cover image upload. Past events tab for browsing event history. Expanded event categories (7 new categories added).

---

## Blog & Mini-sites

### Blog
Built-in blogging for users and organizations. Markdown editor with visual WYSIWYG mode. Personal blogs (`/u/{name}/blog/`) and organization blogs (`/org/{slug}/blog/`). PDF/document attachments (critical for official minutes, regulations, budgets). Photo galleries with lightbox. Video embedding via `::video[uuid]` syntax (PeerTube). Comments. Pinned posts. Taxonomy tags for categorization (News, Announcements, Minutes). Multi-language posts with translation linking. RSS feeds. Subscribers-only posts (body gated to a profile's monthly supporters; title and teaser stay public). Full SEO (meta tags, Open Graph, JSON-LD Article). WoT level 2+ required to publish.

### Mini-sites
Custom-branded websites for organizations on subdomains (`{slug}.org.parahub.io`). Custom accent color, hero section with image and text, configurable navigation. Create unlimited custom pages (History, Services, Contacts, Regulations). Automatic SSL with wildcard certificates. Optional custom domain support (`my-organization.pt`) with CNAME validation and automatic Let's Encrypt certificates.

---

## Video

### PeerTube Integration
Self-hosted video platform at [video.parahub.io](https://video.parahub.io). Upload, transcode, and share videos without third-party services. HLS adaptive bitrate streaming (360p to 1080p). Drag-and-drop upload with progress bar (up to 4 GB). Videos can be attached to any object: marketplace items (product demos), blog posts (embedded via `::video[uuid]`), establishments (video tours), and profiles (personal channels). OIDC single sign-on — same Parahub account, no separate registration. ActivityPub federation for cross-instance video sharing. Browse videos at `/videos` with trending and recent tabs. Live streaming via RTMP (planned). **Platform never hosts on third-party services — all data stays on Parahub infrastructure.**

---

## Payments

### Lightning Wallet
Breez SDK Spark (client-side WASM, non-custodial). The wallet runs entirely in the browser. On-chain and Lightning transactions. QR scanner. Fiat equivalents displayed. Spark addresses for receiving. **The platform never holds funds.**

### Recurring Support (Subscriptions)
Commit to support a profile every month with a fixed Lightning amount -- a non-custodial, no-escrow recurring-support primitive. Because Lightning is push-only, each cycle is a one-tap re-payment from a reminder, sent directly to the recipient (**no auto-pull, no platform cut** -- the recipient keeps ~100%). An active subscription can unlock the recipient's subscribers-only blog posts. "Support monthly" button on any profile; cancel anytime, with access lasting until the paid period ends. Daily background job handles lapsing and renewal reminders.

### Para-Ads
P2P advertising system. Advertisers pay users directly via Lightning micropayments. Banner image upload (auto-resized 1200x630, JPEG 85%). Rich text content via TipTap editor. Linked content: campaigns can reference a marketplace Item or Establishment. Geo-targeting, interest targeting (18 interests, 26 skills), and demographic targeting. Users control which ad categories they see. Yellow reward badge on feed cards. Only verified users earn rewards.

---

## Mesh Networking

OpenWrt 25.x firmware. Two profiles: Bumblebee (L3 gateway, full stack) and Bee (L2 relay, minimal). Supported devices: AXT1800, MT3000, MT6000, AX53U, Cudy AP3000 Outdoor V1 (Bumblebee); AR300M16, CPE710 (Bee). batman-adv mesh + Yggdrasil overlay + WireGuard VPS gateway. Private WiFi with 802.11r/k/v roaming. Free WiFi with speed control (512kbps free, full speed paid via Lightning). Yggdrasil inbound ACL for secure IPv6 access. Anycast gateway for reliable node discovery. OTA auto-updates with SHA256 verification. Heartbeat API. Coverage map. Separate repository (`parahub-mesh/`).

---

## Condominium Management

Condominium management system implementing Portuguese Lei 8/2022. CondominiumFraction model with permilagem (‰) ownership shares. Quota payment tracking with resident info and delinquency alerts. Assembly polls with permilagem-weighted voting and vote history. Permilagem explanation section. Budget display and inline editing for admins. 6 default budget categories (quotas-ordinarias, fundo-reserva, seguros, limpeza, manutencao, outros). Reuses Treasury (participatory budgets), Governance (weighted voting), and Matrix (auto chat room). Frontend wizard: create condo -> manage fractions -> track quotas -> create assemblies.

---

## ParaSOS (Neighborhood Emergency Aid)

Community-driven emergency mutual aid system. Safety groups with geographic coverage (max 50 members). SOS button: tap for level selection, long press (1.5s) for instant EMERGENCY. Three alert levels (INFO/WARNING/EMERGENCY) with per-level notification preferences and quiet hours. Real-time response tracking (SEEN/ON_WAY/ON_SITE) with live elapsed timer. Two member types: LOCAL (physical response in 2-5 min) and REMOTE (coordinates from afar — calls 112, shares medical context). Matrix chat auto-created per group. InactivityWatch: passive safety monitoring for elderly via IoT/HA sensors — auto-WARNING when no activity detected. IoT/HA auto-trigger webhook for smoke/motion/door sensors. "I'm OK" daily check-in button. Auto-resolve stale alerts after 2h. Privacy by design: no background tracking, location shared only during active SOS, responder coordinates ephemeral (never stored). WoT 3+ to create groups, WoT 1+ to join.

---

## Energy

P2P solar energy distribution via ACC groups (Decreto-Lei 15/2022, Portugal). EnergyCell (geographic area), Producer, Consumer models. Property FK for linking to "My Home". GridInfrastructure model. Map layer with polygonal radius and status colors. Production monitoring. Smart Triggers: EnergyRelay model for direct Shelly/Tasmota device control (no Home Assistant required). HA Energy Signal integration: HAEntity energy_signal_role (SURPLUS_BOOL/SURPLUS_POWER/SURPLUS_PRICE) enables P2P energy → smart home automation.

---

## Aerial Imagery (OpenSky)

Community drone mapping protocol. JPG-only upload (batch up to 50 files / 500MB) with ODM (OpenDroneMap) processing. ZIP upload was removed. Automatic tile generation with auto-alignment to existing missions. 3D mesh generation with Draco compression and WebP textures (typical 12x size reduction). GLB download and fullscreen three.js viewer. KMZ flight plan generator for DJI drones (snake pattern, 75% overlap) with oblique angle support. Mission management and season comparison via web dashboard.

---

## Federation

Git-based server-to-server federation enabling multi-node deployment. Node identity via Ed25519 PGP keys. Profile migration with 4 signatures (old user, new user, old node, new node) anchored via OpenTimestamps. Cross-node WoT verifications. Federated search across peer nodes. Data import for profiles and items. WebSocket inter-node protocol with 5-minute heartbeat. All 4 phases complete.

---

## Psychoinformatics

Form 5 "Deep Self-Analysis Questionnaire" -- voluntary self-analysis questionnaire. Generates a 4-word Psycho-Hash (public, human-readable personality fingerprint). Visible to trusted contacts. AI-assisted analysis.

---

## Ticketing

### Unified Tickets
Ticketing for events and transit. Lightning payment directly from buyer to operator (**no escrow**). QR code validation. PGP-signed tickets for cryptographic proof. Purchase flow: Breez SDK pay -> server verifies SHA256(preimage) -> ticket activated. Camera-based QR scanner for operators.

### Operator Tools and Fares
Establishment operators (not just staff) sell and validate tickets. EUR pricing with a live sats quote at purchase. Concession fares (student, senior, child) and validity windows (single-use, time-limited). Network-wide agency tickets valid across every route, not just one line. Offline validation via signed QR -- a ticket verifies without a live server check. Refunds for unused tickets issued directly back to the buyer. Operator sales dashboard with tickets sold, revenue, and validations in real time.

---

## Driver Mode

Browser-based GPS broadcasting for transit vehicles. Verified drivers (WoT 3+) select a route and broadcast their position to the transit real-time pipeline. Passengers see driver vehicles on the map alongside official GTFS-RT feeds. Wake lock prevents screen sleep. TTS announces upcoming stops.

---

## IoT and GPS Tracking

### Tracker Pipeline
Traccar integration for personal GPS trackers. Zero PostgreSQL writes in the hot path: Traccar webhook -> Redis (GEOADD/HSET/PUBLISH) -> TimescaleDB batch insert every 60 seconds. WebSocket for real-time map overlay. Transit bridge: if a tracker device has an active vehicle assignment, positions also appear on the transit layer.

### Property ("My Home")
Personal property management. 7 property types (house, apartment, land, office, dacha, garage, other). Inline map picker for location. Optional WorldObject FK with auto-filled address. Territory polygon for boundaries. Cross-system integration: IoT devices, Home Assistant homes, energy producers/consumers, and contracts can link to a property. Photo upload. GeoJSON map layer.

### Home Assistant Integration
Connect user-owned Home Assistant instances to Parahub. Discover, import, and control smart home entities. Supported domains: light, switch, fan, cover, lock, climate, media_player, vacuum, and more. Fernet-encrypted access tokens. Periodic state sync (60s timer). Connection via Yggdrasil IPv6 (zero NAT), public URL, or any reachable endpoint. SSRF-protected URL validation.

### Dispatch
Staff-only vehicle assignment workflow. Link IoT tracker devices to transit routes. Assignment status: Assigned -> Active (auto on first GPS position) -> Completed/Cancelled. Route search, device inventory, and auto-refresh dashboard. Stop snapping: vehicles with active assignments auto-snap to nearest stop on their route shape.

### Transit Management
Platform for transit companies to manage operations via web UI. Create managed agencies with ownership. Custom route and stop creation with Valhalla shape generation. GTFS export for managed agencies. Managed entities excluded from GTFS feed import cycle. Pages at `/dispatch/routes` and `/dispatch/stops`.

### Mesh Nodes
Mesh network node subscriptions with status monitoring.

---

## P-Hub (Decentralized Logistics)

### Shipment Network
Any Establishment can become a P-Hub — a drop-off/pick-up point for P2P shipments. Hub is a service role (flag on Establishment), not a separate entity. Hub operators set capacity, accepted parcel sizes (S/M/L/XL), storage duration (up to 14 days), and optional daily storage fees in sats. P-Hub markers displayed on the map layer. Hub operator panel on establishment detail page for managing incoming shipments. Auto-expiry of stale shipments via `expire_shipments` management command + systemd timer.

### Shipment Tracking
Full lifecycle: Created -> At Origin -> In Transit -> At Hub -> Ready -> Delivered. 8-character tracking codes for public status lookup. 6-digit pickup codes for secure handoff. Multi-hop relay through intermediate hubs. QR codes for carrier scanning. Hub operator notifications on shipment status changes. "Carrying" tab for carriers to view shipments they're transporting.

### Carrier Offers
Any trusted user (WoT 1+) can offer to carry a shipment between hubs. Sender selects from competing offers based on price, route, and carrier reputation. **No escrow** -- payments direct between parties via Lightning.

---

## Carpool

Passenger-driven rideshare at transit stops. Ride requests, competitive driver offers, post-ride reviews. Matrix DM on booking acceptance. Route-based search via Valhalla routing.

---

## AI Features

### Image Analysis
Multi-provider AI vision (Claude, GPT, Gemini). Quota system (30 analyses/day). Two-step process: analyze first, then verify before publishing.

### Zenith Assistant
Personal AI agent powered by Gemini. Knowledge base stored in Gitea. Context-aware responses about the platform.

### Image Generation
Editorial content (blog illustrations, mascot poses, marketing visuals). Nano Banana Pro/2 prompting with style anchors for series consistency.

### Support Voice
Anonymous voice-to-voice help pipeline. ElevenLabs STT → Gemini Flash (knowledge lookup against docs) → ElevenLabs TTS. No login required.

---

## Infrastructure

### Monitoring
NetData v2.9 (native) for system metrics. Uptime Kuma v2.2 (Docker) with 30 monitors. Public status page at [status.parahub.io](https://status.parahub.io). Auto-heal for service recovery. PostgreSQL automated backups.

### Git Hosting
Gitea with OIDC single sign-on. Iframe embedding in the platform.

### Landing Pages
Static landing pages for feature promotion. Jinja2 + Tailwind CDN + Lucide icon inlining. Zero JavaScript, perfect SEO, instant load. 10 active landings: condominios, energia, transporte, democracia, directorio, eventos, troca, boleias, contratos, sos (all `*.parahub.io`). i18n in 6 languages. `?from=` CTA tracking parameter.

### Design System
UiButton, UiTabs, UiBadge, UiAlert components. Split-complementary color palette with CSS design tokens. Light/dark theme. Design showcase page. Accessibility: WCAG 2.1 compliance (ARIA, keyboard navigation, focus management).

### Mobile App
Capacitor shell (Android/iOS WebView). Same Nuxt codebase. Deep links, push notifications, status bar, keyboard handling, hardware back button. Gamepad navigation for Steam Deck.

### SEO
Server-side rendering (Nuxt SSR). JSON-LD structured data. Automatic sitemap generation. OpenGraph images. hreflang for 6 languages. Plausible CE self-hosted analytics.

### Internationalization
6 languages: English (default, no URL prefix), Portuguese, Spanish, French, German, Russian. Modular translation files. Auto-sync with user profile language preference.
