# Carpool

Passenger-driven rideshare system built on top of GTFS transit stops. Instead of drivers posting routes, passengers post requests at transit stops and drivers offer rides.

## How It Works

1. **Passenger creates a request** at a transit stop (pickup point) with destination stop
2. **Drivers see nearby requests** and make competitive offers (price, time, vehicle info)
3. **Passenger accepts an offer** -- Matrix DM automatically created for coordination
4. **After the ride**, both parties leave reviews affecting reputation

## Key Design Decisions

- **Passenger-driven**: passengers set the demand, drivers respond. This inverts the traditional rideshare model.
- **Stop-based**: uses existing GTFS transit stops as pickup/dropoff points. No arbitrary addresses -- standardized, well-known locations.
- **No platform fee**: direct P2P arrangement. Payment method agreed between parties.
- **Route-based search**: Valhalla routing shows drivers which requests are along their planned route.

## Models

- **RideRequest** -- passenger's request (pickup stop, dropoff stop, time, passengers count)
- **RideBooking** -- driver's accepted offer (price, vehicle, estimated arrival)
- **RideReview** -- post-ride review from both parties

## Integration

- **Transit stops**: leverages GTFS stop database (46K+ stops) as pickup/dropoff points
- **Matrix DM**: auto-created when a booking is accepted
- **Valhalla routing**: route alignment for showing relevant requests to drivers
- **Map**: requests visible on the map layer

## Technical Details

- **Models**: `logistics/models.py` -- RideRequest, RideBooking, RideReview
- **API**: `parahub/endpoints/rides.py`
- **Frontend**: `pages/rides/` (not yet in production UI)
