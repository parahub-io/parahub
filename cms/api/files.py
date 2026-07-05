"""
Post file uploads and AI illustration generation.
"""


from typing import Optional
from datetime import datetime
import logging

from ninja import Schema, File
from ninja.errors import HttpError
from ninja.files import UploadedFile

from django.shortcuts import get_object_or_404

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile
from geo.permissions import SIGNING_ROLES
from core.models import ObjectPhoto, ObjectFile
from ..models import Post

from .base import router
from .posts import _can_edit_post

logger = logging.getLogger(__name__)

class FileOut(Schema):
    id: str
    object_type: str = 'object_file'
    filename: str
    mime_type: str
    size_bytes: int
    url: str
    order: int
    created_at: datetime

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

@router.post('/posts/{post_id}/files/', response=FileOut, auth=ProfileAuth())
@ratelimit(group='cms:upload_file', key=user_or_ip, rate='30/h')
def upload_file(request, post_id: str, file: UploadedFile = File(...)):
    """Upload a file attachment to a post."""
    profile: Profile = request.auth
    post = get_object_or_404(Post, id=post_id)

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to add files to this post")

    if file.size > MAX_FILE_SIZE:
        raise HttpError(400, f"File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)")

    # Validate by file extension (not client-provided Content-Type which can be spoofed)
    import os
    ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.csv'}
    ext = os.path.splitext(file.name or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HttpError(400, f"File type '{ext}' not allowed. Allowed: PDF, DOC, DOCX, XLS, XLSX, TXT, CSV")
    mime = file.content_type or 'application/octet-stream'

    existing_count = ObjectFile.objects.filter(object_id=post.id).count()
    if existing_count >= 20:
        raise HttpError(400, "Maximum 20 files per post")
    obj_file = ObjectFile.objects.create(
        object_id=post.id,
        file=file,
        filename=file.name[:255],
        mime_type=mime,
        size_bytes=file.size,
        uploaded_by=profile,
        order=existing_count,
    )

    return FileOut(
        id=obj_file.id,
        filename=obj_file.filename,
        mime_type=obj_file.mime_type,
        size_bytes=obj_file.size_bytes,
        url=obj_file.file.url,
        order=obj_file.order,
        created_at=obj_file.created_at,
    )

@router.delete('/posts/{post_id}/files/{file_id}/', auth=ProfileAuth())
@ratelimit(group='cms:delete_file', key=user_or_ip, rate='60/h')
def delete_file(request, post_id: str, file_id: str):
    """Delete a file attachment from a post."""
    profile: Profile = request.auth
    post = get_object_or_404(Post, id=post_id)

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized to remove files from this post")

    obj_file = get_object_or_404(ObjectFile, id=file_id, object_id=post.id)
    obj_file.file.delete(save=False)
    obj_file.delete()
    return {'ok': True}

ILLUSTRATION_ALLOWED_SLUG = 'parahub-associacao'

class IllustrationInput(Schema):
    prompt: Optional[str] = None

@router.post('/posts/{post_id}/generate-illustration/', auth=ProfileAuth())
@ratelimit(group='cms:generate_illustration', key=user_or_ip, rate='20/h')
def generate_illustration(request, post_id: str, payload: IllustrationInput = None):
    """Generate a featured image for a post using Gemini Nano Banana Pro.
    Custom prompt or auto-generated from content. Restricted to OWNER/ADMIN of parahub-associacao."""
    profile: Profile = request.auth
    post = get_object_or_404(Post, id=post_id)

    if not _can_edit_post(post, profile):
        raise HttpError(403, "Not authorized")

    # Restrict to parahub-associacao admins
    from geo.models import Establishment, EstablishmentMembership
    try:
        est = Establishment.objects.get(slug=ILLUSTRATION_ALLOWED_SLUG, is_active=True)
    except Establishment.DoesNotExist:
        raise HttpError(403, "Illustration generation not available")

    is_allowed = (
        est.owner_id == profile.id
        or EstablishmentMembership.objects.filter(
            profile=profile, establishment=est, role__in=SIGNING_ROLES
        ).exists()
        or profile.account.is_superuser
    )
    if not is_allowed:
        raise HttpError(403, "Only parahub-associacao admins can generate illustrations")

    # Custom prompt or auto-generate from post content
    custom_prompt = (payload.prompt or '').strip() if payload else ''
    if custom_prompt:
        prompt = f'{custom_prompt}\n\nWide panoramic composition (2:1 aspect ratio). No text overlays on the image.'
    else:
        title = post.title or 'Untitled'
        excerpt = (post.content or '')[:800]
        prompt = (
            f'Generate a wide panoramic illustration (2:1 aspect ratio) for a blog post '
            f'titled "{title}". Context: {excerpt}\n\n'
            f'Style: warm colorful palette, hand-drawn feel, modern editorial illustration. '
            f'No text overlays on the image.'
        )

    try:
        from google import genai
        from google.genai import types as genai_types
        from parahub.models import AISettings

        ai_settings = AISettings.objects.first()
        if not ai_settings or not ai_settings.google_api_key:
            raise HttpError(500, "AI API key not configured")

        client = genai.Client(api_key=ai_settings.google_api_key)
        response = client.models.generate_content(
            model='gemini-3-pro-image-preview',
            contents=[prompt],
            config=genai_types.GenerateContentConfig(
                response_modalities=['IMAGE', 'TEXT'],
            ),
        )

        image_data = None
        for part in response.parts:
            if part.inline_data:
                image_data = part.inline_data.data
                break

        if not image_data:
            raise HttpError(500, "Image generation returned no image (safety filter?)")

        # Save as ObjectPhoto and set as featured image
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded = SimpleUploadedFile('illustration.png', image_data, content_type='image/png')
        photo = ObjectPhoto(object_id=post.id, uploaded_by=profile)
        photo.image.save(f'blog-illust-{post.id[:8]}.png', uploaded, save=True)

        post.featured_image_id = photo.id
        post.save(update_fields=['featured_image_id'])

        logger.info(f"Generated illustration for post {post.id} by {profile.hna}")
        return {
            'ok': True,
            'photo_id': photo.id,
            'url': photo.image.url,
        }

    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Illustration generation failed: {e}")
        raise HttpError(500, f"Generation failed: {str(e)}")
