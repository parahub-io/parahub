# Para-Ads

P2P advertising where advertisers pay users directly for their attention. No advertising network middleman.

## How It Works

1. **Advertiser creates a campaign** with budget (Lightning), targeting criteria, banner image, and rich text content (TipTap editor)
2. **Platform matches ads to users** based on interests, skills, location, and demographics
3. **User sees the ad** (feed card with image + title + yellow reward badge) and receives a Lightning micropayment for viewing/engaging
4. **Advertiser pays the user directly** -- Parahub takes no cut

## Targeting

Advertisers can target by:
- **Interests** (18 categories)
- **Skills** (26 categories)
- **Geographic location** (radius-based)
- **Gender and age range**
- **Children's age groups** (for family-relevant products)

Users control which targeting categories apply to them via AdsProfile settings. Full opt-out available.

## Anti-Fraud

- One reward per account per ad campaign
- Only WoT-verified users can earn ad rewards
- View tracking prevents duplicate payments

## Models

- **AdsProfile** -- user's targeting preferences (interests, skills, location)
- **AdCampaign** -- advertiser's campaign (budget, targeting, content, establishment FK for act-as, optional banner image, linked Item or Establishment)
- **AdView** -- tracking record for each ad impression
- **AdsInterest** (18 items), **AdsSkill** (26 items), **AdsChildrenAge**, **AdsProfileSkill** -- targeting reference data

## Rich Content

- **Banner image**: auto-resized to 1200x630 JPEG (85% quality), deletable via API
- **TipTap rich text**: bold, italic, strikethrough, lists, blockquote, link (no headings)
- **Linked content**: campaign can reference one marketplace Item OR one Establishment (optional, shown in feed card)

## Act-as-Establishment

Campaigns can be posted on behalf of an organization via EstablishmentSelector.

## Technical Details

- **Models**: `ads/models.py`
- **API**: `parahub/endpoints/ads.py`, `parahub/endpoints/lnurl.py`
- **Services**: `ads/ln_wallet_service.py`, `ads/crypto_utils.py`
- **WebSocket**: `ads_feed` channel for live ad updates
- **Frontend**: `pages/ads.vue`
