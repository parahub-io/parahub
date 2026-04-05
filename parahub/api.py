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


@api.get("/health/transit/{ds_id}/rt/", auth=None)
def transit_rt_health(request, ds_id: str):
    """GTFS-RT feed health — based on Redis vehicle data freshness."""
    from geo.models import TransitDataSource
    import redis as _redis

    try:
        ds = TransitDataSource.objects.get(id=ds_id, is_active=True)
    except TransitDataSource.DoesNotExist:
        return Response({"status": "unknown", "error": "feed not found"}, status=404)

    has_rt = bool(ds.rt_vehicles_url and ds.rt_vehicles_url.strip())
    if not has_rt:
        return {"status": "n/a", "name": ds.name, "vehicles": 0, "error": "no RT URL configured"}

    try:
        r = _redis.Redis(host='localhost', port=6379, db=0)
        count = r.scard(f"transit:members:{ds_id}")
    except Exception:
        count = 0

    # "down" only when there's an actual error; 0 vehicles at night is normal
    status = "down" if ds.last_error else "ok"

    return {
        "status": status,
        "name": ds.name,
        "vehicles": count,
        "error": ds.last_error if ds.last_error else None,
    }


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
        import redis
        from django.conf import settings
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
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