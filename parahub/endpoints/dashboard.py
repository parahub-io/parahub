"""
Dashboard API endpoints for Parahub
Provides aggregated stats and activity data for authenticated users
"""

from ninja import Router
from django.db.models import Count, Q
from django.utils import timezone
from typing import Dict, List, Optional
from pydantic import BaseModel

from django.apps import apps as django_apps
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile, Verification, Partner
from identity.visibility import exclude_test_authors
from contracts.models import Contract
from geo.models import Establishment, EstablishmentMembership, Event
from governance.models import Poll
from market.models import Item
from core.models import ObjectPhoto
from ads.models import AdCampaign

# Custom apps that count as "subsystems"
SUBSYSTEM_APPS = {
    'identity', 'market', 'barter', 'taxonomy', 'currency', 'iot', 'geo',
    'finance', 'governance', 'logistics', 'energy', 'treasury', 'agents',
    'tickets', 'ads', 'debts', 'psy', 'core', 'notifications', 'audit_log',
    'oidc_provider',
}

router = Router(tags=["dashboard"])


# Pydantic schemas
class PlatformStatsResponse(BaseModel):
    parahub_members: int
    verified_users: int
    active_items: int
    total_profiles: int
    establishments: int
    contracts: int
    subsystems: int


class ItemCardResponse(BaseModel):
    id: str
    object_type: str = "item"
    title: str
    pricing_display: str  # Display string like "200 EUR" or "Free" or "Barter"
    owner_id: str
    owner_hna: str
    location_name: str
    photos_count: int
    created_at: str


class RecentUserResponse(BaseModel):
    id: str
    object_type: str = "profile"
    hna: str
    display_name: str
    is_verified_wot: bool
    created_at: str


class ActivityResponse(BaseModel):
    recent_items: List[ItemCardResponse]


class RecentUsersResponse(BaseModel):
    users: List[RecentUserResponse]


@router.get("/stats", response=PlatformStatsResponse)
@ratelimit(group='dashboard:stats', key='ip', rate='30/m')
def get_platform_stats(request):
    """
    Get platform-wide statistics (public endpoint)
    Returns count of Parahub Association members and verified users
    """
    try:
        # Get Parahub Association
        parahub_est = Establishment.objects.filter(
            slug='parahub-associacao'
        ).first()

        parahub_members = 0
        if parahub_est:
            parahub_members = EstablishmentMembership.objects.filter(
                establishment=parahub_est
            ).count()

        # Public counters must state the real community, so synthetic (test/bot)
        # profiles are excluded unconditionally — no viewer, no exemption (see
        # identity/visibility.py). Non-public profiles are excluded too: the
        # label this feeds reads "users", and a hidden pseudonymous profile is
        # not a second user.
        real_profiles = exclude_test_authors(
            Profile.objects.filter(is_publicly_linked=True), None, field='')

        verified_users = real_profiles.filter(is_verified_wot=True).count()

        # Count active items
        active_items = Item.objects.filter(
            is_active=True
        ).count()

        # Count total profiles
        total_profiles = real_profiles.count()

        # Directory
        establishments = Establishment.objects.count()

        # Contracts
        contracts = Contract.objects.count()

        # Subsystems
        subsystems = len([
            a for a in django_apps.get_app_configs()
            if a.label in SUBSYSTEM_APPS
        ])

        return {
            "parahub_members": parahub_members,
            "verified_users": verified_users,
            "active_items": active_items,
            "total_profiles": total_profiles,
            "establishments": establishments,
            "contracts": contracts,
            "subsystems": subsystems,
        }
    except Exception:
        # Return zeros on error instead of failing
        return {
            "parahub_members": 0,
            "verified_users": 0,
            "active_items": 0,
            "total_profiles": 0,
            "establishments": 0,
            "contracts": 0,
            "subsystems": 0,
        }


@router.get("/activity", response=ActivityResponse, auth=ProfileAuth())
@ratelimit(group='dashboard:activity', key=user_or_ip, rate='60/m')
def get_user_activity(request):
    """
    Get authenticated user's activity (private endpoint)
    Returns active deals and recent market items
    """
    profile = request.auth

    # Get recent market items (last 6 items from all users)
    recent_items = Item.objects.filter(
        is_active=True
    ).select_related('owner').order_by('-created_at')[:6]

    items_data = []
    for item in recent_items:
        # Get pricing display from pricing_options
        pricing_display = "Free"
        if item.pricing_options and len(item.pricing_options) > 0:
            first_price = item.pricing_options[0]
            if first_price.get('type') == 'free':
                pricing_display = "Free"
            elif first_price.get('type') == 'barter':
                pricing_display = "Barter"
            else:
                amount = first_price.get('amount', 0)
                currency = first_price.get('currency', 'EUR')
                if float(amount) == 0:
                    note = first_price.get('note', '')
                    pricing_display = note if note else "Price negotiable"
                else:
                    pricing_display = f"{float(amount):.2f} {currency}"

        items_data.append({
            'id': item.id,
            'object_type': 'item',
            'title': item.title,
            'pricing_display': pricing_display,
            'owner_id': item.owner.id,
            'owner_hna': item.owner.hna,
            'location_name': getattr(item, 'location_name', '') or '',
            'photos_count': item.images.count() if hasattr(item, 'images') else 0,
            'created_at': item.created_at.isoformat()
        })

    return {
        'recent_items': items_data
    }


@router.get("/recent-users", response=RecentUsersResponse)
@ratelimit(group='dashboard:recent_users', key='ip', rate='30/m')
def get_recent_users(request):
    """
    Get recently registered users (public endpoint)
    Returns last 10 users ordered by registration date
    """
    # Get recent profiles, excluding system/test profiles if needed
    recent_users = Profile.objects.order_by('-created_at')[:10]

    users_data = []
    for profile in recent_users:
        users_data.append({
            'id': profile.id,
            'object_type': 'profile',
            'hna': profile.hna,
            'display_name': profile.display_name,
            'is_verified_wot': profile.is_verified_wot,
            'created_at': profile.created_at.isoformat()
        })

    return {
        'users': users_data
    }


# === Game-like Dashboard Schemas ===

class PartnerCardResponse(BaseModel):
    id: str
    object_type: str = "profile"
    local_name: str
    hna: str
    display_name: str
    reputation_score: float
    is_verified_wot: bool
    verifications_count: int
    items_count: int
    avatar_url: Optional[str] = None


class AchievementResponse(BaseModel):
    category: str  # cryptography, goods_services, profile, ads, verifications
    level: int  # 0 (none), 1 (medium), 2 (master)
    progress: int  # Current value (e.g., 5 active items)
    next_threshold: int | None  # Next level threshold or None if maxed


class DashboardStatsResponse(BaseModel):
    verifications_count: int
    reputation_score: float
    active_deals_count: int  # Active contracts (SIGNED or PENDING_PARTNER)
    partners_count: int  # People you added
    partnered_by_count: int  # People who added you


# === Activity Feed Schemas ===

class FeedItemResponse(BaseModel):
    id: str
    object_type: str = "item"
    title: str
    slug: str
    pricing_display: str
    owner_name: str
    owner_local_name: str
    thumbnail_url: Optional[str] = None
    created_at: str


class FeedEventResponse(BaseModel):
    id: str
    object_type: str = "event"
    title: str
    starts_at: str
    location_name: str
    cover_image_url: Optional[str] = None
    organizer_name: str
    participants_count: int


class FeedPollResponse(BaseModel):
    id: str
    object_type: str = "poll"
    title: str
    options_count: int
    end_time: Optional[str] = None
    context_name: str


class CommunityPulseResponse(BaseModel):
    total_members: int
    active_listings: int
    upcoming_events: int
    active_polls: int


class OnboardingStepsResponse(BaseModel):
    has_profile: bool  # display_name + (avatar or bio)
    has_listing: bool  # at least 1 active item
    has_partners: bool  # at least 1 partner added


class QuestStepsResponse(BaseModel):
    """What a newcomer needs before the platform actually works for them."""
    has_profile: bool  # display_name + (avatar or bio)
    has_keys: bool  # PGP key registered — without it no contract can be signed
    verifications_count: int  # active WoT verifications received
    verifications_required: int  # threshold mirrors Profile.update_wot_status()


class OnboardingResponse(BaseModel):
    steps: QuestStepsResponse
    complete: bool


class GameDashboardResponse(BaseModel):
    top_partners: List[PartnerCardResponse]
    achievements: List[AchievementResponse]
    stats: DashboardStatsResponse
    recent_items: List[FeedItemResponse]
    upcoming_events: List[FeedEventResponse]
    active_polls: List[FeedPollResponse]
    pulse: CommunityPulseResponse
    onboarding_complete: bool
    onboarding_steps: OnboardingStepsResponse


@router.get("/onboarding", response=OnboardingResponse, auth=ProfileAuth())
@ratelimit(group='dashboard:onboarding', key=user_or_ip, rate='60/m')
def get_onboarding(request):
    """Lightweight quest-log progress for the map HUD.

    Three setup steps, in the order they unblock each other: an identity people
    can recognise, keys to sign with (one seed derives both PGP and the wallet),
    and the WoT verifications that open the rest of the platform.
    """
    profile = request.auth_profile
    verifications_required = 3  # keep in sync with Profile.update_wot_status()
    has_profile = bool(profile.display_name) and bool(profile.avatar or profile.bio)
    has_keys = bool(profile.pgp_public_key and profile.pgp_fingerprint)
    verifications_count = Verification.objects.filter(
        verified_profile=profile, is_active=True
    ).count()
    return OnboardingResponse(
        steps=QuestStepsResponse(
            has_profile=has_profile,
            has_keys=has_keys,
            verifications_count=verifications_count,
            verifications_required=verifications_required,
        ),
        complete=has_profile and has_keys and verifications_count >= verifications_required,
    )


@router.get("/game", response=GameDashboardResponse, auth=ProfileAuth())
@ratelimit(group='dashboard:game', key=user_or_ip, rate='60/m')
def get_game_dashboard(request):
    """
    Get game-like dashboard data with achievements, top partners, and stats

    Returns:
    - top_partners: Top 5 partners by reputation
    - achievements: 6 categories (cryptography, goods_services, profile, ads, verifications, ambassador)
    - stats: User statistics (verifications, reputation, deals, partners)
    """
    profile = request.auth_profile

    # === Top 5 Partners by Reputation ===
    partners = Partner.objects.filter(
        profile=profile
    ).select_related('partner_profile').annotate(
        verifications_count=Count('partner_profile__received_verifications',
                                 filter=Q(partner_profile__received_verifications__is_active=True))
    ).order_by('-partner_profile__reputation_score')[:5]

    top_partners = []
    for partnership in partners:
        partner = partnership.partner_profile

        # Count active items
        items_count = Item.objects.filter(
            owner=partner,
            is_active=True
        ).count()

        top_partners.append(PartnerCardResponse(
            id=partner.id,
            object_type="profile",
            local_name=partner.local_name,
            hna=partner.hna,
            # Same gate as every other surface: a one-way partner add must not
            # hand out a name the profile keeps behind name_visible_to
            display_name=(
                partner.display_name if partner.name_visible_to(profile) else ''
            ) or partner.local_name,
            reputation_score=float(partner.reputation_score),
            is_verified_wot=partner.is_verified_wot,
            verifications_count=partnership.verifications_count,
            items_count=items_count,
            avatar_url=partner.avatar_url
        ))

    # === Achievements ===
    achievements = []

    # 1. Cryptography (PGP key setup)
    # Level 0: No PGP key
    # Level 1: Has PGP key
    # Level 2: Has PGP key + 3+ signatures
    has_pgp = bool(profile.pgp_public_key and profile.pgp_fingerprint)
    # Count PGP-signed actions: verifications given + contracts signed
    pgp_signatures = 0
    if has_pgp:
        pgp_signatures += Verification.objects.filter(
            verifier=profile, is_active=True, signature__gt=''
        ).count()
        pgp_signatures += Contract.objects.filter(
            creator=profile, creator_signature__gt=''
        ).count()
        pgp_signatures += Contract.objects.filter(
            partner=profile, partner_signature__gt=''
        ).count()
    if not has_pgp:
        crypto_level = 0
        crypto_next = 1
    elif pgp_signatures < 3:
        crypto_level = 1
        crypto_next = 3
    else:
        crypto_level = 2
        crypto_next = None

    achievements.append(AchievementResponse(
        category="cryptography",
        level=crypto_level,
        progress=pgp_signatures if has_pgp else 0,
        next_threshold=crypto_next
    ))

    # 2. Goods & Services (active items)
    # Level 0: 0 items
    # Level 1: 1-9 items
    # Level 2: 10+ items
    active_items = Item.objects.filter(
        owner=profile,
        is_active=True
    ).count()

    if active_items == 0:
        goods_level = 0
        goods_next = 1
    elif active_items < 10:
        goods_level = 1
        goods_next = 10
    else:
        goods_level = 2
        goods_next = None

    achievements.append(AchievementResponse(
        category="goods_services",
        level=goods_level,
        progress=active_items,
        next_threshold=goods_next
    ))

    # 3. Profile (completeness + verification)
    # Level 0: Basic profile
    # Level 1: Complete profile (display_name, location, PGP)
    # Level 2: WoT verified
    profile_complete = bool(
        profile.display_name and
        profile.location and
        profile.pgp_public_key
    )

    if not profile_complete:
        profile_level = 0
        profile_progress = sum([
            bool(profile.display_name),
            bool(profile.location),
            bool(profile.pgp_public_key)
        ])
        profile_next = 3
    elif not profile.is_verified_wot:
        profile_level = 1
        profile_progress = 1
        profile_next = 1
    else:
        profile_level = 2
        profile_progress = 1
        profile_next = None

    achievements.append(AchievementResponse(
        category="profile",
        level=profile_level,
        progress=profile_progress,
        next_threshold=profile_next
    ))

    # 4. Advertising (created ads)
    # Level 0: 0 ads
    # Level 1: 1-4 ads
    # Level 2: 5+ ads
    ads_count = AdCampaign.objects.filter(
        advertiser=profile,
        status__in=['active', 'paused']
    ).count()

    if ads_count == 0:
        ads_level = 0
        ads_next = 1
    elif ads_count < 5:
        ads_level = 1
        ads_next = 5
    else:
        ads_level = 2
        ads_next = None

    achievements.append(AchievementResponse(
        category="ads",
        level=ads_level,
        progress=ads_count,
        next_threshold=ads_next
    ))

    # 5. Verifications (WoT verifications received)
    # Level 0: 0 verifications
    # Level 1: 1-2 verifications
    # Level 2: 3+ verifications (WoT verified)
    verifications_count = Verification.objects.filter(
        verified_profile=profile,
        is_active=True
    ).count()

    if verifications_count == 0:
        verif_level = 0
        verif_next = 1
    elif verifications_count < 3:
        verif_level = 1
        verif_next = 3
    else:
        verif_level = 2
        verif_next = None

    achievements.append(AchievementResponse(
        category="verifications",
        level=verif_level,
        progress=verifications_count,
        next_threshold=verif_next
    ))

    # 6. Ambassador (invitees who took root)
    # Counts invited people who reached WoT verification, not raw signups —
    # a rooted invite costs three real verifiers, so the metric can't be
    # farmed with throwaway accounts.
    # Level 0: 0 rooted invites
    # Level 1: 1-9 rooted invites
    # Level 2: 10+ rooted invites
    rooted_invites = Profile.objects.filter(
        invited_by=profile,
        is_verified_wot=True
    ).count()

    if rooted_invites == 0:
        ambassador_level = 0
        ambassador_next = 1
    elif rooted_invites < 10:
        ambassador_level = 1
        ambassador_next = 10
    else:
        ambassador_level = 2
        ambassador_next = None

    achievements.append(AchievementResponse(
        category="ambassador",
        level=ambassador_level,
        progress=rooted_invites,
        next_threshold=ambassador_next
    ))

    # === Statistics ===
    partners_count = Partner.objects.filter(profile=profile).count()
    partnered_by_count = Partner.objects.filter(partner_profile=profile).count()
    active_deals_count = Contract.objects.filter(
        Q(creator=profile) | Q(partner=profile),
        status__in=[Contract.Status.SIGNED, Contract.Status.PENDING_PARTNER]
    ).count()

    stats = DashboardStatsResponse(
        verifications_count=verifications_count,
        reputation_score=float(profile.reputation_score),
        active_deals_count=active_deals_count,
        partners_count=partners_count,
        partnered_by_count=partnered_by_count
    )

    # === Activity Feed: Recent Items ===
    items_qs = Item.objects.filter(is_active=True).select_related('owner').order_by('-created_at')
    items_qs = exclude_test_authors(items_qs, request, field='owner')
    recent_items_data = []
    for item in items_qs[:5]:
        pricing_display = "Free"
        if item.pricing_options and len(item.pricing_options) > 0:
            fp = item.pricing_options[0]
            if fp.get('type') == 'barter':
                pricing_display = "Barter"
            elif fp.get('type') != 'free':
                amount = fp.get('amount', 0)
                currency = fp.get('currency', 'EUR')
                if float(amount) == 0:
                    note = fp.get('note', '')
                    pricing_display = note if note else "Price negotiable"
                else:
                    pricing_display = f"{float(amount):.2f} {currency}"
        thumb = ObjectPhoto.objects.filter(object_id=item.id).order_by('order', 'created_at').values_list('image', flat=True).first()
        recent_items_data.append(FeedItemResponse(
            id=item.id,
            title=item.title,
            slug=item.slug or item.id,
            pricing_display=pricing_display,
            owner_name=item.owner.display_name or item.owner.local_name,
            owner_local_name=item.owner.local_name,
            thumbnail_url=f"/media/{thumb}" if thumb else None,
            created_at=item.created_at.isoformat(),
        ))

    # === Activity Feed: Upcoming Events ===
    now = timezone.now()
    events_qs = Event.objects.filter(
        status=Event.Status.PUBLISHED,
        starts_at__gte=now,
    ).select_related('organizer').order_by('starts_at')
    events_qs = exclude_test_authors(events_qs, request, field='organizer')
    upcoming_events_data = []
    for ev in events_qs[:4]:
        cover = None
        if ev.cover_image:
            cover = ev.cover_image.url
        elif ev.cover_image_url:
            cover = ev.cover_image_url
        upcoming_events_data.append(FeedEventResponse(
            id=ev.id,
            title=ev.title,
            starts_at=ev.starts_at.isoformat(),
            location_name=ev.location_name or '',
            cover_image_url=cover,
            organizer_name=ev.organizer.display_name or ev.organizer.local_name,
            participants_count=ev.participants_count,
        ))

    # === Activity Feed: Active Polls ===
    polls_qs = Poll.objects.filter(
        status=Poll.Status.ACTIVE,
    ).select_related('context').annotate(
        options_count=Count('options')
    ).order_by('-start_time')[:4]
    active_polls_data = []
    for poll in polls_qs:
        active_polls_data.append(FeedPollResponse(
            id=poll.id,
            title=poll.title,
            options_count=poll.options_count,
            end_time=poll.end_time.isoformat() if poll.end_time else None,
            context_name=poll.context.get_context_type_display() if poll.context else '',
        ))

    # === Community Pulse ===
    # Pulse counters stay viewer-independent: they report the real community
    # size, so synthetic accounts are excluded even for exempt viewers.
    pulse = CommunityPulseResponse(
        total_members=exclude_test_authors(Profile.objects.all(), field='').count(),
        active_listings=exclude_test_authors(Item.objects.filter(is_active=True), field='owner').count(),
        upcoming_events=Event.objects.filter(status=Event.Status.PUBLISHED, starts_at__gte=now).count(),
        active_polls=Poll.objects.filter(status=Poll.Status.ACTIVE).count(),
    )

    # === Onboarding Steps ===
    has_profile = bool(profile.display_name) and bool(profile.avatar or profile.bio)
    has_listing = active_items > 0
    has_partners = partners_count > 0
    onboarding_steps = OnboardingStepsResponse(
        has_profile=has_profile,
        has_listing=has_listing,
        has_partners=has_partners,
    )
    # Server-side steps all done; frontend combines with localStorage for map/condo
    onboarding_complete = has_profile and has_listing and has_partners

    return GameDashboardResponse(
        top_partners=top_partners,
        achievements=achievements,
        stats=stats,
        recent_items=recent_items_data,
        upcoming_events=upcoming_events_data,
        active_polls=active_polls_data,
        pulse=pulse,
        onboarding_complete=onboarding_complete,
        onboarding_steps=onboarding_steps,
    )
