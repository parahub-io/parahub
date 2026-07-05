"""
Partner Management API endpoints for Parahub
Handles invite links and partner relationships
"""

from ninja import Router
from ninja.pagination import paginate, PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Subquery, OuterRef, IntegerField, Value
from django.db.models.functions import Coalesce
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
import logging
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile, Partner
from market.models import Item

logger = logging.getLogger(__name__)

partner_router = Router()


def get_profile_by_id_or_username(profile_id: str) -> Profile:
    """
    Get profile by ULID or username (local_name).
    ULIDs are 26 chars uppercase alphanumeric starting with 01.
    """
    from core.models import Instance
    from django.conf import settings

    # Check if it looks like ULID (26 chars, starts with 01)
    if len(profile_id) == 26 and profile_id.startswith('01'):
        return get_object_or_404(Profile, id=profile_id)

    # Otherwise treat as username (local_name)
    instance = Instance.objects.get(domain=settings.FEDERATION_DOMAIN)
    return get_object_or_404(Profile, instance=instance, local_name=profile_id.lower())


# Pydantic schemas
class InviteResponse(BaseModel):
    invite_url: str
    invite_token: str
    is_active: bool
    invited_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class PartnerResponse(BaseModel):
    id: str
    hna: str
    display_name: str
    local_name: str
    reputation_score: Decimal
    is_verified_wot: bool
    verifications_count: int
    items_offering_count: int
    items_wanting_count: int
    added_at: str

    model_config = ConfigDict(from_attributes=True)


class AddPartnerRequest(BaseModel):
    invite_token: str = Field(..., description="Invite token from the inviting user")


class ToggleInviteRequest(BaseModel):
    active: bool = Field(..., description="Set invite token active status")


@partner_router.get("/invite/", response={200: InviteResponse, 500: dict}, auth=ProfileAuth())
@ratelimit(group='partners:invite', key=user_or_ip, rate='60/m')
def get_invite_link(request):
    """
    Get or generate permanent invite link for the authenticated user

    Returns the invite URL and token that can be shared with others.
    The token remains the same unless manually regenerated.
    """
    try:
        profile = request.auth_profile

        # Generate token if doesn't exist
        if not profile.invite_token:
            profile.generate_invite_token()

        # Build invite URL
        invite_url = f"https://parahub.io/invite/{profile.invite_token}"

        return InviteResponse(
            invite_url=invite_url,
            invite_token=profile.invite_token,
            is_active=profile.invite_token_active,
            invited_count=profile.invited_profiles.count()
        )

    except Exception as e:
        logger.error(f"Error getting invite link: {e}")
        return 500, {"error": "Failed to get invite link"}


@partner_router.post("/invite/regenerate/", response={200: InviteResponse, 500: dict}, auth=ProfileAuth())
@ratelimit(group='partners:invite_regenerate', key=user_or_ip, rate='5/h', method='POST')
def regenerate_invite_token(request):
    """
    Regenerate invite token (creates new link, old one becomes invalid)
    """
    try:
        profile = request.auth_profile
        profile.generate_invite_token(force_regenerate=True)

        invite_url = f"https://parahub.io/invite/{profile.invite_token}"

        logger.info(f"Invite token regenerated for {profile.hna}: {profile.invite_token}")

        return InviteResponse(
            invite_url=invite_url,
            invite_token=profile.invite_token,
            is_active=profile.invite_token_active,
            invited_count=profile.invited_profiles.count()
        )

    except Exception as e:
        logger.error(f"Error regenerating invite token: {e}")
        return 500, {"error": "Failed to regenerate invite token"}


@partner_router.post("/invite/toggle/", response={200: InviteResponse, 400: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='partners:invite_toggle', key=user_or_ip, rate='30/m', method='POST')
def toggle_invite_token(request, data: ToggleInviteRequest):
    """
    Enable or disable invite token
    """
    try:
        profile = request.auth_profile

        if not profile.invite_token:
            return 400, {"error": "No invite token exists yet"}

        profile.invite_token_active = data.active
        profile.save(update_fields=['invite_token_active'])

        invite_url = f"https://parahub.io/invite/{profile.invite_token}"

        return InviteResponse(
            invite_url=invite_url,
            invite_token=profile.invite_token,
            is_active=profile.invite_token_active,
            invited_count=profile.invited_profiles.count()
        )

    except Exception as e:
        logger.error(f"Error toggling invite token: {e}")
        return 500, {"error": "Failed to toggle invite token"}


class QuickSignupRequest(BaseModel):
    invite_token: str = Field(..., description="Invite token from the inviting user")
    local_name: Optional[str] = Field(None, description="Optional custom username (if not provided, auto-generated)")


class QuickSignupResponse(BaseModel):
    message: str
    username: str
    email: str
    password: str
    hna: str
    inviter_hna: str
    access_token: str
    refresh_token: str


@partner_router.post("/quick-signup/", response={200: QuickSignupResponse, 400: dict, 500: dict}, auth=None)
@ratelimit(group='partners:quick_signup', key='ip', rate='3/h', method='POST')
def quick_signup_via_invite(request, data: QuickSignupRequest):
    """
    Quick signup via invite link - creates account automatically

    Creates new account with auto-generated or custom username, password, and email (username@parahub.io).
    Automatically adds inviter to the new user's partners list.

    If local_name is provided, validates it for availability in both Parahub and Matrix.
    If not provided, generates a random available username.
    """
    try:
        from django.contrib.auth import get_user_model
        from identity.models import Account, Profile
        from core.models import Instance
        from django.conf import settings
        from parahub.endpoints.auth import _check_username_available_in_matrix, _is_username_valid
        import secrets
        import string

        # Find inviter profile by token
        try:
            inviter_profile = Profile.objects.get(
                invite_token=data.invite_token,
                invite_token_active=True
            )
        except Profile.DoesNotExist:
            return 400, {"error": "Invalid or inactive invite token"}

        instance = Instance.objects.get(domain=settings.FEDERATION_DOMAIN)

        # Validate custom username if provided
        if data.local_name:
            username = data.local_name.lower().strip()

            # Validate format
            is_valid, error_msg = _is_username_valid(username)
            if not is_valid:
                return 400, {"error": error_msg}

            # Check availability in Parahub
            if Account.objects.filter(username=username).exists():
                return 400, {"error": "Username already taken"}

            if Profile.objects.filter(instance=instance, local_name=username).exists():
                return 400, {"error": "Username already taken"}

            # Check availability in Matrix
            if not _check_username_available_in_matrix(username):
                return 400, {"error": "Username already taken in chat system"}
        else:
            # Generate unique username using coolname library
            def generate_username():
                from coolname import generate_slug

                max_attempts = 100  # Prevent infinite loop

                for attempt in range(max_attempts):
                    # Generate readable name: adjective-noun (e.g., brave-panda)
                    candidate = generate_slug(2)  # 2 words: shorter and more readable

                    # Check uniqueness in both Account, Profile, and Matrix
                    if (Account.objects.filter(username=candidate).exists() or
                            Profile.objects.filter(instance=instance, local_name=candidate).exists()):
                        continue

                    if not _check_username_available_in_matrix(candidate):
                        continue

                    return candidate

                # Fallback: add timestamp if somehow all attempts failed (extremely rare)
                import time
                timestamp = int(time.time() * 1000) % 100000  # Last 5 digits of timestamp
                return f"user-{timestamp}"

            username = generate_username()

        # Generate secure password
        def generate_password(length=16):
            chars = string.ascii_letters + string.digits + '!@#$%^&*'
            return ''.join(secrets.choice(chars) for _ in range(length))

        password = generate_password()
        email = f"{username}@parahub.io"

        # Get client IP for registration tracking
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        reg_ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')

        # Create account (instance already defined above)
        account = Account.objects.create_user(
            username=username,
            email=email,
            password=password,
            instance=instance,
            first_name='',
            last_name='',
            registration_ip=reg_ip,
        )

        # Create profile (this is the primary/first profile for this account)
        profile = Profile.objects.create(
            account=account,
            instance=instance,
            local_name=username,
            display_name=username.replace('-', ' ').title(),
            profile_type=Profile.ProfileType.PERSONAL,
            is_primary=True,
            is_publicly_linked=True,
            invited_by=inviter_profile
        )

        # Mutual partnership: both users add each other
        Partner.objects.create(
            profile=profile,
            partner_profile=inviter_profile
        )
        Partner.objects.create(
            profile=inviter_profile,
            partner_profile=profile
        )

        # Auto-create Matrix DM between new user and inviter (fire-and-forget)
        try:
            from parahub.endpoints.matrix_auth import create_dm_between_accounts
            create_dm_between_accounts(account.id, inviter_profile.account_id)
        except Exception as e:
            logger.error(f"Failed to auto-create DM for invite signup: {e}")

        # Ensure all changes are committed to DB before generating tokens
        from django.db import transaction
        transaction.on_commit(lambda: None)  # Force commit point

        # Generate JWT tokens for auto-login using ninja_jwt (NOT rest_framework_simplejwt!)
        from ninja_jwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(account)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        logger.info(f"Quick signup via invite: {profile.hna} → invited by {inviter_profile.hna}")
        logger.debug(f"Generated tokens - Access: {access_token[:30]}... Refresh: {refresh_token[:30]}...")
        logger.debug(f"Account ID: {account.id}, Username: {account.username}")

        return QuickSignupResponse(
            message="Account created successfully",
            username=username,
            email=email,
            password=password,
            hna=profile.hna,
            inviter_hna=inviter_profile.hna,
            access_token=access_token,
            refresh_token=refresh_token
        )

    except Exception as e:
        logger.error(f"Error in quick signup: {e}", exc_info=True)
        return 500, {"error": "Failed to create account"}


@partner_router.post("/accept/", response={200: dict, 400: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='partners:accept', key=user_or_ip, rate='20/h', method='POST')
def accept_invitation(request, data: AddPartnerRequest):
    """
    Accept invitation and add the inviter to YOUR partners list (one-way)

    Validates the invite token and creates partner relationship.
    This is one-directional - only you add them to your list.
    For unauthenticated users, use /quick-signup/ instead.
    """
    try:
        current_profile = request.auth_profile

        # Find profile by invite token
        try:
            inviter_profile = Profile.objects.get(
                invite_token=data.invite_token,
                invite_token_active=True
            )
        except Profile.DoesNotExist:
            return 400, {"error": "Invalid or inactive invite token"}

        # Check if trying to add self
        if inviter_profile.id == current_profile.id:
            return 400, {"error": "Cannot add yourself as partner"}

        # Check if already in partners
        if Partner.objects.filter(
            profile=current_profile,
            partner_profile=inviter_profile
        ).exists():
            return {"message": "Already in your partners"}, 200

        # Mutual partnership: both users add each other
        Partner.objects.create(
            profile=current_profile,
            partner_profile=inviter_profile
        )
        if not Partner.objects.filter(
            profile=inviter_profile,
            partner_profile=current_profile
        ).exists():
            Partner.objects.create(
                profile=inviter_profile,
                partner_profile=current_profile
            )

        logger.info(f"Mutual partner added: {current_profile.hna} ↔ {inviter_profile.hna}")

        # Auto-create Matrix DM between accepting user and inviter (fire-and-forget)
        try:
            from parahub.endpoints.matrix_auth import create_dm_between_accounts
            create_dm_between_accounts(current_profile.account_id, inviter_profile.account_id)
        except Exception as e:
            logger.error(f"Failed to auto-create DM for invite accept: {e}")

        # Send WebSocket notification to the person who was added
        try:
            partner_data = {
                'id': current_profile.id,
                'object_type': 'partner',
                'hna': current_profile.hna,
                'display_name': current_profile.display_name or current_profile.local_name or current_profile.hna,
                'added_by': current_profile.hna,
            }
            from parahub.services.ws_publish import ws_publish
            ws_publish(f"user:{inviter_profile.account_id}", {
                "type": "partner.added", "partner": partner_data,
            })
        except Exception as e:
            logger.error(f"Failed to send WS notification for partner added: {e}")

        return {
            "message": "Partner added successfully",
            "partner": {
                "cri": inviter_profile.id,
                "hna": inviter_profile.hna,
                "display_name": inviter_profile.display_name
            }
        }

    except Exception as e:
        logger.error(f"Error accepting invitation: {e}", exc_info=True)
        return 500, {"error": "Failed to accept invitation"}


@partner_router.get("/list/", response=List[PartnerResponse], auth=ProfileAuth())
@ratelimit(group='partners:list', key=user_or_ip, rate='60/m')
@paginate(PageNumberPagination, page_size=20)
def list_partners(request):
    """
    Get list of partners for authenticated user

    Returns detailed information about each partner including stats.
    """
    try:
        current_profile = request.auth_profile

        offering_sq = Item.objects.filter(
            owner_id=OuterRef('partner_profile_id'), is_active=True, type='OFFER'
        ).order_by().values('owner_id').annotate(c=Count('id')).values('c')

        wanting_sq = Item.objects.filter(
            owner_id=OuterRef('partner_profile_id'), is_active=True, type='WANT'
        ).order_by().values('owner_id').annotate(c=Count('id')).values('c')

        partnerships = Partner.objects.filter(
            profile=current_profile
        ).select_related('partner_profile', 'partner_profile__instance').annotate(
            verifications_count=Count('partner_profile__received_verifications', filter=Q(partner_profile__received_verifications__is_active=True)),
            _items_offering=Coalesce(Subquery(offering_sq, output_field=IntegerField()), Value(0)),
            _items_wanting=Coalesce(Subquery(wanting_sq, output_field=IntegerField()), Value(0)),
        )

        results = []
        for partnership in partnerships:
            partner = partnership.partner_profile
            results.append(PartnerResponse(
                id=partner.id,
                hna=partner.hna,
                display_name=partner.display_name or partner.local_name or partner.hna,
                local_name=partner.local_name,
                reputation_score=partner.reputation_score,
                is_verified_wot=partner.is_verified_wot,
                verifications_count=partnership.verifications_count,
                items_offering_count=partnership._items_offering,
                items_wanting_count=partnership._items_wanting,
                added_at=partnership.added_at.isoformat()
            ))

        return results

    except Exception as e:
        logger.error(f"Error listing partners: {e}")
        return []


@partner_router.delete("/{partner_id}/", response={200: dict, 404: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='partners:remove', key=user_or_ip, rate='30/m', method='DELETE')
def remove_partner(request, partner_id: str):
    """
    Remove a partner from YOUR list (one-way)

    Only removes them from your partners, doesn't affect their list.
    """
    try:
        current_profile = request.auth_profile

        # Get partner profile (by ULID or username)
        partner_profile = get_profile_by_id_or_username(partner_id)

        # Delete only from current user's list (one-way)
        deleted_count = Partner.objects.filter(
            profile=current_profile,
            partner_profile=partner_profile
        ).delete()[0]

        if deleted_count == 0:
            return 404, {"error": "Partner not found in your list"}

        logger.info(f"Partner removed: {current_profile.hna} → {partner_profile.hna}")

        # Send WebSocket notification to the person who was removed
        try:
            partner_data = {
                'id': current_profile.id,
                'object_type': 'partner',
                'hna': current_profile.hna,
                'display_name': current_profile.display_name or current_profile.local_name or current_profile.hna,
                'removed_by': current_profile.hna,
            }
            from parahub.services.ws_publish import ws_publish
            ws_publish(f"user:{partner_profile.account_id}", {
                "type": "partner.removed", "partner": partner_data,
            })
        except Exception as e:
            logger.error(f"Failed to send WS notification for partner removed: {e}")

        return {"message": "Partner removed successfully"}

    except Exception as e:
        logger.error(f"Error removing partner: {e}")
        return 500, {"error": "Failed to remove partner"}


@partner_router.post("/add/{profile_id}/", response={200: dict, 400: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='partners:add_direct', key=user_or_ip, rate='30/m', method='POST')
def add_partner_direct(request, profile_id: str):
    """
    Add a partner directly by their ULID to YOUR list (one-way, without invite token)

    Creates one-way partnership - only adds to your list.
    """
    try:
        current_profile = request.auth_profile

        # Get target profile (by ULID or username)
        partner_profile = get_profile_by_id_or_username(profile_id)

        # Check if trying to add self
        if partner_profile.id == current_profile.id:
            return 400, {"error": "Cannot add yourself as partner"}

        # Check if already in your partners
        if Partner.objects.filter(
            profile=current_profile,
            partner_profile=partner_profile
        ).exists():
            return {"message": "Already in your partners"}, 200

        # Create one-way partnership (only add to current user's list)
        Partner.objects.create(
            profile=current_profile,
            partner_profile=partner_profile
        )

        logger.info(f"Partner added: {current_profile.hna} → {partner_profile.hna}")

        # Send WebSocket notification to the person who was added
        try:
            partner_data = {
                'id': current_profile.id,
                'object_type': 'partner',
                'hna': current_profile.hna,
                'display_name': current_profile.display_name or current_profile.local_name or current_profile.hna,
                'added_by': current_profile.hna,
            }
            from parahub.services.ws_publish import ws_publish
            ws_publish(f"user:{partner_profile.account_id}", {
                "type": "partner.added", "partner": partner_data,
            })
        except Exception as e:
            logger.error(f"Failed to send WS notification for partner added: {e}")

        return {
            "message": "Partner added successfully",
            "partner": {
                "cri": partner_profile.id,
                "hna": partner_profile.hna,
                "display_name": partner_profile.display_name
            }
        }

    except Exception as e:
        logger.error(f"Error adding partner: {e}")
        return 500, {"error": "Failed to add partner"}


class PartnershipStatusResponse(BaseModel):
    """Response schema for partnership status check"""
    i_added_them: bool  # Current user added this profile to their partners
    they_added_me: bool  # This profile added current user to their partners
    is_mutual: bool  # Both added each other


@partner_router.get("/status/{profile_id}/", response={200: PartnershipStatusResponse, 500: dict}, auth=ProfileAuth())
@ratelimit(group='partners:status', key=user_or_ip, rate='60/m')
def check_partnership_status(request, profile_id: str):
    """
    Check partnership status with another profile

    Returns:
    - i_added_them: True if you added them to your partners
    - they_added_me: True if they added you to their partners
    - is_mutual: True if both directions exist
    """
    try:
        current_profile = request.auth_profile

        # Get target profile (by ULID or username)
        target_profile = get_profile_by_id_or_username(profile_id)

        # Check if trying to check self
        if target_profile.id == current_profile.id:
            return PartnershipStatusResponse(
                i_added_them=False,
                they_added_me=False,
                is_mutual=False
            )

        # Check if current user added target to their partners
        i_added_them = Partner.objects.filter(
            profile=current_profile,
            partner_profile=target_profile
        ).exists()

        # Check if target user added current to their partners
        they_added_me = Partner.objects.filter(
            profile=target_profile,
            partner_profile=current_profile
        ).exists()

        return PartnershipStatusResponse(
            i_added_them=i_added_them,
            they_added_me=they_added_me,
            is_mutual=i_added_them and they_added_me
        )

    except Exception as e:
        logger.error(f"Error checking partnership status: {e}")
        return 500, {"error": "Failed to check partnership status"}
