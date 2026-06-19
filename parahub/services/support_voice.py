"""
Support Voice Pipeline — ElevenLabs STT → Gemini Flash → ElevenLabs TTS

Public support bot accessible to anyone. Knowledge base: support_kb/knowledge.md
Voice: Andrey (ElevenLabs). No Claude CLI, no tools — pure FAQ answering.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

PROJECT_DIR = Path('/opt/parahub')


class EmptyTranscription(Exception):
    """Raised when STT returns empty text (quiet audio, background noise)."""
    pass


_RETRYABLE_STATUSES = {429, 500, 502, 503}
KNOWLEDGE_FILE = PROJECT_DIR / 'support_kb' / 'knowledge.md'

# ElevenLabs
DEFAULT_TTS_MODEL = 'eleven_multilingual_v2'
DEFAULT_STT_MODEL = 'scribe_v1'
VOICE_ID = 'sL7inhYgWWLlrcPH81Mt'  # Andrey

# Redis cache
DOCS_CACHE_KEY = 'support:docs_context'
DOCS_CACHE_TTL = 3600  # 1 hour
TTS_CACHE_TTL = 86400  # 24h
CONV_TTL = 1800  # 30min for anonymous conversations

SYSTEM_PROMPT = """You are the Parahub Support Assistant — friendly, direct, and knowledgeable.
Parahub is a platform for direct cooperation without middlemen: zero fees, encrypted communication, peer-to-peer trust.

RULES:
1. Answer based on the knowledge base below. If you don't know — say so and suggest emailing support@parahub.io
2. NEVER reveal technical details (tech stack, databases, APIs, server infrastructure, ports)
3. For "how to do X" — give clear steps and tell the user where to go on the platform (use page paths like /market/create)
4. For "what is X" — explain the concept and why it matters, then where to find it
5. If the user asks where to read more — mention /docs pages
6. Respond in the same language as the question
7. Keep answers concise: 2-4 sentences for voice. You can be longer if the question requires detail
8. You are a VOICE assistant — speak naturally. Don't dictate URLs mid-sentence; mention the page path at the end, e.g. "you can do that at /market/create"
9. Be warm and encouraging, especially with newcomers. Sell the value of the platform when appropriate

KNOWLEDGE BASE:
"""


def _get_elevenlabs_key():
    key_file = PROJECT_DIR / '.agents' / '.elevenlabs_key'
    if key_file.exists():
        return key_file.read_text().strip()
    return os.environ.get('ELEVENLABS_API_KEY', '')


def _get_redis():
    import redis
    return redis.Redis.from_url(settings.CACHES['default']['LOCATION'], decode_responses=True)


def _get_redis_binary():
    import redis
    return redis.Redis.from_url(settings.CACHES['default']['LOCATION'], decode_responses=False)


def _load_knowledge() -> str:
    """Load curated knowledge base from support_kb/knowledge.md."""
    if not KNOWLEDGE_FILE.is_file():
        logger.error(f"Knowledge file not found: {KNOWLEDGE_FILE}")
        return "No knowledge base available."

    try:
        content = KNOWLEDGE_FILE.read_text(encoding='utf-8')
        logger.info(f"Loaded knowledge base: {len(content)} chars from {KNOWLEDGE_FILE}")
        return content
    except Exception as e:
        logger.error(f"Failed to read knowledge base: {e}")
        return "No knowledge base available."


def get_docs_context() -> str:
    """Get docs context, cached in Redis for 1 hour."""
    try:
        r = _get_redis()
        cached = r.get(DOCS_CACHE_KEY)
        if cached:
            return cached
    except Exception:
        pass

    context = _load_knowledge()

    try:
        r = _get_redis()
        r.setex(DOCS_CACHE_KEY, DOCS_CACHE_TTL, context)
    except Exception as e:
        logger.warning(f"Failed to cache docs context: {e}")

    return context


class SupportVoicePipeline:
    """Voice pipeline: ElevenLabs STT → Gemini Flash → ElevenLabs TTS"""

    def __init__(self, session_id: str, send_status=None):
        self.session_id = session_id
        self.send_status = send_status or self._noop
        self.elevenlabs_key = _get_elevenlabs_key()
        if not self.elevenlabs_key:
            raise ValueError("No ElevenLabs key configured")
        self.conversation: list[tuple[str, str]] = []
        self._redis_key = f'support:conv:{session_id}'

    @staticmethod
    async def _noop(*a, **kw):
        pass

    def load_conversation(self):
        """Load conversation history from Redis."""
        try:
            r = _get_redis()
            data = r.get(self._redis_key)
            if data:
                self.conversation = [tuple(pair) for pair in json.loads(data)]
        except Exception as e:
            logger.warning(f"Failed to load support conversation: {e}")

    def _save_conversation(self):
        """Save conversation history to Redis (max 10 exchanges)."""
        try:
            r = _get_redis()
            r.setex(self._redis_key, CONV_TTL, json.dumps(self.conversation[-10:]))
        except Exception as e:
            logger.warning(f"Failed to save support conversation: {e}")

    def clear_conversation(self):
        """Clear conversation from memory and Redis."""
        self.conversation.clear()
        try:
            r = _get_redis()
            r.delete(self._redis_key)
        except Exception:
            pass

    async def transcribe(self, audio_bytes: bytes, content_type: str = 'audio/webm') -> str:
        """Transcribe audio using ElevenLabs Scribe."""
        await self.send_status('transcribing')
        ext = 'webm' if 'webm' in content_type else 'wav'

        last_err = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        'https://api.elevenlabs.io/v1/speech-to-text',
                        headers={'xi-api-key': self.elevenlabs_key},
                        files={'file': (f'audio.{ext}', audio_bytes, content_type)},
                        data={'model_id': DEFAULT_STT_MODEL},
                    )
                if resp.status_code in _RETRYABLE_STATUSES and attempt == 0:
                    logger.warning(f"STT transient error {resp.status_code}, retrying...")
                    await asyncio.sleep(1)
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(f"STT error {resp.status_code}: {resp.text[:200]}")
                break
            except httpx.TimeoutException as e:
                last_err = e
                if attempt == 0:
                    logger.warning("STT timeout, retrying...")
                    continue
                raise RuntimeError(f"STT timeout: {e}") from e
        else:
            raise RuntimeError(f"STT failed after retry: {last_err}")

        text = resp.json().get('text', '').strip()
        if not text:
            raise EmptyTranscription()
        return text

    async def think(self, user_text: str) -> str:
        """Query Gemini Flash with docs context."""
        await self.send_status('thinking')

        # Get API key from AISettings
        from parahub.models import AISettings
        from channels.db import database_sync_to_async
        ai_settings = await database_sync_to_async(AISettings.objects.first)()
        if not ai_settings or not ai_settings.google_api_key:
            return "Support service is temporarily unavailable. Please try again later."

        # Build prompt with conversation history
        docs_context = get_docs_context()
        full_system = SYSTEM_PROMPT + docs_context

        messages_text = ""
        if self.conversation:
            for u, a in self.conversation[-5:]:
                messages_text += f"User: {u}\nAssistant: {a}\n\n"

        prompt = f"{messages_text}User: {user_text}\n\nAssistant:"

        try:
            from google import genai
            from google.genai import types as genai_types

            gemini_client = genai.Client(api_key=ai_settings.google_api_key)

            response = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=full_system,
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
            )

            answer = response.text if hasattr(response, 'text') else ""
            if not answer:
                return "I couldn't process your question. Please try again."

            self.conversation.append((user_text, answer))
            self._save_conversation()
            return answer

        except Exception as e:
            logger.exception("Gemini query failed for support voice")
            return "Support service encountered an error. Please try again later."

    def _tts_cache_key(self, text: str) -> str:
        h = hashlib.sha256(f'{VOICE_ID}:{text}'.encode()).hexdigest()[:16]
        return f'tts:cache:support:{h}'

    async def speak(self, text: str) -> bytes:
        """Convert text to speech using ElevenLabs. Cached in Redis for 24h."""
        await self.send_status('speaking')

        cache_key = self._tts_cache_key(text)
        try:
            r = _get_redis_binary()
            cached = r.get(cache_key)
            if cached:
                return cached
        except Exception:
            pass

        last_err = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        f'https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}',
                        headers={
                            'xi-api-key': self.elevenlabs_key,
                            'Content-Type': 'application/json',
                            'Accept': 'audio/mpeg',
                        },
                        json={
                            'text': text,
                            'model_id': DEFAULT_TTS_MODEL,
                            'voice_settings': {
                                'stability': 0.7,
                                'similarity_boost': 0.8,
                                'style': 0.15,
                                'use_speaker_boost': True,
                            },
                            'speed': 1.0,
                        },
                    )
                if resp.status_code in _RETRYABLE_STATUSES and attempt == 0:
                    logger.warning(f"TTS transient error {resp.status_code}, retrying...")
                    await asyncio.sleep(1)
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(f"TTS error {resp.status_code}: {resp.text[:200]}")
                break
            except httpx.TimeoutException as e:
                last_err = e
                if attempt == 0:
                    logger.warning("TTS timeout, retrying...")
                    continue
                raise RuntimeError(f"TTS timeout: {e}") from e
        else:
            raise RuntimeError(f"TTS failed after retry: {last_err}")

        audio = resp.content
        try:
            r = _get_redis_binary()
            r.setex(cache_key, TTS_CACHE_TTL, audio)
        except Exception as e:
            logger.warning(f"Failed to cache TTS audio: {e}")

        return audio
