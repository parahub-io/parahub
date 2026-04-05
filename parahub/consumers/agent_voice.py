"""
Agent Voice WebSocket consumer.

Generic voice chat for any agent with voice_enabled=True.
Agent name from URL: ws/v1/agents/voice/<agent_name>/

Protocol:
  Client → Server:
    - Binary: audio blob (webm/opus from MediaRecorder)
    - Text JSON: {"type": "ping"} or {"type": "clear"}

  Server → Client:
    - Text JSON: status updates, transcripts, response text
    - Binary: TTS audio (mp3)

Security:
  - Staff-only auth (is_staff=True)
  - Rate limiting: 10 req/min, 100 req/day per user (Redis counters)
  - Concurrent connection limit: 1 per user per agent (Redis SET NX + heartbeat)
  - Audio size cap: 5MB max per message
  - Cost tracking: per-turn estimates in Redis (voice:cost:{date})
  - Error messages sanitized (no internal details to client)
"""

import asyncio
import logging
import random
import time
import uuid

import orjson
import redis.asyncio as aioredis
from channels.db import database_sync_to_async
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
MAX_AUDIO_SIZE = 5 * 1024 * 1024  # 5MB (~60s of WebM/Opus)
MIN_AUDIO_SIZE = 1000  # 1KB
RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_PER_DAY = 100
MAX_REPLAY_TEXT_LENGTH = 2000  # Characters
MAX_CONCURRENT_CONNECTIONS = 1  # Per user per agent
CONN_TTL = 120  # Connection lock TTL (seconds), refreshed by heartbeat
CONN_HEARTBEAT_INTERVAL = 60  # Refresh lock every 60s

# Cost tracking (estimated cost per turn in millicents, 1 cent = 100 millicents)
# STT ~$0.01 + LLM ~$0.05 + TTS ~$0.03 = ~$0.09/turn
COST_PER_TURN_MILLICENTS = 9000  # $0.09
COST_PER_REPLAY_MILLICENTS = 3000  # $0.03 (TTS only)


class AgentVoiceConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for agent voice conversations."""

    async def connect(self):
        self.user = self.scope.get('user')
        self.agent_name = self.scope['url_route']['kwargs']['agent_name']
        self.pipeline = None
        self._processing = False
        self._conn_id = str(uuid.uuid4())[:8]
        self._heartbeat_task = None

        # Always accept first — rejecting without accept sends HTTP 403,
        # which Android WebView (Capacitor) may display as a system error page
        await self.accept()

        if not self.user or not self.user.is_authenticated:
            await self._send_json({'type': 'error', 'message': 'Authentication required'})
            await self.close(code=4001)
            return

        if not self.user.is_staff:
            await self._send_json({'type': 'error', 'message': 'Staff access required'})
            await self.close(code=4003)
            return

        # Load agent config from DB
        agent_config = await self._load_agent_config(self.agent_name)
        if not agent_config:
            await self._send_json({'type': 'error', 'message': f'Agent "{self.agent_name}" not found or voice not enabled'})
            await self.close(code=4004)
            return

        # Acquire connection lock (last-writer-wins — always succeeds)
        await self._acquire_connection_lock()
        await self._send_json({'type': 'connected', 'agent': self.agent_name})

        # Start heartbeat to keep connection lock alive
        self._heartbeat_task = asyncio.create_task(self._connection_heartbeat())

        # Init pipeline
        try:
            from agents.voice_pipeline import AgentVoicePipeline
            self.pipeline = AgentVoicePipeline(
                agent_name=self.agent_name,
                voice_id=agent_config['voice_id'],
                system_prompt=agent_config['voice_system_prompt'],
                user_id=self.user.id,
                send_status=self._send_status,
            )
            self.pipeline.load_conversation()
            # Send saved history to frontend
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
            logger.error(f"Voice pipeline init failed for {self.agent_name}: {e}")
            await self._send_json({'type': 'error', 'message': 'Voice service initialization failed'})

    async def disconnect(self, close_code):
        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        # Release connection lock
        await self._release_connection_lock()
        self.pipeline = None

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

    def _conn_lock_key(self) -> str:
        return f'voice:conn:{self.user.id}:{self.agent_name}'

    async def _acquire_connection_lock(self) -> bool:
        """Acquire connection lock using last-writer-wins strategy.

        Always succeeds: if a stale lock exists (page reload, network drop),
        the new connection takes over. The old connection's heartbeat will
        detect the stolen lock and stop gracefully.
        """
        try:
            r = _get_aioredis()
            key = self._conn_lock_key()
            existing = await r.get(key)
            if existing and existing != self._conn_id:
                logger.info(f"Voice lock takeover: user={self.user.username} agent={self.agent_name} old={existing} new={self._conn_id}")
            await r.set(key, self._conn_id, ex=CONN_TTL)
            return True
        except Exception as e:
            logger.error(f"Connection lock acquire failed: {e}")
            return True  # Fail open

    async def _release_connection_lock(self):
        """Release connection lock (only if we own it)."""
        try:
            r = _get_aioredis()
            key = self._conn_lock_key()
            current = await r.get(key)
            if current and current == self._conn_id:
                await r.delete(key)
        except Exception as e:
            logger.error(f"Connection lock release failed: {e}")

    async def _connection_heartbeat(self):
        """Periodically refresh connection lock TTL."""
        try:
            r = _get_aioredis()
            key = self._conn_lock_key()
            while True:
                await asyncio.sleep(CONN_HEARTBEAT_INTERVAL)
                current = await r.get(key)
                if current and current == self._conn_id:
                    await r.expire(key, CONN_TTL)
                else:
                    break  # Lock was stolen or expired
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Connection heartbeat failed: {e}")

    async def _track_cost(self, millicents: int):
        """Increment daily cost counters (global + per-user)."""
        try:
            r = _get_aioredis()
            day = time.strftime('%Y-%m-%d')
            # Global daily cost
            global_key = f'voice:cost:{day}'
            await r.incrby(global_key, millicents)
            await r.expire(global_key, 604800)  # 7 days
            # Per-user daily cost
            user_key = f'voice:cost:{day}:{self.user.id}'
            await r.incrby(user_key, millicents)
            await r.expire(user_key, 604800)
        except Exception as e:
            logger.error(f"Cost tracking failed: {e}")

    async def _check_rate_limit(self) -> bool:
        """Check per-user rate limits (minute + daily). Returns True if allowed."""
        try:
            r = _get_aioredis()
            uid = self.user.id
            now = int(time.time())

            # Per-minute check
            minute_key = f'voice:rl:{uid}:m:{now // 60}'
            count_m = await r.incr(minute_key)
            if count_m == 1:
                await r.expire(minute_key, 120)
            if count_m > RATE_LIMIT_PER_MINUTE:
                logger.warning(f"Voice rate limit (minute) exceeded: user={self.user.username}")
                await self._send_json({'type': 'error', 'message': 'Too many requests. Please wait a moment.'})
                return False

            # Per-day check
            day_key = f'voice:rl:{uid}:d:{now // 86400}'
            count_d = await r.incr(day_key)
            if count_d == 1:
                await r.expire(day_key, 172800)
            if count_d > RATE_LIMIT_PER_DAY:
                logger.warning(f"Voice rate limit (daily) exceeded: user={self.user.username}")
                await self._send_json({'type': 'error', 'message': 'Daily voice chat limit reached. Try again tomorrow.'})
                return False

            return True
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return True  # Fail open — don't block on Redis errors

    async def _handle_replay(self, text: str):
        if not self.pipeline or not text:
            await self._send_json({'type': 'error', 'message': 'Nothing to replay'})
            return
        if self._processing:
            await self._send_json({'type': 'error', 'message': 'Still processing'})
            return
        # Validate text length
        if len(text) > MAX_REPLAY_TEXT_LENGTH:
            await self._send_json({'type': 'error', 'message': 'Text too long'})
            return
        # Rate limit replay too (it calls TTS)
        if not await self._check_rate_limit():
            return
        self._processing = True
        try:
            audio = await self.pipeline.speak(text)
            await self.send(bytes_data=audio)
            await self._send_json({'type': 'done'})
            # Track cost for replay (TTS only)
            await self._track_cost(COST_PER_REPLAY_MILLICENTS)
        except Exception as e:
            logger.exception(f"Replay error for {self.agent_name}")
            await self._send_json({'type': 'error', 'message': 'Replay failed. Please try again.'})
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

        # Rate limit check
        if not await self._check_rate_limit():
            return

        self._processing = True
        try:
            # STT
            user_text = await self.pipeline.transcribe(audio_bytes, content_type='audio/webm')
            await self._send_status('transcript', text=user_text)

            # Ensure system prompt file before parallel tasks
            self.pipeline._ensure_system_prompt_file()

            # Run filler sequence and main response in parallel
            main_task = asyncio.create_task(self._main_response(user_text))
            filler_task = asyncio.create_task(self._filler_sequence(user_text, main_task))

            try:
                response_text, response_audio = await main_task
            except Exception:
                filler_task.cancel()
                try:
                    await filler_task
                except asyncio.CancelledError:
                    pass
                raise

            # Stop fillers
            filler_task.cancel()
            try:
                await filler_task
            except asyncio.CancelledError:
                pass

            # Send main response
            await self._send_status('response', text=response_text)
            await self.send(bytes_data=response_audio)
            await self._send_json({'type': 'done'})
            # Track cost for full turn (STT + LLM + TTS)
            await self._track_cost(COST_PER_TURN_MILLICENTS)
        except Exception as e:
            logger.exception(f"Voice pipeline error for {self.agent_name}")
            await self._send_json({'type': 'error', 'message': 'Voice processing failed. Please try again.'})
        finally:
            self._processing = False

    async def _main_response(self, user_text: str):
        """Run main LLM + TTS pipeline."""
        response_text = await self.pipeline.think(user_text)
        response_audio = await self.pipeline.speak(response_text)
        return response_text, response_audio

    async def _filler_sequence(self, user_text: str, main_task: asyncio.Task):
        """Tier-1: delayed pre-recorded filler. Tier-2: contextual mumble. Tier-3: periodic voiced progress."""
        try:
            # Tier 1: delayed pre-recorded filler
            await asyncio.sleep(random.uniform(0.5, 2.0))
            if main_task.done():
                return

            filler = self.pipeline.get_filler()
            if filler:
                await self.send(bytes_data=filler)

            # Tier 2: contextual filler via Haiku + Flash TTS
            if main_task.done():
                return

            filler_text = await self.pipeline.generate_contextual_filler(user_text)
            if main_task.done() or not filler_text:
                pass  # Continue to tier 3 even if tier 2 failed
            else:
                filler_audio = await self.pipeline.speak_flash(filler_text)
                if not main_task.done():
                    await self.send(bytes_data=filler_audio)

            # Tier 3: periodic voiced progress narration (~every 15s)
            while not main_task.done():
                await asyncio.sleep(15)
                if main_task.done():
                    break

                narration = await self.pipeline.generate_progress_narration(user_text)
                if main_task.done() or not narration:
                    break

                narration_audio = await self.pipeline.speak_flash(narration)
                if main_task.done():
                    break

                await self.send(bytes_data=narration_audio)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Filler failures are non-critical
            logger.warning(f"Filler error for {self.agent_name}: {e}")

    async def _send_json(self, data: dict):
        await self.send(text_data=orjson.dumps(data).decode())

    async def _send_status(self, status: str, **kwargs):
        """Callback for pipeline status updates."""
        msg = {'type': 'status', 'status': status}
        msg.update(kwargs)
        await self._send_json(msg)

    @database_sync_to_async
    def _load_agent_config(self, agent_name: str):
        """Load agent voice config from DB. Returns None if not found or not voice-enabled."""
        from agents.models import Agent
        try:
            agent = Agent.objects.get(name=agent_name, voice_enabled=True, is_active=True)
            return {
                'voice_id': agent.voice_id,
                'voice_system_prompt': agent.voice_system_prompt,
            }
        except Agent.DoesNotExist:
            return None
