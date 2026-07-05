"""
IoT endpoints — split by concern from the former single api.py.
Importing the endpoint modules registers their routes on the shared router.
"""

from .base import router

# Sub-routers mount BEFORE this package's own routes register — the old
# module did the same, and history_router mounts at "" so registration
# order determines URL resolution.
from iot.endpoints.dispatch import router as dispatch_router
from iot.endpoints.ha import router as ha_router
from iot.endpoints.history import router as history_router
from iot.endpoints.property import router as property_router

router.add_router("/dispatch", dispatch_router)
router.add_router("/ha", ha_router)
router.add_router("", history_router)
router.add_router("/properties", property_router)

from . import devices, traccar, mesh, features, monitoring  # noqa: E402,F401

__all__ = ['router']
