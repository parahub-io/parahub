"""Universal like/unlike toggle for any ULID-identified object."""

from ninja import Router, Schema
from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from core.models import Like
import logging

logger = logging.getLogger(__name__)

likes_router = Router(tags=["likes"])


class LikeToggleRequest(Schema):
    target_id: str
    target_type: str = "item"


class LikeResponse(Schema):
    liked: bool
    likes_count: int


@likes_router.post("/toggle/", response=LikeResponse, auth=ProfileAuth())
@ratelimit(group='likes:toggle', key=user_or_ip, rate='30/m', method='POST')
def toggle_like(request, data: LikeToggleRequest):
    """Toggle like on any ULID object. Returns new state and count."""
    profile = request.auth_profile
    like, created = Like.objects.get_or_create(
        profile=profile,
        target_id=data.target_id,
        defaults={"target_type": data.target_type},
    )
    if not created:
        like.delete()

    count = Like.objects.filter(target_id=data.target_id).count()
    return {"liked": created, "likes_count": count}


@likes_router.get("/status/{target_id}/", response=LikeResponse, auth=OptionalProfileAuth())
@ratelimit(group='likes:status', key=user_or_ip, rate='60/m')
def like_status(request, target_id: str):
    """Check if current user liked an object + total count."""
    profile = getattr(request, "auth_profile", None)
    liked = False
    if profile:
        liked = Like.objects.filter(profile=profile, target_id=target_id).exists()
    count = Like.objects.filter(target_id=target_id).count()
    return {"liked": liked, "likes_count": count}
