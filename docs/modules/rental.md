# Rentals & Booking

Rent things by the day or by the slot — bikes, rooms, tools, equipment, studio time. Any marketplace listing can be made bookable, with a live availability calendar that can never be double-booked. Booking is a deliberately lightweight layer: most rentals stop at a booking and never need a signed contract.

## How Booking Works

1. **Find a rentable listing.** Anything offered for rent by a person or an organization shows a live availability calendar.
2. **Choose a time.** Pick a date range (for stays and multi-day rentals) or a fixed time slot (for hourly bookings like a room or a court). Recurring weekly or monthly bookings are supported.
3. **Book it.** Depending on the owner's settings, the booking is confirmed instantly or sent as a request to approve. The calendar updates live for everyone watching the page.

## Two Booking Modes

- **By range** — a date range with pickup and return. Best for stays and multi-day gear.
- **By slot** — fixed time slots generated from the owner's opening hours. Best for a room by the hour, a court, or an appointment. Split shifts and lunch gaps are supported.

## Never Double-Booked

Overlapping bookings are rejected at the database level, not just in the interface — two people cannot grab the same slot in a race. Cancelling a booking frees its slot again immediately.

## For Owners

Make any listing bookable: choose range or slots, set opening hours, decide whether to instant-confirm or approve each request, and set buffers and how far ahead people can book. A live inbox shows incoming requests with one-tap confirm, complete, or cancel, and you can record a reason when cancelling. Owners can also enter a booking by hand for a walk-in client who isn't on Parahub, keeping the calendar accurate.

## Lightweight by Design

A booking sits beneath the heavier signed-contract layer. Most rentals never need more than a booking. For high-value rentals, a booking can still be formalized into a PGP-signed rental contract. As always, the platform holds no funds and no deposit — any payment is arranged directly between renter and owner.

## Access Control

| Action | Requirement |
|--------|------------|
| Browse availability | Anyone (a shared rental page is public) |
| Make a booking | Authenticated profile |
| Make a listing bookable / manage bookings | The item's owner, or a manager of the organization that posted it |
