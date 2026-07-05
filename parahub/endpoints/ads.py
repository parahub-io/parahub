"""
Advertising System API endpoints for Parahub (Para-ads)
Implements pay-per-view advertising with Lightning Network payments
"""

from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q, Avg, F, Count, Func
from django.utils import timezone
from datetime import timedelta
from typing import List, Optional
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
)
from ads.crypto_utils import encrypt_wallet_config, decrypt_wallet_config
from ads.ln_wallet_service import send_payment_via_lnurl, create_wallet_client
from identity.models import Profile

# HTML sanitization: allowed tags for rich text content
ALLOWED_TAGS = {'b', 'i', 'strong', 'em', 's', 'a', 'ul', 'ol', 'li', 'p', 'br', 'blockquote'}
ALLOWED_ATTRIBUTES = {'a': {'href', 'target'}}


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
        # Encrypt sensitive fields (API keys/tokens) before storing
        encrypted_config = encrypt_wallet_config(data.ln_wallet_config)
        ads_profile.ln_wallet_config = encrypted_config

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

    # Activate immediately if advertiser has wallet configured
    ads_profile = AdsProfile.objects.filter(profile=profile).first()
    has_wallet = bool(ads_profile and ads_profile.ln_wallet_config)
    initial_status = 'active' if has_wallet else 'draft'

    with transaction.atomic():
        campaign = AdCampaign.objects.create(
            advertiser=profile,
            establishment=establishment,
            name=data.name,
            post_title=data.post_title,
            post_content=clean_content,
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

    # Update only provided fields
    if data.name is not None:
        campaign.name = data.name
    if data.post_title is not None:
        campaign.post_title = data.post_title
    if data.post_content is not None:
        campaign.post_content = sanitize_html(data.post_content)
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
            advertiser_ads_profile = AdsProfile.objects.filter(profile=profile).first()
            if not advertiser_ads_profile or not advertiser_ads_profile.ln_wallet_config:
                raise HttpError(400, "Configure wallet before activating campaign")
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
    if data.target_interest_ids is not None:
        campaign.target_interests.set(data.target_interest_ids)
    if data.target_children_age_ids is not None:
        campaign.target_children_ages.set(data.target_children_age_ids)
    if data.target_skill_ids is not None:
        campaign.target_skills.set(data.target_skill_ids)
    if data.target_min_skill_level is not None:
        campaign.target_min_skill_level = data.target_min_skill_level
        campaign.save(update_fields=['target_min_skill_level'])
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

    # Only allow deletion if no views
    if campaign.total_views > 0:
        raise ValueError("Cannot delete campaign with existing views")

    campaign.delete()
    return {"success": True}


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

def _get_feed_queryset(profile):
    """Build the feed queryset for a profile. Reused by feed list and count."""
    try:
        ads_profile = AdsProfile.objects.get(profile=profile)
    except AdsProfile.DoesNotExist:
        return AdCampaign.objects.none()

    already_viewed_campaign_ids = AdView.objects.filter(
        user=profile
    ).values_list('campaign_id', flat=True)

    base = Q(status='active')
    base &= ~Q(id__in=already_viewed_campaign_ids)
    base &= Q(spent_sats__lt=F('budget_sats'))

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

    return AdCampaign.objects.filter(own_included | others).distinct().order_by('-created_at')


@ads_router.get("/feed/count/", auth=ProfileAuth())
@ratelimit(group='ads:feed_count', key=user_or_ip, rate='60/m')
def get_ad_feed_count(request):
    """Get count of available ads for badge display."""
    return {"count": _get_feed_queryset(request.auth_profile).count()}


@ads_router.get("/feed/", response=List[AdFeedItem], auth=ProfileAuth())
@ratelimit(group='ads:feed', key=user_or_ip, rate='60/m')
@paginate(PageNumberPagination)
def get_ad_feed(request):
    """Get targeted ads for current user."""
    profile = request.auth
    campaigns = _get_feed_queryset(profile).select_related(
        'advertiser', 'establishment', 'linked_item', 'linked_establishment',
        'linked_establishment__category',
    )

    results = []
    for campaign in campaigns:
        advertiser = campaign.advertiser
        results.append({
            'id': campaign.id,
            'object_type': 'ad_feed_item',
            'campaign_id': campaign.id,
            'post_title': campaign.post_title,
            'post_content': campaign.post_content,
            'link': campaign.link,
            'image_url': campaign.image.url if campaign.image else None,
            'reward_sats': campaign.reward_sats,
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
def get_ad_feed_history(request, q: Optional[str] = None):
    """Get user's ad view history with optional search."""
    profile = request.auth

    views = AdView.objects.filter(
        user=profile
    ).select_related('campaign').order_by('-viewed_at')

    if q:
        views = views.filter(
            Q(campaign__post_title__icontains=q) | Q(campaign__post_content__icontains=q)
        )

    results = []
    for view in views:
        campaign = view.campaign
        results.append({
            'id': view.id,
            'object_type': 'ad_feed_history_item',
            'campaign_id': campaign.id,
            'post_title': campaign.post_title,
            'post_content': campaign.post_content,
            'link': campaign.link,
            'image_url': campaign.image.url if campaign.image else None,
            'reward_sats': campaign.reward_sats,
            'earned_sats': view.payment_amount_sats or 0,
            'payment_sent': view.payment_sent,
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

    # Check if already viewed
    if AdView.objects.filter(campaign=campaign, user=profile).exists():
        raise ValueError("Ad already viewed")

    # Check budget
    if campaign.is_budget_exhausted:
        raise ValueError("Campaign budget exhausted")

    with transaction.atomic():
        # Create view record
        ad_view = AdView.objects.create(
            campaign=campaign,
            user=profile,
            viewed_at=timezone.now(),
            clicked=False,
            payment_sent=False,
            payment_amount_sats=campaign.reward_sats,
        )

        # Update campaign stats
        campaign.total_views += 1
        campaign.spent_sats += (campaign.reward_sats)
        campaign.save()

        # Update user stats
        viewer_ads_profile, created = AdsProfile.objects.get_or_create(profile=profile)
        viewer_ads_profile.total_views += 1
        viewer_ads_profile.total_earned_sats += (campaign.reward_sats)
        viewer_ads_profile.save()

        # Initiate LNURL payment if viewer has Lightning address configured
        payment_invoice = None
        payment_error = None

        if profile.ln_address:
            try:
                # Get advertiser's wallet config for paying
                advertiser_ads_profile = AdsProfile.objects.filter(
                    profile=campaign.advertiser
                ).first()

                if not advertiser_ads_profile or not advertiser_ads_profile.ln_wallet_config:
                    payment_error = "Advertiser has no wallet configured for payments"
                    logger.warning(f"No wallet config for advertiser {campaign.advertiser_id}")
                else:
                    # Decrypt advertiser's wallet credentials
                    advertiser_wallet_config = decrypt_wallet_config(
                        advertiser_ads_profile.ln_wallet_config
                    )

                    # Send payment via LNURL-pay protocol
                    payment_result = send_payment_via_lnurl(
                        ln_address=profile.ln_address,
                        amount_sats=campaign.reward_sats,
                        wallet_config=advertiser_wallet_config,
                        comment=f"Para-ads view reward: {campaign.name}"
                    )

                    if payment_result.get('success'):
                        payment_invoice = payment_result.get('invoice')
                        ad_view.payment_sent = True
                        ad_view.payment_invoice = payment_invoice
                        ad_view.payment_sent_at = timezone.now()
                        ad_view.save()
                        logger.info(f"Payment sent: {ad_view.payment_amount_sats} sats to {profile.ln_address}")
                    else:
                        payment_error = payment_result.get('error', 'Payment failed')
                        logger.warning(f"Payment failed: {payment_error}")

            except Exception as e:
                payment_error = str(e)
                logger.error(f"LNURL payment exception: {e}")

    # The claim toast is ephemeral (~1.5s). If the payout did not actually
    # reach the viewer, drop a persistent in-app notification so a silent
    # failure (no/invalid Lightning address, advertiser wallet down, LNURL
    # error) doesn't leave them believing they were paid.
    if not ad_view.payment_sent:
        try:
            from notifications.services import notify_ad_payment_issue
            notify_ad_payment_issue(
                profile.account,
                campaign=campaign,
                amount_sats=ad_view.payment_amount_sats,
                error=payment_error,
            )
        except Exception:
            logger.exception("notify_ad_payment_issue failed")

    return {
        "success": True,
        "view_id": ad_view.id,
        "earned_sats": ad_view.payment_amount_sats,
        "payment_sent": ad_view.payment_sent,
        "payment_error": payment_error,
    }


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
