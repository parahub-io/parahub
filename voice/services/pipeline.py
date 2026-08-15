"""The three provider calls a voice note is made of: hear it, translate it, say it.

Nothing here touches the database or knows what a note is — it takes bytes and
text and returns text and bytes, and writes one ledger row per paid call. The
lifecycle (clones, quota, delivery) lives in `notes.py` and `cloning.py`, so a
provider swap stays inside this file.

Measured on the sibling project this is ported from: transcribe 0.4 s, translate
1.4 s, speak 0.4 s — ~2.2 s end to end, which is why nothing here streams.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from parahub.models import AIUsageLog
from parahub.services import ai_usage

logger = logging.getLogger(__name__)

PROJECT_DIR = Path('/opt/parahub')

STT_MODEL = 'scribe_v1'
TTS_MODEL = 'eleven_flash_v2_5'

# Flash v2.5 is multilingual: a voice cloned from Portuguese speech reads Russian
# in that same voice. That is the whole product, not a side effect.
TTS_OUTPUT_FORMAT = 'mp3_44100_64'
TTS_VOICE_SETTINGS = {
    'stability': 0.5,
    'similarity_boost': 0.75,
    'use_speaker_boost': True,
    'speed': 1.0,  # a personal message is not read out faster than it was said
}

# Used when the sender has no clone (yet, or ever). Deliberately the neutral
# stock voice: any gendered default would miscast half the senders.
DEFAULT_VOICE_ID = 'SAz9YHcvj6GT2YYXdXww'  # River — relaxed, neutral

# Primary translator plus one higher-tier backup on different infrastructure.
# The chain fired about once in 600 calls in the sibling project's production —
# insurance, not a hot path.
TRANSLATION_CHAIN = ('gemini-3.5-flash-lite', 'gemini-3.6-flash')
# Wall-clock leash per model: the lite tier answers in ~1.4 s, so 3 s means a
# failed primary costs little; the bigger fallback is given room.
TRANSLATION_DEADLINES = {'gemini-3.5-flash-lite': 3.0, 'gemini-3.6-flash': 5.0}
TRANSLATION_DEADLINE_DEFAULT = 5.0

HTTP_TIMEOUT = 60.0
_RETRYABLE_STATUSES = {429, 500, 502, 503}

# The six locales a profile can pick. `pt` is European Portuguese — the audience
# is Portugal, and a model left to guess writes Brazilian.
LANGUAGE_NAMES = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'pt': 'European Portuguese (pt-PT, not Brazilian)',
    'ru': 'Russian',
}
DEFAULT_LANGUAGE = 'en'

# Providers answer with whatever code they like; the platform speaks 2-letter.
_LANG_ALIASES = {
    'eng': 'en', 'spa': 'es', 'fra': 'fr', 'fre': 'fr', 'deu': 'de', 'ger': 'de',
    'por': 'pt', 'rus': 'ru',
}


class VoicePipelineError(Exception):
    """A provider call failed in a way the caller has to surface."""


class EmptyTranscription(VoicePipelineError):
    """Speech-to-text returned nothing — silence, noise, or a truncated blob."""


class VoiceUnusable(VoicePipelineError):
    """The requested voice was refused by the provider.

    Raised for the specific errors that mean the voice itself is gone or barred
    (deleted upstream, moderation-flagged, wrong account) rather than a transient
    failure — the caller drops the clone and retries with the stock voice.
    """

    def __init__(self, voice_id: str, detail: str = ''):
        super().__init__(f"Voice {voice_id} unusable: {detail}")
        self.voice_id = voice_id
        self.detail = detail


_VOICE_GONE_MARKERS = (
    'voice_access_denied', 'detected_captcha_voice',
    'voice_not_found', 'voice_does_not_exist',
)


@dataclass
class Transcription:
    text: str
    language: str
    seconds: float
    raw_language: str = ''


@dataclass
class Translation:
    texts: dict = field(default_factory=dict)   # locale -> translated text
    model: str = ''
    detected_language: str = ''


def normalize_language(code: str) -> str:
    """Map a provider's language code onto the platform's 2-letter set."""
    if not code:
        return ''
    code = code.strip().lower().replace('_', '-')
    if code in _LANG_ALIASES:
        return _LANG_ALIASES[code]
    head = code.split('-')[0]
    return _LANG_ALIASES.get(head, head[:2])


def sniff_audio(audio_bytes: bytes) -> tuple[str, str]:
    """(extension, content type) from magic bytes.

    Browsers name every blob `.webm` even when the container is mp4 (that is what
    iOS Safari records), and the provider trusts the filename it is handed — so
    the bytes get the last word.
    """
    head = audio_bytes[:12]
    if head[4:8] == b'ftyp':
        return 'mp4', 'audio/mp4'
    if head[:4] == b'OggS':
        return 'ogg', 'audio/ogg'
    if head[:4] == b'RIFF':
        return 'wav', 'audio/wav'
    # No browser records mp3, but every file handed to a check command is one.
    if head[:3] == b'ID3' or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return 'mp3', 'audio/mpeg'
    # EBML magic 1A45DFA3, and the fallback for anything unrecognised.
    return 'webm', 'audio/webm'


def elevenlabs_key() -> str:
    key_file = PROJECT_DIR / '.agents' / '.elevenlabs_key'
    if key_file.is_file():
        return key_file.read_text().strip()
    import os
    return os.environ.get('ELEVENLABS_API_KEY', '')


async def _post_with_retry(client: httpx.AsyncClient, url: str, *, label: str, **kwargs):
    """One retry on the statuses that mean "try again", none on the rest."""
    last_err = None
    for attempt in range(2):
        try:
            resp = await client.post(url, **kwargs)
            if resp.status_code in _RETRYABLE_STATUSES and attempt == 0:
                logger.warning("%s transient error %s, retrying", label, resp.status_code)
                await asyncio.sleep(1)
                continue
            return resp
        except httpx.TimeoutException as e:
            last_err = e
            if attempt == 0:
                logger.warning("%s timeout, retrying", label)
                continue
            raise VoicePipelineError(f"{label} timeout: {e}") from e
    raise VoicePipelineError(f"{label} failed after retry: {last_err}")


async def transcribe(audio_bytes: bytes, *, profile=None, meta: dict = None) -> Transcription:
    """Speech to text, with the language the speaker actually used.

    Scribe reports no duration, so the billed length is read off the last word's
    end timestamp — the only number in the response that measures the audio. It
    undercounts trailing silence, which is the right way to be wrong about a
    quota the user pays with.
    """
    key = elevenlabs_key()
    if not key:
        raise VoicePipelineError("No ElevenLabs key configured")

    ext, content_type = sniff_audio(audio_bytes)
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await _post_with_retry(
            client, 'https://api.elevenlabs.io/v1/speech-to-text', label='STT',
            headers={'xi-api-key': key},
            files={'file': (f'note.{ext}', audio_bytes, content_type)},
            data={'model_id': STT_MODEL},
        )
    if resp.status_code != 200:
        raise VoicePipelineError(f"STT error {resp.status_code}: {resp.text[:200]}")

    payload = resp.json()
    text = (payload.get('text') or '').strip()
    words = payload.get('words') or []
    seconds = max((w.get('end') or 0 for w in words), default=0)
    raw_lang = payload.get('language_code') or ''

    await ai_usage.arecord_units(
        AIUsageLog.KIND_VOICE_STT, STT_MODEL, round(float(seconds), 3),
        profile=profile,
        duration_ms=int((time.monotonic() - started) * 1000),
        success=bool(text), error='' if text else 'Empty transcription',
        meta={**(meta or {}), 'audio_bytes': len(audio_bytes), 'container': ext},
    )

    if not text:
        raise EmptyTranscription()
    return Transcription(
        text=text, language=normalize_language(raw_lang),
        seconds=round(float(seconds), 3), raw_language=raw_lang,
    )


def _translation_prompt(text: str, source: str, targets: list[str]) -> str:
    target_lines = '\n'.join(
        f'  "{code}": {LANGUAGE_NAMES.get(code, code)}' for code in targets
    )
    source_name = LANGUAGE_NAMES.get(source, source or 'unknown')
    return (
        "You translate one spoken message between two people who do not share a "
        "language.\n\n"
        "Rules:\n"
        "- Translate literally and completely. Do not summarise, soften, explain, "
        "answer, or add anything that was not said.\n"
        "- Keep the speaker's register, tone and politeness level. Spoken language "
        "stays spoken language.\n"
        "- Keep names, numbers, dates, amounts and addresses exactly as spoken.\n"
        "- Write out abbreviations the way a person would say them.\n"
        "- If the message is already in the target language, repeat it unchanged.\n\n"
        f"Source language: {source_name}\n"
        f"Target languages (locale code -> language):\n{target_lines}\n\n"
        "Answer with JSON only:\n"
        '{"texts": {"<locale>": "<translation>", ...}, "text_lang": "<detected locale>"}\n\n'
        f"Message:\n{text}"
    )


async def _gemini_call(model: str, prompt: str, api_key: str):
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    return await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type='application/json',
            max_output_tokens=2048,
        ),
    )


def _parse_translation(raw: str) -> dict:
    """Read the model's answer, tolerating code fences it was told not to use."""
    body = (raw or '').strip()
    if body.startswith('```'):
        body = body.split('\n', 1)[-1]
        if body.rstrip().endswith('```'):
            body = body.rstrip()[:-3]
    return json.loads(body)


async def translate(text: str, source: str, targets: list[str], *,
                    profile=None, meta: dict = None) -> Translation:
    """One call returns every target language.

    The `texts: {locale: ...}` shape is kept even for a single target: fanning a
    note out to a third language later is then a longer list, not a new protocol.
    Cost barely moves with targets here — the synthesis afterwards is what scales.
    """
    targets = [t for t in targets if t]
    if not targets:
        raise VoicePipelineError("translate() needs at least one target language")

    from asgiref.sync import sync_to_async
    from parahub.models import AISettings
    ai_settings = await sync_to_async(AISettings.objects.first, thread_sensitive=True)()
    api_key = getattr(ai_settings, 'google_api_key', '') if ai_settings else ''
    if not api_key:
        raise VoicePipelineError("No Google API key configured (AISettings)")

    prompt = _translation_prompt(text, source, targets)
    last_error = ''

    for index, model in enumerate(TRANSLATION_CHAIN):
        deadline = TRANSLATION_DEADLINES.get(model, TRANSLATION_DEADLINE_DEFAULT)
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                _gemini_call(model, prompt, api_key), timeout=deadline,
            )
        except asyncio.TimeoutError:
            logger.warning("Translation %s exceeded %ss deadline, falling through",
                           model, deadline)
            last_error = f"{model} deadline"
            continue
        except Exception as e:  # provider error — try the next model
            logger.warning("Translation %s failed: %s", model, e)
            last_error = f"{model}: {e}"
            continue

        raw = getattr(response, 'text', '') or ''
        # A model reached through a fallback is recorded as such, so a rising
        # share of `-fallback` rows reads as the primary degrading.
        billed_model = model + ('-fallback' if index else '')
        try:
            parsed = _parse_translation(raw)
            texts = {
                str(k).lower(): v for k, v in (parsed.get('texts') or {}).items()
                if isinstance(v, str) and v.strip()
            }
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning("Translation %s returned unparseable JSON: %s", model, e)
            texts, parsed = {}, {}
            last_error = f"{model}: unparseable answer"

        missing = [t for t in targets if t not in texts]
        await ai_usage.arecord_gemini(
            AIUsageLog.KIND_VOICE_TRANSLATE, model, response, profile=profile,
            duration_ms=int((time.monotonic() - started) * 1000),
            success=not missing,
            error='' if not missing else f"missing targets: {','.join(missing)}",
            meta={**(meta or {}), 'targets': targets, 'billed_as': billed_model},
        )
        if missing:
            continue

        return Translation(
            texts={t: texts[t] for t in targets},
            model=billed_model,
            detected_language=normalize_language(parsed.get('text_lang') or ''),
        )

    raise VoicePipelineError(f"Translation failed: {last_error or 'no model answered'}")


async def speak(text: str, voice_id: str, *, profile=None, meta: dict = None) -> bytes:
    """Text to mp3 in the given voice.

    Raises `VoiceUnusable` when the provider says that voice is gone or barred —
    the caller decides whether that means dropping a clone.
    """
    key = elevenlabs_key()
    if not key:
        raise VoicePipelineError("No ElevenLabs key configured")

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await _post_with_retry(
            client, f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}',
            label='TTS',
            headers={
                'xi-api-key': key,
                'Content-Type': 'application/json',
                'Accept': 'audio/mpeg',
            },
            # `output_format` is a QUERY parameter. Sent in the body it is
            # ignored without a word of complaint and the default (mp3 128 kbps)
            # comes back — twice the bytes we meant to store, and no error to
            # notice it by.
            params={'output_format': TTS_OUTPUT_FORMAT},
            json={
                'text': text,
                'model_id': TTS_MODEL,
                'voice_settings': TTS_VOICE_SETTINGS,
            },
        )

    if resp.status_code != 200:
        detail = resp.text[:300]
        await ai_usage.arecord_units(
            AIUsageLog.KIND_VOICE_TTS, TTS_MODEL, len(text), profile=profile,
            duration_ms=int((time.monotonic() - started) * 1000),
            success=False, error=f"{resp.status_code}: {detail[:200]}",
            meta={**(meta or {}), 'voice_id': voice_id},
        )
        if any(marker in detail for marker in _VOICE_GONE_MARKERS):
            raise VoiceUnusable(voice_id, detail)
        raise VoicePipelineError(f"TTS error {resp.status_code}: {detail[:200]}")

    audio = resp.content
    await ai_usage.arecord_units(
        AIUsageLog.KIND_VOICE_TTS, TTS_MODEL, len(text), profile=profile,
        duration_ms=int((time.monotonic() - started) * 1000),
        meta={**(meta or {}), 'voice_id': voice_id, 'audio_bytes': len(audio)},
    )
    return audio
