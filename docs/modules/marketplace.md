# Marketplace

The marketplace is Parahub's core economic module. Users create **Items** -- universal listings that represent goods, services, skills, or requests. No platform fees. No algorithmic ranking. Direct P2P trade.

## Items

Every listing is an Item with a direction:
- **Credit** ("I'm offering") -- goods for sale, services available, skills offered, things to give away
- **Debit** ("I'm looking for") -- requests, needs, "want to buy", job postings

### Pricing
Items support flexible pricing options:
- **Sale** -- fixed price in any supported currency, with optional unit (per kg, per hour, etc.)
- **Rent** -- recurring price with period (per day, per month, etc.)
- **Free** -- gift economy, no payment expected

Multiple pricing options per item (e.g., "sell for 50 EUR or rent for 10 EUR/month or free for community members").

### Location
Items are placed on the map with coordinates. Country auto-detected from coordinates via Pelias reverse geocoding. When browsing, users see items filtered by their language and country by default, with a toggle to show all.

### Language
Item language is auto-detected from title/description text (langdetect). International items (`is_international` flag) bypass language/country filters -- useful for digital services, shipping-available goods, or universal offers.

### Images
Multiple images per item with drag-to-reorder. AI validation available (multi-provider: Claude, GPT, Gemini) with quota (30 analyses/day). EXIF GPS extraction for auto-location.

### Visibility
Each item picks its audience: **public** (the default -- visible to everyone, including search engines) or **registered-only** (visible only to signed-in members). Lets sensitive or community-internal offers stay off the public web while public listings reach the whole internet.

### Self-Made Mark
An item can be flagged **made by hand** to signal it is the seller's own craft, produce, or work -- not resale. Shown as a badge on the listing and available as a browse filter, surfacing local makers and "your own and nearby" supply.

## Category-Based Matching

850 categories organized in a hierarchical tree (5 languages: en, es, fr, pt, ru). Each item tagged with categories. SEO-friendly slug URLs for items.

Smart matching:
- **"I can offer"** filter: shows Debit items whose categories match the user's Credit item categories
- **"I want"** filter: shows Credit items whose categories match the user's Debit item categories

This creates a "needs marketplace" -- not just supply finding demand, but demand finding supply.

## Multi-Party Barter

Neo4j graph database stores item ownership and category relationships. Automatic cycle detection finds barter chains:

```
Alice has apples, wants books
Bob has books, wants furniture
Carol has furniture, wants apples
-> 3-party barter cycle detected!
```

Chain length: 2-5 participants (configurable via admin settings). The system finds cycles automatically and presents them to participants for approval.

## Act-as-Establishment

Items can be posted on behalf of an organization (Establishment). The `EstablishmentSelector` dropdown lets members post as their business or association. Requires appropriate membership role (Owner/Admin/Member with posting rights).

## Technical Details

- **Models**: `market/models.py` -- Item (photos via core.ObjectPhoto, videos via core.ObjectVideo)
- **API**: `parahub/endpoints/items.py` -- CRUD, matching, search
- **Frontend**: `pages/market/` (index, create, [id], my-items), `components/market/`
- **Barter**: `barter/graph_service.py` (Neo4j), `barter/neo4j_client.py`
