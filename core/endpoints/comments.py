"""Universal comment endpoints for any ULID-bearing entity."""
from ninja import Router, Schema
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Comments"])


class CommentInput(Schema):
    object_id: str
    text: str


class CommentResponse(BaseModel):
    id: str
    object_type: str = 'object_comment'
    object_id: str
    text: str
    author_id: str
    author_name: str = ""
    author_display_name: str = ""
    created_at: datetime


@router.post("/", auth=ProfileAuth(), response={201: CommentResponse, 400: dict})
@ratelimit(group='core:create_comment', key=user_or_ip, rate='20/m', method='POST')
def create_comment(request, data: CommentInput):
    """Create a comment on any ULID-identified object."""
    from core.models import ObjectComment

    if not data.object_id or len(data.object_id) != 26:
        return 400, {"error": "Invalid object_id"}

    text = data.text.strip()
    if not text or len(text) > 2000:
        return 400, {"error": "Text must be 1-2000 characters"}

    # Civic opinion polls: comments only at local scopes (municipality/parish) —
    # country/region political polls stay commentless (PK/civic-polls-system.md, U4)
    from governance.models import Poll, PollContext
    target_poll = Poll.objects.filter(id=data.object_id).select_related('context').first()
    if target_poll and target_poll.poll_class == Poll.PollClass.OPINION:
        if target_poll.context.context_type == PollContext.ContextType.TERRITORY:
            from geo.models import Territory
            territory = Territory.objects.filter(id=target_poll.context.context_id).first()
            if territory and territory.level in ('country', 'region'):
                return 400, {"error": "Comments are disabled for country/region opinion polls"}

    comment = ObjectComment.objects.create(
        object_id=data.object_id,
        author=request.auth,
        text=text,
    )

    return 201, _format(comment, request.auth, viewer=request.auth)


@router.get("/", auth=None, response=List[CommentResponse])
@ratelimit(group='core:list_comments', key='ip', rate='60/m')
def list_comments(request, object_id: str):
    """List comments for a given object_id."""
    from core.models import ObjectComment

    if not object_id or len(object_id) != 26:
        return []

    return [
        _format(c)
        for c in ObjectComment.objects.filter(object_id=object_id).select_related('author')
    ]


@router.delete("/{comment_id}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='core:delete_comment', key=user_or_ip, rate='30/m', method='DELETE')
def delete_comment(request, comment_id: str):
    """Delete own comment."""
    from core.models import ObjectComment

    try:
        comment = ObjectComment.objects.get(id=comment_id)
    except ObjectComment.DoesNotExist:
        return 404, {"error": "Comment not found"}

    if comment.author_id != request.auth.id:
        return 403, {"error": "Only author can delete"}

    comment.delete()
    return 200, {"success": True}


def _format(comment, author_profile=None, viewer=None) -> CommentResponse:
    author = author_profile or getattr(comment, 'author', None)
    return CommentResponse(
        id=comment.id,
        object_id=comment.object_id,
        text=comment.text,
        author_id=comment.author_id,
        author_name=author.local_name if author else "",
        author_display_name=author.display_name if author and author.name_visible_to(viewer) else "",
        created_at=comment.created_at,
    )
