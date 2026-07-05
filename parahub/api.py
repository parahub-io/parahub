"""
Parahub Main API Entry Point using Django Ninja
Implements API-First principle with secure authentication and PGP validation
"""

from ninja import NinjaAPI
from ninja.errors import ValidationError
from ninja.responses import Response
from django.http import Http404, HttpResponse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from pydantic import BaseModel
from typing import Any, Dict, Optional
import logging
import traceback


# Setup logging
logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """Standard error response schema"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response schema"""
    status: str
    version: str
    timestamp: str
    database: str
    services: Dict[str, str]


def create_ninja_api() -> NinjaAPI:
    """Factory function to create configured NinjaAPI instance"""
    
    # API metadata based on debug mode
    if settings.DEBUG:
        api_title = "Parahub API - Development"
        api_description = "Development instance of Parahub API with full documentation"
    else:
        api_title = "Parahub API"
        api_description = "Secure Parahub API for peer-to-peer marketplace and community"
    
    # Create API instance
    api = NinjaAPI(
        title=api_title,
        description=api_description,
        version="1.0.0",
        urls_namespace="rest_api",
        docs_url="/docs/" if settings.DEBUG else None,  # Disable docs in production
        openapi_url="/openapi.json" if settings.DEBUG else None,
        # csrf param removed in django-ninja 1.5 (JWT auth doesn't need CSRF)
    )
    
    # Global exception handlers
    from parahub.errors import LocalizedHttpError

    @api.exception_handler(LocalizedHttpError)
    def localized_http_error_handler(request, exc):
        """HttpError that also carries a machine-readable `code` for client-side
        localization. `detail` stays as the canonical English fallback."""
        return api.create_response(
            request,
            {"detail": exc.message, "code": exc.code},
            status=exc.status_code,
        )

    @api.exception_handler(ValidationError)
    def validation_exception_handler(request, exc):
        """Handle validation errors with detailed feedback"""
        logger.warning(f"Validation error: {exc.errors}")
        return api.create_response(
            request,
            {"error": "VALIDATION_ERROR", "message": "Invalid request data", "details": exc.errors},
            status=400
        )
    
    @api.exception_handler(Http404)
    def not_found_handler(request, exc):
        """Handle 404 errors"""
        return api.create_response(
            request,
            {"error": "NOT_FOUND", "message": "Resource not found"},
            status=404
        )
    
    @api.exception_handler(PermissionDenied)
    def permission_denied_handler(request, exc):
        """Handle permission denied errors"""
        logger.warning(f"Permission denied: {request.user} accessing {request.path}")
        return api.create_response(
            request,
            {"error": "PERMISSION_DENIED", "message": "Access denied"},
            status=403
        )
    
    @api.exception_handler(Exception)
    def generic_exception_handler(request, exc):
        """Handle all other exceptions"""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        
        if settings.DEBUG:
            # In debug mode, return full traceback
            return api.create_response(
                request,
                {
                    "error": "INTERNAL_ERROR",
                    "message": str(exc),
                    "details": {"traceback": traceback.format_exc()}
                },
                status=500
            )
        else:
            # In production, return generic error
            return api.create_response(
                request,
                {"error": "INTERNAL_ERROR", "message": "An internal error occurred"},
                status=500
            )
    
    return api


# Create the main API instance (cached to avoid multiple registrations)
_api_instance = None

def get_api():
    global _api_instance
    if _api_instance is None:
        _api_instance = create_ninja_api()
    return _api_instance

api = get_api()

# Import routers
from parahub.endpoints.auth import auth_router
from parahub.endpoints.profiles import profile_router
from parahub.endpoints.partners import partner_router
from parahub.endpoints.wot import wot_router
from parahub.endpoints.items import item_router
from parahub.endpoints.governance import governance_router
from parahub.endpoints.dashboard import router as dashboard_router
from parahub.endpoints.matrix_auth import router as matrix_router
from parahub.endpoints.matrix_sso import router as matrix_sso_router
from parahub.endpoints.ads import ads_router
from parahub.endpoints.lnurl import lnurl_router
from parahub.endpoints.ai_vision import ai_router
from iot.api import router as new_iot_router
from barter.api import router as barter_router
from debts.api import router as debts_router
from geo.api import router as geo_router
from parahub.endpoints.contracts import router as contracts_router
from parahub.endpoints.rental import router as rental_router
from audit_log.endpoints import router as audit_router
from notifications.api import router as notifications_router
from parahub.endpoints.zenith import router as zenith_router
from parahub.endpoints.jitsi import router as jitsi_router
from parahub.endpoints.rides import rides_router
from parahub.endpoints.shipments import shipments_router
from energy.api import router as energy_router
from treasury.api import router as treasury_router
from agents.api import router as agents_router
from parahub.endpoints.income import income_router
from parahub.endpoints.subscriptions import subscriptions_router
from parahub.endpoints.federation import router as federation_router
from tickets.api import router as tickets_router
from parahub.endpoints.likes import likes_router
from parasos.api import router as parasos_router
from core.api import router as core_router
from cms.api import router as cms_router

# Create versioned router
from ninja import Router
v1_router = Router()
v1_router.add_router("/auth", auth_router)
v1_router.add_router("/profiles", profile_router)
v1_router.add_router("/partners", partner_router)
v1_router.add_router("/wot", wot_router)
v1_router.add_router("/items", item_router)
v1_router.add_router("/governance", governance_router)
v1_router.add_router("/dashboard", dashboard_router)
v1_router.add_router("/matrix", matrix_router)
v1_router.add_router("/matrix-sso", matrix_sso_router)
v1_router.add_router("/ads", ads_router)
v1_router.add_router("/lnurl", lnurl_router)
v1_router.add_router("/ai", ai_router)
v1_router.add_router("/iot", new_iot_router)
v1_router.add_router("/barter", barter_router)
v1_router.add_router("/debts", debts_router)
v1_router.add_router("/contracts", contracts_router)
v1_router.add_router("/rental", rental_router)
v1_router.add_router("/geo", geo_router)
v1_router.add_router("/audit", audit_router)
v1_router.add_router("/notifications", notifications_router)
v1_router.add_router("/zenith", zenith_router)
v1_router.add_router("/jitsi", jitsi_router)
v1_router.add_router("/rides", rides_router)
v1_router.add_router("/energy", energy_router)
v1_router.add_router("/treasury", treasury_router)
v1_router.add_router("/agents", agents_router)
v1_router.add_router("/income", income_router)
v1_router.add_router("/subscriptions", subscriptions_router)
v1_router.add_router("/federation", federation_router)
v1_router.add_router("/tickets", tickets_router)
v1_router.add_router("/shipments", shipments_router)
v1_router.add_router("/likes", likes_router)
v1_router.add_router("/parasos", parasos_router)
v1_router.add_router("/core", core_router)
v1_router.add_router("/cms", cms_router)

# Add versioned router to main API
api.add_router("/v1", v1_router)


@api.get("/health/transit/{ds_id}/gtfs/", auth=None)
def transit_gtfs_health(request, ds_id: str):
    """GTFS static feed health — based on last import results."""
    from geo.models import TransitDataSource
    from django.utils import timezone as tz

    try:
        ds = TransitDataSource.objects.get(id=ds_id, is_active=True)
    except TransitDataSource.DoesNotExist:
        return Response({"status": "unknown", "error": "feed not found"}, status=404)

    stats = ds.last_import_stats or {}
    age_hours = None
    if ds.last_imported_at:
        age_hours = round((tz.now() - ds.last_imported_at).total_seconds() / 3600, 1)

    has_error = bool(stats.get("error")) or (not ds.last_imported_at)
    too_old = age_hours is not None and age_hours > 240  # >10 days

    status = "down" if (has_error or too_old) else "ok"

    return {
        "status": status,
        "name": ds.name,
        "last_import": ds.last_imported_at.isoformat() if ds.last_imported_at else None,
        "age_hours": age_hours,
        "error": stats.get("error"),
    }


# GTFS-RT liveness thresholds (see _rt_freshness_status)
RT_STALE_SECS = 600          # freshest served vehicle older than this w/ 0 fresh → frozen
RT_NIGHT_GUARD = (1, 5)      # agency-local [start, end) hours where idle-vs-frozen is ambiguous


def _rt_freshness_status(*, fresh_count, mirror_vehicles, now, local_hour, last_error):
    """Pure liveness decision for a GTFS-RT feed → (status, reason, freshest_age).

    The naive "0 vehicles ⇒ down" false-alarms every night; "down only on daemon
    error" (the old rule) never catches a frozen *upstream* — STCP froze for 4h+
    on 2026-06-28 while every poll returned HTTP 200 with stale data, so Kuma
    stayed green (PK/gtfs-feed-quirks.md § STCP). Signal: the unfiltered mirror
    (`transit:rt:{ds}`) keeps the full feed incl. stale fixes; if the feed is
    *serving* vehicles but none are fresh (≥now-180s, the `transit:members` set)
    and its freshest fix is old, the producer has stalled.

      • fresh_count > 0           → ok (delivering live data)
      • mirror empty              → ok / idle (feed returns nothing → genuine no-service)
      • served-but-all-stale      → down once freshest_age > RT_STALE_SECS …
      • … except deep night       → ok (guard: ghost-lingering feeds like CM keep
                                    hours-old parked-bus fixes when off-service and
                                    can't be told apart from a freeze without a
                                    feed-level heartbeat CM doesn't publish; a freeze
                                    persisting into morning service is still caught
                                    when the guard lifts and the mirror stays stale).
    """
    if last_error:
        return "down", f"daemon error: {last_error}", None
    if fresh_count > 0:
        return "ok", None, 0
    total = len(mirror_vehicles) if mirror_vehicles else 0
    if total == 0:
        return "ok", "idle (feed empty)", None
    freshest_age = now - max((v.get("t", 0) for v in mirror_vehicles), default=0)
    if RT_NIGHT_GUARD[0] <= local_hour < RT_NIGHT_GUARD[1]:
        return "ok", "night guard", freshest_age
    if freshest_age > RT_STALE_SECS:
        return ("down",
                f"feed stalled: {total} vehicles served, freshest fix {freshest_age}s old, 0 fresh",
                freshest_age)
    return "ok", None, freshest_age


@api.get("/health/transit/{ds_id}/rt/", auth=None)
def transit_rt_health(request, ds_id: str):
    """GTFS-RT feed health — detects a frozen *upstream* (200 OK + stale data),
    not just daemon errors. Night-safe via deep-night guard. 503 on down so the
    Kuma keyword monitor flips regardless of body text."""
    from geo.models import TransitDataSource, Agency
    from django.core.cache import cache
    from django.utils import timezone as tz
    from zoneinfo import ZoneInfo
    from parahub.services.redis_pool import get_redis
    import json as _json
    import time as _time

    try:
        ds = TransitDataSource.objects.get(id=ds_id, is_active=True)
    except TransitDataSource.DoesNotExist:
        return Response({"status": "unknown", "error": "feed not found"}, status=404)

    has_rt = bool(ds.rt_vehicles_url and ds.rt_vehicles_url.strip())
    if not has_rt:
        return {"status": "n/a", "name": ds.name, "vehicles": 0, "error": "no RT URL configured"}

    now = int(_time.time())
    try:
        fresh_count = get_redis().scard(f"transit:members:{ds_id}")
    except Exception:
        fresh_count = 0

    # unfiltered feed mirror (full incl. stale ghosts) — written via Django cache API
    mirror = []
    try:
        raw = cache.get(f"transit:rt:{ds_id}")
        if raw:
            mirror = _json.loads(raw) if isinstance(raw, (bytes, bytearray, str)) else raw
    except Exception:
        mirror = []

    # agency-local hour for the deep-night guard (feeds span many timezones)
    agency = Agency.objects.filter(data_source=ds).exclude(timezone="").first()
    tzname = agency.timezone if (agency and agency.timezone) else "UTC"
    try:
        local_hour = tz.now().astimezone(ZoneInfo(tzname)).hour
    except Exception:
        local_hour = tz.now().hour

    status, reason, freshest_age = _rt_freshness_status(
        fresh_count=fresh_count,
        mirror_vehicles=mirror,
        now=now,
        local_hour=local_hour,
        last_error=ds.last_error,
    )

    body = {
        "status": status,
        "name": ds.name,
        "vehicles": fresh_count,
        "total_served": len(mirror) if mirror else 0,
        "freshest_age_s": freshest_age,
        "reason": reason,
        "error": ds.last_error if ds.last_error else None,
    }
    return Response(body, status=200 if status in ("ok", "n/a") else 503)


@api.get("/health/", response=HealthResponse, auth=None)
def health_check(request):
    """
    Health check endpoint for monitoring and load balancers
    
    Returns system status, version info, and service health
    """
    from django.db import connection
    from datetime import datetime
    import django
    
    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
    
    # Check Redis connectivity
    try:
        from django.conf import settings
        from parahub.services.redis_pool import get_redis
        get_redis().ping()
        redis_status = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "unhealthy"
    
    # Check Matrix (Synapse) connectivity
    try:
        import httpx
        synapse_url = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')
        with httpx.Client(timeout=3) as client:
            resp = client.get(f"{synapse_url}/_matrix/client/versions")
            matrix_status = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception as e:
        logger.error(f"Matrix health check failed: {e}")
        matrix_status = "unhealthy"

    # Service health checks
    services_status = {
        "database": db_status,
        "redis": redis_status,
        "matrix": matrix_status,
    }
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": "1.0.0-beta",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "database": db_status,
        "services": services_status
    }


@api.get("/", auth=None)
def api_root(request):
    """API root endpoint with basic information"""
    return {
        "name": "Parahub API",
        "version": "1.0.0",
        "description": "Secure peer-to-peer marketplace and community platform",
        "documentation": "/docs/" if settings.DEBUG else None,
        "health": "/api/health/",
        "authentication": {
            "jwt": "/api/v1/auth/token/",
            "refresh": "/api/v1/auth/refresh/",
        }
    }