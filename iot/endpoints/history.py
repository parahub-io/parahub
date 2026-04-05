"""
Tracker position history API.

Returns GPS trail for a device within a date range.
Data from iot_tracker_history TimescaleDB hypertable (90-day retention).
~1440 points/day (1/min), max 90 days ≈ 130K points ≈ 20MB raw / ~1.5MB gzip.
"""

import logging
from datetime import datetime
from typing import List, Optional

from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from iot.models import IoTDevice, TrackerHistory

logger = logging.getLogger(__name__)
router = Router(tags=["Tracker History"])

MAX_RANGE_DAYS = 90


class TrackerHistoryPointOut(Schema):
    time: datetime
    latitude: float
    longitude: float
    speed: Optional[float] = None
    heading: Optional[float] = None
    altitude: Optional[float] = None
    battery_level: Optional[int] = None
    accuracy: Optional[float] = None


class TrackerHistoryOut(Schema):
    device_id: str
    device_name: str
    object_type: str = "tracker_history"
    total_points: int
    points: List[TrackerHistoryPointOut]


@router.get(
    "/devices/{device_id}/history",
    response=TrackerHistoryOut,
    auth=ProfileAuth(),
    summary="Get tracker position history",
)
@ratelimit(group='iot:tracker_history', key=user_or_ip, rate='30/m')
def get_tracker_history(
    request,
    device_id: str,
    start: datetime,
    end: datetime,
):
    profile = request.auth_profile
    device = get_object_or_404(
        IoTDevice,
        id=device_id,
        owner=profile,
        device_type=IoTDevice.DeviceType.TRACKER,
    )

    if end <= start:
        raise HttpError(400, "end must be after start")
    if (end - start).total_seconds() / 86400 > MAX_RANGE_DAYS:
        raise HttpError(400, f"Maximum range is {MAX_RANGE_DAYS} days")

    qs = TrackerHistory.objects.filter(
        device=device, time__gte=start, time__lte=end,
    ).order_by('time').values_list(
        'time', 'latitude', 'longitude', 'speed',
        'heading', 'altitude', 'battery_level', 'accuracy',
    )

    points = [
        TrackerHistoryPointOut(
            time=r[0], latitude=r[1], longitude=r[2], speed=r[3],
            heading=r[4], altitude=r[5], battery_level=r[6], accuracy=r[7],
        )
        for r in qs
    ]

    return TrackerHistoryOut(
        device_id=device.id,
        device_name=device.name,
        total_points=len(points),
        points=points,
    )
