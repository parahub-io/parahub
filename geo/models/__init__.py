"""geo models — split by domain from the former single geo/models.py.

Pure package split: every model keeps app_label 'geo' (Django derives it from
the containing app package), db tables and migrations are untouched. All names
are re-exported here so `from geo.models import X` keeps working everywhere,
including historical migrations.
"""
from .places import Place
from .opensky import OpenSkyMission, OpenSkyTileLayer, OpenSkyConsolidationMember, OpenSkyPoseEdge
from .transit import (
    TransitDataSource, Agency, StopGroup, Stop, Route, Shape, Trip, RouteStop,
    Vehicle, StopTime, CalendarDate, VehiclePositionHistory, FeedHealthSample, DriverShift,
    WaitingSnapshot,
)
from .establishments import (
    WorldObject, Establishment, EstablishmentMembership, EstablishmentInvite, EstablishmentReview,
)
from .condominium import CondominiumFraction, QuotaPayment
from .events import Event, EventParticipant
from .drones import DroneZone
from .urban import UrbanOrdenamento, UrbanCondicionante, UrbanRule, UrbanRuleSignoff
from .territory import Territory

__all__ = [
    'Place',
    'OpenSkyMission', 'OpenSkyTileLayer', 'OpenSkyConsolidationMember', 'OpenSkyPoseEdge',
    'TransitDataSource', 'Agency', 'StopGroup', 'Stop', 'Route', 'Shape', 'Trip', 'RouteStop',
    'Vehicle', 'StopTime', 'CalendarDate', 'VehiclePositionHistory', 'FeedHealthSample', 'DriverShift',
    'WaitingSnapshot',
    'WorldObject', 'Establishment', 'EstablishmentMembership', 'EstablishmentInvite',
    'EstablishmentReview',
    'CondominiumFraction', 'QuotaPayment',
    'Event', 'EventParticipant',
    'DroneZone',
    'UrbanOrdenamento', 'UrbanCondicionante', 'UrbanRule', 'UrbanRuleSignoff',
    'Territory',
]
