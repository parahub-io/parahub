"""Universal video attachment endpoints (PeerTube integration)."""
import logging
import uuid as uuid_mod

from ninja import Router
from pydantic import BaseModel
from typing import List, Optional

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Videos"])


class VideoResponse(BaseModel):
    id: str
    object_type: str = 'object_video'
    object_id: str
    peertube_uuid: str
    peertube_url: str
    title: str
    description: str = ''
    duration_seconds: Optional[int] = None
    thumbnail_url: str = ''
    embed_url: str = ''
    hls_url: str = ''
    order: int = 0
    uploaded_by_id: str
    is_published: bool = False


class VideoCreatePayload(BaseModel):
    object_id: str
    peertube_uuid: str
    title: str
    description: str = ''
    order: int = 0


class UploadConfigResponse(BaseModel):
    upload_url: str
    channel_id: Optional[int] = None
    channel_name: Optional[str] = None
    video_quota: int = 0
    video_quota_used: int = 0


class WebhookPayload(BaseModel):
    peertube_uuid: str


def _video_to_response(v) -> VideoResponse:
    return VideoResponse(
        id=v.id,
        object_id=v.object_id,
        peertube_uuid=str(v.peertube_uuid),
        peertube_url=v.peertube_url,
        title=v.title,
        description=v.description,
        duration_seconds=v.duration_seconds,
        thumbnail_url=v.thumbnail_url,
        embed_url=v.embed_url,
        hls_url=v.hls_url,
        order=v.order,
        uploaded_by_id=str(v.uploaded_by_id),
        is_published=v.is_published,
    )


@router.post("/", auth=ProfileAuth(), response={201: VideoResponse, 400: dict})
@ratelimit(group='core:create_video', key=user_or_ip, rate='10/m', method='POST')
def create_video(request, payload: VideoCreatePayload):
    """Register a PeerTube video as an ObjectVideo. Called after frontend uploads to PeerTube."""
    from core.models import ObjectVideo
    from core.services.peertube import get_video, get_video_urls

    profile = request.auth

    if not payload.object_id or len(payload.object_id) != 26:
        return 400, {"error": "Invalid object_id"}

    # Validate UUID format
    try:
        pt_uuid = uuid_mod.UUID(payload.peertube_uuid)
    except ValueError:
        return 400, {"error": "Invalid peertube_uuid"}

    # Check not duplicate
    if ObjectVideo.objects.filter(peertube_uuid=pt_uuid).exists():
        return 400, {"error": "Video already registered"}

    # Max 10 videos per object
    if ObjectVideo.objects.filter(object_id=payload.object_id).count() >= 10:
        return 400, {"error": "Maximum 10 videos per object"}

    # Fetch metadata from PeerTube
    video_data = get_video(str(pt_uuid))
    urls = get_video_urls(video_data) if video_data else {}

    video = ObjectVideo.objects.create(
        object_id=payload.object_id,
        peertube_uuid=pt_uuid,
        peertube_url=urls.get('peertube_url', ''),
        title=payload.title or (video_data.get('name', '') if video_data else ''),
        description=payload.description or (video_data.get('description', '') or '' if video_data else ''),
        duration_seconds=video_data.get('duration') if video_data else None,
        thumbnail_url=urls.get('thumbnail_url', ''),
        embed_url=urls.get('embed_url', ''),
        hls_url=urls.get('hls_url', ''),
        order=payload.order,
        uploaded_by=profile,
        is_published=video_data.get('state', {}).get('id') == 1 if video_data else False,
    )

    logger.info(f"Video registered: {video.id} (PeerTube {pt_uuid}) for object {payload.object_id} by {profile.id}")
    return 201, _video_to_response(video)


@router.get("/", auth=None, response=List[VideoResponse])
@ratelimit(group='core:list_videos', key='ip', rate='60/m')
def list_videos(request, object_id: str):
    """List all videos for a given object_id."""
    from core.models import ObjectVideo

    if not object_id or len(object_id) != 26:
        return []

    return [_video_to_response(v) for v in ObjectVideo.objects.filter(object_id=object_id)]


@router.get("/{video_id}/", auth=None, response={200: VideoResponse, 404: dict})
@ratelimit(group='core:get_video', key='ip', rate='60/m')
def get_video_detail(request, video_id: str):
    """Get a single video with metadata."""
    from core.models import ObjectVideo

    try:
        video = ObjectVideo.objects.get(id=video_id)
    except ObjectVideo.DoesNotExist:
        return 404, {"error": "Video not found"}

    return 200, _video_to_response(video)


@router.delete("/{video_id}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='core:delete_video', key=user_or_ip, rate='10/m', method='DELETE')
def delete_video(request, video_id: str):
    """Delete a video. Removes from PeerTube and DB. Only uploader can delete."""
    from core.models import ObjectVideo
    from core.services.peertube import delete_video as pt_delete

    try:
        video = ObjectVideo.objects.get(id=video_id)
    except ObjectVideo.DoesNotExist:
        return 404, {"error": "Video not found"}

    if video.uploaded_by_id != request.auth.id:
        return 403, {"error": "Only uploader can delete videos"}

    # Delete from PeerTube
    pt_delete(str(video.peertube_uuid))

    video.delete()
    logger.info(f"Video deleted: {video_id} (PeerTube {video.peertube_uuid})")
    return 200, {"success": True}


@router.post("/upload-config/", auth=ProfileAuth(), response={200: UploadConfigResponse, 400: dict})
@ratelimit(group='core:video_upload_config', key=user_or_ip, rate='10/m', method='POST')
def get_upload_config(request):
    """Get PeerTube upload endpoint and channel info for the current user."""
    from core.services.peertube import get_user_upload_config

    config = get_user_upload_config(request.auth)
    if not config:
        return 400, {"error": "PeerTube user not found. Login to video.parahub.io first."}

    return 200, UploadConfigResponse(**config)


class UploadResponse(BaseModel):
    peertube_uuid: str
    title: str


@router.post("/upload/", auth=ProfileAuth(), response={200: UploadResponse, 400: dict, 500: dict})
@ratelimit(group='core:video_upload', key=user_or_ip, rate='5/m', method='POST')
def upload_video(request):
    """
    Proxy upload: frontend → Django → PeerTube (localhost).
    Accepts multipart form with 'videofile' + optional 'name'.
    Uses admin token + user's PeerTube channel.
    Streams via MultipartEncoder to avoid loading entire file into memory.
    """
    import requests as req
    from requests_toolbelt import MultipartEncoder
    from core.services.peertube import get_user_upload_config, get_admin_token, PEERTUBE_INTERNAL_URL

    profile = request.auth

    videofile = request.FILES.get('videofile')
    if not videofile:
        return 400, {"error": "No videofile provided"}

    # 4GB limit
    if videofile.size > 4 * 1024 * 1024 * 1024:
        return 400, {"error": "File too large (max 4GB)"}

    # Get user's PeerTube channel
    config = get_user_upload_config(profile)
    if not config or not config.get('channel_id'):
        return 400, {"error": "PeerTube user not found. Login to video.parahub.io first."}

    token = get_admin_token()
    if not token:
        return 500, {"error": "PeerTube auth failed"}

    name = request.POST.get('name', videofile.name or 'Untitled')

    try:
        videofile.seek(0)
        encoder = MultipartEncoder(fields={
            'channelId': str(config['channel_id']),
            'name': name[:120],
            'privacy': '1',
            'videofile': (videofile.name or 'video.mp4', videofile.file, videofile.content_type or 'video/mp4'),
        })
        resp = req.post(
            f'{PEERTUBE_INTERNAL_URL}/api/v1/videos/upload',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': encoder.content_type,
            },
            data=encoder,
            timeout=600,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"PeerTube upload failed: {resp.status_code} {resp.text[:200]}")
            return 500, {"error": "PeerTube upload failed"}

        data = resp.json()
        pt_uuid = data.get('video', {}).get('uuid', '')
        pt_name = data.get('video', {}).get('name', name)

        logger.info(f"Video uploaded to PeerTube: {pt_uuid} by {profile.local_name} channel={config['channel_id']}")
        return 200, UploadResponse(peertube_uuid=pt_uuid, title=pt_name)

    except Exception as e:
        logger.error(f"PeerTube upload error: {e}")
        return 500, {"error": "Upload failed"}


@router.post("/sync/{video_id}/", auth=ProfileAuth(), response={200: VideoResponse, 404: dict})
@ratelimit(group='core:sync_video', key=user_or_ip, rate='10/m', method='POST')
def sync_video(request, video_id: str):
    """Sync video metadata from PeerTube (refresh duration, thumbnail, HLS URL, etc.)."""
    from core.models import ObjectVideo
    from core.services.peertube import sync_video_metadata

    try:
        video = ObjectVideo.objects.get(id=video_id)
    except ObjectVideo.DoesNotExist:
        return 404, {"error": "Video not found"}

    sync_video_metadata(video)
    video.refresh_from_db()
    return 200, _video_to_response(video)
