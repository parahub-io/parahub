# Property ("My Home")

Personal property management system. Users register their properties and link them across multiple Parahub subsystems.

## Model

Property (in `iot` app) with fields:
- **owner** -- FK to Profile
- **name** -- unique per owner
- **property_type** -- house, apartment, land, office, dacha, garage, other
- **building** -- optional FK to geo.Building (auto-fills location + address on save)
- **location** -- PointField (GPS coordinates)
- **territory** -- PolygonField (property boundaries, optional)
- **address** -- text
- **photo** -- ImageField

## Cross-System Integration

Property serves as a unifying entity across 5 systems:

| System | FK Field | Purpose |
|--------|----------|---------|
| IoT | `IoTDevice.property` | GPS trackers and sensors at a property |
| Home Assistant | `HAHome.property` | Smart home instance at a property |
| Energy | `EnergyProducer.property` | Solar installation at a property |
| Energy | `EnergyConsumer.property` | Energy consumption at a property |
| Contracts | `Contract.subject_property` | Contract about a property |

## Frontend

- **PropertyCard**: type badge, device count, HA entity count
- **PropertyForm**: name, type, inline map picker (MapLibre) for location, address
- **Map picker**: uses `useMapState()` composable for persisted position (no hardcoded coordinates)
- **GeoJSON layer**: properties displayed on the map with boundaries
- Devices list grouped by property with count badges
- i18n: `locales/{en,pt,es,fr,de,ru}/property.json`

## API

Endpoints at `/api/v1/iot/properties/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | POST | Create property |
| `/` | GET | List user's properties |
| `/{id}/` | GET | Property detail with device/HA counts |
| `/{id}/` | PATCH | Update property |
| `/{id}/` | DELETE | Delete property |
| `/map/` | GET | GeoJSON for map layer |

## Technical Details

- **Model**: `iot/models.py` -- Property (migration iot/0017)
- **API**: `iot/endpoints/property.py`
- **Frontend**: `components/IoT/PropertyCard.vue`, `components/IoT/PropertyForm.vue`
