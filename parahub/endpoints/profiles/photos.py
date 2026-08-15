"""
Avatar, ID photo and verification photo endpoints + AI photo validation.
"""


from ninja import File, Form
from ninja.errors import HttpError
from ninja.files import UploadedFile
from typing import List, Optional
from pydantic import BaseModel
import logging
import time

from parahub.auth import ProfileAuth
from parahub.endpoints.matrix_auth import spawn_matrix_profile_sync
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

        spawn_matrix_profile_sync(profile)

        logger.info(f"Avatar uploaded for profile {profile.id}")

        return PhotoUploadResponse(url=profile.avatar_url)

    except Exception as e:
        logger.error(f"Error uploading avatar: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload avatar: {str(e)}"}

@profile_router.post("/me/avatar/stylize/", response={200: dict, 400: dict, 429: dict, 503: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:stylize_avatar', key=user_or_ip, rate='3/m', method='POST')
def stylize_avatar(request, source: str = 'avatar', image: Optional[UploadedFile] = File(None)):
    """
    Redraw a photo in the brand editorial-watercolor avatar style (opt-in).

    Source: the uploaded `image`; else the WoT verification photo when
    `source=verification`; else the profile's current avatar.
    Returns a base64 preview — nothing is applied; the client uploads the
    preview through POST /me/avatar/ if the user accepts it.

    Quota: 2 restyles per ISO week per account.
    """
    import base64

    from parahub.services.avatar_stylizer import stylize, StylizeError
    from parahub.services.quota import QuotaService

    profile = request.auth_profile

    quota_info = QuotaService.check_quota(profile.account_id, 'avatar_stylize')
    if quota_info['remaining'] <= 0:
        return 429, {"error": "Weekly avatar stylize quota exceeded", "quota": quota_info}

    if image is not None:
        if not image.content_type.startswith('image/'):
            return 400, {"error": "File must be an image"}
        if image.size > 10 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 10MB"}
        source_bytes = image.read()
    elif source == 'verification':
        from identity.models import ProfileVerificationPhoto

        vp = ProfileVerificationPhoto.objects.filter(profile=profile).first()
        if not vp or not vp.photo:
            return 400, {"error": "No verification photo — upload one first"}
        try:
            with vp.photo.open('rb') as f:
                source_bytes = f.read()
        except Exception:
            logger.error(f"Verification photo unreadable for profile {profile.id}", exc_info=True)
            return 400, {"error": "Verification photo is not readable — upload a photo instead"}
    elif profile.avatar:
        try:
            with profile.avatar.open('rb') as f:
                source_bytes = f.read()
        except Exception:
            logger.error(f"Avatar file unreadable for profile {profile.id}", exc_info=True)
            return 400, {"error": "Current avatar is not readable — upload a photo instead"}
    else:
        return 400, {"error": "No source photo: upload an image or set an avatar first"}

    try:
        result = stylize(source_bytes, profile=profile,
                         source='upload' if image is not None else source)
    except StylizeError as e:
        logger.warning(f"Avatar stylize failed for profile {profile.id}: {e}")
        return 503, {"error": "Stylization unavailable — try a different photo or try again later"}
    except Exception as e:
        logger.error(f"Avatar stylize crashed for profile {profile.id}: {e}", exc_info=True)
        return 503, {"error": "Stylization unavailable — try again later"}

    quota_info = QuotaService.consume_quota(
        profile.account_id, 'avatar_stylize', metadata={'profile_id': profile.id}
    )

    return 200, {
        "preview": f"data:image/jpeg;base64,{base64.b64encode(result).decode()}",
        "quota": quota_info,
    }

@profile_router.get("/me/avatar/stylize/prompt/", response={200: dict}, auth=ProfileAuth())
def stylize_prompt(request):
    """The exact prompt the restyler sends, for members who want to run it
    themselves — quota spent, or simply their own tool and their own bill.

    Served from the service module rather than copied into the client: a member
    pasting this into another model must get the text the product actually
    sends, and a hardcoded frontend copy would drift the first time the prompt
    is tuned. Free to call — it costs nothing and gates nothing.

    Deliberately no model id: which model we happen to bill is our operational
    detail, and naming it beside a copy-paste prompt reads as a recommendation.
    The output size is here because it is guidance the member can act on.
    """
    from parahub.services import avatar_stylizer

    return 200, {
        "image_size": avatar_stylizer.IMAGE_SIZE,
        "prompt": avatar_stylizer.PROMPT,
    }

@profile_router.delete("/me/avatar/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_avatar', key=user_or_ip, rate='10/m', method='DELETE')
def delete_avatar(request):
    """Delete avatar photo for the authenticated user."""
    try:
        profile = request.auth_profile

        if profile.avatar:
            profile.avatar.delete(save=True)
            spawn_matrix_profile_sync(profile)
            logger.info(f"Avatar deleted for profile {profile.id}")
            return {"success": True}
        else:
            return {"success": True, "message": "No avatar to delete"}

    except Exception as e:
        logger.error(f"Error deleting avatar: {e}", exc_info=True)
        raise HttpError(500, "Failed to delete avatar")

def _save_id_photo(profile, img) -> PhotoUploadResponse:
    """
    Resize a PIL image to the Para-ID format, run the advisory AI validation
    and store it as the profile's id_photo. Shared by manual upload and the
    derive-from-verification-photo flow.
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    import sys

    # Convert to RGB if necessary
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')
    elif img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background

    # Resize maintaining aspect ratio (max 600x800)
    img.thumbnail((600, 800), Image.Resampling.LANCZOS)

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

    logger.info(f"ID photo saved for profile {profile.id}, verified={verified}")

    return PhotoUploadResponse(
        # id_photo is private — hand back the gated endpoint, not the raw media path
        url=f"/api/v1/profiles/{profile.id}/id-photo/",
        verified=verified,
        verification_issues=verification_issues if verification_issues else None
    )


def _face_crop_3x4(img):
    """
    Crop a PIL image to a 3:4 document portrait around the detected face.

    Deterministic (dlib HOG detector) — the Para-ID card must keep real photo
    pixels, so no generative model is involved. Falls back to a centered 3:4
    crop when no face is found.
    """
    import numpy as np
    import face_recognition

    rgb = img.convert('RGB')
    width, height = rgb.size
    locations = face_recognition.face_locations(np.array(rgb), model='hog')

    if locations:
        top, right, bottom, left = locations[0]
        face_h = bottom - top
        center_x = (left + right) / 2
        # The detector box is forehead-to-chin: leave headroom for hair above
        # and shoulders below so the crop reads as a document portrait
        crop_h = face_h * 2.4
        crop_top = top - face_h * 0.7
    else:
        crop_h = float(height)
        crop_top = 0.0
        center_x = width / 2

    crop_w = crop_h * 0.75
    # Shrink to fit the source while keeping 3:4
    scale = min(1.0, width / crop_w, height / crop_h)
    crop_w *= scale
    crop_h *= scale
    crop_left = min(max(center_x - crop_w / 2, 0), width - crop_w)
    crop_top = min(max(crop_top, 0), height - crop_h)

    return rgb.crop((
        round(crop_left), round(crop_top),
        round(crop_left + crop_w), round(crop_top + crop_h),
    ))


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

    try:
        profile = request.auth_profile

        # Validate file type
        if not image.content_type.startswith('image/'):
            return 400, {"error": "File must be an image"}

        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 10MB"}

        return _save_id_photo(profile, Image.open(image.file))

    except Exception as e:
        logger.error(f"Error uploading ID photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload ID photo: {str(e)}"}


@profile_router.post("/me/id-photo/derive/", response={200: PhotoUploadResponse, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:derive_id_photo', key=user_or_ip, rate='5/m', method='POST')
def derive_id_photo(request):
    """
    Build the Para-ID photo from the profile's WoT verification photo.

    One source photo drives all profile imagery: the verification photo is
    face-cropped to a 3:4 document portrait (deterministic, no AI redraw)
    and stored as id_photo through the same path as a manual upload.
    """
    from PIL import Image
    from io import BytesIO
    from identity.models import ProfileVerificationPhoto

    profile = request.auth_profile

    vp = ProfileVerificationPhoto.objects.filter(profile=profile).first()
    if not vp or not vp.photo:
        return 400, {"error": "No verification photo — upload one first"}

    try:
        with vp.photo.open('rb') as f:
            img = Image.open(BytesIO(f.read()))
        return _save_id_photo(profile, _face_crop_3x4(img))
    except Exception as e:
        logger.error(f"Error deriving ID photo for profile {profile.id}: {e}", exc_info=True)
        return 400, {"error": "Failed to derive ID photo from the verification photo"}

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

    Every fetch by someone other than the owner is recorded in IdPhotoAccess: the
    gate lets in the whole verified membership, so the subject gets a trail of who
    actually looked (read back via /me/id-photo/access-log/). Callers must fetch
    on intent — a page that pre-loads the blob writes a row for a visit that never
    opened the photo, which makes the log lie.
    """
    from django.http import HttpResponse

    from identity.models import IdPhotoAccess

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

    if not is_owner:
        IdPhotoAccess.objects.create(
            viewer=viewer, target_profile=target,
            ip_address=request.META.get('REMOTE_ADDR') or None,
        )
        logger.info(f"ID photo viewed: {viewer.id} -> {target.id}")

    # X-Accel-Redirect for nginx (serves from internal /media/private/)
    response = HttpResponse(content_type='image/jpeg')
    response['X-Accel-Redirect'] = f'/media/{target.id_photo.name}'
    response['Cache-Control'] = 'no-store, no-cache'
    return response


@profile_router.get("/me/id-photo/access-log/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:id_photo_access_log', key=user_or_ip, rate='60/m')
def id_photo_access_log(request):
    """
    Who opened the owner's Para-ID photo, newest first.

    The Para-ID photo has no view notification (see identity.IdPhotoAccess), so
    this log is the whole of the subject's visibility into who looked.
    """
    from identity.models import IdPhotoAccess

    return _grouped_access_log(IdPhotoAccess, request.auth_profile, 'id_photo_access')

PHOTO_STATEMENT_MAX_AGE = 300  # seconds


def _verify_photo_owner_signature(profile, upload_hash: str, statement: str, signature: str) -> bool:
    """Whether this upload carries a fresh claim over these exact bytes, signed by the profile's own key.

    Answers the question the face-distance threshold only guesses at: was the
    photo replaced by the person who holds this profile's identity? A member
    swapping their own portrait proves it in one signature and is spared a
    re-confirmation round (see `face_dedup.requires_reconfirmation`).

    No statement/signature = unsigned upload, not an error: a member may have no
    PGP key yet. But a signature that does not hold up raises — a mismatch means
    tampering or a broken client, and quietly downgrading it to "unsigned" would
    turn every failure of this check into a silent one.
    """
    import json
    from datetime import datetime, timezone as dt_timezone

    if not statement or not signature:
        return False

    if not profile.pgp_public_key:
        raise HttpError(400, "Signed upload requires a PGP key on the profile")

    try:
        submitted = json.loads(statement)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid photo statement JSON")

    timestamp = submitted.get('timestamp')
    try:
        age = (datetime.now(dt_timezone.utc) - datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))).total_seconds()
    except (ValueError, AttributeError, TypeError):
        raise HttpError(400, "Invalid photo statement timestamp")

    if age > PHOTO_STATEMENT_MAX_AGE or age < -60:
        raise HttpError(400, "Photo statement expired — please try the upload again")

    expected = {
        "action": "verification_photo_upload",
        "profile_id": profile.id,
        "profile_hna": profile.hna,
        "sha256": upload_hash,
        "timestamp": timestamp,
    }
    if submitted != expected:
        raise HttpError(400, "Photo statement does not match the uploaded file")

    from parahub.crypto.pgp import pgp_crypto
    try:
        is_valid = pgp_crypto.verify_signature(
            message=statement,
            signature_data=signature,
            public_key_data=profile.pgp_public_key,
        )
    except Exception as e:
        logger.error(f"Verification photo signature check failed for {profile.id}: {e}", exc_info=True)
        raise HttpError(400, "Could not verify the photo signature")

    if not is_valid:
        raise HttpError(400, "Invalid PGP signature on the photo upload")

    return True


@profile_router.post("/me/verification-photo/", response={200: dict, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profile:verification_photo', key=user_or_ip, rate='5/h', method='POST')
def upload_verification_photo(request, image: UploadedFile, biometric_consent: bool = Form(False),
                              photo_statement: str = Form(''), photo_signature: str = Form('')):
    """
    Upload verification photo for WoT face deduplication.

    Requires explicit GDPR biometric consent.
    Extracts face embedding and checks for duplicates against verified profiles.

    `photo_statement` + `photo_signature` are the client's PGP signature over the
    SHA256 of the uploaded bytes. Signed, a replacement is the member's own act
    and nothing else follows; unsigned, replacing a face under standing
    verifications opens a re-confirmation round.
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from django.utils import timezone
    from identity.models import ProfileVerificationPhoto
    from identity.services.face_dedup import (
        extract_embedding, serialize_embedding, check_duplicate,
        requires_reconfirmation, compute_photo_hash, compute_face_fingerprint,
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

        # The client signs the bytes it picked, so hash them before PIL touches
        # anything — the re-encoded JPEG below is ours, not what was signed.
        raw_bytes = image.read()
        owner_signed = _verify_photo_owner_signature(
            profile, compute_photo_hash(raw_bytes), photo_statement, photo_signature
        )

        # Process image with PIL
        img = Image.open(BytesIO(raw_bytes))
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
        try:
            existing = ProfileVerificationPhoto.objects.get(profile=profile)
            old_embedding = bytes(existing.face_embedding)

            reconfirmation_needed = requires_reconfirmation(
                profile.id, old_embedding, embedding_bytes, owner_signed=owner_signed
            )

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
                existing.mark_face_changed()
            elif owner_signed:
                # Signing also settles a round an earlier unsigned upload opened.
                existing.clear_reconfirmation()

            file_name = f"{profile.id}_vp.jpg"
            django_file = InMemoryUploadedFile(
                output, 'ImageField', file_name, 'image/jpeg', sys.getsizeof(output), None
            )
            existing.photo.save(file_name, django_file, save=False)
            existing.save()

        except ProfileVerificationPhoto.DoesNotExist:
            # Create new record. No stored embedding to compare against, so an
            # already-verified profile lands in a re-confirmation round unless the
            # upload is signed — the record may be gone because it was deleted a
            # moment ago.
            reconfirmation_needed = requires_reconfirmation(
                profile.id, None, embedding_bytes, owner_signed=owner_signed
            )

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
            if reconfirmation_needed:
                existing.mark_face_changed()
            existing.photo.save(file_name, django_file, save=False)
            existing.save()

        logger.info(f"Verification photo uploaded for profile {profile.id}, reconfirmation_needed={existing.reconfirmation_needed}")

        return {
            "success": True,
            "face_detected": True,
            # The row's state, not this upload's verdict: a round opened by an
            # earlier upload stays open until it is confirmed.
            "reconfirmation_needed": existing.reconfirmation_needed,
            "reconfirmation_count": existing.reconfirmation_count,
            "owner_signed": owner_signed,
            "quality_warnings": quality_warnings,
            "face_fingerprint": compute_face_fingerprint(embedding),
        }

    except HttpError as e:
        # Rejected on its own terms (a signature that doesn't hold up) — keep the
        # reason instead of folding it into the generic failure below.
        logger.warning(f"Verification photo 400 for profile {request.auth_profile.id}: {e}")
        return 400, {"error": str(e)}
    except Exception as e:
        logger.error(f"Error uploading verification photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload verification photo: {str(e)}"}

@profile_router.delete("/me/verification-photo/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_verification_photo', key=user_or_ip, rate='10/m', method='DELETE')
def delete_verification_photo(request):
    """
    Delete verification photo and face embedding (GDPR right to erasure).

    Existing verifications are left alone — erasing biometric data is a privacy
    right, not a withdrawal from the Web of Trust. What it does cost the profile
    is the ability to receive new verifications (verifiers have no photo to match
    against) and a clean re-upload: uploading again with verifications standing
    opens a re-confirmation round, since the embedding that would have proved the
    face unchanged is gone.
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

@profile_router.get("/me/verification-photo/file/", auth=ProfileAuth())
@ratelimit(group='profiles:my_verification_photo', key=user_or_ip, rate='60/m')
def my_verification_photo(request):
    """
    Serve the owner their own WoT verification photo (private media, X-Accel-Redirect).

    Verifiers read the photo through /wot/verification-photo/{profile_id}/; this is the
    owner-only twin, so the profile page can show which photo is actually stored — the
    WoT photo is otherwise invisible to the person it belongs to.
    """
    from django.http import HttpResponse
    from identity.models import ProfileVerificationPhoto

    profile = request.auth_profile

    try:
        vp = ProfileVerificationPhoto.objects.get(profile=profile)
    except ProfileVerificationPhoto.DoesNotExist:
        raise HttpError(404, "No verification photo")

    if not vp.photo:
        raise HttpError(404, "No verification photo")

    response = HttpResponse(content_type='image/jpeg')
    response['X-Accel-Redirect'] = f'/media/{vp.photo.name}'
    response['Cache-Control'] = 'no-store, no-cache'
    return response

def _grouped_access_log(access_model, profile, object_type: str) -> dict:
    """Who opened one of `profile`'s private photos, newest first.

    Shared by the verification-photo and Para-ID logs — same table shape, same
    reading. Grouped per viewer per day: one session reopens a photo several
    times and a raw feed of those would bury the next viewer. Every single
    access stays in the table for a forensic/legal read.
    """
    from django.db.models import Count, Max
    from django.db.models.functions import TruncDate

    from identity.models import Profile as ProfileModel

    groups = list(
        access_model.objects
        .filter(target_profile=profile)
        .annotate(day=TruncDate('created_at'))
        .values('viewer_id', 'day')
        .annotate(views=Count('id'), last_at=Max('created_at'))
        .order_by('-last_at')[:50]
    )

    viewers = {
        p.id: p for p in ProfileModel.objects.filter(
            id__in={g['viewer_id'] for g in groups}
        ).select_related('instance')
    }

    return {
        "accesses": [
            {
                "object_type": object_type,
                "viewer_id": g['viewer_id'],
                "viewer_hna": viewers[g['viewer_id']].hna if g['viewer_id'] in viewers else '',
                "viewer_display_name": (
                    viewers[g['viewer_id']].display_name or viewers[g['viewer_id']].local_name
                ) if g['viewer_id'] in viewers else '',
                "viewed_at": g['last_at'].isoformat(),
                "views": g['views'],
            }
            for g in groups
        ]
    }

@profile_router.get("/me/verification-photo/access-log/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:verification_photo_access_log', key=user_or_ip, rate='60/m')
def verification_photo_access_log(request):
    """
    Who opened the owner's WoT verification photo, newest first.

    The counterpart to the notification: GDPR Art.15(1)(c) recipients, readable at
    any time. Rows outlive the photo itself, so this stays answerable after erasure.
    """
    from identity.models import VerificationPhotoAccess

    return _grouped_access_log(
        VerificationPhotoAccess, request.auth_profile, 'verification_photo_access')

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

    # Call AI provider. `provider` holds a tier alias ('gemini-flash-lite',
    # 'haiku', 'gpt-5-nano', …), never a model id — match on the family.
    try:
        claude_alias = ai_settings.provider.startswith('claude') or ai_settings.provider == 'haiku'
        if ai_settings.provider.startswith('gemini'):
            result = _call_gemini_vision(ai_settings, image_bytes, prompt, profile)
        elif claude_alias and ai_settings.claude_api_key:
            result = _call_claude_vision(ai_settings, image_bytes, prompt, profile)
        elif ai_settings.provider.startswith('gpt') and ai_settings.openai_api_key:
            result = _call_openai_vision(ai_settings, image_bytes, prompt, profile)
        else:
            # Gemini is the fallback: a tier with no key configured must still
            # produce a verdict rather than an error the uploader can't act on.
            result = _call_gemini_vision(ai_settings, image_bytes, prompt, profile)

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

def _call_gemini_vision(ai_settings, image_bytes: bytes, prompt: str, profile=None) -> dict:
    """Call Gemini Vision API for ID photo validation.

    Model follows the configured tier rather than a local constant, so the admin
    dropdown means the same thing here as it does for item analysis. A non-Gemini
    alias reaching this fallback resolves to the cheap tier.
    """
    from google import genai
    from google.genai import types as genai_types
    from parahub.models import AIUsageLog
    from parahub.services import ai_usage
    from parahub.services.vision_ai import gemini_model_for
    import json

    client = genai.Client(api_key=ai_settings.google_api_key)
    image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    model = gemini_model_for(ai_settings.provider)
    started = time.monotonic()
    response = client.models.generate_content(
        model=model,
        contents=[prompt, image_part]
    )
    ai_usage.record_gemini(
        AIUsageLog.KIND_ID_PHOTO_VALIDATION, model, response, profile=profile,
        duration_ms=int((time.monotonic() - started) * 1000),
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

def _call_claude_vision(ai_settings, image_bytes: bytes, prompt: str, profile=None) -> dict:
    """Call Claude Vision API for ID photo validation."""
    import anthropic
    import base64
    import json

    from parahub.models import AIUsageLog
    from parahub.services import ai_usage

    client = anthropic.Anthropic(api_key=ai_settings.claude_api_key)

    # Undated alias, matching the categorization provider and the price table —
    # the dated id that used to be here ("…-20250514") belongs to another model.
    model = "claude-haiku-4-5"
    started = time.monotonic()
    response = client.messages.create(
        model=model,
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
    ai_usage.record_tokens(
        AIUsageLog.KIND_ID_PHOTO_VALIDATION, model,
        getattr(response.usage, 'input_tokens', 0) or 0,
        getattr(response.usage, 'output_tokens', 0) or 0,
        profile=profile, duration_ms=int((time.monotonic() - started) * 1000),
    )

    return json.loads(response.content[0].text)

def _call_openai_vision(ai_settings, image_bytes: bytes, prompt: str, profile=None) -> dict:
    """Call OpenAI Vision API for ID photo validation."""
    import openai
    import base64
    import json

    from parahub.models import AIUsageLog
    from parahub.services import ai_usage

    client = openai.OpenAI(api_key=ai_settings.openai_api_key)

    # The configured tier alias IS the OpenAI model id ('gpt-5-nano' / 'gpt-5-mini'),
    # so the dropdown means the same thing here as it does for item analysis.
    model = ai_settings.provider
    params = {
        "model": model,
        "messages": [{
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
        }],
    }
    # GPT-5 counts reasoning against the completion budget and rejects max_tokens.
    # The budget has to be generous for a reasoning model: nano has been measured
    # spending >1200 tokens thinking, and a budget it exhausts before answering
    # returns empty content — a verdict the uploader never gets.
    if model.startswith('gpt-5'):
        params['max_completion_tokens'] = 4096
    else:
        params['max_tokens'] = 500

    started = time.monotonic()
    response = client.chat.completions.create(**params)
    ai_usage.record_tokens(
        AIUsageLog.KIND_ID_PHOTO_VALIDATION, model,
        getattr(response.usage, 'prompt_tokens', 0) or 0,
        getattr(response.usage, 'completion_tokens', 0) or 0,
        profile=profile, duration_ms=int((time.monotonic() - started) * 1000),
    )

    return json.loads(response.choices[0].message.content)
