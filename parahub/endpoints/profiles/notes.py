"""
Private per-profile notes.
"""


from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from pydantic import BaseModel, ConfigDict, Field
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile

from .base import profile_router

logger = logging.getLogger(__name__)

class ProfileNoteResponse(BaseModel):
    id: str
    note: str

    model_config = ConfigDict(from_attributes=True)

class ProfileNoteInput(BaseModel):
    note: str = Field(..., max_length=10000, description="Private note content")

@profile_router.get('/{id}/note/', response={200: ProfileNoteResponse, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:get_note', key=user_or_ip, rate='60/m')
def get_profile_note(request, id: str):
    """
    Get private note about a profile (only for authenticated user)
    """
    from identity.models import ProfileNote

    try:
        if len(id) == 26 and id.isalnum():
            target_profile = get_object_or_404(Profile, id=id)
        else:
            target_profile = get_object_or_404(Profile, local_name=id)
        owner_profile = request.auth_profile

        # Try to get note - raise 404 if doesn't exist
        try:
            note = ProfileNote.objects.get(owner=owner_profile, about=target_profile)
        except ProfileNote.DoesNotExist:
            raise Http404("Note not found")

        return ProfileNoteResponse(
            id=note.id,
            note=note.note
        )

    except Http404:
        raise
    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving note: {e}")
        raise HttpError(500, "Failed to retrieve note")

@profile_router.post('/{id}/note/', response={200: ProfileNoteResponse, 400: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:save_note', key=user_or_ip, rate='30/m', method='POST')
def create_or_update_profile_note(request, id: str, data: ProfileNoteInput):
    """
    Create or update private note about a profile (only for authenticated user)
    """
    from identity.models import ProfileNote

    try:
        if len(id) == 26 and id.isalnum():
            target_profile = get_object_or_404(Profile, id=id)
        else:
            target_profile = get_object_or_404(Profile, local_name=id)
        owner_profile = request.auth_profile

        # Prevent creating note about yourself
        if owner_profile.id == target_profile.id:
            raise HttpError(400, "Cannot create note about yourself")

        # Create or update note
        note, created = ProfileNote.objects.update_or_create(
            owner=owner_profile,
            about=target_profile,
            defaults={'note': data.note}
        )

        return ProfileNoteResponse(
            id=note.id,
            note=note.note
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error creating/updating note: {e}")
        raise HttpError(500, "Failed to save note")
