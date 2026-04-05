"""
Association Income API — donation tracking and transparency.
"""

from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
import logging

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from finance.models import Donation
from identity.models import Profile

logger = logging.getLogger(__name__)

income_router = Router()


# --- Schemas ---

class IncomeConfigResponse(BaseModel):
    ln_address: str = ''
    spark_address: str = ''
    support_level: Decimal = Decimal('0.1')


class DonationCreateRequest(BaseModel):
    source: str  # WALLET_SEND, ADS_CAMPAIGN, MANUAL
    source_amount_sats: int
    donation_amount_sats: int
    support_level_at_time: Decimal
    ln_payment_hash: str = ''
    status: str = 'COMPLETED'  # COMPLETED or SKIPPED


class DonationResponse(BaseModel):
    id: str
    source: str
    source_amount_sats: int
    donation_amount_sats: int
    support_level_at_time: Decimal
    status: str
    created_at: str


class TransparencyMonthResponse(BaseModel):
    month: str
    total_sats: int
    count: int


class TransparencyResponse(BaseModel):
    total_donated_sats: int
    total_donations_count: int
    supporters_count: int
    by_month: List[TransparencyMonthResponse]
    by_source: dict


# --- Endpoints ---

@income_router.get("/config/", auth=OptionalProfileAuth())
@ratelimit(group='income:config', key=user_or_ip, rate='60/m')
def get_income_config(request):
    """Get association donation addresses and user's support level.

    Reads spark_address/ln_address from the governing Establishment
    (configured via GOVERNING_ASSOCIATION_SLUG in Constance).
    """
    from constance import config
    from geo.models import Establishment

    support_level = Decimal('0.1')
    if hasattr(request, 'auth_profile') and request.auth_profile:
        support_level = request.auth_profile.support_level

    spark_address = ''
    ln_address = ''
    try:
        est = Establishment.objects.get(slug=config.GOVERNING_ASSOCIATION_SLUG, is_active=True)
        spark_address = est.spark_address or ''
        ln_address = est.ln_address or ''
    except Establishment.DoesNotExist:
        pass

    return {
        'ln_address': ln_address,
        'spark_address': spark_address,
        'support_level': support_level,
    }


@income_router.post("/donations/", auth=ProfileAuth(), response={200: dict, 400: dict})
@ratelimit(group='income:record_donation', key=user_or_ip, rate='30/m', method='POST')
def record_donation(request, data: DonationCreateRequest):
    """Record a donation (completed or skipped)."""
    profile = request.auth_profile

    if data.status not in ('COMPLETED', 'SKIPPED', 'FAILED'):
        raise HttpError(400, "Invalid status")
    if data.source not in ('WALLET_SEND', 'ADS_CAMPAIGN', 'MANUAL'):
        raise HttpError(400, "Invalid source")

    donation = Donation.objects.create(
        profile=profile,
        source=data.source,
        source_amount_sats=data.source_amount_sats,
        donation_amount_sats=data.donation_amount_sats,
        support_level_at_time=data.support_level_at_time,
        ln_payment_hash=data.ln_payment_hash,
        status=data.status,
    )

    # Mark as supporter on first completed donation
    if data.status == 'COMPLETED' and not profile.is_supporter:
        profile.is_supporter = True
        profile.save(update_fields=['is_supporter'])

    return {
        'id': donation.id,
        'status': donation.status,
        'donation_amount_sats': donation.donation_amount_sats,
    }


@income_router.get("/donations/my/", auth=ProfileAuth())
@ratelimit(group='income:my_donations', key=user_or_ip, rate='60/m')
def my_donations(request):
    """User's donation history."""
    profile = request.auth_profile
    donations = Donation.objects.filter(
        profile=profile
    ).exclude(
        status='SKIPPED'
    ).order_by('-created_at')[:50]

    total = Donation.objects.filter(
        profile=profile, status='COMPLETED'
    ).aggregate(total=Sum('donation_amount_sats'))['total'] or 0

    return {
        'total_donated_sats': total,
        'donations': [
            {
                'id': d.id,
                'source': d.source,
                'source_amount_sats': d.source_amount_sats,
                'donation_amount_sats': d.donation_amount_sats,
                'support_level_at_time': d.support_level_at_time,
                'status': d.status,
                'created_at': d.created_at.isoformat(),
            }
            for d in donations
        ],
    }


@income_router.get("/transparency/", auth=None)
@ratelimit(group='income:transparency', key='ip', rate='60/m')
def transparency(request):
    """Public transparency — total collected, breakdown."""
    completed = Donation.objects.filter(status='COMPLETED')

    totals = completed.aggregate(
        total_sats=Sum('donation_amount_sats'),
        total_count=Count('id'),
    )

    by_month = list(
        completed.annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total_sats=Sum('donation_amount_sats'), count=Count('id'))
        .order_by('-month')[:12]
    )

    by_source = {}
    for source_choice in Donation.Source.choices:
        key = source_choice[0]
        agg = completed.filter(source=key).aggregate(
            total=Sum('donation_amount_sats'), count=Count('id')
        )
        by_source[key] = {
            'total_sats': agg['total'] or 0,
            'count': agg['count'],
        }

    supporters_count = Profile.objects.filter(is_supporter=True).count()

    return {
        'total_donated_sats': totals['total_sats'] or 0,
        'total_donations_count': totals['total_count'],
        'supporters_count': supporters_count,
        'by_month': [
            {
                'month': m['month'].strftime('%Y-%m'),
                'total_sats': m['total_sats'],
                'count': m['count'],
            }
            for m in by_month
        ],
        'by_source': by_source,
    }
