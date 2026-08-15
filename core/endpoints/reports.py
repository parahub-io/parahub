"""Universal content/user reporting endpoints (Play UGC policy).

Reporting is open to any signed-in profile; the queue below it is the other
half — reading and resolving those reports is `moderation.review`, so a
moderator can be appointed without Django admin coming with the job.
"""
from datetime import datetime
from typing import List, Optional

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import BaseModel
import logging

from django.db import IntegrityError
from django.utils import timezone

from parahub.auth import ProfileAuth
from parahub.capabilities import require_platform_capability
from parahub.errors import LocalizedHttpError
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

#: Reading and resolving abuse reports (`parahub/capabilities.py`).
MODERATION = 'moderation.review'

router = Router(tags=["Reports"])


class ReportInput(Schema):
    object_id: str
    reason: str
    details: str = ''
    context_url: str = ''


class ReportResponse(BaseModel):
    id: str
    object_type: str = 'content_report'
    target_id: str
    target_type: str
    reason: str
    status: str
    created_at: datetime


class ReportReasonResponse(BaseModel):
    value: str
    label: str


class QueueProfile(BaseModel):
    id: str
    local_name: str = ''
    display_name: str = ''
    avatar_url: str = ''


class QueueReport(BaseModel):
    id: str
    object_type: str = 'content_report'
    target_id: str
    target_type: str
    reason: str
    status: str
    details: str = ''
    excerpt: str = ''
    context_url: str = ''
    created_at: datetime
    reporter: Optional[QueueProfile] = None
    reported_profile: Optional[QueueProfile] = None
    #: Other people who reported the same object and are still waiting.
    duplicate_pending: int = 0
    #: How often this author has been reported, ever / upheld — the repeat signal.
    author_reports_total: int = 0
    author_reports_actioned: int = 0
    reviewed_by: str = ''
    reviewed_at: Optional[datetime] = None
    resolution_note: str = ''


class QueueResponse(BaseModel):
    items: List[QueueReport]
    total: int
    pending_total: int


class ResolveInput(Schema):
    status: str
    note: str = ''


class ResolveResponse(BaseModel):
    status: str
    #: Includes the sibling reports closed with it — the decision is about the
    #: object, not about who happened to report it first.
    resolved: int


@router.get("/reasons/", auth=None, response=List[ReportReasonResponse])
def list_report_reasons(request):
    """Report reason choices (labels are canonical English; client localizes by value)."""
    from core.models import ContentReport
    return [ReportReasonResponse(value=v, label=l) for v, l in ContentReport.Reason.choices]


@router.post("/", auth=ProfileAuth(), response={201: ReportResponse})
@ratelimit(group='core:create_report', key=user_or_ip, rate='10/h', method='POST')
def create_report(request, data: ReportInput):
    """Report any ULID-identified object (item, profile, comment, post, ...)."""
    from core.models import ContentReport
    from core.services.reports import resolve_report_target

    if not data.object_id or len(data.object_id) != 26 or not data.object_id.isalnum():
        raise LocalizedHttpError(400, "report_invalid_target", "Invalid object id")

    if data.reason not in ContentReport.Reason.values:
        raise LocalizedHttpError(400, "report_invalid_reason", "Invalid report reason")

    details = (data.details or '').strip()
    if len(details) > 2000:
        raise LocalizedHttpError(400, "report_details_too_long", "Details must be at most 2000 characters")

    resolved = resolve_report_target(data.object_id)
    if resolved is None:
        raise LocalizedHttpError(404, "report_target_not_found", "Reported object not found")
    object_type, reported_profile, excerpt = resolved

    reporter = request.auth
    if reported_profile is not None and reported_profile.id == reporter.id:
        raise LocalizedHttpError(400, "report_own_content", "You cannot report your own content")

    if ContentReport.objects.filter(
        reporter=reporter, object_id=data.object_id,
        status=ContentReport.Status.PENDING,
    ).exists():
        raise LocalizedHttpError(400, "report_already_pending", "You already reported this; the report is pending review")

    try:
        report = ContentReport.objects.create(
            object_id=data.object_id,
            object_type=object_type,
            reporter=reporter,
            reported_profile=reported_profile,
            reason=data.reason,
            details=details,
            excerpt=excerpt,
            context_url=(data.context_url or '')[:500],
        )
    except IntegrityError:
        raise LocalizedHttpError(400, "report_already_pending", "You already reported this; the report is pending review")

    logger.info(f"Content report {report.id}: {data.reason} on {object_type}:{data.object_id} by {reporter.id}")

    return 201, ReportResponse(
        id=report.id,
        target_id=report.object_id,
        target_type=report.object_type,
        reason=report.reason,
        status=report.status,
        created_at=report.created_at,
    )


# ===== Moderation queue (`moderation.review`) =====

def _queue_profile(profile) -> Optional[QueueProfile]:
    if profile is None:
        return None
    return QueueProfile(
        id=profile.id,
        local_name=profile.local_name or '',
        # The queue is a moderation surface: it needs to name the author even
        # when the profile hides its display name from the public.
        display_name=profile.display_name or '',
        avatar_url=profile.avatar_url or '',
    )


@router.get("/queue/", auth=ProfileAuth(), response={200: QueueResponse, 403: dict})
@ratelimit(group='core:report_queue', key=user_or_ip, rate='120/m')
def report_queue(request, status: str = 'PENDING', reason: str = '',
                 object_type: str = '', limit: int = 50, offset: int = 0):
    """The abuse-report queue. Needs `moderation.review`."""
    from django.db.models import Count, Q
    from core.models import ContentReport

    require_platform_capability(request, MODERATION)

    qs = ContentReport.objects.select_related('reporter', 'reported_profile', 'reviewed_by')
    if status:
        if status not in ContentReport.Status.values:
            raise HttpError(400, "Unknown status")
        qs = qs.filter(status=status)
    if reason:
        if reason not in ContentReport.Reason.values:
            raise HttpError(400, "Unknown reason")
        qs = qs.filter(reason=reason)
    if object_type:
        qs = qs.filter(object_type=object_type)

    total = qs.count()
    pending_total = ContentReport.objects.filter(status=ContentReport.Status.PENDING).count()

    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    rows = list(qs[offset:offset + limit])

    # Two aggregates the moderator needs on every row, batched instead of per-row:
    # how many other people are still waiting on the same object, and whether the
    # author is a repeat case.
    object_ids = {r.object_id for r in rows}
    dup = {
        row['object_id']: row['n']
        for row in ContentReport.objects.filter(
            object_id__in=object_ids, status=ContentReport.Status.PENDING,
        ).values('object_id').annotate(n=Count('id'))
    }
    author_ids = {r.reported_profile_id for r in rows if r.reported_profile_id}
    authors = {
        row['reported_profile_id']: row
        for row in ContentReport.objects.filter(reported_profile_id__in=author_ids)
        .values('reported_profile_id')
        .annotate(n=Count('id'),
                  actioned=Count('id', filter=Q(status=ContentReport.Status.ACTIONED)))
    }

    items = []
    for r in rows:
        stats = authors.get(r.reported_profile_id, {})
        items.append(QueueReport(
            id=r.id,
            target_id=r.object_id,
            target_type=r.object_type,
            reason=r.reason,
            status=r.status,
            details=r.details,
            excerpt=r.excerpt,
            context_url=r.context_url,
            created_at=r.created_at,
            reporter=_queue_profile(r.reporter),
            reported_profile=_queue_profile(r.reported_profile),
            duplicate_pending=max(0, dup.get(r.object_id, 0) - (1 if r.status == ContentReport.Status.PENDING else 0)),
            author_reports_total=stats.get('n', 0),
            author_reports_actioned=stats.get('actioned', 0),
            reviewed_by=r.reviewed_by.username if r.reviewed_by else '',
            reviewed_at=r.reviewed_at,
            resolution_note=r.resolution_note,
        ))

    return 200, QueueResponse(items=items, total=total, pending_total=pending_total)


@router.post("/{report_id}/resolve/", auth=ProfileAuth(),
             response={200: ResolveResponse, 400: dict, 403: dict, 404: dict})
@ratelimit(group='core:resolve_report', key=user_or_ip, rate='60/m', method='POST')
def resolve_report(request, report_id: str, data: ResolveInput):
    """
    Close a report as ACTIONED or DISMISSED. Needs `moderation.review`.

    Every other pending report on the same object closes with it: the verdict is
    about the content, and leaving the duplicates open would hand the next
    moderator the same decision again.

    Acting on the content itself (deactivating an item, deleting a comment) is
    still a Django-admin job — see `PK/moderation-system.md`.
    """
    from core.models import ContentReport

    account = require_platform_capability(request, MODERATION)

    if data.status not in (ContentReport.Status.ACTIONED, ContentReport.Status.DISMISSED):
        raise HttpError(400, "Resolution must be ACTIONED or DISMISSED")

    report = ContentReport.objects.filter(id=report_id).first()
    if report is None:
        raise HttpError(404, "Report not found")

    from django.db.models import Q

    note = (data.note or '').strip()[:500]
    # Pending siblings on the same object, plus this row whatever state it is in:
    # a verdict must be correctable, or a mis-click becomes permanent.
    resolved = ContentReport.objects.filter(
        Q(object_id=report.object_id, status=ContentReport.Status.PENDING) | Q(id=report.id),
    ).update(
        status=data.status, reviewed_by=account, reviewed_at=timezone.now(),
        resolution_note=note,
    )

    logger.info(f"Report {report.id} on {report.object_type}:{report.object_id} "
                f"→ {data.status} by {account.username} ({resolved} row(s))")
    return 200, ResolveResponse(status=data.status, resolved=resolved)
