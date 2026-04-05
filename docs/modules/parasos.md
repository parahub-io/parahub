# ParaSOS

Community-driven neighborhood emergency mutual aid system. Replaces expensive security companies with direct neighbor-to-neighbor coordination. A neighbor 300 meters away arrives in 2-5 minutes -- faster than any police response in rural areas.

## The Problem

In rural areas, police response times can exceed 20 minutes. Security companies like Prosegur charge 30-50 EUR/month and essentially just call the police for you. Friends and family live far away. The result: homes are vulnerable, elderly people are without quick help, and opportunistic thieves need only 10 minutes.

## How It Works

Residents form **safety groups** tied to a geographic area. When someone needs help, they press the **SOS button** -- all group members instantly receive a push notification with the sender's location. Nearby members can come look at the situation within minutes. No intervention required -- just the presence of observers is enough to deter 90% of opportunistic incidents.

### Two Types of Participants

- **Local members**: Neighbors who can physically respond in 2-5 minutes. They come, observe, and report
- **Remote members**: Family members in other cities who get notified instantly. They can call 112, share medical history with responders, and coordinate the situation from afar

### Three Alert Levels

| Level | Examples | Sound | Quiet Hours |
|-------|----------|-------|-------------|
| **Info** | Suspicious car, unfamiliar person | Silent push | Respected |
| **Warning** | Alarm triggered, door knocked at night | Short alert | Ignored |
| **Emergency** | Need help NOW, break-in, fire, medical | Siren + repeat | Ignored |

## Features

- **Safety groups** with geographic coverage area (map-based, max 50 members by default)
- **SOS button** -- tap for level selection, long press (1.5s) for instant EMERGENCY
- **Real-time response tracking** -- see who has seen your alert, who is on the way, who is on site
- **Live elapsed timer** on active SOS alerts
- **Push notifications** with level-based sound and vibration patterns
- **Matrix chat room** auto-created for each group -- encrypted group communication
- **Privacy by design** -- no background tracking, location shared only during active SOS
- **Web of Trust** integration -- only verified members can create or join groups
- **Passive safety (InactivityWatch)** -- monitors elderly via IoT/HA sensors, triggers WARNING if no activity detected for configurable hours
- **IoT/HA auto-triggers** -- smoke sensors, motion detectors, door sensors can automatically send SOS alerts via webhook
- **"I'm OK" check-in** -- daily button for elderly as alternative to IoT sensors
- **Auto-resolve** -- stale alerts (active >2h) are automatically resolved

## Privacy Guarantees

ParaSOS does NOT track members. Location is shared ONLY:
- **SOS sender**: automatically when pressing the button (they asked for help)
- **Responder**: voluntarily, only while actively responding

No "last seen", no "nearby" features, no background GPS -- these data simply do not exist in the system. Responder coordinates are ephemeral (WebSocket only) and never stored in the database.

## Use Cases

- **Home security**: Alarm triggered at night? Neighbors check within minutes
- **Medical emergency**: Elderly person fell? Neighbor provides first aid while ambulance is coming
- **Fire**: Smoke detected? Neighbors can alert everyone and help evacuate
- **Elderly care**: Remote family members receive alerts and can coordinate with local neighbors
- **General safety**: Suspicious activity in the neighborhood? Inform everyone with a single tap

## Coming Soon

- **Physical panic button**: Zigbee/WiFi hardware button for one-press emergency
- **Responder map**: Real-time MapLibre map of responder positions during active SOS
- **Embedded Matrix chat**: In-app chat on the active SOS screen
- **Voice messages**: Audio recording attached to SOS alerts
- **Federated SOS**: Cross-node emergency alerts between Parahub instances

## Technical Details

- **Models**: `parasos/models.py` -- SafetyGroup, SafetyGroupMember, SOSAlert, SOSResponse, InactivityWatch, GroupInvite
- **API**: `parasos/api.py` -- `/api/v1/parasos/` (21 endpoints including auto-trigger, activity check-in, and group invites)
- **Frontend**: `pages/parasos/` -- group list, detail with SOS button (long press), create wizard
- **Real-time**: WebSocket channel `parasos:{group_id}` + Web Push notifications
- **Matrix**: Auto-created room per group, SOS notices as `m.notice`
- **Timers**: `parahub-sos-resolve` (15min, auto-resolve), `parahub-inactivity-check` (hourly)
- **Landing**: `sos.parahub.io` (static, 6 locales)
