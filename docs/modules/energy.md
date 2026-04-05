# Energy

Peer-to-peer solar energy distribution through ACC (Autoconsumo Coletivo) groups, implementing Portugal's Decreto-Lei 15/2022 for renewable energy communities.

## Concept

Portuguese law allows groups of neighbors to share solar energy production. An EnergyCell defines a geographic area where producers and consumers can form a group. Solar panel owners feed excess energy to the group. Consumers in the same cell benefit from local renewable energy at reduced cost.

## Models

- **EnergyCell** -- geographic area (polygon on map) with status monitoring
- **EnergyProducer** -- solar panel installation within a cell (capacity, production data, optional Property FK)
- **EnergyConsumer** -- household or business consuming shared energy within a cell (optional Property FK)
- **GridInfrastructure** -- grid infrastructure elements
- **EnergyRelay** -- direct smart trigger for Shelly/Tasmota devices (no Home Assistant required)

## Features

- Map layer with polygonal radius showing cell coverage areas
- Status colors indicating cell health (active, inactive, needs members)
- Producer/consumer registration and management
- Production monitoring dashboard

## Smart Triggers

Two pathways for energy surplus → device control:

1. **EnergyRelay** (direct): Shelly/Tasmota HTTP commands triggered by surplus events. No Home Assistant required. Model stores device URL, command templates, and trigger conditions.
2. **HA Energy Signal**: HAEntity `energy_signal_role` field (SURPLUS_BOOL / SURPLUS_POWER / SURPLUS_PRICE) enables Home Assistant entities to react to P2P energy surplus signals. Requires HA integration.

## Map Integration

Energy cells are displayed as a layer on the Parahub map. Each cell shows its boundary, member count, and current status. Click to view details and join.

## Technical Details

- **Models**: `energy/models.py` -- EnergyCell, EnergyProducer, EnergyConsumer, EnergyRelay, EnergyBillingRecord
- **HA Signal**: `iot/models.py` -- HAEntity.energy_signal_role
- **API**: `energy/api.py` -- `/api/v1/energy/`
- **Frontend**: `pages/energy.vue`
