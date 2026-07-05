"""
Profile CRUD: me/preferences/update, create, search, public detail,
switch/delete, manageable list, mail credentials.
"""


from ninja.pagination import paginate, PageNumberPagination
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from typing import List, Optional
import logging

from parahub.auth import GlobalAuth, ProfileAuth
from parahub.middleware.pgp import PGPSignatureAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile

from .base import profile_router
from .schemas import ProfileCreateRequest, ProfileDetailResponse, ProfilePrivateResponse, ProfilePublicResponse, ProfileSearchResponse, ProfileUpdateRequest

logger = logging.getLogger(__name__)

@profile_router.get("/me/", response=ProfilePrivateResponse, auth=ProfileAuth())
@ratelimit(group='profiles:me', key=user_or_ip, rate='60/m')
def get_my_profile(request):
    """
    Get authenticated user's complete profile information

    Returns all profile data including private information
    only accessible to the profile owner.
    """
    try:
        profile = request.auth_profile

        # Auto-detect country on first request (one-time, user can override later)
        if not profile.country_code:
            from geo.utils import get_country_code_from_request
            detected = get_country_code_from_request(request)
            if detected:
                profile.country_code = detected
                profile.save(update_fields=['country_code'])

        # Convert location point to dict if exists
        location_data = None
        if profile.location:
            location_data = {
                'latitude': profile.location.y,
                'longitude': profile.location.x
            }

        response_data = ProfilePrivateResponse.model_validate(profile)
        response_data.location = location_data

        return response_data

    except Exception as e:
        logger.error(f"Error retrieving private profile: {e}")
        return {"error": "Failed to retrieve profile"}, 500

@profile_router.get("/me/mail-credentials/", auth=ProfileAuth())
@ratelimit(group='profiles:mail_credentials', key=user_or_ip, rate='30/m')
def get_mail_credentials(request):
    """Return decrypted mail password for the authenticated user (used for webmail auto-login)."""
    account = request.auth_profile.account
    if not account.mail_password:
        return {"error": "No mail account found"}, 404
    try:
        from parahub.services.mailcow import decrypt_mail_password
        from django.conf import settings as djsettings
        return {
            'username': account.username,
            'password': decrypt_mail_password(account.mail_password),
            'email': f'{account.username}@{djsettings.MAILCOW_DOMAIN}',
        }
    except Exception as e:
        logger.error(f'Failed to decrypt mail password for {account.username}: {e}')
        return {"error": "Failed to retrieve mail credentials"}, 500

@profile_router.patch("/me/preferences/", response={200: ProfilePrivateResponse, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:preferences', key=user_or_ip, rate='30/m', method='PATCH')
def update_my_preferences(request, data: ProfileUpdateRequest):
    """
    Update authenticated user's preferences (language, currency, map style, animations)

    Does NOT require PGP signature for non-critical preferences.
    Only updates preference settings (not profile identity).
    """
    try:
        profile = request.auth_profile

        # Track which fields to update
        update_fields = []

        # Only update non-critical preference fields
        if data.preferred_language is not None:
            profile.preferred_language = data.preferred_language
            update_fields.append('preferred_language')

        if data.preferred_currency is not None:
            profile.preferred_currency = data.preferred_currency
            update_fields.append('preferred_currency')

        if data.map_style is not None:
            profile.map_style = data.map_style
            update_fields.append('map_style')

        if data.animation_enabled is not None:
            profile.animation_enabled = data.animation_enabled
            update_fields.append('animation_enabled')

        if data.display_name is not None:
            profile.display_name = data.display_name
            update_fields.append('display_name')

        if data.bio is not None:
            profile.bio = data.bio
            update_fields.append('bio')

        if data.ln_address is not None:
            profile.ln_address = data.ln_address
            update_fields.append('ln_address')

        if data.spark_address is not None:
            profile.spark_address = data.spark_address
            update_fields.append('spark_address')

        if data.country_code is not None:
            profile.country_code = data.country_code.upper()
            update_fields.append('country_code')

        if data.support_level is not None:
            profile.support_level = data.support_level
            update_fields.append('support_level')

        if data.notification_prefs is not None:
            allowed_keys = {'social', 'contracts', 'governance', 'calls'}
            prefs = {k: bool(v) for k, v in data.notification_prefs.items() if k in allowed_keys}
            profile.notification_prefs = prefs
            update_fields.append('notification_prefs')

        if data.name_public is not None:
            profile.name_public = data.name_public
            update_fields.append('name_public')

        # Save only the updated fields
        if update_fields:
            profile.save(update_fields=update_fields)

        logger.info(f"Profile preferences updated successfully: {profile.id} - fields: {update_fields}")

        # Return updated profile
        return get_my_profile(request)

    except Exception as e:
        logger.error(f"Error updating profile preferences: {e}")
        raise HttpError(500, "Failed to update preferences")

@profile_router.put("/me/", response=ProfilePrivateResponse, auth=PGPSignatureAuth())
@ratelimit(group='profiles:update', key=user_or_ip, rate='30/m', method='PUT')
def update_my_profile(request, data: ProfileUpdateRequest):
    """
    Update authenticated user's profile information

    Requires PGP signature for security.
    Only profile owner can update their profile.
    """
    try:
        profile = request.auth_profile
        
        # Update only provided fields
        if data.display_name is not None:
            profile.display_name = data.display_name

        if data.bio is not None:
            profile.bio = data.bio

        if data.antispam_fee_sats is not None:
            profile.antispam_fee_sats = data.antispam_fee_sats
        
        if data.is_publicly_linked is not None:
            profile.is_publicly_linked = data.is_publicly_linked

        if data.preferred_language is not None:
            profile.preferred_language = data.preferred_language

        if data.preferred_currency is not None:
            profile.preferred_currency = data.preferred_currency

        # Handle location update
        if data.location is not None:
            from django.contrib.gis.geos import Point
            if 'latitude' in data.location and 'longitude' in data.location:
                profile.location = Point(
                    data.location['longitude'], 
                    data.location['latitude']
                )
            elif data.location == {}:  # Empty dict means remove location
                profile.location = None
        
        profile.full_clean()
        profile.save()
        
        logger.info(f"Profile updated successfully: {profile.id}")
        
        # Return updated profile
        return get_my_profile(request)
        
    except ValidationError as e:
        logger.warning(f"Profile update validation error: {e}")
        return {"error": "Invalid profile data", "details": str(e)}, 400
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return {"error": "Failed to update profile"}, 500

@profile_router.get("/manageable/", response=List[ProfileDetailResponse], auth=ProfileAuth())
@ratelimit(group='profiles:manageable', key=user_or_ip, rate='60/m')
def get_manageable_profiles(request):
    """
    Get all profiles that the authenticated user can manage

    Returns:
    - Primary personal profile
    - Organization profiles where user is owner/admin
    - Pseudonymous profiles created by this user (if primary profile)
    """
    try:
        current_profile = request.auth_profile

        # Get all manageable profiles with account preloaded
        profiles = current_profile.get_manageable_profiles().select_related('account')

        # Build response with management flag
        result = []
        for profile in profiles:
            profile_data = ProfileDetailResponse.model_validate(profile, can_manage=True)
            result.append(profile_data)

        logger.info(f"Retrieved {len(result)} manageable profiles for {current_profile.id}")
        return result

    except Exception as e:
        logger.error(f"Error retrieving manageable profiles: {e}")
        return {"error": "Failed to retrieve profiles"}, 500

@profile_router.get("/search/", response=dict, auth=ProfileAuth())
@ratelimit(group='profiles:search', key=user_or_ip, rate='60/m')
def search_profiles(request, q: Optional[str] = None, verified_only: bool = False, only_partners: bool = False, page: int = 1, page_size: int = 50):
    """
    Search for public profiles (requires authentication)

    Args:
        q: Search query for display name or local name
        verified_only: Only return WoT verified profiles
        only_partners: Only return user's partners
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 100)
    """
    try:
        current_profile = request.auth

        queryset = Profile.objects.filter(is_publicly_linked=True).select_related('account', 'instance')

        # Hide test/bot/admin accounts and localhost instance profiles from directory listings
        queryset = queryset.exclude(account__is_test=True).exclude(account__is_bot=True).exclude(account__is_superuser=True)
        queryset = queryset.exclude(instance__domain='localhost')

        # Filter by partners if requested
        if only_partners and current_profile:
            from identity.models import Partner
            partner_ids = Partner.objects.filter(
                profile=current_profile
            ).values_list('partner_profile_id', flat=True)
            queryset = queryset.filter(id__in=partner_ids)

        # Filter by verification status
        if verified_only:
            queryset = queryset.filter(is_verified_wot=True)

        # Search by name if query provided
        if q:
            from django.db.models import Q

            # Check if query looks like HNA (contains @)
            if '@' in q:
                parts = q.split('@', 1)
                local_name_part = parts[0]
                domain_part = parts[1] if len(parts) > 1 else ''

                if domain_part:
                    # Full HNA search: local_name@domain
                    queryset = queryset.filter(
                        local_name__iexact=local_name_part,
                        instance__domain__iexact=domain_part
                    )
                else:
                    # Partial HNA: just local_name@
                    queryset = queryset.filter(local_name__istartswith=local_name_part)
            else:
                # Regular search by display_name or local_name
                queryset = queryset.filter(
                    Q(display_name__icontains=q) | Q(local_name__icontains=q)
                )

        # Order by reputation score descending
        queryset = queryset.order_by('-reputation_score', '-created_at')

        # Count total before pagination
        total_count = queryset.count()

        # Apply pagination
        page_size = min(page_size, 100)  # Max 100 items per page
        offset = (page - 1) * page_size
        paginated_queryset = queryset[offset:offset + page_size]

        # Get partner info if authenticated
        partner_map = {}
        if current_profile:
            from identity.models import Partner
            partners = Partner.objects.filter(
                profile=current_profile,
                partner_profile_id__in=[p.id for p in paginated_queryset]
            ).select_related('partner_profile')
            partner_map = {
                p.partner_profile_id: {
                    'added_at': p.added_at.isoformat() if p.added_at else None,
                }
                for p in partners
            }

        # Get item counts for ALL profiles (not just partners)
        from market.models import Item
        from django.db.models import Count, Q
        profile_ids = [p.id for p in paginated_queryset]
        item_counts = {}
        if profile_ids:
            # Use aggregation to efficiently count items per profile
            # CREDIT = user offers (has to give), DEBIT = user wants (needs to receive)
            items_query = Item.objects.filter(
                owner_id__in=profile_ids
            ).values('owner_id', 'type').annotate(count=Count('id'))

            for item in items_query:
                if item['owner_id'] not in item_counts:
                    item_counts[item['owner_id']] = {'CREDIT': 0, 'DEBIT': 0}
                item_counts[item['owner_id']][item['type']] = item['count']

        # Get verification counts for ALL profiles
        from identity.models import Verification
        verification_counts = {}
        if profile_ids:
            # Count verifications received (where profile is verified_profile)
            verifications_received_query = Verification.objects.filter(
                verified_profile_id__in=profile_ids,
                is_active=True
            ).values('verified_profile_id').annotate(count=Count('id'))

            for v in verifications_received_query:
                if v['verified_profile_id'] not in verification_counts:
                    verification_counts[v['verified_profile_id']] = {'received': 0, 'given': 0}
                verification_counts[v['verified_profile_id']]['received'] = v['count']

            # Count verifications given (where profile is verifier)
            verifications_given_query = Verification.objects.filter(
                verifier_id__in=profile_ids,
                is_active=True
            ).values('verifier_id').annotate(count=Count('id'))

            for v in verifications_given_query:
                if v['verifier_id'] not in verification_counts:
                    verification_counts[v['verifier_id']] = {'received': 0, 'given': 0}
                verification_counts[v['verifier_id']]['given'] = v['count']

        # Build response with partner info, item counts, and verification counts
        results = []
        for profile in paginated_queryset:
            partner_info = partner_map.get(profile.id, {})
            counts = item_counts.get(profile.id, {'CREDIT': 0, 'DEBIT': 0})
            verif_counts = verification_counts.get(profile.id, {'received': 0, 'given': 0})
            result = ProfileSearchResponse(
                id=profile.id,
                account_id=profile.account.id,
                hna=profile.hna,
                display_name=profile.display_name if profile.name_visible_to(current_profile) else '',
                reputation_score=profile.reputation_score,
                is_verified_wot=profile.is_verified_wot,
                antispam_fee_sats=profile.antispam_fee_sats,
                is_publicly_linked=profile.is_publicly_linked,
                preferred_language=profile.preferred_language or '',
                preferred_currency=profile.preferred_currency or 'EUR',
                bio=profile.bio or '',
                avatar_url=profile.avatar.url if profile.avatar else None,
                country_code=profile.country_code or '',
                is_partner=profile.id in partner_map,
                items_credit_count=counts.get('CREDIT', 0),
                items_debit_count=counts.get('DEBIT', 0),
                verifications_received_count=verif_counts.get('received', 0),
                verifications_given_count=verif_counts.get('given', 0),
                partner_added_at=partner_info.get('added_at'),
            )
            results.append(result)

        return {
            "items": results,
            "count": total_count,
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Error searching profiles: {e}")
        return {"items": [], "count": 0, "page": page, "page_size": page_size}

@profile_router.post("/create/", response={200: ProfileDetailResponse, 400: dict, 403: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:create', key=user_or_ip, rate='3/h', method='POST')
def create_profile(request, data: ProfileCreateRequest):
    """
    Create a new pseudonymous profile

    Requirements:
    - User must be WoT verified (3+ verifications)
    - local_name must be unique on this instance
    """
    try:
        current_profile = request.auth_profile

        # Check WoT verification requirement (must check primary profile, not current active profile)
        primary_profile = Profile.objects.filter(
            account=current_profile.account,
            is_primary=True
        ).first()

        if not primary_profile or not primary_profile.can_create_additional_profiles():
            raise HttpError(403, "Only WoT verified members can create additional profiles (3+ verifications required)")

        # Check max profiles limit (1 primary + 6 additional = 7 total)
        total_profiles = Profile.objects.filter(account=current_profile.account).count()
        if total_profiles >= 7:
            raise HttpError(403, "Maximum number of profiles reached (6 additional profiles allowed)")

        # Check if local_name is already taken
        instance = current_profile.instance
        if Profile.objects.filter(instance=instance, local_name=data.local_name).exists():
            raise HttpError(400, f"Profile name '{data.local_name}' is already taken")

        # Create new pseudonymous profile
        new_profile = Profile(
            account=current_profile.account,
            instance=instance,
            local_name=data.local_name,
            display_name=data.display_name,
            profile_type=Profile.ProfileType.PSEUDONYMOUS,
            is_primary=False,
            # The display_name of a pseudonymous profile is itself a pseudonym (the
            # intended public face), so it is shown publicly — gating it gives no privacy.
            name_public=True,
        )

        new_profile.full_clean()
        new_profile.save()

        logger.info(f"New pseudonymous profile created: {new_profile.hna} by {current_profile.hna}")

        # Automatically switch to the newly created profile
        request.session['active_profile_id'] = new_profile.id
        request.session.modified = True

        return ProfileDetailResponse.model_validate(new_profile, can_manage=True)

    except ValidationError as e:
        logger.warning(f"Profile creation validation error: {e}")
        raise HttpError(400, f"Invalid profile data: {str(e)}")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HttpError(500, "Failed to create profile")

@profile_router.get("/{id}/", response=ProfilePublicResponse, auth=None)
@ratelimit(group='profiles:public', key='ip', rate='60/m')
def get_public_profile(request, id: str):
    """
    Get public profile information by ULID or local_name (nickname)

    This endpoint returns publicly available profile data including
    reputation score, verification status, and display name.

    Supports both formats:
    - /profiles/01K2SH48YZ42G55225PMWBCHD3/ (ULID)
    - /profiles/daring-water/ (local_name/nickname)

    If user is authenticated, also returns whether they already verified this profile.
    """
    try:
        # Try to find by ULID first (26 alphanumeric chars), otherwise by local_name
        if len(id) == 26 and id.isalnum():
            profile = get_object_or_404(Profile.objects.select_related('account'), id=id)
        else:
            profile = get_object_or_404(Profile.objects.select_related('account'), local_name=id)

        # Check if profile is publicly linked
        if not profile.is_publicly_linked:
            raise Http404("Profile not found")

        # Try to get authenticated profile (optional)
        current_profile = None
        authenticated_user = None
        try:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                # Use GlobalAuth to validate JWT and get user
                global_auth = GlobalAuth()
                user = global_auth.authenticate(request, token)
                if user:
                    authenticated_user = user
                    # Get profile for this user
                    current_profile = global_auth.get_user_profile(request)
        except Exception as e:
            # Optional auth failed - this is OK for public endpoint
            logger.debug(f"Optional auth failed for profile {id}: {e}")

        # Count items for this profile
        from market.models import Item
        from market.visibility import visible_items_q
        from django.db.models import Count, Q

        # This endpoint is auth=None, so the viewer is always anonymous for
        # visibility: counts reflect the PUBLIC storefront face and never leak
        # the existence of REGISTERED items to crawlers.
        item_counts = Item.objects.filter(
            owner_id=profile.id
        ).filter(visible_items_q(request)).values('type').annotate(count=Count('id'))

        counts = {'CREDIT': 0, 'DEBIT': 0}
        for item in item_counts:
            counts[item['type']] = item['count']

        # Rentable storefront count: the person's OWN bookable items (org-posted
        # items belong to that org's board, not the person's). Mirrors the
        # establishment rentable_count and the rental profile_board filter.
        rentable_count = Item.objects.filter(
            owner_id=profile.id, establishment_id__isnull=True,
            is_active=True, bookable__isnull=False, bookable__is_active=True,
        ).filter(visible_items_q(request)).count()

        # Count verifications for this profile
        from identity.models import Verification
        verifications_received = Verification.objects.filter(
            verified_profile_id=profile.id,
            is_active=True
        ).count()

        verifications_given = Verification.objects.filter(
            verifier_id=profile.id,
            is_active=True
        ).count()

        # Check if current user already verified this profile
        i_verified_them = False
        if current_profile and current_profile.id != profile.id:
            i_verified_them = Verification.objects.filter(
                verifier_id=current_profile.id,
                verified_profile_id=profile.id,
                is_active=True
            ).exists()

        # Whether this profile uploaded a WoT verification photo (consent + face embedding).
        # Mirrors the backend gate in wot.create_verification — without it nobody can verify them.
        from identity.models import ProfileVerificationPhoto
        has_verification_photo = ProfileVerificationPhoto.objects.filter(
            profile_id=profile.id,
            biometric_consent=True,
            face_embedding__isnull=False,
        ).exists()

        # Count contracts for this profile
        from contracts.models import Contract
        contracts_active = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='SIGNED'
        ).count()

        contracts_completed = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='COMPLETED'
        ).count()

        # Count debts for this profile
        from debts.models import Debt
        debts_active = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status__in=['ACTIVE', 'PARTIALLY_SETTLED']
        ).count()

        debts_settled = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status='FULLY_SETTLED'
        ).count()

        # Count invited users and how many are verified (3+ WoT)
        invited_profiles = Profile.objects.filter(invited_by=profile)
        invited_count = invited_profiles.count()
        invited_verified_count = 0
        if invited_count > 0:
            invited_verified_count = invited_profiles.filter(
                is_verified_wot=True
            ).filter(
                id__in=Verification.objects.filter(
                    is_active=True
                ).values('verified_profile_id').annotate(
                    cnt=Count('id')
                ).filter(cnt__gte=3).values('verified_profile_id')
            ).count()

        return ProfilePublicResponse.model_validate(
            profile,
            items_credit_count=counts.get('CREDIT', 0),
            items_debit_count=counts.get('DEBIT', 0),
            verifications_received_count=verifications_received,
            verifications_given_count=verifications_given,
            i_verified_them=i_verified_them,
            has_verification_photo=has_verification_photo,
            contracts_active_count=contracts_active,
            contracts_completed_count=contracts_completed,
            debts_active_count=debts_active,
            debts_settled_count=debts_settled,
            invited_count=invited_count,
            invited_verified_count=invited_verified_count,
            rentable_count=rentable_count,
            current_user=authenticated_user,
            current_profile=current_profile,
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving public profile {id}: {e}")
        raise Http404("Profile not found")

@profile_router.get("/by-account/{account_id}/", response=ProfilePublicResponse, auth=None)
@ratelimit(group='profiles:by_account', key='ip', rate='60/m')
def get_profile_by_account(request, account_id: str):
    """
    Get primary profile by account ULID

    Returns the primary profile for a given account ID.
    Used by Matrix integration to resolve display names.
    ULIDs are case-insensitive, so we uppercase the input.
    """
    try:
        # ULID is case-insensitive - normalize to uppercase
        account_id_upper = account_id.upper()

        # Get primary profile for the account
        profile = get_object_or_404(
            Profile.objects.select_related('account'),
            account_id=account_id_upper,
            is_primary=True
        )

        # Check if profile is publicly linked
        if not profile.is_publicly_linked:
            raise Http404("Profile not found")

        # Count items for this profile
        from market.models import Item
        from market.visibility import visible_items_q
        from django.db.models import Count

        # auth=None -> anonymous viewer: PUBLIC-only counts (no REGISTERED leak).
        item_counts = Item.objects.filter(
            owner_id=profile.id
        ).filter(visible_items_q(request)).values('type').annotate(count=Count('id'))

        counts = {'CREDIT': 0, 'DEBIT': 0}
        for item in item_counts:
            counts[item['type']] = item['count']

        # Count verifications for this profile
        from identity.models import Verification
        verifications_received = Verification.objects.filter(
            verified_profile_id=profile.id,
            is_active=True
        ).count()

        verifications_given = Verification.objects.filter(
            verifier_id=profile.id,
            is_active=True
        ).count()

        # Count contracts for this profile
        from contracts.models import Contract
        contracts_active = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='SIGNED'
        ).count()

        contracts_completed = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='COMPLETED'
        ).count()

        # Count debts for this profile
        from debts.models import Debt
        debts_active = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status__in=['ACTIVE', 'PARTIALLY_SETTLED']
        ).count()

        debts_settled = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status='FULLY_SETTLED'
        ).count()

        # Count invited users and how many are verified (3+ WoT)
        invited_profiles = Profile.objects.filter(invited_by=profile)
        invited_count = invited_profiles.count()
        invited_verified_count = 0
        if invited_count > 0:
            invited_verified_count = invited_profiles.filter(
                is_verified_wot=True
            ).filter(
                id__in=Verification.objects.filter(
                    is_active=True
                ).values('verified_profile_id').annotate(
                    cnt=Count('id')
                ).filter(cnt__gte=3).values('verified_profile_id')
            ).count()

        return ProfilePublicResponse.model_validate(
            profile,
            items_credit_count=counts.get('CREDIT', 0),
            items_debit_count=counts.get('DEBIT', 0),
            verifications_received_count=verifications_received,
            verifications_given_count=verifications_given,
            contracts_active_count=contracts_active,
            contracts_completed_count=contracts_completed,
            debts_active_count=debts_active,
            debts_settled_count=debts_settled,
            invited_count=invited_count,
            invited_verified_count=invited_verified_count
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving profile for account {account_id}: {e}")
        raise Http404("Profile not found")

@profile_router.get("/{id}/reviews/", response=List[dict])
@ratelimit(group='profiles:reviews', key='ip', rate='60/m')
@paginate(PageNumberPagination, page_size=10)
def get_profile_reviews(request, id: str):
    """
    Get reviews for a specific profile

    Returns paginated list of reviews received by this profile.
    Note: This is a placeholder - full review system will be implemented in Phase 3.
    """
    try:
        profile = get_object_or_404(Profile, id=id)

        # Placeholder return - will be implemented with Review model in Phase 3
        return []

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving reviews for profile {id}: {e}")
        return []

@profile_router.post("/switch/{id}/", response={200: ProfileDetailResponse, 403: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:switch', key=user_or_ip, rate='30/m', method='POST')
def switch_active_profile(request, id: str):
    """
    Switch active profile context

    Allows user to switch between their manageable profiles (personal, organization, pseudonymous).
    The active profile is stored in session and used for creating items, sending messages, etc.

    Returns the newly active profile details.
    """
    try:
        current_profile = request.auth_profile
        target_profile = get_object_or_404(Profile, id=id)

        # Check if user can manage this profile (use primary profile for permission check)
        primary_profile = Profile.objects.filter(
            account=current_profile.account,
            is_primary=True
        ).first()

        # Check if target profile belongs to same account
        if target_profile.account_id != current_profile.account_id:
            raise HttpError(403, "You don't have permission to switch to this profile")

        # Store active profile in session
        request.session['active_profile_id'] = target_profile.id
        request.session.modified = True

        logger.info(f"Profile switched: {current_profile.hna} → {target_profile.hna}")

        return ProfileDetailResponse.model_validate(target_profile, can_manage=True)

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error switching profile: {e}")
        raise HttpError(500, "Failed to switch profile")

@profile_router.delete("/{id}/", auth=ProfileAuth())
@ratelimit(group='profiles:delete', key=user_or_ip, rate='10/m', method='DELETE')
def delete_profile(request, id: str):
    """
    Delete a profile (only non-primary profiles)

    Requirements:
    - Profile must not be primary (cannot delete main profile)
    - User must have permission to manage this profile

    Deletes:
    - The profile itself
    - Profile's data (cascades automatically)

    Note: Items and other content created by this profile are NOT deleted
    """
    try:
        current_profile = request.auth_profile
        target_profile = get_object_or_404(Profile, id=id)

        # Cannot delete primary profile
        if target_profile.is_primary:
            return {
                "error": "CANNOT_DELETE_PRIMARY",
                "message": "Cannot delete primary profile"
            }, 400

        # Check if user can manage this profile
        if not current_profile.can_manage_profile(target_profile):
            return {
                "error": "PERMISSION_DENIED",
                "message": "You don't have permission to delete this profile"
            }, 403

        # Store HNA for logging
        profile_hna = target_profile.hna

        # Delete the profile (cascades to ProfileData, etc.)
        target_profile.delete()

        # If deleted profile was active in session, switch back to current profile
        if request.session.get('active_profile_id') == id:
            request.session['active_profile_id'] = current_profile.id
            request.session.modified = True

        logger.info(f"Profile deleted: {profile_hna} by {current_profile.hna}")

        return {"message": "Profile deleted successfully", "deleted_profile": profile_hna}

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to delete profile"}, 500
