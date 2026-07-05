"""
Psycho-informatics (Yellow Protocol) endpoints.
"""


from django.shortcuts import get_object_or_404
from django.http import Http404
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
import logging

from parahub.auth import GlobalAuth, ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile

from .base import profile_router

logger = logging.getLogger(__name__)

class PsychProfileResponse(BaseModel):
    """Response with psycho-informatics profile data"""
    id: str
    profile_id: str
    psych_hash_4: List[str] = []
    form3_completed_at: Optional[str] = None
    psych_hash_4_updated_at: Optional[str] = None
    form3_data: Optional[dict] = None  # Only returned to owner (via /me/psych/)

    model_config = ConfigDict(from_attributes=True)

class PsychProfileUpdateRequest(BaseModel):
    """Request to update psycho-informatics profile"""
    form3_data: Optional[dict] = Field(None, description="Answers to 30 questions (1-5 scale). Format: {q1: 3, q2: 5, ...}")
    psych_hash_4: Optional[List[str]] = Field(None, description="4 words describing personality", max_length=4)

@profile_router.get("/me/psych/", response=PsychProfileResponse, auth=ProfileAuth())
@ratelimit(group='profiles:my_psych', key=user_or_ip, rate='60/m')
def get_my_psych_profile(request):
    """
    Get my psycho-informatics profile

    Returns (to owner only):
    - psych_hash_4: 4 words (PUBLIC)
    - form3_completed_at: timestamp
    - form3_data: answers to 30 questions (PRIVATE, only returned to owner)
    """
    from identity.models import PsychProfile
    from django.utils import timezone

    try:
        profile = request.auth_profile

        # Get or create PsychProfile
        psych_profile, created = PsychProfile.objects.get_or_create(profile=profile)

        return PsychProfileResponse(
            id=psych_profile.id,
            profile_id=profile.id,
            psych_hash_4=psych_profile.psych_hash_4 or [],
            form3_completed_at=psych_profile.form3_completed_at.isoformat() if psych_profile.form3_completed_at else None,
            psych_hash_4_updated_at=psych_profile.psych_hash_4_updated_at.isoformat() if psych_profile.psych_hash_4_updated_at else None,
            form3_data=psych_profile.form3_data or {},  # Return to owner
        )

    except Exception as e:
        logger.error(f"Error retrieving psych profile: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to retrieve psych profile"}, 500

@profile_router.post("/me/psych/", response=PsychProfileResponse, auth=ProfileAuth())
@ratelimit(group='profiles:update_psych', key=user_or_ip, rate='30/m', method='POST')
def update_my_psych_profile(request, data: PsychProfileUpdateRequest):
    """
    Update my psycho-informatics profile

    Can update:
    - form3_data: Answers to 30 questions (1-5 scale) - PRIVATE
    - psych_hash_4: 4 words - PUBLIC

    form3_data is stored but NEVER returned to users (system only).
    """
    from identity.models import PsychProfile
    from django.utils import timezone

    try:
        profile = request.auth_profile

        # Get or create PsychProfile
        psych_profile, created = PsychProfile.objects.get_or_create(profile=profile)

        # Update form3_data if provided
        if data.form3_data is not None:
            # Validate form3_data structure (30 questions, values 1-5)
            if not isinstance(data.form3_data, dict):
                return {"error": "VALIDATION_ERROR", "message": "form3_data must be a dict"}, 400

            # Validate each answer is 1-5
            for key, value in data.form3_data.items():
                if not isinstance(value, int) or value < 1 or value > 5:
                    return {
                        "error": "VALIDATION_ERROR",
                        "message": f"Invalid answer for {key}: must be integer 1-5"
                    }, 400

            psych_profile.form3_data = data.form3_data

            # Only set form3_completed_at if all 30 questions answered
            if len(data.form3_data) >= 30:
                psych_profile.form3_completed_at = timezone.now()
            else:
                psych_profile.form3_completed_at = None

        # Update psych_hash_4 if provided
        if data.psych_hash_4 is not None:
            if not isinstance(data.psych_hash_4, list) or len(data.psych_hash_4) != 4:
                return {"error": "VALIDATION_ERROR", "message": "psych_hash_4 must be array of 4 strings"}, 400

            psych_profile.psych_hash_4 = data.psych_hash_4
            psych_profile.psych_hash_4_updated_at = timezone.now()

        psych_profile.save()

        logger.info(f"Psych profile updated for {profile.hna}")

        return PsychProfileResponse(
            id=psych_profile.id,
            profile_id=profile.id,
            psych_hash_4=psych_profile.psych_hash_4 or [],
            form3_completed_at=psych_profile.form3_completed_at.isoformat() if psych_profile.form3_completed_at else None,
            psych_hash_4_updated_at=psych_profile.psych_hash_4_updated_at.isoformat() if psych_profile.psych_hash_4_updated_at else None,
            form3_data=psych_profile.form3_data or {},  # Return to owner
        )

    except Exception as e:
        logger.error(f"Error updating psych profile: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to update psych profile"}, 500

@profile_router.get("/{id}/psych/", response={200: PsychProfileResponse, 404: dict}, auth=GlobalAuth())
@ratelimit(group='profiles:public_psych', key=user_or_ip, rate='60/m')
def get_profile_psych_hash(request, id: str):
    """
    Get psycho-informatics data for a profile (PUBLIC DATA ONLY)

    Returns only:
    - psych_hash_4: 4 words (for WoT matching)

    Does NOT return:
    - form3_data (private, system only)
    """
    from identity.models import PsychProfile

    try:
        profile = get_object_or_404(Profile, id=id)

        # Try to get PsychProfile
        try:
            psych_profile = PsychProfile.objects.get(profile=profile)
        except PsychProfile.DoesNotExist:
            # Return empty response if no psych profile
            return PsychProfileResponse(
                id="",
                profile_id=profile.id,
                psych_hash_4=[],
                form3_completed_at=None,
                psych_hash_4_updated_at=None,
                form3_data=None,  # NEVER expose to others
            )

        # Return only PUBLIC data (psych_hash_4)
        return PsychProfileResponse(
            id=psych_profile.id,
            profile_id=profile.id,
            psych_hash_4=psych_profile.psych_hash_4 or [],
            form3_completed_at=None,  # Don't expose timestamp to others
            psych_hash_4_updated_at=None,  # Don't expose timestamp to others
            form3_data=None,  # NEVER expose to others
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving psych profile for {id}: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to retrieve psych profile"}, 500
