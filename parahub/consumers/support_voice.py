"""
Support Voice WebSocket consumer.

Public voice support bot — no auth required.
Rate limiting by IP address. Route: ws/v1/support/voice/

Protocol:
  Client → Server:
    - Binary: audio blob (webm/opus from MediaRecorder)
    - Text JSON: {"type": "ping"} or {"type": "clear"}

  Server → Client:
    - Text JSON: status updates, transcripts, response text
    - Binary: TTS audio (mp3)

Security:
  - Anonymous access (no auth required)
  - Rate limiting by IP: 5 req/min, 30 req/day
  - Audio size cap: 5MB max per message
  - Session tracking by IP hash (for conversation continuity)
  - Cost tracking in Redis
"""

import asyncio
import hashlib
import logging
import time
import uuid

import orjson
import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_aioredis() -> aioredis.Redis:
    """Lazy module-level async Redis connection."""
    global _aioredis_conn
    if _aioredis_conn is None:
        url = settings.CACHES['default']['LOCATION']
        _aioredis_conn = aioredis.from_url(url, decode_responses=True)
    return _aioredis_conn


_aioredis_conn: aioredis.Redis | None = None

# Security limits
MAX_AUDIO_SIZE = 5 * 1024 * 1024  # 5MB
MIN_AUDIO_SIZE = 1000  # 1KB
RATE_LIMIT_PER_MINUTE = 5
RATE_LIMIT_PER_DAY = 30
MAX_REPLAY_TEXT_LENGTH = 1000
MAX_CONCURRENT_CONNECTIONS = 3  # Per IP
CONN_TTL = 120
CONN_HEARTBEAT_INTERVAL = 60

# Cost tracking (estimated: STT ~$0.01 + Gemini ~$0.001 + TTS ~$0.03 = ~$0.04/turn)
COST_PER_TURN_MILLICENTS = 4000  # $0.04
COST_PER_REPLAY_MILLICENTS = 3000  # $0.03 (TTS only)
COST_PER_TEXT_TURN_MILLICENTS = 100  # $0.001 (Gemini only, no STT/TTS)
MAX_TEXT_LENGTH = 500


class SupportVoiceConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for public support voice conversations."""

    async def connect(self):
        # Get client IP for rate limiting and session
        self._client_ip = self._get_client_ip()
        self._session_id = hashlib.sha256(self._client_ip.encode()).hexdigest()[:16]
        self._conn_id = str(uuid.uuid4())[:8]
        self._processing = False
        self._heartbeat_task = None
        self.pipeline = None

        # Check concurrent connection limit
        if not await self._check_concurrent_limit():
            await self.close(code=4029)
            return

        await self.accept()
        await self._send_json({'type': 'connected'})

        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._connection_heartbeat())

        # Init pipeline
        try:
            from parahub.services.support_voice import SupportVoicePipeline
            self.pipeline = SupportVoicePipeline(
                session_id=self._session_id,
                send_status=self._send_status,
            )
            self.pipeline.load_conversation()
            if self.pipeline.conversation:
                await self._send_json({
                    'type': 'history',
                    'messages': [
                        {'user': u, 'agent': a}
                        for u, a in self.pipeline.conversation
                    ],
                })
            await self._send_json({'type': 'ready'})
        except Exception as e:
            logger.error(f"Support voice pipeline init failed: {e}")
            await self._send_json({'type': 'error', 'message': 'Voice service initialization failed'})

    async def disconnect(self, close_code):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self._release_connection()
        self.pipeline = None

    def _get_client_ip(self) -> str:
        """Extract client IP from WebSocket scope."""
        headers = dict(self.scope.get('headers', []))
        # Check X-Forwarded-For (behind nginx)
        xff = headers.get(b'x-forwarded-for', b'').decode()
        if xff:
            return xff.split(',')[0].strip()
        # Check X-Real-IP
        xri = headers.get(b'x-real-ip', b'').decode()
        if xri:
            return xri.strip()
        # Fallback to direct connection
        client = self.scope.get('client')
        return client[0] if client else '0.0.0.0'

    def _conn_lock_key(self) -> str:
        return f'support:conn:{self._session_id}'

    async def _check_concurrent_limit(self) -> bool:
        """Check if IP doesn't exceed concurrent connection limit."""
        try:
            r = _get_aioredis()
            key = self._conn_lock_key()
            await r.sadd(key, self._conn_id)
            await r.expire(key, CONN_TTL)
            count = await r.scard(key)
            if count > MAX_CONCURRENT_CONNECTIONS:
                await r.srem(key, self._conn_id)
                return False
            return True
        except Exception as e:
            logger.error(f"Concurrent limit check failed: {e}")
            return True

    async def _release_connection(self):
        """Remove connection from concurrent set."""
        try:
            r = _get_aioredis()
            key = self._conn_lock_key()
            await r.srem(key, self._conn_id)
        except Exception as e:
            logger.error(f"Connection release failed: {e}")

    async def _connection_heartbeat(self):
        """Periodically refresh connection TTL."""
        try:
            r = _get_aioredis()
            key = self._conn_lock_key()
            while True:
                await asyncio.sleep(CONN_HEARTBEAT_INTERVAL)
                if await r.sismember(key, self._conn_id):
                    await r.expire(key, CONN_TTL)
                else:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Support heartbeat failed: {e}")

    async def _track_cost(self, millicents: int):
        """Increment daily cost counters."""
        try:
            r = _get_aioredis()
            day = time.strftime('%Y-%m-%d')
            key = f'support:cost:{day}'
            await r.incrby(key, millicents)
            await r.expire(key, 604800)
        except Exception as e:
            logger.error(f"Cost tracking failed: {e}")

    async def _check_rate_limit(self) -> bool:
        """Check IP-based rate limits. Returns True if allowed."""
        try:
            r = _get_aioredis()
            ip_hash = self._session_id
            now = int(time.time())

            # Per-minute
            minute_key = f'support:rl:{ip_hash}:m:{now // 60}'
            count_m = await r.incr(minute_key)
            if count_m == 1:
                await r.expire(minute_key, 120)
            if count_m > RATE_LIMIT_PER_MINUTE:
                await self._send_json({'type': 'error', 'message': 'Too many requests. Please wait a moment.'})
                return False

            # Per-day
            day_key = f'support:rl:{ip_hash}:d:{now // 86400}'
            count_d = await r.incr(day_key)
            if count_d == 1:
                await r.expire(day_key, 172800)
            if count_d > RATE_LIMIT_PER_DAY:
                await self._send_json({'type': 'error', 'message': 'Daily limit reached. Please try again tomorrow or email support@parahub.io'})
                return False

            return True
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return True

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            try:
                data = orjson.loads(text_data)
                await self._handle_json(data)
            except orjson.JSONDecodeError:
                await self._send_json({'type': 'error', 'message': 'Invalid JSON'})
        elif bytes_data:
            await self._handle_audio(bytes_data)

    async def _handle_json(self, data):
        msg_type = data.get('type')
        if msg_type == 'ping':
            await self._send_json({'type': 'pong'})
        elif msg_type == 'clear':
            if self.pipeline:
                self.pipeline.clear_conversation()
            await self._send_json({'type': 'cleared'})
        elif msg_type == 'replay':
            await self._handle_replay(data.get('text', ''))
        elif msg_type == 'text':
            await self._handle_text(data.get('text', ''))

    async def _handle_replay(self, text: str):
        if not self.pipeline or not text:
            await self._send_json({'type': 'error', 'message': 'Nothing to replay'})
            return
        if self._processing:
            await self._send_json({'type': 'error', 'message': 'Still processing'})
            return
        if len(text) > MAX_REPLAY_TEXT_LENGTH:
            await self._send_json({'type': 'error', 'message': 'Text too long'})
            return
        if not await self._check_rate_limit():
            return
        self._processing = True
        try:
            audio = await self.pipeline.speak(text)
            await self.send(bytes_data=audio)
            await self._send_json({'type': 'done'})
            await self._track_cost(COST_PER_REPLAY_MILLICENTS)
        except Exception as e:
            logger.exception("Support replay error")
            await self._send_json({'type': 'error', 'message': 'Replay failed. Please try again.'})
        finally:
            self._processing = False

    async def _handle_text(self, text: str):
        """Handle text input — skip STT/TTS, just Think."""
        if not self.pipeline or not text.strip():
            await self._send_json({'type': 'error', 'message': 'Empty message'})
            return
        if self._processing:
            await self._send_json({'type': 'error', 'message': 'Still processing'})
            return
        if len(text) > MAX_TEXT_LENGTH:
            await self._send_json({'type': 'error', 'message': f'Message too long (max {MAX_TEXT_LENGTH} chars)'})
            return
        if not await self._check_rate_limit():
            return
        self._processing = True
        try:
            user_text = text.strip()
            await self._send_status('transcript', text=user_text)
            response_text = await self.pipeline.think(user_text)
            await self._send_status('response', text=response_text)
            await self._send_json({'type': 'done'})
            await self._track_cost(COST_PER_TEXT_TURN_MILLICENTS)
        except Exception as e:
            logger.exception("Support text pipeline error")
            await self._send_json({'type': 'error', 'message': 'Processing failed. Please try again.'})
        finally:
            self._processing = False

    async def _handle_audio(self, audio_bytes: bytes):
        if not self.pipeline:
            await self._send_json({'type': 'error', 'message': 'Pipeline not ready'})
            return
        if self._processing:
            await self._send_json({'type': 'error', 'message': 'Still processing previous request'})
            return
        if len(audio_bytes) < MIN_AUDIO_SIZE:
            await self._send_json({'type': 'error', 'message': 'Audio too short'})
            return
        if len(audio_bytes) > MAX_AUDIO_SIZE:
            await self._send_json({'type': 'error', 'message': f'Audio too large (max {MAX_AUDIO_SIZE // 1024 // 1024}MB)'})
            return
        if not await self._check_rate_limit():
            return

        self._processing = True
        try:
            # STT
            user_text = await self.pipeline.transcribe(audio_bytes, content_type='audio/webm')
            await self._send_status('transcript', text=user_text)

            # Think (Gemini)
            response_text = await self.pipeline.think(user_text)

            # TTS
            await self._send_status('response', text=response_text)
            response_audio = await self.pipeline.speak(response_text)

            await self.send(bytes_data=response_audio)
            await self._send_json({'type': 'done'})
            await self._track_cost(COST_PER_TURN_MILLICENTS)
        except Exception as e:
            logger.exception("Support voice pipeline error")
            await self._send_json({'type': 'error', 'message': 'Voice processing failed. Please try again.'})
        finally:
            self._processing = False

    async def _send_json(self, data: dict):
        await self.send(text_data=orjson.dumps(data).decode())

    async def _send_status(self, status: str, **kwargs):
        msg = {'type': 'status', 'status': status}
        msg.update(kwargs)
        await self._send_json(msg)
