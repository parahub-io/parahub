"""Universal photo upload and retrieval endpoints."""
from ninja import Router, UploadedFile, Form
from pydantic import BaseModel
from typing import List
import logging
import sys
from io import BytesIO

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from parahub.endpoints.ai_vision import _is_valid_image_magic

logger = logging.getLogger(__name__)

router = Router(tags=["Photos"])


class PhotoResponse(BaseModel):
    id: str
    object_type: str = 'object_photo'
    object_id: str
    url: str
    order: int
    caption: str
    uploaded_by_id: str


@router.post("/", auth=ProfileAuth(), response={201: PhotoResponse, 400: dict})
@ratelimit(group='core:upload_photo', key=user_or_ip, rate='10/m', method='POST')
def upload_photo(request, image: UploadedFile, object_id: str = Form(...), order: int = Form(0), caption: str = Form("")):
    """Upload a photo for any ULID-identified object. Max 20 per object."""
    from PIL import Image
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from core.models import ObjectPhoto

    profile = request.auth

    if not object_id or len(object_id) != 26:
        return 400, {"error": "Invalid object_id"}

    if ObjectPhoto.objects.filter(object_id=object_id).count() >= 20:
        return 400, {"error": "Maximum 20 photos per object"}

    if not image.content_type.startswith('image/') or not _is_valid_image_magic(image.file):
        return 400, {"error": "File must be an image"}

    if image.size > 15 * 1024 * 1024:
        return 400, {"error": "Image size must be less than 15MB"}

    try:
        img = Image.open(image.file)

        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        max_size = (1600, 1600)
        if img.width > max_size[0] or img.height > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        img_format = 'JPEG' if img.mode == 'RGB' else 'PNG'
        img.save(output, format=img_format, quality=85, optimize=True)
        output.seek(0)

        file_name = f"{object_id}_{order}.{img_format.lower()}"
        django_file = InMemoryUploadedFile(
            output, 'ImageField', file_name,
            f'image/{img_format.lower()}', sys.getsizeof(output), None
        )

        photo = ObjectPhoto(
            object_id=object_id,
            order=order,
            caption=caption,
            uploaded_by=profile,
        )
        photo.image.save(file_name, django_file, save=True)

        logger.info(f"Photo uploaded for object {object_id} by {profile.id}")

        return 201, PhotoResponse(
            id=photo.id,
            object_id=photo.object_id,
            url=photo.image.url,
            order=photo.order,
            caption=photo.caption,
            uploaded_by_id=str(profile.id),
        )

    except Exception as e:
        logger.error(f"Error uploading photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload photo: {str(e)}"}


@router.get("/", auth=None, response=List[PhotoResponse])
@ratelimit(group='core:list_photos', key='ip', rate='60/m')
def list_photos(request, object_id: str):
    """List all photos for a given object_id."""
    from core.models import ObjectPhoto

    if not object_id or len(object_id) != 26:
        return []

    return [
        PhotoResponse(
            id=p.id,
            object_id=p.object_id,
            url=p.image.url,
            order=p.order,
            caption=p.caption,
            uploaded_by_id=str(p.uploaded_by_id),
        )
        for p in ObjectPhoto.objects.filter(object_id=object_id)
    ]


@router.delete("/{photo_id}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='core:delete_photo', key=user_or_ip, rate='30/m', method='DELETE')
def delete_photo(request, photo_id: str):
    """Delete a photo. Only uploader can delete."""
    from core.models import ObjectPhoto

    try:
        photo = ObjectPhoto.objects.get(id=photo_id)
    except ObjectPhoto.DoesNotExist:
        return 404, {"error": "Photo not found"}

    if photo.uploaded_by_id != request.auth.id:
        return 403, {"error": "Only uploader can delete photos"}

    photo.image.delete(save=False)
    photo.delete()
    return 200, {"success": True}
