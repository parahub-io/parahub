"""Live mode: one phone lying between two people who do not share a language.

The asynchronous note has a recipient with an account, a profile and a stated
language. Here the other side is whoever is sitting across the table. That one
difference is the whole of this file:

- **The language pair comes from the screen, not from two profiles.** Each half
  of the page has its own picker, and every turn carries the pair it was spoken
  under. There is no second profile to read a preference off.
- **Nothing is written down but the seconds.** The guest agreed to nothing, and
  on a shared microphone we cannot even prove which of the two people spoke —
  so no transcript, no translation and no audio survive the turn, and no
  recording is ever kept as clone material. ``VoiceLiveTurn`` exists to meter
  the provider spend, and holds nothing else.
- **The speaker's side picks the voice.** The account holder speaks in their own
  clone if they have one; the guest is read back in the stock voice, because a
  stranger has no clone here and building one would need their consent.

Everything else — hearing, translating, speaking — is the same three provider
calls a note makes, called through the same `pipeline` module.
"""

import logging
from dataclasses import dataclass

from asgiref.sync import sync_to_async

from voice.models import VoiceLiveTurn
from voice.services import cloning, pipeline
from voice.services.notes import (
    MAX_AUDIO_BYTES, MAX_NOTE_SECONDS, MIN_AUDIO_BYTES,
    NoteTooLong, QuotaExceeded, _touch_clone, quota_for,
)

logger = logging.getLogger(__name__)

HOST = VoiceLiveTurn.Side.HOST
GUEST = VoiceLiveTurn.Side.GUEST


class SameLanguage(Exception):
    """Both halves of the screen are set to the same language.

    Refused rather than served: a translation from a language into itself plays
    the guest their own sentence back, and the only way to reach it is to have
    mis-set a picker. The asynchronous note tolerates this case (two people who
    share a language can still send each other notes); a live conversation
    between two people who share a language has nothing to translate.
    """


@dataclass
class LiveTurn:
    """One utterance, translated and spoken. Alive only as long as this object."""

    spoken_by: str
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    seconds: float
    cloned_voice: bool
    audio: bytes

    def as_dict(self) -> dict:
        return {
            'spoken_by': self.spoken_by,
            'source_lang': self.source_lang,
            'target_lang': self.target_lang,
            'source_text': self.source_text,
            'target_text': self.target_text,
            'seconds': round(self.seconds, 1),
            # AI Act: the audio that follows is machine-generated, always say so.
            'synthetic_voice': True,
            'cloned_voice': self.cloned_voice,
        }


def resolve_direction(spoken_by: str, source: str, target: str,
                      heard_language: str) -> tuple[str, str, str]:
    """(spoken_by, source, target), corrected for whoever actually spoke.

    The pair is the user's, so detection does not get to invent a third
    language: it is only allowed to say that the two known languages are the
    other way round. That happens constantly on a shared phone — the guest
    reaches over and talks into the host's half — and left uncorrected the turn
    is wasted, since the model is told to repeat a message that is already in
    the target language.

    Whoever spoke also decides the voice, so the side flips with the pair.
    """
    if heard_language and heard_language == target and heard_language != source:
        spoken_by = GUEST if spoken_by == HOST else HOST
        source, target = target, source
    return spoken_by, source, target


async def translate_turn(profile, audio_bytes: bytes, *, spoken_by: str,
                         source_lang: str, target_lang: str, on_status=None) -> LiveTurn:
    """Hear one utterance, say it in the other language. Raises on every refusal."""
    async def status(stage: str, **extra):
        if on_status:
            await on_status(stage, **extra)

    if source_lang == target_lang:
        raise SameLanguage()
    if len(audio_bytes) < MIN_AUDIO_BYTES:
        raise ValueError("Recording too short")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("Recording too large")

    quota = await sync_to_async(quota_for, thread_sensitive=True)(profile)
    if quota.exhausted:
        raise QuotaExceeded(quota.used_seconds, quota.limit_seconds)

    meta = {'mode': 'live'}

    await status('transcribing')
    heard = await pipeline.transcribe(audio_bytes, profile=profile, meta=meta)
    if heard.seconds > MAX_NOTE_SECONDS:
        raise NoteTooLong(heard.seconds)

    spoken_by, source_lang, target_lang = resolve_direction(
        spoken_by, source_lang, target_lang, heard.language,
    )
    await status('transcribed', text=heard.text, language=source_lang,
                 spoken_by=spoken_by)

    await status('translating')
    translated = await pipeline.translate(
        heard.text, source_lang, [target_lang], profile=profile,
        meta={**meta, 'spoken_by': spoken_by},
    )
    target_text = translated.texts[target_lang]

    await status('speaking')
    clone = None
    if spoken_by == HOST:
        clone = await sync_to_async(cloning.usable_clone, thread_sensitive=True)(profile)
    voice_id = clone.voice_id if clone else pipeline.DEFAULT_VOICE_ID
    try:
        audio_out = await pipeline.speak(
            target_text, voice_id, profile=profile, meta={**meta, 'voice_id': voice_id},
        )
    except pipeline.VoiceUnusable as e:
        await sync_to_async(cloning.drop_unusable_clone, thread_sensitive=True)(
            profile, e.voice_id, e.detail,
        )
        clone, voice_id = None, pipeline.DEFAULT_VOICE_ID
        audio_out = await pipeline.speak(target_text, voice_id, profile=profile, meta=meta)

    # The meter, and the only thing that outlives this call. Deliberately
    # written after the last provider call: a turn that never reached the
    # speaker was never worth charging for.
    await sync_to_async(VoiceLiveTurn.objects.create, thread_sensitive=True)(
        profile=profile, spoken_by=spoken_by,
        source_lang=source_lang, target_lang=target_lang,
        audio_seconds=heard.seconds, voice_id_used=voice_id,
    )
    if clone:
        await sync_to_async(_touch_clone, thread_sensitive=True)(clone)

    return LiveTurn(
        spoken_by=spoken_by,
        source_lang=source_lang, target_lang=target_lang,
        source_text=heard.text, target_text=target_text,
        seconds=heard.seconds,
        cloned_voice=voice_id != pipeline.DEFAULT_VOICE_ID,
        audio=audio_out,
    )
