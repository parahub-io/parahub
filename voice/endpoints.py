"""REST surface for voice notes: threads to read, audio to fetch, a voice to own.

Sending is not here — it rides the WebSocket (`voice/consumers.py`), because the
work behind one note is seconds long and this router has a 50 ms budget.

Everything is scoped to the account's **primary** profile, whichever profile is
active in the session. A voiceprint identifies a person; hanging one off a
pseudonymous profile would publish exactly the link that profile exists to hide,
so the whole feature lives on the identity that is already public.
"""

import logging

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel, Field

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from voice.models import VoiceNote
from voice.services import cloning, notes as notes_service

logger = logging.getLogger(__name__)

router = Router(tags=["Voice notes"])

THREAD_PAGE_SIZE = 50


class ConsentInput(BaseModel):
    accepted: bool = Field(..., description="Must be true — an explicit opt-in, never a default")
    consent_text_version: str = Field(default='', max_length=16)


def _voice_profile(request):
    """The profile voice notes belong to: the account's primary one."""
    profile = request.auth_profile
    if profile.is_primary:
        return profile
    from identity.models import Profile
    primary = (
        Profile.objects.select_related('account', 'instance')
        .filter(account=profile.account, is_primary=True).first()
    )
    if primary is None:
        raise HttpError(400, "No primary profile for this account")
    return primary


def _profile_card(profile) -> dict:
    return {
        'id': profile.id,
        'object_type': 'profile',
        'hna': profile.hna,
        'local_name': profile.local_name,
        'display_name': profile.display_name or profile.local_name,
        'avatar_url': profile.avatar_url,
        'language': profile.preferred_language or '',
    }


@router.get("/threads", auth=ProfileAuth())
@ratelimit(group="voice:threads", key=user_or_ip, rate="120/m")
def list_threads(request):
    """Everyone this profile has exchanged notes with, most recent first."""
    me = _voice_profile(request)
    rows = (
        VoiceNote.objects
        .filter(Q(sender=me) | Q(recipient=me))
        .select_related('sender', 'sender__instance', 'recipient', 'recipient__instance')
        .order_by('-id')[:500]
    )

    threads: dict[str, dict] = {}
    for note in rows:
        other = note.recipient if note.sender_id == me.id else note.sender
        thread = threads.get(other.id)
        if thread is None:
            # Rows arrive newest-first, so the first one seen is the last note.
            thread = threads[other.id] = {
                'profile': _profile_card(other),
                'last_note': notes_service.serialize_note(note, viewer=me),
                'unplayed': 0,
            }
        if note.recipient_id == me.id and note.played_at is None:
            thread['unplayed'] += 1

    items = list(threads.values())
    return {
        'items': items,
        'count': len(items),
        'quota': notes_service.quota_for(me).as_dict(),
    }


@router.get("/threads/{profile_ref}", auth=ProfileAuth())
@ratelimit(group="voice:thread", key=user_or_ip, rate="240/m")
def get_thread(request, profile_ref: str, before: str = None):
    """One conversation, oldest last. `before` is the id of the previous page's
    last note (ULID cursor, same convention as the notification feed)."""
    from identity.models import Profile
    from identity.services.blocks import dm_blocked_between_accounts

    me = _voice_profile(request)
    other = (
        Profile.objects.select_related('account', 'instance').filter(id=profile_ref).first()
        or get_object_or_404(
            Profile.objects.select_related('account', 'instance'),
            instance=me.instance, local_name=profile_ref.split('@')[0],
        )
    )
    if other.id == me.id:
        raise HttpError(400, "A conversation needs two people")
    if dm_blocked_between_accounts(me.account_id, other.account_id):
        raise HttpError(403, "This conversation is not available")

    qs = (
        VoiceNote.objects
        .filter(Q(sender=me, recipient=other) | Q(sender=other, recipient=me))
        .order_by('-id')
    )
    if before:
        qs = qs.filter(id__lt=before)
    page = list(qs[:THREAD_PAGE_SIZE])

    return {
        'profile': _profile_card(other),
        'items': [notes_service.serialize_note(n, viewer=me) for n in reversed(page)],
        'count': len(page),
        'has_more': len(page) == THREAD_PAGE_SIZE,
        'quota': notes_service.quota_for(me).as_dict(),
    }


@router.post("/notes/{note_id}/played", auth=ProfileAuth())
@ratelimit(group="voice:played", key=user_or_ip, rate="240/m")
def mark_played(request, note_id: str):
    """Mark a received note as heard. Idempotent — the first play is the record."""
    me = _voice_profile(request)
    note = get_object_or_404(VoiceNote, id=note_id, recipient=me)
    if note.played_at is None:
        note.played_at = timezone.now()
        note.save(update_fields=['played_at', 'updated_at'])
    return {'id': note.id, 'played_at': note.played_at.isoformat()}


@router.get("/notes/{note_id}/audio", auth=ProfileAuth())
@ratelimit(group="voice:audio", key=user_or_ip, rate="240/m")
def get_note_audio(request, note_id: str):
    """Serve one note's mp3 to the two people it belongs to, and nobody else.

    The file lives under `media/private/` (an nginx `internal` location), so the
    only way to it is this handler's X-Accel-Redirect — the same pattern as
    verification photos.
    """
    me = _voice_profile(request)
    note = get_object_or_404(
        VoiceNote.objects.filter(Q(sender=me) | Q(recipient=me)), id=note_id,
    )
    if not note.audio_path:
        raise HttpError(410, "The audio for this note has expired; the text remains")

    response = HttpResponse(content_type='audio/mpeg')
    response['X-Accel-Redirect'] = f"/media/{note.audio_path}"
    response['Content-Disposition'] = f'inline; filename="note-{note.id}.mp3"'
    # The recording never changes, and it is the listener's own message — their
    # browser may keep it, no shared cache may.
    response['Cache-Control'] = 'private, max-age=3600'
    return response


@router.get("/clone", auth=ProfileAuth())
@ratelimit(group="voice:clone", key=user_or_ip, rate="120/m")
def get_clone(request):
    """Consent state, collection progress and clone state for the profile screen."""
    me = _voice_profile(request)
    return {
        **cloning.clone_status(me),
        'thresholds': {
            'stage1_seconds': cloning.STAGE1_SECONDS,
            'stage2_seconds': cloning.STAGE2_SECONDS,
            'max_total_seconds': cloning.MAX_TOTAL_SECONDS,
            'min_sample_seconds': cloning.SAMPLE_MIN_SECONDS,
        },
        'quota': notes_service.quota_for(me).as_dict(),
    }


@router.post("/clone", auth=ProfileAuth())
@ratelimit(group="voice:clone-grant", key=user_or_ip, rate="20/h")
def grant_clone_consent(request, data: ConsentInput):
    """Record an explicit opt-in to voice cloning (GDPR Art. 9(2)(a)).

    Refuses anything but a true `accepted`: consent has to be an act, and an
    endpoint that would accept `false` as a grant is an endpoint that can be
    called by accident.
    """
    if not data.accepted:
        raise HttpError(400, "Consent must be given explicitly")

    me = _voice_profile(request)
    evidence = {
        'ip': request.META.get('REMOTE_ADDR', ''),
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:300],
        'locale': request.headers.get('Accept-Language', '')[:100],
        'client_text_version': data.consent_text_version,
    }
    cloning.grant_consent(me, evidence=evidence)
    return cloning.clone_status(me)


@router.delete("/clone", auth=ProfileAuth())
@ratelimit(group="voice:clone-delete", key=user_or_ip, rate="20/h")
def delete_clone(request, revoke_consent: bool = True):
    """Delete the voice. With `revoke_consent` (the default) collection stops too.

    `revoke_consent=false` is "rebuild it from scratch": the clone and its
    samples go, the opt-in stands, and the next notes start a new one.
    """
    me = _voice_profile(request)
    if revoke_consent:
        cloning.revoke_consent(me)
    else:
        cloning.delete_voice(me, reason='rebuild requested')
    return cloning.clone_status(me)
