"""
P-Hub Shipment API endpoints.
Any Establishment with is_hub=True can be a logistics point.
"""

from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel, Field
from typing import Optional
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, F
import logging

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from logistics.models import Shipment, ShipmentEvent, CarrierOffer
from geo.models import Establishment

logger = logging.getLogger(__name__)

shipments_router = Router()

SIZE_CHOICES = {'S', 'M', 'L', 'XL'}


# --- Schemas ---

class ShipmentCreate(BaseModel):
    title: str = Field(max_length=200)
    size_category: str = Field(pattern="^(S|M|L|XL)$")
    receiver_id: str
    origin_hub_id: str
    destination_hub_id: str
    item_id: Optional[str] = None
    delivery_fee: int = Field(default=0, ge=0)

class CarrierOfferCreate(BaseModel):
    fee_sats: int = Field(default=0, ge=0)

class VerifyPickupBody(BaseModel):
    pickup_code: str = Field(min_length=6, max_length=6)

class HubSettingsUpdate(BaseModel):
    is_hub: Optional[bool] = None
    hub_capacity: Optional[int] = Field(default=None, ge=0)
    hub_max_days: Optional[int] = Field(default=None, ge=1, le=90)
    hub_storage_fee_daily: Optional[int] = Field(default=None, ge=0)
    hub_accepted_sizes: Optional[list[str]] = None
    hub_instructions: Optional[str] = None


# --- Helpers ---

def _profile_brief(profile) -> dict:
    return {
        'id': profile.id,
        'display_name': profile.display_name,
        'hna': profile.hna,
    }


def _hub_brief(est) -> Optional[dict]:
    if not est:
        return None
    loc = est.location or (est.world_object.location if est.world_object else None)
    return {
        'id': est.id,
        'name': est.name,
        'slug': est.slug,
        'lat': loc.y if loc else None,
        'lon': loc.x if loc else None,
        'hub_instructions': est.hub_instructions,
    }


def _shipment_response(shipment, include_pickup_code=False) -> dict:
    data = {
        'id': shipment.id,
        'object_type': 'shipment',
        'title': shipment.title,
        'tracking_code': f"PH-{shipment.tracking_code}",
        'status': shipment.status,
        'size_category': shipment.size_category,
        'sender': _profile_brief(shipment.sender),
        'receiver': _profile_brief(shipment.receiver),
        'origin_hub': _hub_brief(shipment.origin_hub),
        'destination_hub': _hub_brief(shipment.destination_hub),
        'current_hub': _hub_brief(shipment.current_hub),
        'item_id': shipment.item_id,
        'storage_fee_total': shipment.storage_fee_total,
        'delivery_fee': shipment.delivery_fee,
        'expires_at': shipment.expires_at.isoformat() if shipment.expires_at else None,
        'delivered_at': shipment.delivered_at.isoformat() if shipment.delivered_at else None,
        'created_at': shipment.created_at.isoformat(),
    }
    if include_pickup_code:
        data['pickup_code'] = shipment.pickup_code
    return data


def _event_response(event) -> dict:
    return {
        'id': event.id,
        'object_type': 'shipment_event',
        'event_type': event.event_type,
        'hub': _hub_brief(event.hub),
        'actor': _profile_brief(event.actor) if event.actor else None,
        'note': event.note,
        'created_at': event.created_at.isoformat(),
    }


def _offer_response(offer) -> dict:
    return {
        'id': offer.id,
        'object_type': 'carrier_offer',
        'carrier': _profile_brief(offer.carrier),
        'from_hub': _hub_brief(offer.from_hub),
        'to_hub': _hub_brief(offer.to_hub),
        'fee_sats': offer.fee_sats,
        'status': offer.status,
        'matrix_room_id': offer.matrix_room_id or None,
        'created_at': offer.created_at.isoformat(),
    }


def _validate_hub(est_id: str, label: str = "Hub") -> Establishment:
    est = Establishment.objects.filter(id=est_id, is_hub=True, is_active=True).first()
    if not est:
        raise HttpError(404, f"{label} not found or not an active hub")
    return est


def _is_hub_operator(profile, establishment) -> bool:
    """Check if profile is owner, admin, or member of the hub."""
    if establishment.owner_id == profile.id:
        return True
    from geo.models import EstablishmentMembership
    return EstablishmentMembership.objects.filter(
        establishment=establishment,
        profile=profile,
        role__in=['OWNER', 'ADMIN', 'MEMBER'],
    ).exists()


def _add_event(shipment, event_type, actor, hub=None, note=''):
    return ShipmentEvent.objects.create(
        shipment=shipment,
        event_type=event_type,
        hub=hub,
        actor=actor,
        note=note,
    )


def _notify_shipment(shipment):
    """Send WebSocket notification to sender, receiver, and hub operators."""
    try:
        from parahub.services.ws_publish import ws_publish
        data = _shipment_response(shipment)

        # Notify sender + receiver
        notified_ids = set()
        for profile in (shipment.sender, shipment.receiver):
            ws_publish(f'user:{profile.account_id}', {
                'type': 'shipment.updated',
                'data': data,
            })
            notified_ids.add(profile.account_id)

        # Notify hub operators at current_hub (if any)
        if shipment.current_hub_id:
            from geo.models import EstablishmentMembership
            operator_account_ids = set(
                EstablishmentMembership.objects.filter(
                    establishment_id=shipment.current_hub_id,
                    role__in=['OWNER', 'ADMIN', 'MEMBER'],
                ).values_list('profile__account_id', flat=True)
            )
            # Include establishment owner (may not have membership record)
            operator_account_ids.add(shipment.current_hub.owner.account_id)

            for account_id in operator_account_ids - notified_ids:
                ws_publish(f'user:{account_id}', {
                    'type': 'shipment.updated',
                    'data': data,
                })
    except Exception as e:
        logger.warning(f"Failed to notify shipment update: {e}")


# --- Hub Discovery (MUST be before /{tracking_code}/ to avoid path collision) ---

@shipments_router.get("/hubs/", auth=OptionalProfileAuth())
@ratelimit(group='shipments:hubs_list', key=user_or_ip, rate='30/m')
def list_hubs(request, lat: float = None, lon: float = None, radius_km: float = 20):
    """List active P-Hub establishments."""
    qs = Establishment.objects.filter(is_hub=True, is_active=True).select_related('world_object')

    if lat is not None and lon is not None:
        from django.contrib.gis.geos import Point
        from django.contrib.gis.measure import D
        from django.contrib.gis.db.models.functions import Distance
        from django.db.models.functions import Coalesce
        point = Point(lon, lat, srid=4326)
        radius_km = min(radius_km, 100)
        qs = qs.filter(
            Q(location__distance_lte=(point, D(km=radius_km))) |
            Q(world_object__location__distance_lte=(point, D(km=radius_km)))
        ).annotate(
            distance=Distance(Coalesce('location', 'world_object__location'), point)
        ).order_by('distance')
    else:
        qs = qs.order_by('name')

    qs = qs[:50]
    items = []
    for est in qs:
        loc = est.location or (est.world_object.location if est.world_object else None)
        items.append({
            'id': est.id,
            'object_type': 'hub',
            'name': est.name,
            'slug': est.slug,
            'lat': loc.y if loc else None,
            'lon': loc.x if loc else None,
            'hub_capacity': est.hub_capacity,
            'hub_max_days': est.hub_max_days,
            'hub_storage_fee_daily': est.hub_storage_fee_daily,
            'hub_accepted_sizes': est.hub_accepted_sizes,
            'hub_instructions': est.hub_instructions,
            'opening_hours': est.opening_hours,
            'phone': est.phone,
            'spark_address': est.spark_address,
            'rating_avg': float(est.rating_avg),
            'distance_m': round(est.distance.m) if hasattr(est, 'distance') and est.distance else None,
        })
    return {'items': items, 'count': len(items)}


@shipments_router.patch("/hubs/{establishment_id}/settings/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:hub_settings', key=user_or_ip, rate='10/m', method='PATCH')
def update_hub_settings(request, establishment_id: str, body: HubSettingsUpdate):
    """Update hub settings. Owner/admin only. WoT 2+ to activate."""
    profile = request.auth_profile
    est = Establishment.objects.filter(id=establishment_id, is_active=True).first()
    if not est:
        raise HttpError(404, "Establishment not found")
    if not _is_hub_operator(profile, est):
        raise HttpError(403, "Not authorized")

    if body.is_hub is True and not est.is_hub:
        if not profile.is_verified_wot and not profile.is_foundation_member():
            raise HttpError(403, "WoT 2+ required to activate hub mode")

    if body.hub_accepted_sizes is not None:
        invalid = set(body.hub_accepted_sizes) - SIZE_CHOICES
        if invalid:
            raise HttpError(400, f"Invalid sizes: {invalid}")

    update_fields = ['updated_at']
    for field in ['is_hub', 'hub_capacity', 'hub_max_days', 'hub_storage_fee_daily',
                   'hub_accepted_sizes', 'hub_instructions']:
        value = getattr(body, field, None)
        if value is not None:
            setattr(est, field, value)
            update_fields.append(field)

    est.save(update_fields=update_fields)

    return {
        'id': est.id,
        'is_hub': est.is_hub,
        'hub_capacity': est.hub_capacity,
        'hub_max_days': est.hub_max_days,
        'hub_storage_fee_daily': est.hub_storage_fee_daily,
        'hub_accepted_sizes': est.hub_accepted_sizes,
        'hub_instructions': est.hub_instructions,
    }


# --- Carrier (literal paths before param paths) ---

@shipments_router.get("/available/", auth=ProfileAuth())
@ratelimit(group='shipments:available', key=user_or_ip, rate='30/m')
def available_shipments(request, lat: float = None, lon: float = None, radius_km: float = 10):
    """List shipments needing carriers (optionally geo-filtered)."""
    qs = Shipment.objects.filter(
        status__in=[Shipment.Status.AT_ORIGIN, Shipment.Status.AT_HUB],
    ).exclude(
        origin_hub=F('destination_hub'),
    ).select_related('sender', 'receiver', 'origin_hub', 'destination_hub', 'current_hub')

    if lat is not None and lon is not None:
        from django.contrib.gis.geos import Point
        from django.contrib.gis.measure import D
        point = Point(lon, lat, srid=4326)
        radius_km = min(radius_km, 50)
        qs = qs.filter(
            Q(current_hub__location__distance_lte=(point, D(km=radius_km))) |
            Q(current_hub__world_object__location__distance_lte=(point, D(km=radius_km)))
        )

    qs = qs.order_by('-created_at')[:50]
    return {'items': [_shipment_response(s) for s in qs], 'count': len(qs)}


@shipments_router.post("/{shipment_id}/offer/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:carrier_offer', key=user_or_ip, rate='10/m', method='POST')
def create_carrier_offer(request, shipment_id: str, body: CarrierOfferCreate):
    """Carrier offers to transport a shipment. Requires WoT 1+."""
    profile = request.auth_profile
    if not profile.is_verified_wot and not profile.is_foundation_member():
        raise HttpError(403, "WoT verification required to carry shipments")

    shipment = Shipment.objects.filter(
        id=shipment_id,
        status__in=[Shipment.Status.AT_ORIGIN, Shipment.Status.AT_HUB],
    ).select_related('sender', 'receiver', 'current_hub', 'destination_hub').first()
    if not shipment:
        raise HttpError(404, "Shipment not found or not available for carrier offers")

    if profile.id in (shipment.sender_id, shipment.receiver_id):
        raise HttpError(400, "Sender/receiver cannot be the carrier")

    if not shipment.current_hub:
        raise HttpError(400, "Shipment has no current hub")

    # Check for existing active offer from this carrier
    existing = CarrierOffer.objects.filter(
        shipment=shipment, carrier=profile,
        status__in=[CarrierOffer.Status.OFFERED, CarrierOffer.Status.ACCEPTED],
    ).exists()
    if existing:
        raise HttpError(400, "You already have an active offer for this shipment")

    offer = CarrierOffer.objects.create(
        shipment=shipment,
        carrier=profile,
        from_hub=shipment.current_hub,
        to_hub=shipment.destination_hub,
        fee_sats=body.fee_sats,
    )

    _notify_shipment(shipment)
    return _offer_response(offer)


@shipments_router.patch("/offers/{offer_id}/accept/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:accept_offer', key=user_or_ip, rate='10/m', method='PATCH')
def accept_carrier_offer(request, offer_id: str):
    """Sender or receiver accepts a carrier offer."""
    profile = request.auth_profile
    offer = CarrierOffer.objects.filter(
        id=offer_id, status=CarrierOffer.Status.OFFERED
    ).select_related('shipment__sender', 'shipment__receiver', 'carrier', 'from_hub', 'to_hub').first()
    if not offer:
        raise HttpError(404, "Offer not found")

    shipment = offer.shipment
    if profile.id not in (shipment.sender_id, shipment.receiver_id):
        raise HttpError(403, "Only sender or receiver can accept")

    with transaction.atomic():
        offer.status = CarrierOffer.Status.ACCEPTED
        offer.save(update_fields=['status', 'updated_at'])

        CarrierOffer.objects.filter(
            shipment=shipment, status=CarrierOffer.Status.OFFERED
        ).exclude(id=offer.id).update(status=CarrierOffer.Status.CANCELLED)

        shipment.status = Shipment.Status.IN_TRANSIT
        shipment.current_hub = None
        shipment.save(update_fields=['status', 'current_hub', 'updated_at'])
        _add_event(shipment, ShipmentEvent.EventType.CARRIER_PICKUP, offer.carrier, hub=offer.from_hub)

    try:
        from parahub.endpoints.matrix_auth import create_dm_between_accounts
        room_id = create_dm_between_accounts(
            str(profile.account_id),
            str(offer.carrier.account_id),
        )
        if room_id:
            offer.matrix_room_id = room_id
            offer.save(update_fields=['matrix_room_id', 'updated_at'])
    except Exception as e:
        logger.warning(f"Failed to create Matrix DM for carrier: {e}")

    _notify_shipment(shipment)
    return _offer_response(offer)


@shipments_router.patch("/offers/{offer_id}/complete/", auth=ProfileAuth(), response={200: dict, 404: dict})
@ratelimit(group='shipments:complete_offer', key=user_or_ip, rate='10/m', method='PATCH')
def complete_carrier_offer(request, offer_id: str):
    """Carrier confirms delivery to destination hub."""
    profile = request.auth_profile
    offer = CarrierOffer.objects.filter(
        id=offer_id, carrier=profile, status=CarrierOffer.Status.ACCEPTED
    ).select_related(
        'shipment__sender', 'shipment__receiver',
        'shipment__origin_hub', 'shipment__destination_hub',
        'from_hub', 'to_hub',
    ).first()
    if not offer:
        raise HttpError(404, "Active offer not found")

    shipment = offer.shipment
    is_final = offer.to_hub_id == shipment.destination_hub_id

    with transaction.atomic():
        offer.status = CarrierOffer.Status.COMPLETED
        offer.save(update_fields=['status', 'updated_at'])

        shipment.current_hub = offer.to_hub
        shipment.status = Shipment.Status.READY if is_final else Shipment.Status.AT_HUB
        if offer.to_hub.hub_max_days:
            shipment.expires_at = timezone.now() + timedelta(days=offer.to_hub.hub_max_days)
        shipment.save(update_fields=['current_hub', 'status', 'expires_at', 'updated_at'])

        event_type = ShipmentEvent.EventType.READY if is_final else ShipmentEvent.EventType.ARRIVED
        _add_event(shipment, event_type, profile, hub=offer.to_hub)

    _notify_shipment(shipment)
    return _offer_response(offer)


# --- Hub Operator (literal /hub/ prefix before param paths) ---

@shipments_router.get("/hub/{establishment_id}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:hub_list', key=user_or_ip, rate='30/m')
def hub_shipments(request, establishment_id: str):
    """List shipments at my hub."""
    profile = request.auth_profile
    est = _validate_hub(establishment_id)
    if not _is_hub_operator(profile, est):
        raise HttpError(403, "Not a hub operator")

    qs = Shipment.objects.filter(
        current_hub=est,
        status__in=[Shipment.Status.AT_ORIGIN, Shipment.Status.AT_HUB, Shipment.Status.READY],
    ).select_related('sender', 'receiver', 'origin_hub', 'destination_hub').order_by('-created_at')

    items = [_shipment_response(s) for s in qs]
    return {'items': items, 'count': len(items)}


@shipments_router.patch("/hub/{establishment_id}/{shipment_id}/confirm-arrival/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:confirm_arrival', key=user_or_ip, rate='20/m', method='PATCH')
def confirm_arrival(request, establishment_id: str, shipment_id: str):
    """Hub operator confirms shipment arrival."""
    profile = request.auth_profile
    est = _validate_hub(establishment_id)
    if not _is_hub_operator(profile, est):
        raise HttpError(403, "Not a hub operator")

    shipment = Shipment.objects.filter(
        id=shipment_id, status=Shipment.Status.IN_TRANSIT
    ).select_related('sender', 'receiver', 'origin_hub', 'destination_hub').first()
    if not shipment:
        raise HttpError(404, "Shipment not found or not in transit")

    is_final = est.id == shipment.destination_hub_id
    with transaction.atomic():
        shipment.current_hub = est
        shipment.status = Shipment.Status.READY if is_final else Shipment.Status.AT_HUB
        shipment.expires_at = timezone.now() + timedelta(days=est.hub_max_days)
        shipment.save(update_fields=['current_hub', 'status', 'expires_at', 'updated_at'])
        event_type = ShipmentEvent.EventType.READY if is_final else ShipmentEvent.EventType.ARRIVED
        _add_event(shipment, event_type, profile, hub=est)

    _notify_shipment(shipment)
    return _shipment_response(shipment)


@shipments_router.patch("/hub/{establishment_id}/{shipment_id}/mark-ready/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:mark_ready', key=user_or_ip, rate='20/m', method='PATCH')
def mark_ready(request, establishment_id: str, shipment_id: str):
    """Hub operator marks shipment ready for pickup."""
    profile = request.auth_profile
    est = _validate_hub(establishment_id)
    if not _is_hub_operator(profile, est):
        raise HttpError(403, "Not a hub operator")

    shipment = Shipment.objects.filter(
        id=shipment_id, current_hub=est,
        status__in=[Shipment.Status.AT_ORIGIN, Shipment.Status.AT_HUB],
    ).select_related('sender', 'receiver', 'origin_hub', 'destination_hub').first()
    if not shipment:
        raise HttpError(404, "Shipment not found at this hub")

    with transaction.atomic():
        shipment.status = Shipment.Status.READY
        shipment.save(update_fields=['status', 'updated_at'])
        _add_event(shipment, ShipmentEvent.EventType.READY, profile, hub=est)

    _notify_shipment(shipment)
    return _shipment_response(shipment)


@shipments_router.patch("/hub/{establishment_id}/{shipment_id}/verify-pickup/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:verify_pickup', key=user_or_ip, rate='20/m', method='PATCH')
def verify_pickup(request, establishment_id: str, shipment_id: str, body: VerifyPickupBody):
    """Hub operator verifies pickup code and releases shipment."""
    profile = request.auth_profile
    est = _validate_hub(establishment_id)
    if not _is_hub_operator(profile, est):
        raise HttpError(403, "Not a hub operator")

    shipment = Shipment.objects.filter(
        id=shipment_id, current_hub=est, status=Shipment.Status.READY,
    ).select_related('sender', 'receiver', 'origin_hub', 'destination_hub').first()
    if not shipment:
        raise HttpError(404, "Shipment not found or not ready")

    if body.pickup_code != shipment.pickup_code:
        raise HttpError(400, "Invalid pickup code")

    with transaction.atomic():
        shipment.status = Shipment.Status.DELIVERED
        shipment.delivered_at = timezone.now()
        shipment.save(update_fields=['status', 'delivered_at', 'updated_at'])
        _add_event(shipment, ShipmentEvent.EventType.DELIVERED, profile, hub=est)

    _notify_shipment(shipment)
    return _shipment_response(shipment)


# --- Shipment CRUD ---

@shipments_router.post("/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:create', key=user_or_ip, rate='10/m', method='POST')
def create_shipment(request, body: ShipmentCreate):
    """Create a shipment. Requires WoT 1+."""
    profile = request.auth_profile
    if not profile.is_verified_wot and not profile.is_foundation_member():
        raise HttpError(403, "WoT verification required")

    from identity.models import Profile
    receiver = Profile.objects.filter(id=body.receiver_id).first()
    if not receiver:
        raise HttpError(404, "Receiver not found")
    if receiver.id == profile.id:
        raise HttpError(400, "Cannot send to yourself")

    origin = _validate_hub(body.origin_hub_id, "Origin hub")
    destination = _validate_hub(body.destination_hub_id, "Destination hub")

    # Check size accepted by both hubs
    for hub, label in [(origin, "Origin"), (destination, "Destination")]:
        if hub.hub_accepted_sizes and body.size_category not in hub.hub_accepted_sizes:
            raise HttpError(400, f"{label} hub does not accept size {body.size_category}")

    # Check origin hub capacity
    if origin.hub_capacity is not None:
        current = Shipment.objects.filter(
            current_hub=origin,
            status__in=[Shipment.Status.AT_ORIGIN, Shipment.Status.AT_HUB, Shipment.Status.READY],
        ).count()
        if current >= origin.hub_capacity:
            raise HttpError(400, "Origin hub is at capacity")

    item = None
    if body.item_id:
        from market.models import Item
        item = Item.objects.filter(id=body.item_id, is_active=True).first()

    with transaction.atomic():
        shipment = Shipment.objects.create(
            sender=profile,
            receiver=receiver,
            origin_hub=origin,
            destination_hub=destination,
            title=body.title,
            size_category=body.size_category,
            item=item,
            delivery_fee=body.delivery_fee,
        )
        _add_event(shipment, ShipmentEvent.EventType.CREATED, profile, hub=origin)

    return _shipment_response(shipment, include_pickup_code=(profile.id == shipment.receiver_id))


@shipments_router.get("/", auth=ProfileAuth())
@ratelimit(group='shipments:my_list', key=user_or_ip, rate='30/m')
def my_shipments(request):
    """List my shipments (sent, received, carrying)."""
    profile = request.auth_profile

    # Shipments where user is carrier with accepted offer
    carrier_shipment_ids = set(
        CarrierOffer.objects.filter(
            carrier=profile,
            status=CarrierOffer.Status.ACCEPTED,
        ).values_list('shipment_id', flat=True)
    )

    qs = Shipment.objects.filter(
        Q(sender=profile) | Q(receiver=profile) | Q(id__in=carrier_shipment_ids)
    ).select_related(
        'sender', 'receiver', 'origin_hub', 'destination_hub', 'current_hub'
    ).order_by('-created_at')[:100]

    results = []
    for s in qs:
        is_receiver = s.receiver_id == profile.id
        data = _shipment_response(s, include_pickup_code=is_receiver)
        # Role priority: carrier > receiver > sender
        if s.id in carrier_shipment_ids:
            data['role'] = 'carrier'
        elif is_receiver:
            data['role'] = 'receiver'
        else:
            data['role'] = 'sender'
        results.append(data)
    return {'items': results, 'count': len(results)}


@shipments_router.get("/{tracking_code}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='shipments:detail', key=user_or_ip, rate='30/m')
def get_shipment(request, tracking_code: str):
    """Get shipment by tracking code (with or without PH- prefix)."""
    code = tracking_code.replace("PH-", "").replace("ph-", "")
    profile = request.auth_profile
    shipment = Shipment.objects.filter(tracking_code=code).select_related(
        'sender', 'receiver', 'origin_hub', 'destination_hub', 'current_hub'
    ).first()
    if not shipment:
        raise HttpError(404, "Shipment not found")

    is_receiver = shipment.receiver_id == profile.id
    is_sender = shipment.sender_id == profile.id
    is_operator = False
    if shipment.current_hub:
        is_operator = _is_hub_operator(profile, shipment.current_hub)

    if not is_sender and not is_receiver and not is_operator:
        raise HttpError(403, "Access denied")

    data = _shipment_response(shipment, include_pickup_code=is_receiver)

    # Include events
    events = shipment.events.select_related('hub', 'actor').all()
    data['events'] = [_event_response(e) for e in events]

    # Include carrier offers
    offers = shipment.carrier_offers.select_related(
        'carrier', 'from_hub', 'to_hub'
    ).order_by('-created_at')
    data['carrier_offers'] = [_offer_response(o) for o in offers]

    return data


@shipments_router.patch("/{shipment_id}/deposit/", auth=ProfileAuth(), response={200: dict, 404: dict})
@ratelimit(group='shipments:deposit', key=user_or_ip, rate='10/m', method='PATCH')
def deposit_shipment(request, shipment_id: str):
    """Sender confirms deposit at origin hub."""
    profile = request.auth_profile
    shipment = Shipment.objects.filter(id=shipment_id, sender=profile, status=Shipment.Status.CREATED).first()
    if not shipment:
        raise HttpError(404, "Shipment not found or not in CREATED status")

    with transaction.atomic():
        shipment.status = Shipment.Status.AT_ORIGIN
        shipment.current_hub = shipment.origin_hub
        # Set expiry from hub settings
        shipment.expires_at = timezone.now() + timedelta(days=shipment.origin_hub.hub_max_days)
        shipment.save(update_fields=['status', 'current_hub', 'expires_at', 'updated_at'])
        _add_event(shipment, ShipmentEvent.EventType.DEPOSITED, profile, hub=shipment.origin_hub)

    _notify_shipment(shipment)
    return _shipment_response(shipment)


@shipments_router.patch("/{shipment_id}/cancel/", auth=ProfileAuth(), response={200: dict, 404: dict})
@ratelimit(group='shipments:cancel', key=user_or_ip, rate='10/m', method='PATCH')
def cancel_shipment(request, shipment_id: str):
    """Cancel shipment (only CREATED status)."""
    profile = request.auth_profile
    shipment = Shipment.objects.filter(id=shipment_id, sender=profile, status=Shipment.Status.CREATED).first()
    if not shipment:
        raise HttpError(404, "Shipment not found or cannot be cancelled")

    with transaction.atomic():
        shipment.status = Shipment.Status.CANCELLED
        shipment.save(update_fields=['status', 'updated_at'])
        _add_event(shipment, ShipmentEvent.EventType.CANCELLED, profile)

    return _shipment_response(shipment)
