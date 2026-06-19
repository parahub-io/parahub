# Parahub — Knowledge Base for Support Bot

## What is Parahub

Parahub is a peer-to-peer platform that eliminates middlemen from everyday economic interactions. Instead of paying 15-30% to platforms like Amazon, Upwork, or Airbnb, people trade, barter, and cooperate directly — with cryptographic trust, encrypted communication, and zero platform fees.

Parahub is a registered Portuguese non-profit association (Associacao PARAHUB, Viana do Castelo). It is not a marketplace (it's infrastructure), not a payment processor (never holds funds), not a social network (it's transactional).

Available in 6 languages: English, Portuguese, Spanish, French, German, Russian.

---

## Marketplace

Post what you have (Credit) or what you need (Debit) — goods, services, skills, or requests.

- Zero platform fees
- Automatic matching between buyers and sellers
- Multi-currency (fiat + Bitcoin optional)
- AI image validation for quality
- Geographic filtering by your location

**How to create a listing:**
1. Go to Marketplace (/market)
2. Click "Create" (/market/create)
3. Fill in title, description, photos, category, price, location
4. Publish — it appears on the map and in search

**How to buy:**
1. Browse items at /market or on the map (/map with Items layer)
2. Click on an item
3. Contact seller via encrypted chat
4. Agree on terms, optionally create a contract
5. Payment handled directly between you (not through the platform)

Manage your listings at /market/my-items.

**Requirements:** Registered account for limited items. Verified (3 Web of Trust confirmations) for full access.

---

## Identity & Web of Trust

Decentralized identity verification based on real relationships, not government documents.

- Multiple profiles: keep personal and pseudonymous identities separate (up to 7 per account)
- Portable reputation that follows you
- No KYC required — use anonymously until you want verified status
- Social recovery: trusted contacts can help you regain access

**Trust levels:**
- Anonymous: browse only
- Registered: create limited items, basic access
- Verified (WoT 3+): full marketplace, voting, events, contracts, messaging
- Supporter: extended quotas, governance badge

**How to get verified:**
1. Meet 3 verified users in person or via video call
2. Ask them to confirm your identity on the platform
3. Once confirmed, you unlock full access

Anti-fraud: if a verified person turns out to be fake, all 3 who verified them get consequences too. This makes false verification personally costly.

View and edit your profile at /profile.

---

## Contracts & Arbitration

Digital agreements with cryptographic signatures and built-in dispute resolution.

- No escrow: money stays with parties until both confirm completion
- Dual completion: both must sign off
- Contract file stays on your device — platform stores only a hash
- Court-ready proof with timestamps

**How to create a contract:**
1. From a marketplace item: click "Buy" — contract created automatically
2. Or go to /contracts and create manually (upload PDF or document)
3. Both parties verify the file, both sign with PGP
4. Work proceeds, both confirm completion
5. Both leave reviews

**If dispute occurs:**
- Level 1: hire a peer arbiter (trusted community member)
- Level 2: escalate to formal arbitration
- Level 3: take to court with cryptographic proof

Browse arbiters at /arbiters. View your contracts at /contracts.

---

## Communication & Chat

End-to-end encrypted messaging built into every interaction.

- Matrix protocol (decentralized, not locked to one company)
- Auto-created chat rooms when you buy/sell something
- Video calls built in
- Three chat clients: lightweight Cinny, mobile FluffyChat, full-featured Element

**How to message someone:**
1. Click "Chat" on any user's profile or marketplace item
2. Encrypted DM room opens immediately
3. Chat history persists

Go to /chat for all your conversations.

---

## Maps & Directory

Interactive map showing items, businesses, events, energy, transit, and real-time user presence.

- Find things nearby: items, services, businesses, events
- Turn-by-turn directions for walking, biking, driving
- Real-time transit vehicle tracking
- Business directory with hours, reviews, photos
- MMORPG-style avatars of online users on the map

**How to use:**
1. Open the map at /map
2. Toggle layers: Items, Establishments, Events, Transit, Energy, etc.
3. Search by address, business name, or category
4. Click any result for details

Browse the business directory at /directory.

---

## Governance & Voting

Direct democracy with optional delegation to trusted people (liquid democracy).

- One vote = one person
- Delegate your vote to an expert if you don't have time
- Change your vote or revoke delegation anytime
- Cryptographic audit trail — all votes verifiable

**How to vote:**
1. Go to /governance or /governance/polls
2. Review the poll question and options
3. Vote directly, or delegate to someone you trust
4. Results visible in real-time

**Treasury (budget voting):**
Members vote on how to spend organization budget. Each member assigns percentages to categories. Final allocation = median of all votes.

Requirements: Verified status to participate.

---

## Transit & Public Transport

Real-time public transport monitoring with live vehicle tracking.

Coverage: multiple cities worldwide with real-time GPS tracking. Check available cities at /transit.

**How to use:**
1. Open map (/map) and toggle Transit layer
2. See live bus/tram positions
3. Click a vehicle or stop for routes and schedules
4. Click a route to see all stops and arrival times
5. Plan trips: enter start/end points for walking + transit directions

Browse routes and schedules at /transit.

**Driver Mode:** Verified drivers (WoT 3+) can broadcast their GPS position so passengers see them on the map like official transit. Activate at /driver.

---

## P-Hub (Decentralized Logistics)

Send packages through local businesses and people as drop-off/pickup points.

- Any cafe or business can be a hub
- Multiple carriers compete to carry your package
- 6-character tracking code (no login needed)
- 4-digit pickup code for security
- Payment via Lightning directly to carrier

**How to send a package:**
1. Go to /shipments
2. Create shipment: select origin and destination hubs
3. Receive carrier offers with prices
4. Choose carrier, pay via Lightning
5. Track with 6-character code
6. Recipient picks up with 4-digit code

---

## Energy (P2P Solar Sharing)

Community solar sharing. Neighbors with solar panels share excess energy at fair prices.

- Direct producer-to-consumer, no utility middleman
- Smart triggers: automate devices based on solar surplus
- Compliant with Portuguese renewable energy law

**How to join:**
1. Browse energy cells on the map (/map with Energy layer) or at /energy
2. As producer: register your solar installation
3. As consumer: join a cell, choose producers
4. Set up smart triggers for your devices

Requirements: Property in an active energy cell.

---

## Wallet & Payments

Non-custodial Bitcoin Lightning wallet in your browser. You hold your own keys.

- Instant Lightning payments
- No platform can freeze or steal funds
- 12-word seed phrase (same phrase generates your PGP keys)
- Works for marketplace, tickets, ads, shipments, donations

**How to set up:**
1. Go to /seed-setup — generate and write down 12 words
2. Open wallet at /wallet
3. Receive: share Lightning invoice or Spark address
4. Send: paste invoice or scan QR code

---

## Events

Community events and meetups — online, offline, or hybrid.

- Every event gets an auto-created chat room
- QR ticket support with Lightning payment
- Map venue selection

**How to create an event:**
1. Go to /events
2. Click "Create" — fill in details, date, location
3. Share event link
4. Attendees RSVP and join chat

Requirements: Verified (WoT 3+) to create events.

---

## Blog & Mini-sites

Parahub has a built-in blog and website builder for users and organizations.

**Blog:**
- Write posts with a visual editor or in Markdown
- Attach PDF documents and photos to posts
- Pin important posts to the top
- Tag posts by category (News, Announcements, Minutes, etc.)
- Comments and photo galleries on posts
- RSS feed available

**How to create a blog post:**
1. Go to /blog and click "New post"
2. Choose to post as yourself or as an organization you manage
3. Write your post, attach files or photos
4. Save as draft or publish immediately

Requirements: Verified (WoT 3+) to publish posts. Drafts can be saved without verification.

**Mini-sites:**
- Organizations get a free website at {name}.org.parahub.io
- Custom branding: accent color and hero section
- Create custom pages (History, Services, Contacts)
- Connect your own domain name (e.g., my-organization.pt)

**How to set up a mini-site:**
1. Go to /org/{your-org}/manage
2. Click the Settings tab
3. Set your accent color and hero text
4. Add custom pages in the Pages tab
5. Optionally connect a custom domain

---

## ParaSOS (Emergency Mutual Aid)

Neighborhood emergency response network — faster than calling 911.

- SOS button with 3 alert levels: INFO, WARNING, EMERGENCY
- Group members see alert and respond in real-time
- Location sharing, medical info
- Hardware panic button support (volume down x3 on phone)

**How to use:**
1. Go to /sos
2. Create or join a safety group (max 50 members)
3. In emergency: press SOS, choose level
4. Group members see alert, respond with status

Requirements: WoT 1+ to join, WoT 3+ to create groups.

---

## Condominium Management

Building management for apartment buildings.

- Quota (maintenance fee) payments
- Assembly voting using liquid democracy
- Budget tracking, member list

Set up and manage at /condo.

---

## Advertising (Para-Ads)

Users-pay-users ad network. Advertisers pay YOU to view ads.

- Control which ad categories you see
- No tracking or surveillance
- Direct Lightning payment from advertiser to viewer

Browse and manage at /ads.

---

## OpenSky (Drone Mapping)

Upload drone photos — system creates orthomosaic maps and 3D models.

- Automatic stitching and georeferencing
- Flight plan generation for drones
- Compare same area across seasons

Access at /opensky.

---

## Mesh Networking

Community-owned WiFi using mesh routers.

- Free tier (512 kbps) or paid full-speed via Lightning
- Resilient local network
- Monitor coverage at /mesh

---

## Home Assistant Integration

Connect your smart home to Parahub.

- Control devices from the platform
- React to platform events (e.g., turn on heater when energy surplus)
- Manage at /iot

---

## Property ("My Home")

Track your properties and link them to contracts, energy, IoT.

- Draw land boundaries on map
- Upload photos
- Central location for all property-related activities

Manage at /my (My Home section in profile).

---

## Zenith (Personal AI Assistant)

Personal AI that answers questions based on your own knowledge base stored in Git.

- Create a knowledge repository
- AI answers questions from your contacts based only on your docs
- Access at /zenith

---

## Account & Getting Started

**How to register:**
1. Go to /register
2. Choose username or get an auto-generated one
3. Set password
4. (Optional) Set up PGP keys at /pgp-setup for encryption
5. (Optional) Create wallet at /seed-setup for payments

**How to sign in:** Go to /login.

**Contact support:** Email support@parahub.io

**Documentation:** Read detailed guides at /docs — with pages on each feature.
