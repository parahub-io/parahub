# Carpool

Passenger-driven rideshare system built on top of GTFS transit stops. Instead of drivers posting routes, passengers post requests at transit stops and drivers offer rides.

## How It Works

1. **Passenger creates a request** at a transit stop (pickup point) with destination stop
2. **Drivers see nearby requests** and make competitive offers (available seats plus a note with vehicle and timing details)
3. **Passenger accepts an offer** -- Matrix DM automatically created for coordination
4. **After the ride**, both parties leave reviews affecting reputation

## Key Design Decisions

- **Passenger-driven**: passengers set the demand, drivers respond. This inverts the traditional rideshare model.
- **Stop-based**: uses existing GTFS transit stops as pickup/dropoff points. No arbitrary addresses -- standardized, well-known locations, and the passenger never has to publish their home address.
- **Live requests**: requests are for right now, not a schedule -- they expire automatically after about an hour, so drivers only see people actually waiting.
- **No platform fee**: direct P2P arrangement. Payment method agreed between parties.
- **Route-based search**: Valhalla routing shows drivers which requests are along their planned route.

## Models

- **RideRequest** -- passenger's request (pickup stop, dropoff stop, passenger count, price offered)
- **RideBooking** -- driver's offer, later the confirmed booking (available seats, driver's note)
- **RideReview** -- post-ride 1-5 review from both parties

## Integration

- **Transit stops**: leverages the GTFS stop database as pickup/dropoff points
- **Stranded passengers**: when someone has been waiting at a stop with nothing live on their awaited line, the stop page promotes the rideshare option and shows how many others are stuck there -- a bridge from a failed bus to a neighbour's car
- **Matrix DM**: auto-created when a booking is accepted
- **Valhalla routing**: route alignment for showing relevant requests to drivers
- **Web of Trust**: both sides are verified members -- creating a request and offering a ride each require WoT verification

## Technical Details

- **Models**: `logistics/models.py` -- RideRequest, RideBooking, RideReview
- **API**: `parahub/endpoints/rides.py`
- **Frontend**: `pages/transit/rides/` -- the Rideshare tab on `/transit`
