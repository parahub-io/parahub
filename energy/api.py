from typing import List, Optional
from decimal import Decimal
import logging

from ninja import Router, Schema, Field
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

from parahub.auth import ProfileAuth, GlobalAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile, Verification
from .models import EnergyCell, EnergyProducer, EnergyConsumer, EnergyRelay
from . import relay_service

logger = logging.getLogger(__name__)
router = Router(tags=["Energy"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class EnergyCellMapOut(Schema):
    """Lightweight schema for the map layer (public, anonymous)."""
    id: str
    object_type: str = 'energy_cell'
    name: str
    longitude: float
    latitude: float
    radius_km: float
    status: str
    current_price_eur: Optional[float] = None
    producers_count: int
    consumers_count: int


class EnergyCellDetailOut(Schema):
    id: str
    object_type: str = 'energy_cell'
    name: str
    description: str
    longitude: float
    latitude: float
    radius_km: float
    transformer_id: str
    status: str
    current_price_eur: Optional[float] = None
    producers_count: int
    consumers_count: int
    total_capacity_kw: float
    created_by_hna: Optional[str] = None
    created_by_display_name: Optional[str] = None
    establishment_id: Optional[str] = None
    establishment_name: Optional[str] = None


class EnergyCellCreateIn(Schema):
    name: str
    description: str = ''
    longitude: float
    latitude: float
    radius_km: float = 2.0
    transformer_id: str = ''
    establishment_id: Optional[str] = None


class EnergyCellUpdateIn(Schema):
    description: Optional[str] = None
    current_price_eur: Optional[float] = None


class JoinProducerIn(Schema):
    cpe_code: str = Field(..., min_length=5, max_length=30)
    capacity_kw: float = Field(..., gt=0)
    battery_kwh: Optional[float] = Field(None, ge=0)
    inverter_type: str = 'OTHER'
    inverter_api_url: str = ''
    inverter_api_token: str = ''


class JoinConsumerIn(Schema):
    cpe_code: str = Field(..., min_length=5, max_length=30)


class MemberOut(Schema):
    profile_id: str
    profile_hna: str
    profile_display_name: Optional[str] = None
    role: str  # 'producer' | 'consumer'
    capacity_kw: Optional[float] = None
    battery_kwh: Optional[float] = None
    inverter_type: Optional[str] = None
    joined_at: str


class MyEnergyStatusOut(Schema):
    """Current user's membership status across all cells."""
    is_member: bool
    role: Optional[str] = None          # 'producer' | 'consumer'
    cell_id: Optional[str] = None
    cell_name: Optional[str] = None
    cell_status: Optional[str] = None
    current_price_eur: Optional[float] = None


class CellLiveOut(Schema):
    """Real-time production/consumption data for a cell."""
    cell_id: str
    status: str
    current_price_eur: Optional[float] = None
    total_production_w: float
    total_capacity_kw: float
    producers_online: int
    producers_total: int


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cell_to_map(cell: EnergyCell) -> EnergyCellMapOut:
    return EnergyCellMapOut(
        id=cell.id,
        name=cell.name,
        longitude=cell.location.x,
        latitude=cell.location.y,
        radius_km=float(cell.radius_km),
        status=cell.status,
        current_price_eur=float(cell.current_price_eur) if cell.current_price_eur else None,
        producers_count=cell.producers.filter(is_active=True).count(),
        consumers_count=cell.consumers.filter(is_active=True).count(),
    )


def _cell_to_detail(cell: EnergyCell) -> EnergyCellDetailOut:
    producers = cell.producers.filter(is_active=True)
    total_kw = sum(float(p.capacity_kw) for p in producers)
    created_by_hna = cell.created_by.hna if cell.created_by else None
    created_by_display_name = cell.created_by.display_name if cell.created_by else None
    return EnergyCellDetailOut(
        id=cell.id,
        name=cell.name,
        description=cell.description,
        longitude=cell.location.x,
        latitude=cell.location.y,
        radius_km=float(cell.radius_km),
        transformer_id=cell.transformer_id,
        status=cell.status,
        current_price_eur=float(cell.current_price_eur) if cell.current_price_eur else None,
        producers_count=producers.count(),
        consumers_count=cell.consumers.filter(is_active=True).count(),
        total_capacity_kw=total_kw,
        created_by_hna=created_by_hna,
        created_by_display_name=created_by_display_name or None,
        establishment_id=cell.establishment_id,
        establishment_name=cell.establishment.name if cell.establishment else None,
    )


def _check_wot3(profile: Profile):
    """Raise 403 if profile doesn't meet WoT 3+ requirement."""
    if profile.account.is_superuser:
        return
    if profile.is_foundation_member():
        return
    count = Verification.objects.filter(
        verified_profile=profile,
        is_active=True,
    ).count()
    if count < 3:
        raise HttpError(403, "Requires WoT level 3+ to join energy cells (or be admin/parahub member)")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get('/cells/map/', response=List[EnergyCellMapOut], auth=None)
@ratelimit(group='energy:cells_map', key='ip', rate='60/m')
def cells_map(request):
    """
    Public GeoJSON-style list of all active energy cells for the map layer.
    No auth required — cells are not sensitive.
    """
    cells = EnergyCell.objects.exclude(status=EnergyCell.Status.OFFLINE)
    return [_cell_to_map(c) for c in cells]


@router.get('/cells/', response=List[EnergyCellDetailOut], auth=GlobalAuth())
@ratelimit(group='energy:cells_list', key=user_or_ip, rate='60/m')
def cells_list(request):
    """All cells (for authenticated users)."""
    cells = EnergyCell.objects.all().select_related('created_by__instance').order_by('-created_at')
    return [_cell_to_detail(c) for c in cells]


@router.get('/cells/{cell_id}/', response=EnergyCellDetailOut, auth=None)
@ratelimit(group='energy:cell_detail', key='ip', rate='60/m')
def cell_detail(request, cell_id: str):
    cell = get_object_or_404(EnergyCell.objects.select_related('created_by__instance', 'establishment'), id=cell_id)
    return _cell_to_detail(cell)


@router.post('/cells/', response=EnergyCellDetailOut, auth=ProfileAuth())
@ratelimit(group='energy:cell_create', key=user_or_ip, rate='10/m', method='POST')
def cell_create(request, payload: EnergyCellCreateIn):
    """Create a new ACC energy cell. Requires WoT 3+."""
    profile: Profile = request.auth
    _check_wot3(profile)
    establishment = None
    if payload.establishment_id:
        from geo.models import Establishment
        establishment = get_object_or_404(Establishment, id=payload.establishment_id)
        if establishment.organization_type != 'COOPERATIVE':
            raise HttpError(400, "Establishment must be a COOPERATIVE")

    cell = EnergyCell.objects.create(
        name=payload.name,
        description=payload.description,
        location=Point(payload.longitude, payload.latitude, srid=4326),
        radius_km=payload.radius_km,
        transformer_id=payload.transformer_id,
        created_by=profile,
        establishment=establishment,
        status=EnergyCell.Status.OFFLINE,
    )
    return _cell_to_detail(cell)


@router.patch('/cells/{cell_id}/', response=EnergyCellDetailOut, auth=ProfileAuth())
@ratelimit(group='energy:cell_update', key=user_or_ip, rate='60/m', method='PATCH')
def cell_update(request, cell_id: str, payload: EnergyCellUpdateIn):
    """Update cell settings. Only cell creator or admin."""
    profile: Profile = request.auth
    cell = get_object_or_404(EnergyCell, id=cell_id)
    if cell.created_by_id != profile.id and not profile.account.is_superuser:
        raise HttpError(403, "Only cell creator can update settings")
    if payload.description is not None:
        cell.description = payload.description
    if payload.current_price_eur is not None:
        cell.current_price_eur = Decimal(str(payload.current_price_eur))
    cell.save()
    return _cell_to_detail(cell)


# ── Members ────────────────────────────────────────────────────────────────────

@router.get('/cells/{cell_id}/members/', response=List[MemberOut], auth=None)
@ratelimit(group='energy:members', key='ip', rate='60/m')
def cell_members(request, cell_id: str):
    """Public list of cell members."""
    cell = get_object_or_404(EnergyCell, id=cell_id)
    members = []
    for p in cell.producers.filter(is_active=True).select_related('profile__instance'):
        members.append(MemberOut(
            profile_id=p.profile_id,
            profile_hna=p.profile.hna,
            profile_display_name=p.profile.display_name or None,
            role='producer',
            capacity_kw=float(p.capacity_kw),
            battery_kwh=float(p.battery_kwh) if p.battery_kwh else None,
            inverter_type=p.inverter_type,
            joined_at=p.joined_at.isoformat(),
        ))
    for c in cell.consumers.filter(is_active=True).select_related('profile__instance'):
        members.append(MemberOut(
            profile_id=c.profile_id,
            profile_hna=c.profile.hna,
            profile_display_name=c.profile.display_name or None,
            role='consumer',
            joined_at=c.joined_at.isoformat(),
        ))
    return members


# ── Join / Leave ───────────────────────────────────────────────────────────────

@router.post('/cells/{cell_id}/join/producer/', response={200: dict, 400: dict, 403: dict}, auth=ProfileAuth())
@ratelimit(group='energy:join_producer', key=user_or_ip, rate='10/m', method='POST')
def join_as_producer(request, cell_id: str, payload: JoinProducerIn):
    """Join cell as producer (UPAC). Requires WoT 3+. Checks geographic radius."""
    profile: Profile = request.auth
    _check_wot3(profile)
    cell = get_object_or_404(EnergyCell, id=cell_id)

    # Check not already a member of any cell
    if EnergyProducer.objects.filter(profile=profile, is_active=True).exists():
        raise HttpError(400, "Already a producer in another cell")
    if EnergyConsumer.objects.filter(profile=profile, is_active=True).exists():
        raise HttpError(400, "Already a consumer in another cell. Leave first")

    # Validate inverter_type
    valid_types = [c[0] for c in EnergyProducer.InverterType.choices]
    if payload.inverter_type not in valid_types:
        raise HttpError(400, f"Invalid inverter_type. Must be one of: {', '.join(valid_types)}")

    EnergyProducer.objects.create(
        cell=cell,
        profile=profile,
        cpe_code=payload.cpe_code,
        capacity_kw=payload.capacity_kw,
        battery_kwh=payload.battery_kwh,
        inverter_type=payload.inverter_type,
        inverter_api_url=payload.inverter_api_url,
        inverter_api_token=payload.inverter_api_token,
    )
    logger.info(f"Producer {profile.hna} joined cell {cell.name}")
    return {"ok": True}


@router.post('/cells/{cell_id}/join/consumer/', response={200: dict, 400: dict, 403: dict}, auth=ProfileAuth())
@ratelimit(group='energy:join_consumer', key=user_or_ip, rate='10/m', method='POST')
def join_as_consumer(request, cell_id: str, payload: JoinConsumerIn):
    """Join cell as consumer (neighbor). Requires WoT 3+."""
    profile: Profile = request.auth
    _check_wot3(profile)
    cell = get_object_or_404(EnergyCell, id=cell_id)

    # Check not already a member of any cell
    if EnergyProducer.objects.filter(profile=profile, is_active=True).exists():
        raise HttpError(400, "Already a producer in another cell. Leave first")
    if EnergyConsumer.objects.filter(profile=profile, is_active=True).exists():
        raise HttpError(400, "Already a consumer in another cell")

    EnergyConsumer.objects.create(
        cell=cell,
        profile=profile,
        cpe_code=payload.cpe_code,
    )
    logger.info(f"Consumer {profile.hna} joined cell {cell.name}")
    return {"ok": True}


@router.post('/cells/{cell_id}/leave/', response={200: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='energy:leave', key=user_or_ip, rate='10/m', method='POST')
def leave_cell(request, cell_id: str):
    """Leave current cell (deactivate membership)."""
    profile: Profile = request.auth
    cell = get_object_or_404(EnergyCell, id=cell_id)

    producer = EnergyProducer.objects.filter(cell=cell, profile=profile, is_active=True).first()
    if producer:
        producer.is_active = False
        producer.save(update_fields=['is_active'])
        logger.info(f"Producer {profile.hna} left cell {cell.name}")
        return {"ok": True}

    consumer = EnergyConsumer.objects.filter(cell=cell, profile=profile, is_active=True).first()
    if consumer:
        consumer.is_active = False
        consumer.save(update_fields=['is_active'])
        logger.info(f"Consumer {profile.hna} left cell {cell.name}")
        return {"ok": True}

    raise HttpError(404, "Not a member of this cell")


# ── My Status ──────────────────────────────────────────────────────────────────

@router.get('/my/', response=MyEnergyStatusOut, auth=ProfileAuth())
@ratelimit(group='energy:my_status', key=user_or_ip, rate='60/m')
def my_status(request):
    """
    Current user's active membership in any energy cell.
    Used by widgets/status indicators.
    """
    profile: Profile = request.auth

    producer = (
        EnergyProducer.objects
        .filter(profile=profile, is_active=True)
        .select_related('cell')
        .first()
    )
    if producer:
        cell = producer.cell
        return MyEnergyStatusOut(
            is_member=True,
            role='producer',
            cell_id=cell.id,
            cell_name=cell.name,
            cell_status=cell.status,
            current_price_eur=float(cell.current_price_eur) if cell.current_price_eur else None,
        )

    consumer = (
        EnergyConsumer.objects
        .filter(profile=profile, is_active=True)
        .select_related('cell')
        .first()
    )
    if consumer:
        cell = consumer.cell
        return MyEnergyStatusOut(
            is_member=True,
            role='consumer',
            cell_id=cell.id,
            cell_name=cell.name,
            cell_status=cell.status,
            current_price_eur=float(cell.current_price_eur) if cell.current_price_eur else None,
        )

    return MyEnergyStatusOut(is_member=False)


# ── Live Data ──────────────────────────────────────────────────────────────────

@router.get('/cells/{cell_id}/live/', response=CellLiveOut, auth=None)
@ratelimit(group='energy:cell_live', key='ip', rate='120/m')
def cell_live(request, cell_id: str):
    """Real-time production data for a cell. Reads from Redis cache (populated by Shelly poller)."""
    import json

    from parahub.services.redis_pool import get_redis

    cell = get_object_or_404(EnergyCell, id=cell_id)
    producers = cell.producers.filter(is_active=True)
    total_capacity = sum(float(p.capacity_kw) for p in producers)

    # Read cached live data from Redis
    live_key = f"energy:live:{cell_id}"
    raw = get_redis().get(live_key)

    total_production_w = 0.0
    producers_online = 0

    if raw:
        data = json.loads(raw)
        total_production_w = data.get('total_production_w', 0.0)
        producers_online = data.get('producers_online', 0)

    return CellLiveOut(
        cell_id=cell.id,
        status=cell.status,
        current_price_eur=float(cell.current_price_eur) if cell.current_price_eur else None,
        total_production_w=total_production_w,
        total_capacity_kw=total_capacity,
        producers_online=producers_online,
        producers_total=producers.count(),
    )


# ── Smart Relays (Direct Trigger) ────────────────────────────────────────────

class RelayOut(Schema):
    id: str
    object_type: str = 'energy_relay'
    name: str
    relay_type: str
    url: str
    channel: int
    is_active: bool
    last_triggered: Optional[str] = None
    last_error: str

class RelayCreateIn(Schema):
    name: str
    relay_type: str  # SHELLY_GEN2, SHELLY_GEN1, TASMOTA
    url: str
    channel: int = 0

class RelayUpdateIn(Schema):
    name: Optional[str] = None
    url: Optional[str] = None
    channel: Optional[int] = None
    is_active: Optional[bool] = None


def _relay_to_out(relay: EnergyRelay) -> dict:
    return {
        'id': relay.id,
        'object_type': 'energy_relay',
        'name': relay.name,
        'relay_type': relay.relay_type,
        'url': relay.url,
        'channel': relay.channel,
        'is_active': relay.is_active,
        'last_triggered': relay.last_triggered.isoformat() if relay.last_triggered else None,
        'last_error': relay.last_error,
    }


@router.get('/my/relays/', response=List[RelayOut], auth=ProfileAuth())
@ratelimit(group='energy:my_relays', key=user_or_ip, rate='60/m')
def my_relays(request):
    """List current user's smart relays (must be active consumer)."""
    profile: Profile = request.auth
    consumer = EnergyConsumer.objects.filter(profile=profile, is_active=True).first()
    if not consumer:
        return []
    return [_relay_to_out(r) for r in consumer.relays.all()]


@router.post('/my/relays/', response=RelayOut, auth=ProfileAuth())
@ratelimit(group='energy:relay_create', key=user_or_ip, rate='10/m', method='POST')
def create_relay(request, payload: RelayCreateIn):
    """Add a smart relay. Must be active consumer in a cell."""
    profile: Profile = request.auth
    consumer = EnergyConsumer.objects.filter(profile=profile, is_active=True).first()
    if not consumer:
        raise HttpError(400, "You must be an active consumer in an energy cell")

    valid_types = [c[0] for c in EnergyRelay.RelayType.choices]
    if payload.relay_type not in valid_types:
        raise HttpError(400, f"Invalid relay_type. Must be one of: {', '.join(valid_types)}")

    name = payload.name.strip()[:100]
    if not name:
        raise HttpError(400, "Name is required")

    relay = EnergyRelay.objects.create(
        consumer=consumer,
        name=name,
        relay_type=payload.relay_type,
        url=payload.url.strip()[:255],
        channel=max(0, payload.channel),
    )
    logger.info(f"Relay created: {relay.name} ({relay.relay_type}) by {profile.hna}")
    return _relay_to_out(relay)


@router.patch('/relays/{relay_id}/', response=RelayOut, auth=ProfileAuth())
@ratelimit(group='energy:relay_update', key=user_or_ip, rate='60/m', method='PATCH')
def update_relay(request, relay_id: str, payload: RelayUpdateIn):
    """Update relay settings. Owner only."""
    profile: Profile = request.auth
    relay = get_object_or_404(EnergyRelay.objects.select_related('consumer'), id=relay_id)
    if relay.consumer.profile_id != profile.id:
        raise HttpError(403, "Not your relay")

    if payload.name is not None:
        relay.name = payload.name.strip()[:100]
    if payload.url is not None:
        relay.url = payload.url.strip()[:255]
    if payload.channel is not None:
        relay.channel = max(0, payload.channel)
    if payload.is_active is not None:
        relay.is_active = payload.is_active
    relay.save()
    return _relay_to_out(relay)


@router.delete('/relays/{relay_id}/', auth=ProfileAuth())
@ratelimit(group='energy:relay_delete', key=user_or_ip, rate='30/m', method='DELETE')
def delete_relay(request, relay_id: str):
    """Delete a relay."""
    profile: Profile = request.auth
    relay = get_object_or_404(EnergyRelay.objects.select_related('consumer'), id=relay_id)
    if relay.consumer.profile_id != profile.id:
        raise HttpError(403, "Not your relay")
    relay.delete()
    return {'ok': True}


@router.post('/relays/{relay_id}/test/', auth=ProfileAuth())
@ratelimit(group='energy:relay_test', key=user_or_ip, rate='10/m', method='POST')
def test_relay_connection(request, relay_id: str):
    """Test connection to a relay device."""
    profile: Profile = request.auth
    relay = get_object_or_404(EnergyRelay.objects.select_related('consumer'), id=relay_id)
    if relay.consumer.profile_id != profile.id:
        raise HttpError(403, "Not your relay")
    result = relay_service.test_relay(relay.relay_type, relay.url, relay.channel)
    if result['ok']:
        relay.last_error = ''
        relay.save(update_fields=['last_error'])
    else:
        relay.last_error = result.get('error', '')[:500]
        relay.save(update_fields=['last_error'])
    return result
