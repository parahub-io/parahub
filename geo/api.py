"""
Geo API — aggregator for sub-routers.
"""

from ninja import Router

from geo.endpoints.geocoding import router as geocoding_router
from geo.endpoints.buildings import router as buildings_router
from geo.endpoints.events import router as events_router
from geo.endpoints.opensky import router as opensky_router
from geo.endpoints.transit import router as transit_router
from geo.endpoints.driver import router as driver_router
from geo.endpoints.transit_manage import router as transit_manage_router
from geo.endpoints.condominium import router as condominium_router
from geo.endpoints.world_objects import router as world_objects_router

router = Router(tags=["Geo"])

router.add_router("", geocoding_router)
router.add_router("", buildings_router)
router.add_router("", events_router)
router.add_router("", opensky_router)
router.add_router("", transit_router)
router.add_router("driver", driver_router)
router.add_router("transit/manage", transit_manage_router)
router.add_router("", condominium_router)
router.add_router("world-objects", world_objects_router)
