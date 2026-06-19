# Directory

Business and organization directory with building-centric listings, map integration, and reviews.

## Overview

The directory lets communities map their local businesses, cooperatives, associations, and other organizations. Click on a building on the map to see what's inside, or browse the catalog with filters.

## WorldObjects and Establishments

- **WorldObject**: A universal real-world entity (building, landmark, infrastructure). Linked to OpenStreetMap data via xeno_source/xeno_id. Has address, type, and location
- **Establishment**: A business or organization linked to a WorldObject. Has a name, category, opening hours, contact info, and more

One WorldObject can house many establishments (like a shopping center). Establishments can also exist without a WorldObject (online organizations).

## Organization Types

Establishments can be: company, NGO, cooperative, association, condominium, community, or government. Each type has specific features — for example, associations have a public Board (Direção) section showing president, board members, treasurer, and auditor.

## Features

### Open Now Indicator
Opening hours (in OSM format) are displayed on every listing. A real-time badge shows whether the establishment is currently open or closed.

### Reviews and Ratings
Verified users (WoT 3+) can leave star ratings (1-5) and written reviews. Establishment owners can reply to reviews. Average ratings and review counts are displayed on listings.

### Membership
Organizations (associations, cooperatives, NGOs, communities) support membership management:
- Join/leave with optional terms acceptance
- Member roles: Owner, Admin, Member
- Membership levels: Apoiante, Efetivo, Fundador
- Treasurer designation (receives organization payments)
- Auditor (Fiscal Único) designation for financial oversight

### Act as Establishment
Members with posting rights can create items, events, and ads on behalf of the establishment.

### Map Integration
- Click on any building on the map to see its establishments
- Browsable catalog panel with search, category filters, and viewport-based results
- Each establishment detail view includes an inline map

### Payment
Establishments can set a Lightning/Spark address for receiving payments directly.

## Access Control

- **View/search**: Public (no login required)
- **Create building or establishment**: WoT 3+ (verified by 2 or more users)
- **Write reviews**: WoT 3+
- **Edit/delete establishment**: Owner only
- **Manage members/treasurer/auditor**: Owner or Admin
