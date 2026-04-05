"""Core API — universal photo, comment, video, share, and distribution endpoints."""
from ninja import Router

from core.endpoints.photos import router as photos_router
from core.endpoints.comments import router as comments_router
from core.endpoints.videos import router as videos_router
from core.endpoints.shares import router as shares_router
from core.endpoints.distributions import router as distributions_router

router = Router(tags=["Core"])
router.add_router("photos", photos_router)
router.add_router("comments", comments_router)
router.add_router("videos", videos_router)
router.add_router("shares", shares_router)
router.add_router("distributions", distributions_router)
