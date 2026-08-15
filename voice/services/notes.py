"""One voice note, start to finish: heard, translated, spoken, delivered.

This is the only place that knows the order of operations, so the consumer stays
a transport and the pipeline stays a set of provider calls. Everything that
costs money happens here, once, per note.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from voice.models import VoiceLiveTurn, VoiceNote
from voice.services import cloning, pipeline

logger = logging.getLogger(__name__)

# The recorder stops itself at 60 s; the server accepts twice that before
# refusing, so a clip that measures a little long is never thrown away for it.
MAX_NOTE_SECONDS = 120.0
MAX_AUDIO_BYTES = 5 * 1024 * 1024
MIN_AUDIO_BYTES = 1000

# Free tier: half an hour of sent audio a month, ≈ $0.70–1.40 of provider spend.
# Staff are unmetered. The rows are the counter — at a few dozen notes a day a
# Redis mirror would be machinery guarding nothing.
FREE_MONTHLY_SECONDS = 30 * 60

AUDIO_RETENTION_DAYS = 30
AUDIO_ROOT = Path(settings.MEDIA_ROOT) / 'private' / 'voice_notes'
# The path handed to nginx; `media/private/` is an `internal` location, so this
# is reachable only through the gated endpoint's X-Accel-Redirect.
AUDIO_URL_PREFIX = '/media/private/voice_notes/'


class QuotaExceeded(Exception):
    def __init__(self, used_seconds: float, limit_seconds: float):
        super().__init__("Monthly voice quota exhausted")
        self.used_seconds = used_seconds
        self.limit_seconds = limit_seconds


class NoteTooLong(Exception):
    def __init__(self, seconds: float):
        super().__init__(f"Recording is {seconds:.0f}s, over the {MAX_NOTE_SECONDS:.0f}s limit")
        self.seconds = seconds


@dataclass
class Quota:
    used_seconds: float
    limit_seconds: float
    unlimited: bool
    resets_at: str

    @property
    def exhausted(self) -> bool:
        return not self.unlimited and self.used_seconds >= self.limit_seconds

    def as_dict(self) -> dict:
        return {
            'used_seconds': round(self.used_seconds, 1),
            'limit_seconds': self.limit_seconds,
            'unlimited': self.unlimited,
            'resets_at': self.resets_at,
        }


def month_start(now=None):
    now = now or timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(now=None):
    start = month_start(now)
    return (start + timedelta(days=32)).replace(day=1)


def quota_for(profile) -> Quota:
    """How much of this month's allowance the profile has spent speaking.

    Both surfaces draw on the one allowance, because both spend the same money:
    a note this profile sent, and a turn spoken into its phone in live mode —
    including the guest's turns, which are the account holder's provider bill
    even though they are not the account holder's words.
    """
    unlimited = bool(profile.account.is_staff)
    since = month_start()
    sent = VoiceNote.objects.filter(
        sender=profile, created_at__gte=since,
    ).aggregate(total=Sum('audio_seconds'))['total'] or 0.0
    live = VoiceLiveTurn.objects.filter(
        profile=profile, created_at__gte=since,
    ).aggregate(total=Sum('audio_seconds'))['total'] or 0.0
    return Quota(
        used_seconds=float(sent) + float(live),
        limit_seconds=float(FREE_MONTHLY_SECONDS),
        unlimited=unlimited,
        resets_at=next_month_start().isoformat(),
    )


def resolve_languages(sender, recipient, heard_language: str) -> tuple[str, str]:
    """(source, target) for one note.

    The **detected** language wins over the sender's stated preference whenever
    it is one the platform speaks: the preference says which UI they read, the
    detection says which language they just spoke, and only the second one
    decides whether this recording needs translating at all. The preference is
    the fallback for a clip too short or too noisy to place.
    """
    supported = pipeline.LANGUAGE_NAMES
    source = heard_language if heard_language in supported else ''
    if not source:
        source = sender.preferred_language or pipeline.DEFAULT_LANGUAGE
    target = recipient.preferred_language or pipeline.DEFAULT_LANGUAGE
    return source, target


def audio_relative_path(note_id: str, created) -> str:
    return f"private/voice_notes/{created:%Y/%m}/{note_id}.mp3"


async def create_note(sender, recipient, audio_bytes: bytes, *, on_status=None) -> VoiceNote:
    """Turn a recording into a delivered note. Raises on every refusal path."""
    async def status(stage: str, **extra):
        if on_status:
            await on_status(stage, **extra)

    if len(audio_bytes) < MIN_AUDIO_BYTES:
        raise ValueError("Recording too short")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("Recording too large")

    quota = await sync_to_async(quota_for, thread_sensitive=True)(sender)
    if quota.exhausted:
        raise QuotaExceeded(quota.used_seconds, quota.limit_seconds)

    note = VoiceNote(sender=sender, recipient=recipient)
    meta = {'note': note.id}

    await status('transcribing')
    heard = await pipeline.transcribe(audio_bytes, profile=sender, meta=meta)
    if heard.seconds > MAX_NOTE_SECONDS:
        raise NoteTooLong(heard.seconds)

    source, target = await sync_to_async(resolve_languages, thread_sensitive=True)(
        sender, recipient, heard.language,
    )
    note.source_lang = source
    note.target_lang = target
    note.source_text = heard.text
    note.audio_seconds = heard.seconds
    note.stt_model = pipeline.STT_MODEL
    await status('transcribed', text=heard.text, language=source)

    if source == target:
        # Both sides already read this language — paying a model to copy a string
        # would be the only thing translation did here.
        note.target_text = heard.text
        note.translation_model = ''
    else:
        await status('translating')
        translated = await pipeline.translate(
            heard.text, source, [target], profile=sender, meta=meta,
        )
        note.target_text = translated.texts[target]
        note.translation_model = translated.model

    await status('speaking')
    clone = await sync_to_async(cloning.usable_clone, thread_sensitive=True)(sender)
    voice_id = clone.voice_id if clone else pipeline.DEFAULT_VOICE_ID
    try:
        audio_out = await pipeline.speak(note.target_text, voice_id, profile=sender, meta=meta)
    except pipeline.VoiceUnusable as e:
        # The voice is gone or barred upstream. Drop it and speak in the stock
        # voice rather than leaving the sender mute.
        await sync_to_async(cloning.drop_unusable_clone, thread_sensitive=True)(
            sender, e.voice_id, e.detail,
        )
        voice_id = pipeline.DEFAULT_VOICE_ID
        audio_out = await pipeline.speak(note.target_text, voice_id, profile=sender, meta=meta)

    note.voice_id_used = voice_id
    note.tts_model = pipeline.TTS_MODEL
    note.audio_path = audio_relative_path(note.id, timezone.now())
    note.audio_expires_at = timezone.now() + timedelta(days=AUDIO_RETENTION_DAYS)
    note.delivered_at = timezone.now()

    await asyncio.to_thread(_write_audio, note.audio_path, audio_out)
    await sync_to_async(note.save, thread_sensitive=True)()

    if clone:
        await sync_to_async(_touch_clone, thread_sensitive=True)(clone)

    # The sender's own speech may be kept as clone material — never the other
    # side's, who agreed to nothing.
    ext, _ = pipeline.sniff_audio(audio_bytes)
    await sync_to_async(_maybe_retain_sample, thread_sensitive=True)(
        sender, audio_bytes, heard.seconds, ext,
    )

    await sync_to_async(_queue_delivery, thread_sensitive=True)(note.id)
    return note


def _write_audio(relative_path: str, audio: bytes) -> None:
    path = Path(settings.MEDIA_ROOT) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)


def _touch_clone(clone) -> None:
    from voice.models import VoiceClone
    VoiceClone.objects.filter(pk=clone.pk).update(last_used_at=timezone.now())


def _maybe_retain_sample(sender, audio_bytes: bytes, seconds: float, ext: str) -> None:
    try:
        if cloning.retain_sample(sender, audio_bytes, seconds, ext):
            cloning.maybe_start_clone(sender)
    except Exception:
        # Cloning is a bonus on top of the note; it must never fail the delivery.
        logger.exception("Voice sample retention failed for profile %s", sender.id)


def _queue_delivery(note_id: str) -> None:
    """Hand the notification to the background pool.

    Push delivery talks to Web Push and FCM endpoints over the network; doing it
    inline would hold the sender's WebSocket open for the recipient's push
    provider's latency.
    """
    from parahub.background import spawn
    spawn(lambda: _deliver(note_id))


def _deliver(note_id: str) -> None:
    from notifications.services import notify_voice_note
    from parahub.services.ws_publish import ws_publish

    note = VoiceNote.objects.select_related(
        'sender', 'recipient', 'recipient__account',
    ).filter(id=note_id).first()
    if note is None:
        logger.warning("Voice note %s vanished before delivery", note_id)
        return

    # An open thread appends the note itself; the notification below is what
    # reaches a recipient who is not looking at it.
    try:
        ws_publish(f'user:{note.recipient.account_id}', {
            'type': 'voice_note.new',
            'note': serialize_note(note, viewer=note.recipient),
            'sender': {
                'id': note.sender_id,
                'hna': note.sender.hna,
                'display_name': note.sender.display_name or note.sender.local_name,
            },
        })
    except Exception:
        logger.exception("Voice note %s live publish failed", note_id)

    try:
        notify_voice_note(note.recipient.account, note)
    except Exception:
        logger.exception("Voice note %s notification failed", note_id)


def serialize_note(note, *, viewer=None) -> dict:
    """One note as both sides see it — the pair of texts is the record."""
    return {
        'id': note.id,
        'object_type': 'voice_note',
        'sender_id': note.sender_id,
        'recipient_id': note.recipient_id,
        'direction': 'out' if viewer and note.sender_id == viewer.id else 'in',
        'source_lang': note.source_lang,
        'target_lang': note.target_lang,
        'source_text': note.source_text,
        'target_text': note.target_text,
        'audio_seconds': round(note.audio_seconds, 1),
        'has_audio': note.has_audio,
        'audio_expires_at': note.audio_expires_at.isoformat() if note.audio_expires_at else None,
        'synthetic_voice': True,  # AI Act: the audio is machine-generated, always say so
        'cloned_voice': bool(note.voice_id_used) and note.voice_id_used != pipeline.DEFAULT_VOICE_ID,
        'played_at': note.played_at.isoformat() if note.played_at else None,
        'created_at': note.created_at.isoformat() if note.created_at else None,
    }
