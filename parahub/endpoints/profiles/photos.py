"""
Avatar, ID photo and verification photo endpoints + AI photo validation.
"""


from ninja import Form
from ninja.errors import HttpError
from ninja.files import UploadedFile
from typing import List, Optional
from pydantic import BaseModel
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile

from .base import profile_router

logger = logging.getLogger(__name__)

class PhotoUploadResponse(BaseModel):
    """Response for photo upload"""
    url: str
    verified: Optional[bool] = None  # Only for ID photo
    verification_issues: Optional[List[str]] = None  # AI validation issues

@profile_router.post("/me/avatar/", response={200: PhotoUploadResponse, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:upload_avatar', key=user_or_ip, rate='10/m', method='POST')
def upload_avatar(request, image: UploadedFile):
    """
    Upload avatar photo for the authenticated user.

    Avatar is automatically:
    - Cropped to square (center crop)
    - Resized to 400x400 max
    - Compressed to JPEG quality 85

    Max file size: 10MB
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    import sys

    try:
        profile = request.auth_profile

        # Validate file type
        if not image.content_type.startswith('image/'):
            return 400, {"error": "File must be an image"}

        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 10MB"}

        # Process image with PIL
        img = Image.open(image.file)

        # Convert to RGB if necessary
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        elif img.mode == 'RGBA':
            # Convert RGBA to RGB with white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Center crop to square
        width, height = img.size
        min_dim = min(width, height)
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))

        # Resize to 400x400
        img = img.resize((400, 400), Image.Resampling.LANCZOS)

        # Save to BytesIO
        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        # Delete old avatar if exists
        if profile.avatar:
            profile.avatar.delete(save=False)

        # Create Django file object
        file_name = f"{profile.id}.jpg"
        django_file = InMemoryUploadedFile(
            output, 'ImageField', file_name,
            'image/jpeg', sys.getsizeof(output), None
        )

        # Save avatar
        profile.avatar.save(file_name, django_file, save=True)

        logger.info(f"Avatar uploaded for profile {profile.id}")

        return PhotoUploadResponse(url=profile.avatar.url)

    except Exception as e:
        logger.error(f"Error uploading avatar: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload avatar: {str(e)}"}

@profile_router.delete("/me/avatar/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_avatar', key=user_or_ip, rate='10/m', method='DELETE')
def delete_avatar(request):
    """Delete avatar photo for the authenticated user."""
    try:
        profile = request.auth_profile

        if profile.avatar:
            profile.avatar.delete(save=True)
            logger.info(f"Avatar deleted for profile {profile.id}")
            return {"success": True}
        else:
            return {"success": True, "message": "No avatar to delete"}

    except Exception as e:
        logger.error(f"Error deleting avatar: {e}", exc_info=True)
        raise HttpError(500, "Failed to delete avatar")

@profile_router.post("/me/id-photo/", response={200: PhotoUploadResponse, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:upload_id_photo', key=user_or_ip, rate='10/m', method='POST')
def upload_id_photo(request, image: UploadedFile):
    """
    Upload ID photo for Para-ID badge.

    ID photo is:
    - Resized to 600x800 max (3:4 ratio)
    - Compressed to JPEG quality 90
    - AI-validated for face detection (advisory, not blocking)

    Returns verification status and any issues found.
    Max file size: 10MB
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    import sys

    try:
        profile = request.auth_profile

        # Validate file type
        if not image.content_type.startswith('image/'):
            return 400, {"error": "File must be an image"}

        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 10MB"}

        # Process image with PIL
        img = Image.open(image.file)

        # Convert to RGB if necessary
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        elif img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Resize maintaining aspect ratio (max 600x800)
        max_width, max_height = 600, 800
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Save to BytesIO for AI validation
        output = BytesIO()
        img.save(output, format='JPEG', quality=90, optimize=True)
        output.seek(0)

        # AI validation (advisory, doesn't block upload)
        verified = False
        verification_issues = []

        try:
            validation_result = _validate_id_photo_with_ai(output.getvalue(), profile)
            verified = validation_result.get('valid', False)
            verification_issues = validation_result.get('issues', [])
        except Exception as ai_error:
            logger.warning(f"AI validation failed (non-blocking): {ai_error}")
            verification_issues = ["AI validation unavailable"]

        # Reset buffer position
        output.seek(0)

        # Delete old id_photo if exists
        if profile.id_photo:
            profile.id_photo.delete(save=False)

        # Create Django file object
        file_name = f"{profile.id}.jpg"
        django_file = InMemoryUploadedFile(
            output, 'ImageField', file_name,
            'image/jpeg', sys.getsizeof(output), None
        )

        # Save id_photo and verification status
        profile.id_photo.save(file_name, django_file, save=False)
        profile.id_photo_verified = verified
        profile.save(update_fields=['id_photo', 'id_photo_verified'])

        logger.info(f"ID photo uploaded for profile {profile.id}, verified={verified}")

        return PhotoUploadResponse(
            # id_photo is private — hand back the gated endpoint, not the raw media path
            url=f"/api/v1/profiles/{profile.id}/id-photo/",
            verified=verified,
            verification_issues=verification_issues if verification_issues else None
        )

    except Exception as e:
        logger.error(f"Error uploading ID photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload ID photo: {str(e)}"}

@profile_router.delete("/me/id-photo/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_id_photo', key=user_or_ip, rate='10/m', method='DELETE')
def delete_id_photo(request):
    """Delete ID photo for the authenticated user."""
    try:
        profile = request.auth_profile

        if profile.id_photo:
            profile.id_photo.delete(save=False)
            profile.id_photo_verified = False
            profile.save(update_fields=['id_photo', 'id_photo_verified'])
            logger.info(f"ID photo deleted for profile {profile.id}")
            return {"success": True}
        else:
            return {"success": True, "message": "No ID photo to delete"}

    except Exception as e:
        logger.error(f"Error deleting ID photo: {e}", exc_info=True)
        raise HttpError(500, "Failed to delete ID photo")

@profile_router.get("/{id}/id-photo/", auth=ProfileAuth())
@ratelimit(group='profiles:id_photo', key=user_or_ip, rate='60/m')
def get_id_photo(request, id: str):
    """
    Serve a profile's Para-ID id_photo (private media) via nginx X-Accel-Redirect.

    Visible only to the owner or to WoT-verified viewers — everyone else gets 403.
    Mirrors the gating of WoT verification photos (see wot.get_verification_photo).
    """
    from django.http import HttpResponse

    viewer = request.auth_profile

    try:
        target = Profile.objects.get(id=id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Profile not found")

    if not target.id_photo:
        raise HttpError(404, "No ID photo for this profile")

    is_owner = viewer.id == target.id
    if not (is_owner or getattr(viewer, 'is_verified_wot', False)):
        raise HttpError(403, "Only the owner or WoT-verified members can view this photo")

    # X-Accel-Redirect for nginx (serves from internal /media/private/)
    response = HttpResponse(content_type='image/jpeg')
    response['X-Accel-Redirect'] = f'/media/{target.id_photo.name}'
    response['Cache-Control'] = 'no-store, no-cache'
    return response

@profile_router.post("/me/verification-photo/", response={200: dict, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profile:verification_photo', key=user_or_ip, rate='5/h', method='POST')
def upload_verification_photo(request, image: UploadedFile, biometric_consent: bool = Form(False)):
    """
    Upload verification photo for WoT face deduplication.

    Requires explicit GDPR biometric consent.
    Extracts face embedding and checks for duplicates against verified profiles.
    If updating existing photo with significantly different face, requires 3 re-confirmations.
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from django.utils import timezone
    from identity.models import ProfileVerificationPhoto
    from identity.services.face_dedup import (
        extract_embedding, serialize_embedding, check_duplicate,
        is_significant_change, compute_photo_hash, compute_face_fingerprint,
    )
    import sys

    try:
        profile = request.auth_profile

        # Only personal profiles can have verification photos
        if profile.profile_type != Profile.ProfileType.PERSONAL:
            logger.warning(f"Verification photo 400 for profile {profile.id}: non-personal profile_type={profile.profile_type}")
            return 400, {"error": "Only personal profiles can upload verification photos"}

        # GDPR: explicit biometric consent required
        if not biometric_consent:
            logger.warning(f"Verification photo 400 for profile {profile.id}: biometric_consent=false")
            return 400, {"error": "Biometric consent is required. Please check the consent checkbox to proceed."}

        # Validate file type
        if not image.content_type.startswith('image/'):
            logger.warning(f"Verification photo 400 for profile {profile.id}: bad content_type={image.content_type}")
            return 400, {"error": "File must be an image"}

        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            logger.warning(f"Verification photo 400 for profile {profile.id}: oversize {image.size} bytes")
            return 400, {"error": "Image size must be less than 10MB"}

        # Process image with PIL
        img = Image.open(image.file)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        elif img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Resize (max 600x800)
        img.thumbnail((600, 800), Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format='JPEG', quality=90, optimize=True)
        image_bytes = output.getvalue()
        output.seek(0)

        # Extract face embedding + non-blocking quality warnings
        try:
            embedding, quality_warnings = extract_embedding(image_bytes)
        except ValueError as e:
            logger.warning(f"Verification photo 400 for profile {profile.id}: extract_embedding ValueError: {e}")
            return 400, {"error": str(e)}

        if embedding is None:
            logger.warning(f"Verification photo 400 for profile {profile.id}: embedding is None")
            return 400, {"error": "Could not extract face features from photo"}

        embedding_bytes = serialize_embedding(embedding)
        photo_hash = compute_photo_hash(image_bytes)

        # Check for duplicates against all verified profiles
        duplicate = check_duplicate(embedding_bytes, exclude_profile_id=profile.id)
        if duplicate:
            logger.warning(f"Face dedup blocked upload for profile {profile.id}: distance={duplicate['distance']:.4f}")
            return 400, {"error": "Verification blocked: this face matches an already-verified profile"}

        # Check if updating existing photo
        reconfirmation_needed = False
        try:
            existing = ProfileVerificationPhoto.objects.get(profile=profile)
            old_embedding = bytes(existing.face_embedding)

            if old_embedding and profile.is_verified_wot:
                if is_significant_change(old_embedding, embedding_bytes):
                    reconfirmation_needed = True

            # Delete old photo file
            if existing.photo:
                existing.photo.delete(save=False)

            # Update existing record
            existing.face_embedding = embedding_bytes
            existing.photo_hash = photo_hash
            existing.biometric_consent = True
            existing.biometric_consent_at = timezone.now()
            existing.embedding_version = 1
            if reconfirmation_needed:
                existing.reconfirmation_needed = True
                existing.reconfirmation_count = 0

            file_name = f"{profile.id}_vp.jpg"
            django_file = InMemoryUploadedFile(
                output, 'ImageField', file_name, 'image/jpeg', sys.getsizeof(output), None
            )
            existing.photo.save(file_name, django_file, save=False)
            existing.save()

        except ProfileVerificationPhoto.DoesNotExist:
            # Create new record
            file_name = f"{profile.id}_vp.jpg"
            output.seek(0)
            django_file = InMemoryUploadedFile(
                output, 'ImageField', file_name, 'image/jpeg', sys.getsizeof(output), None
            )
            existing = ProfileVerificationPhoto(
                profile=profile,
                face_embedding=embedding_bytes,
                photo_hash=photo_hash,
                biometric_consent=True,
                biometric_consent_at=timezone.now(),
                embedding_version=1,
            )
            existing.photo.save(file_name, django_file, save=False)
            existing.save()

        logger.info(f"Verification photo uploaded for profile {profile.id}, reconfirmation_needed={reconfirmation_needed}")

        return {
            "success": True,
            "face_detected": True,
            "reconfirmation_needed": reconfirmation_needed,
            "quality_warnings": quality_warnings,
            "face_fingerprint": compute_face_fingerprint(embedding),
        }

    except Exception as e:
        logger.error(f"Error uploading verification photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload verification photo: {str(e)}"}

@profile_router.delete("/me/verification-photo/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_verification_photo', key=user_or_ip, rate='10/m', method='DELETE')
def delete_verification_photo(request):
    """
    Delete verification photo and face embedding (GDPR right to erasure).
    This will also reset WoT verified status since photo is required for WoT.
    """
    from identity.models import ProfileVerificationPhoto

    try:
        profile = request.auth_profile
        try:
            vp = ProfileVerificationPhoto.objects.get(profile=profile)
            if vp.photo:
                vp.photo.delete(save=False)
            vp.delete()
            logger.info(f"Verification photo deleted for profile {profile.id}")
            return {"success": True}
        except ProfileVerificationPhoto.DoesNotExist:
            return {"success": True, "message": "No verification photo to delete"}
    except Exception as e:
        logger.error(f"Error deleting verification photo: {e}", exc_info=True)
        raise HttpError(500, "Failed to delete verification photo")

@profile_router.get("/me/verification-photo/status/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:verification_photo_status', key=user_or_ip, rate='60/m')
def verification_photo_status(request):
    """Get current verification photo status."""
    from identity.models import ProfileVerificationPhoto
    from identity.services.face_dedup import face_fingerprint_from_bytes

    try:
        profile = request.auth_profile
        try:
            vp = ProfileVerificationPhoto.objects.get(profile=profile)
            return {
                "has_photo": True,
                "biometric_consent": vp.biometric_consent,
                "reconfirmation_needed": vp.reconfirmation_needed,
                "reconfirmation_count": vp.reconfirmation_count,
                "uploaded_at": vp.uploaded_at.isoformat() if vp.uploaded_at else None,
                "face_fingerprint": face_fingerprint_from_bytes(bytes(vp.face_embedding)) if vp.face_embedding else None,
            }
        except ProfileVerificationPhoto.DoesNotExist:
            return {"has_photo": False}
    except Exception as e:
        logger.error(f"Error getting verification photo status: {e}", exc_info=True)
        raise HttpError(500, "Failed to get verification photo status")

def _validate_id_photo_with_ai(image_bytes: bytes, profile) -> dict:
    """
    Validate ID photo using AI vision.

    Uses existing AI vision infrastructure with quota system.
    Returns: {"valid": bool, "confidence": float, "issues": list, "face_detected": bool}
    """
    from parahub.services.quota import QuotaService
    from parahub.models import AISettings
    import base64
    import json

    # Check quota (uses same quota as AI analysis)
    quota_info = QuotaService.check_quota(profile.account_id, 'ai_analysis')
    if quota_info['remaining'] <= 0:
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["AI quota exceeded for today"],
            "face_detected": False
        }

    # Get AI settings
    try:
        ai_settings = AISettings.objects.first()
        if not ai_settings:
            raise ValueError("AI settings not configured")
    except Exception:
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["AI service not configured"],
            "face_detected": False
        }

    # Prepare prompt for ID photo validation.
    # This photo goes on the Para-ID badge (a "this is me" portrait shown to humans),
    # not into face embeddings — so we don't enforce passport-style composition.
    # The WoT verification photo has its own pipeline with embedding-quality checks.
    prompt = """Analyze this photo for use as a personal ID badge portrait. Check:
1. Exactly one person visible (not zero, not multiple)
2. A face is visible and recognizable as the same person (not a back of the head, not heavily obscured)
3. Eyes are visible (no opaque sunglasses, eyes open)
4. Photo is in focus (not heavily blurred)

Composition, framing, background, lighting style, accessories (hats, glasses, makeup), and mood are NOT issues — the user picks their own portrait style.

Return ONLY valid JSON with no markdown formatting:
{"valid": true/false, "confidence": 0.0-1.0, "issues": ["list of problems found"], "face_detected": true/false, "face_count": number}

If the photo meets the four checks above, set valid=true and issues=[].
"""

    # Call AI provider
    try:
        if ai_settings.provider == 'gemini-2.5-flash-lite':
            result = _call_gemini_vision(ai_settings, image_bytes, prompt)
        elif ai_settings.provider.startswith('claude'):
            result = _call_claude_vision(ai_settings, image_bytes, prompt)
        elif ai_settings.provider.startswith('gpt'):
            result = _call_openai_vision(ai_settings, image_bytes, prompt)
        else:
            # Default to Gemini
            result = _call_gemini_vision(ai_settings, image_bytes, prompt)

        # Consume quota after successful validation
        QuotaService.consume_quota(profile.account_id, 'ai_analysis', metadata={'type': 'id_photo_validation'})

        return result

    except Exception as e:
        logger.error(f"AI vision call failed: {e}")
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": [f"AI validation error: {str(e)}"],
            "face_detected": False
        }

def _call_gemini_vision(ai_settings, image_bytes: bytes, prompt: str) -> dict:
    """Call Gemini Vision API for ID photo validation."""
    from google import genai
    from google.genai import types as genai_types
    import json

    client = genai.Client(api_key=ai_settings.google_api_key)
    image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    response = client.models.generate_content(
        model='gemini-3.1-flash-lite-preview',
        contents=[prompt, image_part]
    )

    # Parse JSON response
    text = response.text.strip()
    # Remove markdown code blocks if present
    if text.startswith('```'):
        text = text.split('\n', 1)[1]
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0]
        text = text.strip()

    return json.loads(text)

def _call_claude_vision(ai_settings, image_bytes: bytes, prompt: str) -> dict:
    """Call Claude Vision API for ID photo validation."""
    import anthropic
    import base64
    import json

    client = anthropic.Anthropic(api_key=ai_settings.claude_api_key)

    response = client.messages.create(
        model="claude-haiku-4-5-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(image_bytes).decode()
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )

    return json.loads(response.content[0].text)

def _call_openai_vision(ai_settings, image_bytes: bytes, prompt: str) -> dict:
    """Call OpenAI Vision API for ID photo validation."""
    import openai
    import base64
    import json

    client = openai.OpenAI(api_key=ai_settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                    }
                }
            ]
        }]
    )

    return json.loads(response.choices[0].message.content)
