"""
Advertising System API endpoints for Parahub (Para-ads)
Implements pay-per-view advertising with Lightning Network payments
"""

from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.db.models import Q, Avg, F, Count, Func, Sum
from django.utils import timezone
from datetime import timedelta
from typing import List, Optional
import hashlib
import logging

import nh3
from ninja import File, UploadedFile

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from parahub.schemas import (
    AdsProfileResponse,
    AdsProfileUpdate,
    AdCampaignCreate,
    AdCampaignUpdate,
    AdCampaignResponse,
    AdFeedItem,
    AdFeedHistoryItem,
    AdViewCreate,
    EarningsStatsResponse,
    AdsInterestSchema,
    AdsSkillSchema,
    AdsChildrenAgeSchema,
    WalletTestRequest,
    AdPayoutReport,
)
from ads.models import (
    AdsProfile,
    AdsProfileLocation,
    AdCampaign,
    AdView,
    AdsInterest,
    AdsSkill,
    AdsChildrenAge,
    AdsProfileSkill,
    default_ln_wallet_config,
)
from ads.crypto_utils import encrypt_wallet_config, decrypt_wallet_config
from ads.ln_wallet_service import (
    send_payment_via_lnurl,
    create_wallet_client,
    resolve_lnurl_invoice,
    bolt11_payment_hash,
)
from identity.models import Profile
from identity.visibility import exclude_test_authors

# HTML sanitization: allowed tags for rich text content
ALLOWED_TAGS = {'b', 'i', 'strong', 'em', 's', 'a', 'ul', 'ol', 'li', 'p', 'br', 'blockquote'}
ALLOWED_ATTRIBUTES = {'a': {'href', 'target'}}

# A payout left in 'pending' this long lost its worker mid-flight (restart,
# crash). After that the viewer may claim again — the LNURL chain is short
# enough that a real in-flight payout can never take that long. 'queued'
# payouts (browser-paid rail) are exempt: they legitimately wait for the
# advertiser's next visit.
PAYOUT_STALE_AFTER = timedelta(minutes=5)

# Browser-paid payouts: one device works on a payout at a time (Redis lease),
# and a resolved invoice is reused within its window so an interrupted payer
# retries the SAME invoice instead of minting a fresh one.
PAYOUT_LEASE_TTL = 180
PAYOUT_INVOICE_TTL = 600


def _payout_lease_key(view_id: str) -> str:
    return f'ads:payout:lease:{view_id}'


def _payout_invoice_key(view_id: str) -> str:
    return f'ads:payout:invoice:{view_id}'


def _wallet_provider(ads_profile) -> str:
    """Provider name from a wallet config. The provider field is stored in
    plaintext (only credentials are Fernet-encrypted), so no decrypt needed."""
    if not ads_profile:
        return ''
    return (ads_profile.ln_wallet_config or {}).get('provider', '')


def sanitize_html(html: str) -> str:
    """Sanitize HTML content, keeping only safe formatting tags."""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel='noopener noreferrer',
    )

logger = logging.getLogger(__name__)

# Create ads router
ads_router = Router()


# ============================================================================
# REFERENCE DATA ENDPOINTS
# ============================================================================

@ads_router.get("/interests/", response=List[AdsInterestSchema])
@ratelimit(group='ads:interests', key='ip', rate='60/m')
def list_interests(request):
    """Get all available interests for ad targeting."""
    interests = AdsInterest.objects.all()
    return [
        {
            'id': interest.id,
            'object_type': 'ads_interest',
            'name': interest.name,
            'slug': interest.slug,
        }
        for interest in interests
    ]


@ads_router.get("/skills/", response=List[AdsSkillSchema])
@ratelimit(group='ads:skills', key='ip', rate='60/m')
def list_skills(request):
    """Get all available skills for ad targeting."""
    skills = AdsSkill.objects.all()
    return [
        {
            'id': skill.id,
            'object_type': 'ads_skill',
            'name': skill.name,
            'slug': skill.slug,
        }
        for skill in skills
    ]


@ads_router.get("/children-ages/", response=List[AdsChildrenAgeSchema])
@ratelimit(group='ads:children_ages', key='ip', rate='60/m')
def list_children_ages(request):
    """Get all available children age ranges."""
    ages = AdsChildrenAge.objects.all()
    return [
        {
            'id': age.id,
            'object_type': 'ads_children_age',
            'name': age.name,
        }
        for age in ages
    ]


# ============================================================================
# ADS PROFILE ENDPOINTS
# ============================================================================

@ads_router.get("/profile/", response=AdsProfileResponse, auth=ProfileAuth())
@ratelimit(group='ads:get_profile', key=user_or_ip, rate='60/m')
def get_ads_profile(request):
    """Get or create user's ads profile."""
    profile = request.auth_profile

    # Get or create ads profile
    ads_profile, created = AdsProfile.objects.select_related('profile').get_or_create(
        profile=profile,
        defaults={
            'gender': 'any',
            'total_views': 0,
            'total_earned_sats': 0,
        }
    )

    # Get M2M relationships
    interest_ids = list(ads_profile.interests.values_list('id', flat=True))
    children_age_ids = list(ads_profile.children_ages.values_list('id', flat=True))

    # Get skill ratings
    skill_ratings = AdsProfileSkill.objects.filter(profile=ads_profile).select_related('skill')
    skills = [
        {
            'skill_id': sr.skill.id,
            'skill_name': sr.skill.name,
            'level': sr.level,
        }
        for sr in skill_ratings
    ]

    # Get locations
    locations = [
        {'id': loc.id, 'label': loc.label, 'latitude': loc.location.y, 'longitude': loc.location.x}
        for loc in AdsProfileLocation.objects.filter(profile=ads_profile)
    ]

    # Determine wallet config status (without exposing secrets)
    wallet_config = ads_profile.ln_wallet_config or {}
    has_wallet_config = bool(wallet_config.get('provider'))
    wallet_provider = wallet_config.get('provider', '') if has_wallet_config else ''

    return {
        'id': ads_profile.id,
        'object_type': 'ads_profile',
        'profile_id': profile.id,
        'gender': ads_profile.gender,
        'age': ads_profile.age,
        'birth_date': ads_profile.birth_date.isoformat() if ads_profile.birth_date else None,
        'min_reward_sats': ads_profile.min_reward_sats,
        'interests': interest_ids,
        'children_ages': children_age_ids,
        'skills': skills,
        'locations': locations,
        'ln_address': ads_profile.profile.ln_address,
        'has_wallet_config': has_wallet_config,
        'wallet_provider': wallet_provider,
        'total_views': ads_profile.total_views,
        'total_earned_sats': ads_profile.total_earned_sats,
        'created_at': ads_profile.created_at,
        'updated_at': ads_profile.updated_at,
    }


@ads_router.put("/profile/", response=AdsProfileResponse, auth=ProfileAuth())
@ratelimit(group='ads:update_profile', key=user_or_ip, rate='30/m', method='PUT')
def update_ads_profile(request, data: AdsProfileUpdate):
    """Update user's ads profile settings."""
    from datetime import datetime
    profile = request.auth

    ads_profile, created = AdsProfile.objects.get_or_create(profile=profile)

    # Update only provided fields
    if data.gender is not None:
        ads_profile.gender = data.gender
    if data.age is not None:
        ads_profile.age = data.age
    if data.birth_date is not None:
        try:
            ads_profile.birth_date = datetime.fromisoformat(data.birth_date).date()
        except ValueError:
            raise ValueError("Invalid birth_date format. Use YYYY-MM-DD")
    if data.min_reward_sats is not None:
        ads_profile.min_reward_sats = data.min_reward_sats
    if data.ln_wallet_config is not None:
        if not data.ln_wallet_config.get('provider'):
            # Clearing the config means "back to the default", not "no wallet":
            # the browser-paid Parahub wallet needs no credentials, so an
            # unconfigured state does not exist.
            ads_profile.ln_wallet_config = default_ln_wallet_config()
        else:
            # External server-paid rails (nwc/lnbits/alby) make the platform
            # initiate payments from the advertiser's wallet — for third
            # parties that is an open MiCA question (see PK/ads-system.md
            # § Regulatory line), so they stay staff-only until cleared in
            # writing. Everyone else runs the browser-paid default.
            if data.ln_wallet_config['provider'] != 'spark' and not profile.account.is_staff:
                raise HttpError(403, "External wallet providers are staff-only; the default Parahub wallet needs no setup")
            # Encrypt sensitive fields (API keys/tokens) before storing
            ads_profile.ln_wallet_config = encrypt_wallet_config(data.ln_wallet_config)

    ads_profile.save()

    # Update locations (replace-all pattern, max 3)
    if data.locations is not None:
        from django.contrib.gis.geos import Point
        AdsProfileLocation.objects.filter(profile=ads_profile).delete()
        for loc_data in data.locations[:3]:
            AdsProfileLocation.objects.create(
                profile=ads_profile,
                label=loc_data.label,
                location=Point(loc_data.longitude, loc_data.latitude, srid=4326),
            )

    # Update M2M relationships
    if data.interest_ids is not None:
        ads_profile.interests.set(data.interest_ids)

    if data.children_age_ids is not None:
        ads_profile.children_ages.set(data.children_age_ids)

    # Update skill ratings
    if data.skill_ratings is not None:
        # Delete existing ratings
        AdsProfileSkill.objects.filter(profile=ads_profile).delete()
        # Create new ratings (clamp to 1-4)
        for skill_id, level in data.skill_ratings.items():
            if level > 0:
                clamped = max(1, min(5, level))
                AdsProfileSkill.objects.create(
                    profile=ads_profile,
                    skill_id=skill_id,
                    level=clamped
                )

    # Reload M2M data for response
    interest_ids = list(ads_profile.interests.values_list('id', flat=True))
    children_age_ids = list(ads_profile.children_ages.values_list('id', flat=True))
    skill_ratings = AdsProfileSkill.objects.filter(profile=ads_profile).select_related('skill')
    skills = [
        {
            'skill_id': sr.skill.id,
            'skill_name': sr.skill.name,
            'level': sr.level,
        }
        for sr in skill_ratings
    ]

    # Get locations for response
    locations = [
        {'id': loc.id, 'label': loc.label, 'latitude': loc.location.y, 'longitude': loc.location.x}
        for loc in AdsProfileLocation.objects.filter(profile=ads_profile)
    ]

    # Determine wallet config status
    wallet_config_data = ads_profile.ln_wallet_config or {}
    has_wallet_config = bool(wallet_config_data.get('provider'))
    wallet_provider_name = wallet_config_data.get('provider', '') if has_wallet_config else ''

    return {
        'id': ads_profile.id,
        'object_type': 'ads_profile',
        'profile_id': profile.id,
        'gender': ads_profile.gender,
        'age': ads_profile.age,
        'birth_date': ads_profile.birth_date.isoformat() if ads_profile.birth_date else None,
        'min_reward_sats': ads_profile.min_reward_sats,
        'interests': interest_ids,
        'children_ages': children_age_ids,
        'skills': skills,
        'locations': locations,
        'ln_address': ads_profile.profile.ln_address,
        'has_wallet_config': has_wallet_config,
        'wallet_provider': wallet_provider_name,
        'total_views': ads_profile.total_views,
        'total_earned_sats': ads_profile.total_earned_sats,
        'created_at': ads_profile.created_at,
        'updated_at': ads_profile.updated_at,
    }


@ads_router.post("/wallet-test/", auth=ProfileAuth())
@ratelimit(group='ads:wallet_test', key=user_or_ip, rate='10/m', method='POST')
def test_wallet_connection(request, data: WalletTestRequest):
    """Test wallet provider connection with provided credentials."""
    config = {k: v for k, v in data.dict().items() if v is not None}

    if config.get('provider') == 'spark':
        # Nothing to test server-side: the paying wallet lives in the
        # advertiser's browser and holds no server-visible credentials.
        return {"success": True, "provider": "spark"}

    # Same staff-only gate as saving the config: no point probing external
    # wallets with credentials that cannot be stored anyway.
    if not request.auth.account.is_staff:
        raise HttpError(403, "External wallet providers are staff-only; the default Parahub wallet needs no setup")

    try:
        client = create_wallet_client(config)
        result = client.test_connection()
        return result
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.warning(f"Wallet test failed for {data.provider}: {e}")
        return {"success": False, "error": str(e)}


@ads_router.get("/earnings/", response=EarningsStatsResponse, auth=ProfileAuth())
@ratelimit(group='ads:earnings', key=user_or_ip, rate='60/m')
def get_earnings_stats(request):
    """Get user's earnings statistics."""
    profile = request.auth

    try:
        ads_profile = AdsProfile.objects.get(profile=profile)
        avg_per_view = (
            ads_profile.total_earned_sats / ads_profile.total_views
            if ads_profile.total_views > 0
            else 0.0
        )

        return {
            'total_views': ads_profile.total_views,
            'total_earned_sats': ads_profile.total_earned_sats,
            'avg_per_view_sats': avg_per_view,
        }
    except AdsProfile.DoesNotExist:
        return {
            'total_views': 0,
            'total_earned_sats': 0,
            'avg_per_view_sats': 0.0,
        }


# ============================================================================
# AUDIENCE ESTIMATE
# ============================================================================

@ads_router.get("/audience-estimate/", auth=ProfileAuth())
@ratelimit(group='ads:audience_estimate', key=user_or_ip, rate='10/m')
def audience_estimate(
    request,
    target_gender: str = 'any',
    target_age_from: int = 18,
    target_age_to: int = 65,
    reward_sats: int = 10,
    target_interest_ids: str = '',
    target_children_age_ids: str = '',
    target_skill_ids: str = '',
    target_min_skill_level: int = 1,
    target_latitude: float = None,
    target_longitude: float = None,
    target_radius_km: float = 0,
    include_self: bool = False,
    exclude_self: bool = False,
):
    """Estimate how many AdsProfiles match the given targeting criteria."""
    from django.db.models.functions import Extract

    q = Q()

    # Gender filter: if not 'any', match profiles with that gender OR 'any'
    if target_gender != 'any':
        q &= Q(gender='any') | Q(gender=target_gender)

    # Age filter: PostgreSQL AGE() gives exact age accounting for month/day
    # EXTRACT(YEAR FROM AGE(birth_date)) → exact integer years
    qs = AdsProfile.objects.annotate(
        computed_age=Extract(Func(F('birth_date'), function='AGE'), 'year')
    )
    q &= Q(birth_date__isnull=True) | Q(computed_age__gte=target_age_from, computed_age__lte=target_age_to)

    # Min reward filter: only profiles willing to view for this reward
    q &= Q(min_reward_sats__lte=reward_sats)

    # Interest filter: if interest IDs provided, only count profiles with at least one matching
    if target_interest_ids:
        interest_id_list = [i.strip() for i in target_interest_ids.split(',') if i.strip()]
        if interest_id_list:
            q &= Q(interests__in=interest_id_list)

    # Children age filter
    if target_children_age_ids:
        children_ids = [i.strip() for i in target_children_age_ids.split(',') if i.strip()]
        if children_ids:
            q &= Q(children_ages__in=children_ids)

    matched_profile_ids = set(qs.filter(q).distinct().values_list('id', flat=True))

    # Geo filter: if target location provided, only count profiles with ≥1 location within radius
    if target_latitude is not None and target_longitude is not None and target_radius_km > 0:
        from django.contrib.gis.geos import Point
        from django.contrib.gis.measure import D
        target_point = Point(target_longitude, target_latitude, srid=4326)
        nearby_profile_ids = set(
            AdsProfileLocation.objects.filter(
                profile_id__in=matched_profile_ids,
                location__dwithin=(target_point, D(km=target_radius_km)),
            ).values_list('profile_id', flat=True)
        )
        matched_profile_ids &= nearby_profile_ids

    # Skills filter (post-query set intersection)
    if target_skill_ids:
        skill_ids = [i.strip() for i in target_skill_ids.split(',') if i.strip()]
        if skill_ids:
            skill_matching = set(
                AdsProfileSkill.objects.filter(
                    profile_id__in=matched_profile_ids,
                    skill_id__in=skill_ids,
                    level__gte=target_min_skill_level,
                ).values_list('profile_id', flat=True)
            )
            matched_profile_ids &= skill_matching

    own_profile_id = request.auth_profile.id
    if exclude_self:
        matched_profile_ids.discard(own_profile_id)
    elif include_self:
        matched_profile_ids.add(own_profile_id)

    reach = len(matched_profile_ids)

    # Breakdown computation
    matched_qs = AdsProfile.objects.filter(id__in=matched_profile_ids)

    gender_data = {
        g['gender']: g['cnt']
        for g in matched_qs.values('gender').annotate(cnt=Count('id'))
    }

    avg_age_result = matched_qs.filter(birth_date__isnull=False).annotate(
        computed_age=Extract(Func(F('birth_date'), function='AGE'), 'year')
    ).aggregate(avg=Avg('computed_age'))['avg']

    has_location = AdsProfileLocation.objects.filter(
        profile_id__in=matched_profile_ids
    ).values('profile_id').distinct().count()

    has_skills = AdsProfileSkill.objects.filter(
        profile_id__in=matched_profile_ids
    ).values('profile_id').distinct().count()

    no_children_ids = list(
        AdsChildrenAge.objects.filter(name='No children').values_list('id', flat=True)
    )
    has_children = matched_qs.filter(
        children_ages__isnull=False
    ).exclude(
        children_ages__id__in=no_children_ids
    ).distinct().count()

    return {
        "reach": reach,
        "max_budget_sats": reach * reward_sats,
        "breakdown": {
            "by_gender": {
                "male": gender_data.get('male', 0),
                "female": gender_data.get('female', 0),
                "any": gender_data.get('any', 0),
            },
            "avg_age": round(avg_age_result, 1) if avg_age_result else None,
            "has_location": has_location,
            "has_children": has_children,
            "has_skills": has_skills,
        },
    }


def _linked_item_data(item):
    """Build linked item mini-response."""
    if not item:
        return None
    # Sort prefetched images in Python to avoid bypassing prefetch cache
    images = sorted(item.images.all(), key=lambda i: i.order)
    first_image = images[0] if images else None
    return {
        'id': item.id,
        'title': item.title,
        'image_url': first_image.image.url if first_image else None,
        'pricing_options': item.pricing_options,
    }


def _linked_establishment_data(est):
    """Build linked establishment mini-response."""
    if not est:
        return None
    return {
        'id': est.id,
        'name': est.name,
        'slug': est.slug,
        'logo_url': est.logo_url or None,
        'category_name': est.category.name if est.category else None,
    }


def _campaign_response(campaign):
    """Build campaign response dict (DRY helper)."""
    return {
        'id': campaign.id,
        'object_type': 'ad_campaign',
        'advertiser_id': campaign.advertiser_id,
        'name': campaign.name,
        'post_title': campaign.post_title,
        'post_content': campaign.post_content,
        'source_lang': campaign.source_lang,
        'link': campaign.link,
        'image_url': campaign.image.url if campaign.image else None,
        'reward_sats': campaign.reward_sats,
        'budget_sats': campaign.budget_sats,
        'spent_sats': campaign.spent_sats,
        'remaining_budget_sats': campaign.remaining_budget_sats,
        'target_gender': campaign.target_gender,
        'target_age_from': campaign.target_age_from,
        'target_age_to': campaign.target_age_to,
        'target_interest_ids': [i.id for i in campaign.target_interests.all()],
        'target_children_age_ids': [i.id for i in campaign.target_children_ages.all()],
        'target_skill_ids': [i.id for i in campaign.target_skills.all()],
        'target_min_skill_level': campaign.target_min_skill_level,
        'target_latitude': campaign.target_location.y if campaign.target_location else None,
        'target_longitude': campaign.target_location.x if campaign.target_location else None,
        'target_radius_km': campaign.target_radius_km,
        'status': campaign.status,
        'include_self': campaign.include_self,
        'exclude_self': campaign.exclude_self,
        'total_views': campaign.total_views,
        'total_clicks': campaign.total_clicks,
        'ctr': campaign.ctr,
        'establishment_id': campaign.establishment_id if campaign.establishment_id else None,
        'establishment_name': campaign.establishment.name if campaign.establishment else None,
        'establishment_slug': campaign.establishment.slug if campaign.establishment else None,
        'establishment_logo_url': campaign.establishment.logo_url if campaign.establishment else None,
        'linked_item': _linked_item_data(campaign.linked_item),
        'linked_establishment': _linked_establishment_data(campaign.linked_establishment),
        'created_at': campaign.created_at,
        'updated_at': campaign.updated_at,
    }


# ============================================================================
# CAMPAIGN ENDPOINTS
# ============================================================================

@ads_router.get("/campaigns/", response=List[AdCampaignResponse], auth=ProfileAuth())
@ratelimit(group='ads:list_campaigns', key=user_or_ip, rate='60/m')
@paginate(PageNumberPagination)
def list_campaigns(request):
    """List user's ad campaigns."""
    profile = request.auth

    campaigns = AdCampaign.objects.filter(advertiser=profile).select_related(
        'advertiser', 'establishment', 'linked_item', 'linked_establishment',
        'linked_establishment__category',
    ).prefetch_related(
        'target_interests', 'target_children_ages', 'target_skills',
        'linked_item__images',
    )

    return [_campaign_response(c) for c in campaigns]


@ads_router.post("/campaigns/", response=AdCampaignResponse, auth=ProfileAuth())
@ratelimit(group='ads:create_campaign', key=user_or_ip, rate='10/m', method='POST')
def create_campaign(request, data: AdCampaignCreate):
    """Create new advertising campaign."""
    profile = request.auth

    # Validate establishment if posting on behalf
    establishment = None
    if data.establishment_id:
        from geo.permissions import get_establishment_for_action, POSTING_ROLES
        establishment = get_establishment_for_action(data.establishment_id, profile, POSTING_ROLES)

    # Validate budget vs reward
    if data.budget_sats < data.reward_sats:
        raise ValueError("Budget must be at least equal to reward per view")

    # Validate linked content
    linked_item = None
    linked_establishment = None
    if data.linked_item_id:
        from market.models import Item
        linked_item = Item.objects.filter(id=data.linked_item_id, is_active=True).first()
        if not linked_item:
            raise HttpError(400, "Linked item not found or inactive")
    if data.linked_establishment_id:
        from geo.models import Establishment
        linked_establishment = Establishment.objects.filter(
            id=data.linked_establishment_id, is_active=True
        ).first()
        if not linked_establishment:
            raise HttpError(400, "Linked establishment not found or inactive")

    # Sanitize HTML content
    clean_content = sanitize_html(data.post_content)

    # Build geo point if coordinates provided
    target_location = None
    if data.target_latitude is not None and data.target_longitude is not None:
        from django.contrib.gis.geos import Point
        target_location = Point(data.target_longitude, data.target_latitude, srid=4326)

    # Activate immediately if advertiser has wallet configured,
    # unless they explicitly asked for a draft. Lazy get_or_create so a
    # first-time advertiser gets the default browser-paid wallet.
    ads_profile, _ = AdsProfile.objects.get_or_create(profile=profile)
    has_wallet = bool(ads_profile.ln_wallet_config)
    initial_status = 'active' if has_wallet and not data.save_as_draft else 'draft'

    with transaction.atomic():
        campaign = AdCampaign.objects.create(
            advertiser=profile,
            establishment=establishment,
            name=data.name,
            post_title=data.post_title,
            post_content=clean_content,
            source_lang=data.source_lang,
            link=data.link or '',
            linked_item=linked_item,
            linked_establishment=linked_establishment,
            reward_sats=data.reward_sats,
            budget_sats=data.budget_sats,
            spent_sats=0,
            target_gender=data.target_gender,
            target_age_from=data.target_age_from,
            target_age_to=data.target_age_to,
            target_location=target_location,
            target_radius_km=data.target_radius_km,
            status=initial_status,
            include_self=data.include_self,
            exclude_self=data.exclude_self,
        )
        if data.target_interest_ids:
            campaign.target_interests.set(data.target_interest_ids)
        if data.target_children_age_ids:
            campaign.target_children_ages.set(data.target_children_age_ids)
        if data.target_skill_ids:
            campaign.target_skills.set(data.target_skill_ids)
        campaign.target_min_skill_level = data.target_min_skill_level
        campaign.save(update_fields=['target_min_skill_level'])

    if initial_status == 'active':
        from parahub.services.ws_publish import ws_publish
        ws_publish('ads_feed', {'type': 'ads.new_ad', 'campaign_id': campaign.id})
        ws_publish('ads_feed', {'type': 'ads.feed_updated'})

    return _campaign_response(campaign)


@ads_router.get("/campaigns/{campaign_id}/", response={200: AdCampaignResponse, 404: dict}, auth=ProfileAuth())
@ratelimit(group='ads:get_campaign', key=user_or_ip, rate='60/m')
def get_campaign(request, campaign_id: str):
    """Get campaign details."""
    profile = request.auth

    campaign = get_object_or_404(
        AdCampaign,
        id=campaign_id,
        advertiser=profile
    )

    return _campaign_response(campaign)


@ads_router.put("/campaigns/{campaign_id}/", response={200: AdCampaignResponse, 400: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='ads:update_campaign', key=user_or_ip, rate='30/m', method='PUT')
def update_campaign(request, campaign_id: str, data: AdCampaignUpdate):
    """Update campaign details."""
    profile = request.auth

    campaign = get_object_or_404(
        AdCampaign,
        id=campaign_id,
        advertiser=profile
    )

    # Reward/budget are the payer agent's trust anchor: every claimed view is
    # stamped with the campaign's reward_sats, so once a single AdView exists
    # these numbers must never move. Before the first view nothing references
    # them and they are freely editable. The check runs under the same
    # campaign row lock the claim path takes, so a concurrent first claim
    # either commits before us (we refuse) or waits for our new numbers.
    if data.reward_sats is not None or data.budget_sats is not None:
        new_reward = data.reward_sats if data.reward_sats is not None else campaign.reward_sats
        new_budget = data.budget_sats if data.budget_sats is not None else campaign.budget_sats
        if new_budget < new_reward:
            raise HttpError(400, "Budget must be at least equal to reward per view")
        with transaction.atomic():
            locked = AdCampaign.objects.select_for_update().get(pk=campaign.pk)
            if AdView.objects.filter(campaign=locked).exists():
                raise HttpError(400, "Reward and budget are locked once the campaign has views")
            locked.reward_sats = new_reward
            locked.budget_sats = new_budget
            locked.save(update_fields=['reward_sats', 'budget_sats'])
        campaign.reward_sats = new_reward
        campaign.budget_sats = new_budget

    # Update only provided fields
    if data.name is not None:
        campaign.name = data.name
    # Any real change of the ad text (or of its declared language) invalidates
    # the machine-translation cache; the advertiser's own translation maps are
    # theirs and are never wiped here. Compare against the stored values so
    # the full-form PUT the edit page sends doesn't wipe a warm cache.
    text_changed = False
    if data.post_title is not None and data.post_title != campaign.post_title:
        campaign.post_title = data.post_title
        text_changed = True
    if data.post_content is not None:
        clean_content = sanitize_html(data.post_content)
        if clean_content != campaign.post_content:
            campaign.post_content = clean_content
            text_changed = True
    if data.source_lang is not None and data.source_lang != campaign.source_lang:
        campaign.source_lang = data.source_lang
        text_changed = True
    if text_changed:
        campaign.mt_cache = {}
    if data.link is not None:
        campaign.link = data.link
    # Linked content
    if data.linked_item_id is not None:
        if data.linked_item_id == '':
            campaign.linked_item = None
        else:
            from market.models import Item
            li = Item.objects.filter(id=data.linked_item_id, is_active=True).first()
            if not li:
                raise HttpError(400, "Linked item not found or inactive")
            campaign.linked_item = li
    if data.linked_establishment_id is not None:
        if data.linked_establishment_id == '':
            campaign.linked_establishment = None
        else:
            from geo.models import Establishment
            le = Establishment.objects.filter(id=data.linked_establishment_id, is_active=True).first()
            if not le:
                raise HttpError(400, "Linked establishment not found or inactive")
            campaign.linked_establishment = le
    status_changed = False
    if data.status is not None:
        # Budget/wallet check on activation
        if data.status == 'active':
            advertiser_ads_profile, _ = AdsProfile.objects.get_or_create(profile=profile)
            if not advertiser_ads_profile.ln_wallet_config:
                raise HttpError(400, "Configure wallet before activating campaign")
            # Browser-paid wallets have no server-visible balance to probe —
            # the payer agent verifies funds at payment time instead.
            if _wallet_provider(advertiser_ads_profile) != 'spark':
                try:
                    wallet_config = decrypt_wallet_config(advertiser_ads_profile.ln_wallet_config)
                    client = create_wallet_client(wallet_config)
                    result = client.test_connection()
                    balance = result.get('balance_sats', 0)
                    remaining = campaign.remaining_budget_sats
                    if balance < remaining:
                        raise HttpError(400, f"Insufficient balance: {balance} sats (need {remaining})")
                except HttpError:
                    raise
                except Exception as e:
                    logger.warning(f"Balance check failed for campaign {campaign.id}: {e}")
        campaign.status = data.status
        status_changed = True
    if data.target_gender is not None:
        campaign.target_gender = data.target_gender
    if data.target_age_from is not None:
        campaign.target_age_from = data.target_age_from
    if data.target_age_to is not None:
        campaign.target_age_to = data.target_age_to
    if data.target_interest_ids is not None:
        campaign.target_interests.set(data.target_interest_ids)
    if data.target_children_age_ids is not None:
        campaign.target_children_ages.set(data.target_children_age_ids)
    if data.target_skill_ids is not None:
        campaign.target_skills.set(data.target_skill_ids)
    if data.target_min_skill_level is not None:
        campaign.target_min_skill_level = data.target_min_skill_level
        campaign.save(update_fields=['target_min_skill_level'])
    if data.clear_target_location:
        campaign.target_location = None
        campaign.target_radius_km = 0
    else:
        if data.target_latitude is not None and data.target_longitude is not None:
            from django.contrib.gis.geos import Point
            campaign.target_location = Point(data.target_longitude, data.target_latitude, srid=4326)
        if data.target_radius_km is not None:
            campaign.target_radius_km = data.target_radius_km
    if data.include_self is not None:
        campaign.include_self = data.include_self
        if data.include_self:
            campaign.exclude_self = False  # Mutually exclusive
    if data.exclude_self is not None:
        campaign.exclude_self = data.exclude_self
        if data.exclude_self:
            campaign.include_self = False  # Mutually exclusive

    campaign.save()

    # Broadcast feed update to all connected users when campaign status changes
    if status_changed:
        _broadcast_ads_feed_updated()

    return _campaign_response(campaign)


@ads_router.delete("/campaigns/{campaign_id}/", auth=ProfileAuth())
@ratelimit(group='ads:delete_campaign', key=user_or_ip, rate='10/m', method='DELETE')
def delete_campaign(request, campaign_id: str):
    """Delete campaign (only if no views yet)."""
    profile = request.auth

    campaign = get_object_or_404(
        AdCampaign,
        id=campaign_id,
        advertiser=profile
    )

    # Only allow deletion if no views: AdView rows are the payout audit
    # trail. Viewed campaigns can only be archived (status='archived').
    if campaign.total_views > 0:
        raise HttpError(400, "Cannot delete campaign with existing views — archive it instead")

    campaign.delete()
    return {"success": True}


@ads_router.post("/campaigns/{campaign_id}/duplicate/", response={200: AdCampaignResponse, 404: dict}, auth=ProfileAuth())
@ratelimit(group='ads:duplicate_campaign', key=user_or_ip, rate='10/m', method='POST')
def duplicate_campaign(request, campaign_id: str):
    """Copy a campaign into a fresh draft: content, image, payment numbers and
    targeting carry over; stats start at zero. The copy has no views, so its
    reward/budget stay editable until it is served."""
    from django.core.files.base import ContentFile
    import os

    profile = request.auth

    src = get_object_or_404(AdCampaign, id=campaign_id, advertiser=profile)

    with transaction.atomic():
        copy = AdCampaign.objects.create(
            advertiser=profile,
            establishment=src.establishment,
            name=src.name,
            post_title=src.post_title,
            post_content=src.post_content,
            source_lang=src.source_lang,
            post_title_i18n=src.post_title_i18n,
            post_content_i18n=src.post_content_i18n,
            mt_cache=src.mt_cache,
            link=src.link,
            reward_sats=src.reward_sats,
            budget_sats=src.budget_sats,
            target_gender=src.target_gender,
            target_age_from=src.target_age_from,
            target_age_to=src.target_age_to,
            target_min_skill_level=src.target_min_skill_level,
            target_location=src.target_location,
            target_radius_km=src.target_radius_km,
            include_self=src.include_self,
            exclude_self=src.exclude_self,
            linked_item=src.linked_item,
            linked_establishment=src.linked_establishment,
            status='draft',
        )
        copy.target_interests.set(src.target_interests.all())
        copy.target_children_ages.set(src.target_children_ages.all())
        copy.target_skills.set(src.target_skills.all())
        if src.image:
            copy.image.save(
                os.path.basename(src.image.name),
                ContentFile(src.image.read()),
                save=True,
            )

    return _campaign_response(copy)


@ads_router.post("/campaigns/{campaign_id}/image/", auth=ProfileAuth())
@ratelimit(group='ads:upload_image', key=user_or_ip, rate='10/m', method='POST')
def upload_campaign_image(request, campaign_id: str, image: UploadedFile = File(...)):
    """Upload or replace campaign banner image."""
    from PIL import Image
    from io import BytesIO
    from django.core.files.base import ContentFile
    import os

    profile = request.auth

    campaign = get_object_or_404(AdCampaign, id=campaign_id, advertiser=profile)

    # Validate file
    if not image.content_type or not image.content_type.startswith('image/'):
        raise HttpError(400, "File must be an image")
    if image.size > 10 * 1024 * 1024:
        raise HttpError(400, "Image must be under 10MB")

    # Process with PIL
    img = Image.open(image)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')

    # Resize to max 1200x630 (16:9 banner), maintain aspect ratio
    max_w, max_h = 1200, 630
    if img.width > max_w or img.height > max_h:
        img.thumbnail((max_w, max_h), Image.LANCZOS)

    # Save to buffer
    buf = BytesIO()
    fmt = 'PNG' if img.mode == 'RGBA' else 'JPEG'
    ext = 'png' if fmt == 'PNG' else 'jpg'
    save_kwargs = {'optimize': True}
    if fmt == 'JPEG':
        save_kwargs['quality'] = 85
    img.save(buf, format=fmt, **save_kwargs)
    buf.seek(0)

    # Delete old image if exists
    if campaign.image:
        campaign.image.delete(save=False)

    campaign.image.save(f'{campaign.id}.{ext}', ContentFile(buf.read()), save=True)

    return {'success': True, 'image_url': campaign.image.url}


@ads_router.delete("/campaigns/{campaign_id}/image/", auth=ProfileAuth())
@ratelimit(group='ads:delete_image', key=user_or_ip, rate='10/m', method='DELETE')
def delete_campaign_image(request, campaign_id: str):
    """Delete campaign banner image."""
    profile = request.auth
    campaign = get_object_or_404(AdCampaign, id=campaign_id, advertiser=profile)

    if campaign.image:
        campaign.image.delete(save=True)

    return {'success': True}


def _broadcast_ads_feed_updated():
    """Broadcast ads feed update to all connected WS clients."""
    from parahub.services.ws_publish import ws_publish
    ws_publish('ads_feed', {'type': 'ads.feed_updated'})


# ============================================================================
# AD FEED ENDPOINTS
# ============================================================================

# Fresh Gemini calls allowed per feed request. A cold cache warms a few
# campaigns per request instead of stalling one viewer on the whole page;
# untranslated items just show the original until a later request fills them.
MT_PER_REQUEST_CAP = 3


def _resolve_ad_translation(campaign, translate_to, mt_budget):
    """Viewer-language text for one campaign, resolved per field:
    advertiser's authoritative *_i18n -> mt_cache -> fresh MT (budget
    permitting, cached on the row) -> None (viewer sees the original).

    Returns (translated_title, translated_content, is_translated); the flag
    marks machine translation only — an authoritative translation is the
    advertiser's own text and carries no badge. mt_budget is a single-element
    list shared across one request's items.
    """
    from parahub.services.translation import PROJECT_LANGS, TranslationService

    if not translate_to or translate_to not in PROJECT_LANGS \
            or translate_to == campaign.source_lang:
        return None, None, False

    title = campaign.post_title_i18n.get(translate_to)
    content = campaign.post_content_i18n.get(translate_to)
    mt_used = False

    if title is None or content is None:
        cached = campaign.mt_cache.get(translate_to) or {}
        if title is None and cached.get('post_title'):
            title = cached['post_title']
            mt_used = True
        if content is None and cached.get('post_content'):
            content = cached['post_content']
            mt_used = True

        if (title is None or content is None) and mt_budget[0] > 0:
            mt_budget[0] -= 1
            fresh_entry = dict(cached)
            if title is None:
                t = TranslationService.translate(
                    campaign.post_title, campaign.source_lang, translate_to,
                    context={'object_type': 'ad_campaign', 'object_id': campaign.id,
                             'field_name': 'post_title'})
                if t:
                    fresh_entry['post_title'] = title = t
                    mt_used = True
            if content is None:
                c = TranslationService.translate_html(
                    campaign.post_content, campaign.source_lang, translate_to,
                    sanitizer=sanitize_html,
                    context={'object_type': 'ad_campaign', 'object_id': campaign.id,
                             'field_name': 'post_content'})
                if c:
                    fresh_entry['post_content'] = content = c
                    mt_used = True
            if fresh_entry != cached:
                # Read-modify-write on a fresh row copy: a concurrent writer
                # for a sibling language can lose at worst its cache entry
                # (re-translated later), never authoritative data.
                row_cache = AdCampaign.objects.filter(pk=campaign.pk) \
                    .values_list('mt_cache', flat=True).first() or {}
                row_cache[translate_to] = {**(row_cache.get(translate_to) or {}), **fresh_entry}
                AdCampaign.objects.filter(pk=campaign.pk).update(mt_cache=row_cache)
                campaign.mt_cache = row_cache

    return title, content, mt_used


def _get_feed_queryset(request, profile):
    """Build the feed queryset for a profile. Reused by feed list and count."""
    # Every profile has an ads profile by default — created lazily here with
    # the widest targeting (gender=any, no age/interests/skills/locations), so
    # a newcomer with zero setup already sees every broadly-targeted ad.
    ads_profile, _ = AdsProfile.objects.get_or_create(profile=profile)

    # Views whose payout failed — or went stale because its worker died
    # mid-flight — do not count as viewed: the reward never arrived, so the ad
    # stays in the feed and can be claimed again. The claim path applies the
    # same staleness rule, so what the feed shows is claimable.
    stale_before = timezone.now() - PAYOUT_STALE_AFTER
    already_viewed_campaign_ids = AdView.objects.filter(
        user=profile
    ).exclude(
        Q(payment_status='failed')
        | Q(payment_status='pending', viewed_at__lt=stale_before)
    ).values_list('campaign_id', flat=True)

    base = Q(status='active')
    base &= ~Q(id__in=already_viewed_campaign_ids)
    # budget_sats is a ceiling: only show ads that can still fund one full
    # reward, so a claim on anything visible cannot push spending past it.
    base &= Q(spent_sats__lte=F('budget_sats') - F('reward_sats'))

    targeting = Q()
    if ads_profile.gender != 'any':
        targeting &= (Q(target_gender='any') | Q(target_gender=ads_profile.gender))
    # Compute age from birth_date on the fly
    if ads_profile.birth_date:
        from datetime import date
        today = date.today()
        age = today.year - ads_profile.birth_date.year - (
            (today.month, today.day) < (ads_profile.birth_date.month, ads_profile.birth_date.day)
        )
        targeting &= Q(target_age_from__lte=age) & Q(target_age_to__gte=age)

    # Interest targeting: show if campaign has no target interests OR user shares at least one
    user_interest_ids = list(ads_profile.interests.values_list('id', flat=True))
    targeting &= Q(target_interests__isnull=True) | Q(target_interests__in=user_interest_ids)

    # Children age targeting: show if campaign has no target OR user has matching age
    user_children_age_ids = list(ads_profile.children_ages.values_list('id', flat=True))
    targeting &= (
        Q(target_children_ages__isnull=True) |
        Q(target_children_ages__in=user_children_age_ids)
    )

    # Skills targeting: show if campaign has no target_skills OR
    # user has at least one targeted skill at >= target_min_skill_level
    user_skill_levels = {
        s.skill_id: s.level
        for s in AdsProfileSkill.objects.filter(profile=ads_profile)
    }
    if user_skill_levels:
        skill_targeted_qs = AdCampaign.objects.filter(
            target_skills__isnull=False
        ).prefetch_related('target_skills').distinct()
        skill_matching_ids = set()
        for camp in skill_targeted_qs:
            for skill in camp.target_skills.all():
                if user_skill_levels.get(skill.id, 0) >= camp.target_min_skill_level:
                    skill_matching_ids.add(camp.id)
                    break
        targeting &= Q(target_skills__isnull=True) | Q(id__in=skill_matching_ids)
    else:
        targeting &= Q(target_skills__isnull=True)

    # Geo targeting: campaigns with no target_location pass through;
    # geo-targeted campaigns shown only if user has a location within radius
    user_locations = list(AdsProfileLocation.objects.filter(profile=ads_profile))
    if user_locations:
        from django.contrib.gis.db.models.functions import Distance
        geo_campaign_ids = set()
        geo_qs = AdCampaign.objects.filter(target_location__isnull=False, target_radius_km__gt=0)
        for loc in user_locations:
            nearby_ids = geo_qs.annotate(
                _dist=Distance('target_location', loc.location)
            ).filter(
                _dist__lte=F('target_radius_km') * 1000  # km → meters
            ).values_list('id', flat=True)
            geo_campaign_ids.update(nearby_ids)
        targeting &= Q(target_location__isnull=True) | Q(target_radius_km=0) | Q(id__in=geo_campaign_ids)
    else:
        # No locations set → hide geo-targeted campaigns
        targeting &= Q(target_location__isnull=True) | Q(target_radius_km=0)

    own_included = base & Q(advertiser=profile, include_self=True)
    others = base & targeting & ~Q(advertiser=profile, exclude_self=True)

    qs = AdCampaign.objects.filter(own_included | others).distinct().order_by('-created_at')
    # Hide test/bot-authored campaigns unless the viewer is exempt
    # (platform synthetic-content policy, identity.visibility). The feed is
    # the only discovery surface for claims, so filtering here keeps
    # synthetic ads out of real users' feeds and badges alike.
    return exclude_test_authors(qs, request, field='advertiser')


@ads_router.get("/feed/count/", auth=ProfileAuth())
@ratelimit(group='ads:feed_count', key=user_or_ip, rate='60/m')
def get_ad_feed_count(request):
    """Get count of available ads for badge display.

    The badge counts claimable rewards, so campaigns from the viewer's own
    account are excluded: they appear in the feed as previews only.
    """
    profile = request.auth_profile
    agg = _get_feed_queryset(request, profile).exclude(
        advertiser__account_id=profile.account_id
    ).aggregate(count=Count('id'), total_reward_sats=Sum('reward_sats'))
    return {
        "count": agg['count'] or 0,
        "total_reward_sats": agg['total_reward_sats'] or 0,
    }


@ads_router.get("/feed/", response=List[AdFeedItem], auth=ProfileAuth())
@ratelimit(group='ads:feed', key=user_or_ip, rate='60/m')
@paginate(PageNumberPagination)
def get_ad_feed(request, translate_to: Optional[str] = None):
    """Get targeted ads for current user, optionally in the viewer's language."""
    profile = request.auth
    campaigns = _get_feed_queryset(request, profile).select_related(
        'advertiser', 'establishment', 'linked_item', 'linked_establishment',
        'linked_establishment__category',
    )

    mt_budget = [MT_PER_REQUEST_CAP]
    results = []
    for campaign in campaigns:
        advertiser = campaign.advertiser
        tr_title, tr_content, is_translated = _resolve_ad_translation(
            campaign, translate_to, mt_budget)
        results.append({
            'id': campaign.id,
            'object_type': 'ad_feed_item',
            'campaign_id': campaign.id,
            'post_title': campaign.post_title,
            'post_content': campaign.post_content,
            'source_lang': campaign.source_lang,
            'translated_post_title': tr_title,
            'translated_post_content': tr_content,
            'is_translated': is_translated,
            'link': campaign.link,
            'image_url': campaign.image.url if campaign.image else None,
            'reward_sats': campaign.reward_sats,
            'is_own': bool(advertiser and advertiser.account_id == profile.account_id),
            'advertiser_id': advertiser.id if advertiser else None,
            'advertiser_name': advertiser.local_name if advertiser else None,
            'advertiser_hna': advertiser.hna if advertiser else None,
            'linked_item': _linked_item_data(campaign.linked_item),
            'linked_establishment': _linked_establishment_data(campaign.linked_establishment),
            'establishment_name': campaign.establishment.name if campaign.establishment else None,
            'establishment_logo_url': campaign.establishment.logo_url if campaign.establishment else None,
        })

    return results


@ads_router.get("/feed/history/", response=List[AdFeedHistoryItem], auth=ProfileAuth())
@ratelimit(group='ads:feed_history', key=user_or_ip, rate='60/m')
@paginate(PageNumberPagination)
def get_ad_feed_history(request, q: Optional[str] = None, translate_to: Optional[str] = None):
    """Get user's ad view history with optional search."""
    profile = request.auth

    views = AdView.objects.filter(
        user=profile
    ).select_related('campaign').order_by('-viewed_at')

    if q:
        views = views.filter(
            Q(campaign__post_title__icontains=q) | Q(campaign__post_content__icontains=q)
        )

    # History is bulk and already-seen: serve authoritative/cached translations
    # (usually warm from the feed) but never spend fresh MT calls on it.
    no_mt_budget = [0]
    results = []
    for view in views:
        campaign = view.campaign
        tr_title, tr_content, is_translated = _resolve_ad_translation(
            campaign, translate_to, no_mt_budget)
        results.append({
            'id': view.id,
            'object_type': 'ad_feed_history_item',
            'campaign_id': campaign.id,
            'post_title': campaign.post_title,
            'post_content': campaign.post_content,
            'source_lang': campaign.source_lang,
            'translated_post_title': tr_title,
            'translated_post_content': tr_content,
            'is_translated': is_translated,
            'link': campaign.link,
            'image_url': campaign.image.url if campaign.image else None,
            'reward_sats': campaign.reward_sats,
            'earned_sats': view.payment_amount_sats if view.payment_sent else 0,
            'payment_sent': view.payment_sent,
            'payment_status': view.payment_status,
            'viewed_at': view.viewed_at,
        })

    return results


@ads_router.post("/feed/{campaign_id}/view/", auth=ProfileAuth())
@ratelimit(group='ads:record_view', key=user_or_ip, rate='30/m', method='POST')
def record_ad_view(request, campaign_id: str):
    """Record ad view and initiate LNURL payment to viewer's Lightning address."""
    profile = request.auth

    # Rate limit: max 20 ad views per hour
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_views = AdView.objects.filter(user=profile, viewed_at__gte=one_hour_ago).count()
    if recent_views >= 20:
        raise HttpError(429, "Rate limit: max 20 ad views per hour")

    campaign = get_object_or_404(AdCampaign, id=campaign_id, status='active')

    # An advertiser can never claim their own reward. Account-scoped, not
    # profile-scoped: pseudonyms share the account's Spark wallet, so on the
    # browser-paid rail the "payout" would be a wallet paying itself (the
    # Spark SDK refuses self-transfers), and on any external rail it would
    # only inflate spent/earned stats without a real transfer. The feed
    # still shows own campaigns — as previews (is_own).
    if campaign.advertiser and campaign.advertiser.account_id == profile.account_id:
        raise HttpError(409, "This is your own campaign — rewards cannot be claimed from the advertiser's account")

    # Browser-paid rail: a 'spark' advertiser wallet lives in their own
    # browser, so the server never attempts the payment itself — the claim
    # becomes a queued payout instruction the advertiser's next open tab
    # picks up (or their current one, within seconds, via the WS push).
    advertiser_ads_profile = AdsProfile.objects.filter(profile=campaign.advertiser).first()
    browser_paid = _wallet_provider(advertiser_ads_profile) == 'spark'
    claim_status = 'queued' if browser_paid else 'pending'

    # Claiming the view and marking the payout in-flight happens under a row
    # lock: two tabs claiming the same ad at once must not both pay out. The
    # campaign row is locked first (same order for every claimer), so the
    # budget check can count in-flight payouts without racing them.
    with transaction.atomic():
        campaign = AdCampaign.objects.select_for_update().get(pk=campaign.pk)

        existing_view = AdView.objects.select_for_update().filter(
            campaign=campaign, user=profile
        ).first()

        # A view whose payout failed stays claimable: the reward was never paid,
        # so the ad goes back to the feed instead of being lost in history. Only
        # a paid view (or one whose payout is still in flight) blocks a claim.
        if existing_view and existing_view.payment_status == 'sent':
            raise HttpError(409, "Ad already viewed")
        if existing_view and existing_view.payment_status == 'queued':
            raise HttpError(409, "Reward already queued for payout")
        if (
            existing_view
            and existing_view.payment_status == 'pending'
            and existing_view.viewed_at > timezone.now() - PAYOUT_STALE_AFTER
        ):
            raise HttpError(409, "Payout already in progress")

        # budget_sats is a ceiling on the advertiser's wallet, but spent_sats
        # only moves when a payout succeeds — so the payouts currently in
        # flight (and the ones queued for the advertiser's browser) are
        # reserved against the budget here. Without this, N claimers of the
        # last reward would all pass and the wallet would pay past the budget.
        reserved_sats = AdView.objects.filter(
            campaign=campaign, payment_status__in=('pending', 'queued')
        ).exclude(user=profile).aggregate(
            total=Sum('payment_amount_sats')
        )['total'] or 0
        if campaign.spent_sats + reserved_sats + campaign.reward_sats > campaign.budget_sats:
            raise HttpError(409, "Campaign budget exhausted")

        if existing_view:
            # Retry of a failed payout — reuse the row, don't count the
            # impression twice. The previous attempt's error and invoice
            # belong to that attempt, not this one.
            ad_view = existing_view
            ad_view.viewed_at = timezone.now()
            ad_view.payment_status = claim_status
            ad_view.payment_amount_sats = campaign.reward_sats
            ad_view.payment_error = ''
            ad_view.payment_invoice = ''
            ad_view.payment_proof = ''
            ad_view.save(update_fields=[
                'viewed_at', 'payment_status', 'payment_amount_sats',
                'payment_error', 'payment_invoice', 'payment_proof',
            ])
        else:
            try:
                ad_view = AdView.objects.create(
                    campaign=campaign,
                    user=profile,
                    viewed_at=timezone.now(),
                    clicked=False,
                    payment_sent=False,
                    payment_status=claim_status,
                    payment_amount_sats=campaign.reward_sats,
                )
            except IntegrityError:
                # Lost the race against a parallel first claim — that request
                # owns the payout.
                raise HttpError(409, "Payout already in progress")
            # Impression counters: one per view, regardless of payout outcome.
            AdCampaign.objects.filter(pk=campaign.pk).update(total_views=F('total_views') + 1)
            AdsProfile.objects.get_or_create(profile=profile)
            AdsProfile.objects.filter(profile=profile).update(total_views=F('total_views') + 1)

    if browser_paid and (profile.spark_address or profile.ln_address):
        _dispatch_queued_payout(request, campaign, ad_view, profile)
        return {
            "success": True,
            "view_id": ad_view.id,
            "earned_sats": ad_view.payment_amount_sats,
            "payment_sent": False,
            "payment_error": None,
            # The reward is on its way, just not in this HTTP response: the
            # advertiser's own wallet pays it (in seconds if they're online).
            "queued": True,
            "retryable": False,
        }

    # Payment runs outside the transaction: it is a chain of external HTTP
    # calls and must not hold a DB connection open for its whole duration.
    payment_invoice = None
    payment_error = None
    payment_stage = None
    wallet_answered = False  # Only a wallet that talked back is worth probing

    if not profile.ln_address:
        payment_error = "No Lightning address configured on your profile"
    else:
        try:
            advertiser_ads_profile = AdsProfile.objects.filter(
                profile=campaign.advertiser
            ).first()

            if not advertiser_ads_profile or not advertiser_ads_profile.ln_wallet_config:
                payment_error = "Advertiser has no wallet configured for payments"
                payment_stage = 'pay'
                wallet_answered = True  # Nothing to reach: balance is known to be unusable
                logger.warning(f"No wallet config for advertiser {campaign.advertiser_id}")
            else:
                advertiser_wallet_config = decrypt_wallet_config(
                    advertiser_ads_profile.ln_wallet_config
                )

                payment_result = send_payment_via_lnurl(
                    ln_address=profile.ln_address,
                    amount_sats=campaign.reward_sats,
                    wallet_config=advertiser_wallet_config,
                    comment=f"Para-ads view reward: {campaign.name}"
                )

                if payment_result.get('success'):
                    payment_invoice = payment_result.get('invoice')
                else:
                    payment_error = payment_result.get('error', 'Payment failed')
                    payment_stage = payment_result.get('stage')
                    wallet_answered = bool(payment_result.get('rejected'))
                    logger.warning(f"Payment failed: {payment_error}")

        except Exception as e:
            payment_error = str(e)
            payment_stage = 'pay'
            logger.error(f"LNURL payment exception: {e}")

    # Spent/earned totals only move when the sats actually left the advertiser's
    # wallet — a failed payout must never show up as budget spent or as earnings.
    with transaction.atomic():
        ad_view.payment_attempts = F('payment_attempts') + 1
        if payment_error is None:
            ad_view.payment_sent = True
            ad_view.payment_status = 'sent'
            ad_view.payment_invoice = payment_invoice or ''
            ad_view.payment_error = ''
            ad_view.payment_sent_at = timezone.now()
            AdCampaign.objects.filter(pk=campaign.pk).update(
                spent_sats=F('spent_sats') + ad_view.payment_amount_sats
            )
            AdsProfile.objects.filter(profile=profile).update(
                total_earned_sats=F('total_earned_sats') + ad_view.payment_amount_sats
            )
            logger.info(f"Payment sent: {ad_view.payment_amount_sats} sats to {profile.ln_address}")
        else:
            ad_view.payment_status = 'failed'
            ad_view.payment_error = payment_error[:500]
        ad_view.save(update_fields=[
            'payment_sent', 'payment_status', 'payment_invoice',
            'payment_error', 'payment_sent_at', 'payment_attempts',
        ])
        ad_view.refresh_from_db(fields=['payment_attempts'])

    # The claim toast is ephemeral (~1.5s). If the payout did not actually
    # reach the viewer, drop a persistent in-app notification so a silent
    # failure (no/invalid Lightning address, advertiser wallet down, LNURL
    # error) doesn't leave them believing they were paid.
    if payment_error is not None:
        # The ad is claimable again, so the feed badge has to come back.
        _broadcast_ads_feed_updated()
        try:
            from notifications.services import notify_ad_payment_issue
            notify_ad_payment_issue(
                profile.account,
                campaign=campaign,
                amount_sats=ad_view.payment_amount_sats,
                error=payment_error,
                fault='payer' if payment_stage == 'pay' else 'viewer',
            )
        except Exception:
            logger.exception("notify_ad_payment_issue failed")

        if payment_stage == 'pay' and wallet_answered:
            _warn_advertiser_if_unfunded(campaign)

    return {
        "success": True,
        "view_id": ad_view.id,
        "earned_sats": ad_view.payment_amount_sats,
        "payment_sent": ad_view.payment_sent,
        "payment_error": payment_error,
        # Nothing was charged and nothing was paid — the viewer can claim again.
        "retryable": payment_error is not None,
    }


def _warn_advertiser_if_unfunded(campaign):
    """Tell the advertiser when their wallet can no longer cover the reward.

    A campaign carries a `budget_sats` number that lives only in our DB; the
    sats live in the advertiser's own wallet. When those two disagree the
    campaign keeps being served while every payout fails, so the advertiser is
    the only one who can fix it — and they need to hear about it.
    """
    try:
        advertiser_ads_profile = AdsProfile.objects.filter(profile=campaign.advertiser).first()
        if not advertiser_ads_profile or not advertiser_ads_profile.ln_wallet_config:
            balance_sats = 0
        else:
            wallet_config = decrypt_wallet_config(advertiser_ads_profile.ln_wallet_config)
            balance_sats = create_wallet_client(wallet_config).test_connection().get('balance_sats', 0)

        if balance_sats >= campaign.reward_sats:
            return  # Payout failed for some other reason — not a funding problem

        # One warning per campaign per day: every viewer who claims hits the
        # same empty wallet, and a flooded bell gets ignored.
        from notifications.models import Notification
        already_warned = Notification.objects.filter(
            recipient=campaign.advertiser.account,
            type='ad_campaign_unfunded',
            data__campaign_id=campaign.id,
            created_at__gte=timezone.now() - timedelta(days=1),
        ).exists()
        if already_warned:
            return

        from notifications.services import notify_ad_campaign_unfunded
        notify_ad_campaign_unfunded(
            campaign.advertiser.account,
            campaign=campaign,
            balance_sats=balance_sats,
        )
    except Exception:
        logger.exception("Unfunded-campaign check failed for campaign %s", campaign.id)


def _dispatch_queued_payout(request, campaign, ad_view, viewer_profile):
    """Fan out a freshly queued browser-paid payout.

    Three signals: a WS nudge to the advertiser's open tabs (pays within
    seconds when online), a persistent "queued" notification to the viewer
    (a silent wait would read as an unpaid claim), and — only when no tab of
    the advertiser's account is online to pay right now — a push telling the
    advertiser that payouts are waiting, deduped to one per day.
    """
    from parahub.services.ws_publish import ws_publish

    ws_publish(f'user:{campaign.advertiser.account_id}', {
        'type': 'ads.payout_requested',
        'view_id': ad_view.id,
        'campaign_id': campaign.id,
        'amount_sats': ad_view.payment_amount_sats,
    })

    try:
        from notifications.services import notify_ad_payment_queued
        notify_ad_payment_queued(
            viewer_profile.account,
            campaign=campaign,
            amount_sats=ad_view.payment_amount_sats,
        )
    except Exception:
        logger.exception("notify_ad_payment_queued failed")

    try:
        _notify_advertiser_payouts_waiting(request, campaign)
    except Exception:
        logger.exception("Advertiser payouts-waiting notification failed")


def _notify_advertiser_payouts_waiting(request, campaign):
    """Push "N payouts are waiting" to an advertiser with no open tab.

    An online advertiser is skipped: one of their tabs received the WS event
    and is about to pay automatically — pushing "come pay" at that moment
    would only teach them to ignore the push.
    """
    from parahub.consumers.deploy_slot import get_deploy_slot_from_request
    from parahub.services.presence import PresenceService

    account = campaign.advertiser.account
    profile_ids = list(Profile.objects.filter(account=account).values_list('id', flat=True))
    if PresenceService.is_any_online(get_deploy_slot_from_request(request), profile_ids):
        return

    # One nudge per day: every queued claim while they're away hits the same
    # closed browser, and a flooded push channel gets muted.
    from notifications.models import Notification
    already_nudged = Notification.objects.filter(
        recipient=account,
        type='ad_payouts_waiting',
        created_at__gte=timezone.now() - timedelta(days=1),
    ).exists()
    if already_nudged:
        return

    waiting = AdView.objects.filter(
        campaign__advertiser__account=account, payment_status='queued',
    ).aggregate(count=Count('id'), total=Sum('payment_amount_sats'))

    from notifications.services import notify_ad_payouts_waiting
    notify_ad_payouts_waiting(
        account,
        count=waiting['count'] or 0,
        total_sats=waiting['total'] or 0,
    )


# ============================================================================
# BROWSER-PAID PAYOUT QUEUE (advertiser's payer agent)
# ============================================================================
# The advertiser's wallet is their in-browser Parahub Spark wallet, so the
# server can only hold *instructions*: which viewer is owed how much. The
# browser leases an instruction, pays it from the advertiser's own wallet,
# and reports the outcome with proof. Queue scope is the whole account, not
# the active profile — the seed (and thus the paying wallet) is per account,
# so a pseudonym's campaigns are payable from any of the account's profiles.

def _payout_queue_qs(profile):
    return AdView.objects.filter(
        campaign__advertiser__account=profile.account,
        payment_status='queued',
    )


@ads_router.get("/payouts/queue/", auth=ProfileAuth())
@ratelimit(group='ads:payout_queue', key=user_or_ip, rate='60/m')
def get_payout_queue(request):
    """Queued payouts awaiting this account's browser wallet.

    Viewer identity is deliberately absent — the payer needs a payment
    address and an amount, not who watched their ad.
    """
    profile = request.auth
    qs = _payout_queue_qs(profile)
    views = qs.select_related('campaign', 'user').order_by('viewed_at')[:50]
    items = [
        {
            'view_id': v.id,
            'amount_sats': v.payment_amount_sats,
            'queued_at': v.viewed_at.isoformat(),
            'attempts': v.payment_attempts,
            'viewer_spark_address': v.user.spark_address or None,
            'viewer_ln_address': v.user.ln_address or None,
            'campaign': {
                'id': v.campaign.id,
                'name': v.campaign.name,
                'reward_sats': v.campaign.reward_sats,
                'budget_sats': v.campaign.budget_sats,
                'spent_sats': v.campaign.spent_sats,
                'status': v.campaign.status,
            },
        }
        for v in views
    ]
    return {'items': items, 'count': qs.count()}


@ads_router.post("/payouts/{view_id}/lease/", auth=ProfileAuth())
@ratelimit(group='ads:payout_lease', key=user_or_ip, rate='120/m', method='POST')
def lease_payout(request, view_id: str):
    """Claim one queued payout for this device.

    The WS event lands on every open tab of every device; the Redis lease
    (atomic add) makes sure only one of them pays. A crashed payer's lease
    simply expires and the payout returns to the pool.
    """
    profile = request.auth
    get_object_or_404(_payout_queue_qs(profile), id=view_id)
    if not cache.add(_payout_lease_key(view_id), str(profile.id), timeout=PAYOUT_LEASE_TTL):
        raise HttpError(409, "Payout is being processed by another device")
    return {'leased': True, 'ttl': PAYOUT_LEASE_TTL}


@ads_router.post("/payouts/{view_id}/resolve/", auth=ProfileAuth())
@ratelimit(group='ads:payout_resolve', key=user_or_ip, rate='30/m', method='POST')
def resolve_payout_invoice(request, view_id: str):
    """LNURL-resolve the viewer's Lightning address into a BOLT11 invoice.

    Browsers cannot run LNURL themselves (CORS), so the server resolves the
    *instruction* — it never touches the payment. The invoice is stored on
    the view row so the preimage the payer later reports can be verified
    against its payment hash, and cached briefly so an interrupted payer
    retries the same invoice instead of minting a new one.
    """
    profile = request.auth
    ad_view = get_object_or_404(
        _payout_queue_qs(profile).select_related('campaign', 'user'), id=view_id
    )
    viewer = ad_view.user
    if not viewer.ln_address:
        raise HttpError(400, "Viewer has no Lightning address")

    invoice = cache.get(_payout_invoice_key(view_id))
    if not invoice:
        try:
            invoice = resolve_lnurl_invoice(
                viewer.ln_address,
                ad_view.payment_amount_sats,
                comment=f"Para-ads view reward: {ad_view.campaign.name}",
            )
        except Exception as e:
            raise HttpError(502, f"Could not resolve viewer's Lightning address: {e}")
        cache.set(_payout_invoice_key(view_id), invoice, timeout=PAYOUT_INVOICE_TTL)
        AdView.objects.filter(pk=ad_view.pk).update(payment_invoice=invoice)
    return {'invoice': invoice, 'amount_sats': ad_view.payment_amount_sats}


@ads_router.post("/payouts/{view_id}/complete/", auth=ProfileAuth())
@ratelimit(group='ads:payout_complete', key=user_or_ip, rate='120/m', method='POST')
def complete_payout(request, view_id: str, data: AdPayoutReport):
    """The advertiser's browser reports how one payout went.

    'sent' moves spent/earned totals, so it demands proof: for an LNURL
    payment the preimage must hash to the resolved invoice's payment hash —
    the one thing only a wallet that actually paid can know. Spark-address
    transfers carry no preimage; the SDK payment id is recorded instead
    (see PK/ads-system.md on that trust gap). Idempotent for repeated
    'sent' reports — totals move exactly once.
    """
    profile = request.auth

    with transaction.atomic():
        ad_view = get_object_or_404(
            AdView.objects.select_for_update().select_related('campaign', 'user'),
            id=view_id,
            campaign__advertiser__account=profile.account,
        )

        if ad_view.payment_status == 'sent':
            return {'status': 'sent', 'already_reported': True}

        if data.result == 'sent':
            if data.method == 'lnurl':
                expected_hash = bolt11_payment_hash(ad_view.payment_invoice or '')
                if not expected_hash:
                    raise HttpError(400, "No resolved invoice on record for this payout")
                try:
                    preimage = bytes.fromhex((data.proof or '').strip())
                except ValueError:
                    raise HttpError(400, "Preimage must be hex")
                if hashlib.sha256(preimage).hexdigest() != expected_hash:
                    raise HttpError(400, "Preimage does not match the invoice payment hash")
                proof = preimage.hex()
            else:
                proof = (data.proof or '').strip()
                if not proof:
                    raise HttpError(400, "Spark payment id required as proof")

            ad_view.payment_sent = True
            ad_view.payment_status = 'sent'
            ad_view.payment_proof = proof[:200]
            ad_view.payment_error = ''
            ad_view.payment_sent_at = timezone.now()
            ad_view.payment_attempts = F('payment_attempts') + 1
            ad_view.save(update_fields=[
                'payment_sent', 'payment_status', 'payment_proof',
                'payment_error', 'payment_sent_at', 'payment_attempts',
            ])
            AdCampaign.objects.filter(pk=ad_view.campaign_id).update(
                spent_sats=F('spent_sats') + ad_view.payment_amount_sats
            )
            AdsProfile.objects.get_or_create(profile=ad_view.user)
            AdsProfile.objects.filter(profile=ad_view.user).update(
                total_earned_sats=F('total_earned_sats') + ad_view.payment_amount_sats
            )
        else:
            ad_view.payment_sent = False
            ad_view.payment_status = 'failed'
            ad_view.payment_error = (data.error or 'Advertiser wallet could not pay')[:500]
            ad_view.payment_attempts = F('payment_attempts') + 1
            ad_view.save(update_fields=[
                'payment_sent', 'payment_status', 'payment_error', 'payment_attempts',
            ])

    cache.delete(_payout_lease_key(view_id))
    cache.delete(_payout_invoice_key(view_id))

    from parahub.services.ws_publish import ws_publish
    if data.result == 'sent':
        # The viewer may still be sitting on the claim screen — flip their
        # "queued" into "paid" live.
        ws_publish(f'user:{ad_view.user.account_id}', {
            'type': 'ads.payout_sent',
            'view_id': ad_view.id,
            'campaign_id': ad_view.campaign_id,
            'amount_sats': ad_view.payment_amount_sats,
        })
        logger.info(
            f"Browser payout sent: {ad_view.payment_amount_sats} sats, view {ad_view.id}"
        )
        return {'status': 'sent'}

    # Nothing was paid: the ad returns to the feed and the viewer learns why.
    _broadcast_ads_feed_updated()
    try:
        from notifications.services import notify_ad_payment_issue
        notify_ad_payment_issue(
            ad_view.user.account,
            campaign=ad_view.campaign,
            amount_sats=ad_view.payment_amount_sats,
            error=ad_view.payment_error,
            fault='payer' if data.stage == 'pay' else 'viewer',
        )
    except Exception:
        logger.exception("notify_ad_payment_issue failed")
    return {'status': 'failed'}


@ads_router.post("/feed/{campaign_id}/click/", auth=ProfileAuth())
@ratelimit(group='ads:record_click', key=user_or_ip, rate='30/m', method='POST')
def record_ad_click(request, campaign_id: str):
    """Record click on ad link."""
    profile = request.auth

    try:
        ad_view = AdView.objects.get(campaign_id=campaign_id, user=profile)

        if not ad_view.clicked:
            with transaction.atomic():
                ad_view.clicked = True
                ad_view.clicked_at = timezone.now()
                ad_view.save()

                # Update campaign stats
                campaign = ad_view.campaign
                campaign.total_clicks += 1
                campaign.save()

        return {"success": True}
    except AdView.DoesNotExist:
        raise ValueError("Ad not viewed yet")
