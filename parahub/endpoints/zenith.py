"""
Zenith Protocol API endpoints

Provides AI-powered personal assistant functionality based on user's
knowledge base stored in Gitea.
"""

from ninja import Router
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["zenith"])


# ============== Request/Response Models ==============

class ZenithAskRequest(BaseModel):
    """Request to ask Zenith a question"""
    question: str = Field(..., min_length=1, max_length=4000, description="Question to ask")
    target_profile_id: Optional[str] = Field(
        None,
        description="Profile ID whose Zenith to ask. If null, asks your own Zenith."
    )


class ZenithUsage(BaseModel):
    """AI usage info"""
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ZenithAskResponse(BaseModel):
    """Response from Zenith"""
    answer: str
    files_used: List[str]
    processing_time_ms: int
    usage: ZenithUsage
    log_id: int


class ZenithSettingsResponse(BaseModel):
    """Zenith settings for a profile"""
    enabled: bool
    gitea_repo_name: str
    allow_contacts_access: bool
    has_api_key: bool
    total_queries: int
    system_prompt: Optional[str] = None


class ZenithSettingsUpdateRequest(BaseModel):
    """Request to update Zenith settings"""
    enabled: Optional[bool] = None
    gitea_repo_name: Optional[str] = None
    gemini_api_key: Optional[str] = None
    system_prompt: Optional[str] = None
    allow_contacts_access: Optional[bool] = None


class ZenithQueryLogEntry(BaseModel):
    """Single query log entry"""
    id: int
    querier_hna: Optional[str]
    querier_id: Optional[str]
    question: str
    answer: str
    files_used: List[str]
    processing_time_ms: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    cost_usd: Optional[float]
    success: bool
    error_message: Optional[str]
    created_at: datetime


class ZenithStatusResponse(BaseModel):
    """Zenith status for a profile (public info)"""
    enabled: bool
    can_ask: bool  # Whether current user can ask this Zenith
    reason: Optional[str] = None  # Why can't ask (if can_ask=False)


# ============== Endpoints ==============

@router.post("/ask", response={200: ZenithAskResponse, 400: dict, 403: dict}, auth=ProfileAuth())
@ratelimit(group='zenith:ask', key=user_or_ip, rate='10/h', method='POST')
def ask_zenith(request, data: ZenithAskRequest):
    """
    Ask a question to Zenith (yours or someone else's).

    If target_profile_id is not specified, asks your own Zenith.
    If target_profile_id is specified, asks that profile's Zenith (if you have access).

    Access rules:
    - You can always ask your own Zenith
    - You can ask a contact's Zenith if they enabled it and you're in their contacts
    """
    from parahub.services.zenith_service import ZenithService
    from identity.models import Profile

    querier_profile = request.auth_profile

    # Determine target profile
    if data.target_profile_id:
        try:
            target_profile = Profile.objects.get(id=data.target_profile_id)
        except Profile.DoesNotExist:
            return 400, {"error": "Profile not found"}
    else:
        target_profile = querier_profile

    # Determine if querier is the owner (for logging)
    querier_for_log = None if target_profile.id == querier_profile.id else querier_profile

    try:
        result = ZenithService.ask_zenith(
            zenith_owner_profile=target_profile,
            question=data.question,
            querier_profile=querier_for_log
        )

        return 200, ZenithAskResponse(
            answer=result['answer'],
            files_used=result['files_used'],
            processing_time_ms=result['processing_time_ms'],
            usage=ZenithUsage(**result['usage']),
            log_id=result['log_id']
        )

    except ValueError as e:
        error_msg = str(e)
        if "not a contact" in error_msg.lower() or "access" in error_msg.lower():
            return 403, {"error": error_msg}
        return 400, {"error": error_msg}

    except Exception as e:
        logger.error(f"Zenith ask error: {e}", exc_info=True)
        return 400, {"error": f"Failed to get answer: {str(e)}"}


@router.get("/settings", response=ZenithSettingsResponse, auth=ProfileAuth())
@ratelimit(group='zenith:settings', key=user_or_ip, rate='30/m')
def get_zenith_settings(request):
    """
    Get your Zenith settings.
    """
    from parahub.models import ZenithSettings

    settings = ZenithSettings.get_or_create_for_profile(request.auth_profile)

    return ZenithSettingsResponse(
        enabled=settings.enabled,
        gitea_repo_name=settings.gitea_repo_name or 'zenith-knowledge',
        allow_contacts_access=settings.allow_contacts_access,
        has_api_key=bool(settings.gemini_api_key),
        total_queries=settings.total_queries,
        system_prompt=settings.system_prompt or None
    )


@router.put("/settings", response=ZenithSettingsResponse, auth=ProfileAuth())
@ratelimit(group='zenith:settings_update', key=user_or_ip, rate='10/m', method='PUT')
def update_zenith_settings(request, data: ZenithSettingsUpdateRequest):
    """
    Update your Zenith settings.
    """
    from parahub.models import ZenithSettings

    settings = ZenithSettings.get_or_create_for_profile(request.auth_profile)

    # Update fields if provided
    if data.enabled is not None:
        settings.enabled = data.enabled
    if data.gitea_repo_name is not None:
        settings.gitea_repo_name = data.gitea_repo_name
    if data.gemini_api_key is not None:
        settings.gemini_api_key = data.gemini_api_key
    if data.system_prompt is not None:
        settings.system_prompt = data.system_prompt
    if data.allow_contacts_access is not None:
        settings.allow_contacts_access = data.allow_contacts_access

    settings.save()

    return ZenithSettingsResponse(
        enabled=settings.enabled,
        gitea_repo_name=settings.gitea_repo_name or 'zenith-knowledge',
        allow_contacts_access=settings.allow_contacts_access,
        has_api_key=bool(settings.gemini_api_key),
        total_queries=settings.total_queries,
        system_prompt=settings.system_prompt or None
    )


@router.get("/logs", response=List[ZenithQueryLogEntry], auth=ProfileAuth())
@ratelimit(group='zenith:logs', key=user_or_ip, rate='30/m')
def get_zenith_logs(request, limit: int = 50, offset: int = 0):
    """
    Get query logs for your Zenith.
    Shows all questions asked to your Zenith.
    """
    from parahub.models import ZenithQueryLog

    logs = ZenithQueryLog.objects.filter(
        zenith_owner=request.auth_profile
    ).order_by('-created_at')[offset:offset + limit]

    return [
        ZenithQueryLogEntry(
            id=log.id,
            querier_hna=log.querier.hna if log.querier else None,
            querier_id=log.querier.id if log.querier else None,
            question=log.question,
            answer=log.answer,
            files_used=log.files_used,
            processing_time_ms=log.processing_time_ms,
            input_tokens=log.input_tokens,
            output_tokens=log.output_tokens,
            cost_usd=float(log.estimated_cost_usd) if log.estimated_cost_usd else None,
            success=log.success,
            error_message=log.error_message or None,
            created_at=log.created_at
        )
        for log in logs
    ]


@router.get("/status/{profile_id}", response=ZenithStatusResponse, auth=ProfileAuth())
@ratelimit(group='zenith:status', key=user_or_ip, rate='30/m')
def get_zenith_status(request, profile_id: str):
    """
    Check if you can ask a specific profile's Zenith.

    Returns:
    - enabled: Whether the profile has Zenith enabled
    - can_ask: Whether YOU can ask this Zenith
    - reason: Why you can't ask (if can_ask=False)
    """
    from parahub.models import ZenithSettings
    from identity.models import Profile, Partner

    try:
        target_profile = Profile.objects.get(id=profile_id)
    except Profile.DoesNotExist:
        return ZenithStatusResponse(
            enabled=False,
            can_ask=False,
            reason="Profile not found"
        )

    # Check if it's your own Zenith
    if target_profile.id == request.auth_profile.id:
        try:
            settings = ZenithSettings.objects.get(profile=target_profile)
            return ZenithStatusResponse(
                enabled=settings.enabled,
                can_ask=settings.enabled,
                reason=None if settings.enabled else "Zenith is not enabled"
            )
        except ZenithSettings.DoesNotExist:
            return ZenithStatusResponse(
                enabled=False,
                can_ask=False,
                reason="Zenith is not configured"
            )

    # Check target's Zenith settings
    try:
        settings = ZenithSettings.objects.get(profile=target_profile)
    except ZenithSettings.DoesNotExist:
        return ZenithStatusResponse(
            enabled=False,
            can_ask=False,
            reason="User has not configured Zenith"
        )

    if not settings.enabled:
        return ZenithStatusResponse(
            enabled=False,
            can_ask=False,
            reason="User has not enabled Zenith"
        )

    if not settings.allow_contacts_access:
        return ZenithStatusResponse(
            enabled=True,
            can_ask=False,
            reason="User has disabled Zenith for contacts"
        )

    # Check if you're a contact
    is_contact = Partner.objects.filter(
        profile=target_profile,
        partner=request.auth_profile
    ).exists()

    if not is_contact:
        return ZenithStatusResponse(
            enabled=True,
            can_ask=False,
            reason="You must be in this user's contacts to ask their Zenith"
        )

    return ZenithStatusResponse(
        enabled=True,
        can_ask=True,
        reason=None
    )
