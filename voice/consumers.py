"""WebSocket transport for the two ways of speaking through the platform.

Why a socket and not a POST: the work is three model calls deep and takes about
two seconds. Parking that on the REST budget (p95 under 50 ms) would be lying
about what the API is, and the sender would stare at a spinner with nothing to
read. Here the stages arrive as they finish — heard, translating, speaking —
and the result lands on the same connection.

One connection serves both modes because they differ only in what they address:
a note goes to a profile, a live turn goes to a language. Everything before that
— the handshake, the quota, the rate limiter, the error vocabulary — is shared,
and a second consumer would be a second copy of it.

Protocol, common
    server -> {"type": "connection.established"}
    server -> {"type": "ready", "profile_id", "language", "quota", "limits"}
    server -> {"type": "status", "status": "transcribing"|"transcribed"|
                                           "translating"|"speaking"}
    server -> {"type": "error", "code": "...", "message": "..."}

Notes (asynchronous, to a person)
    client -> {"type": "note.begin", "recipient_id": "<profile id or handle>"}
    client -> <binary audio frame>
    server -> {"type": "note.ready", "recipient": {...}}
    server -> {"type": "note", "note": {...}, "quota": {...}}

Live (face to face, one phone, no second account)
    client -> {"type": "live.begin", "source_lang", "target_lang",
               "spoken_by": "HOST"|"GUEST"}
    client -> <binary audio frame>
    server -> {"type": "live.ready", "source_lang", "target_lang", "spoken_by"}
    server -> {"type": "live.turn", "turn": {...}, "quota": {...}}
    server -> <binary mp3 frame>          # always straight after `live.turn`

The audio of a live turn comes back on the wire and is never stored, so the
frame order is the only thing binding it to the metadata that describes it.

One utterance in flight per connection; the next `*.begin` is refused until the
current one lands. The last `*.begin` also decides which mode the audio frame
that follows is read as.
"""

import logging
import time

from channels.db import database_sync_to_async

from parahub.consumers.base import AuthenticatedJsonWebsocketConsumer
from voice.services import live as live_service
from voice.services import notes as notes_service
from voice.services import pipeline

logger = logging.getLogger(__name__)

# Far above any conversation, low enough that a client stuck in a loop cannot
# run up a provider bill — the monthly quota does not bind staff, this does.
NOTES_PER_HOUR = 60
# A live conversation is turns, not messages: two people going back and forth
# pass 60 an hour without trying. One every fifteen seconds for a solid hour is
# still well past any real exchange.
LIVE_TURNS_PER_HOUR = 240


class VoiceNoteConsumer(AuthenticatedJsonWebsocketConsumer):
    """Send voice notes, or translate a face-to-face conversation."""

    async def connect(self):
        self.user = self.scope.get('user')
        self.profile = self.scope.get('profile')
        self._mode = ''
        self._recipient = None
        self._live = None
        self._processing = False

        # Accept before refusing anything. A close without a prior accept answers
        # the upgrade with HTTP 403, and the Android WebView renders that as a
        # full-page system error instead of handing the app a close code it can
        # act on (`parahub/consumers/agent_voice.py` hit this first).
        await self.accept()
        await self.send_json({'type': 'connection.established'})

        if not self.user or not self.user.is_authenticated:
            await self._error('unauthenticated', "Sign in to send voice notes")
            await self.close(code=4001)
            return
        if not self.profile:
            # Authenticated but profile-less: nothing here can be addressed.
            await self._error('no_profile', "This account has no profile")
            await self.close(code=4003)
            return

        quota = await database_sync_to_async(notes_service.quota_for)(self.profile)
        await self.send_json({
            'type': 'ready',
            'profile_id': self.profile.id,
            # The language the sender's notes are attributed to when detection
            # cannot place a clip. The server owns this — a client reading it off
            # its own auth store gets whatever that store happened to hydrate.
            'language': self.profile.preferred_language or pipeline.DEFAULT_LANGUAGE,
            'quota': quota.as_dict(),
            'limits': {
                'max_bytes': notes_service.MAX_AUDIO_BYTES,
                'max_seconds': notes_service.MAX_NOTE_SECONDS,
            },
        })

    async def receive(self, text_data=None, bytes_data=None):
        """Route binary frames to the pipeline; JSON keeps the base's dispatch."""
        if bytes_data is not None:
            await self._handle_audio(bytes_data)
            return
        await super().receive(text_data=text_data)

    async def handle_note_begin(self, content):
        """Name the recipient for the audio frame that follows."""
        if self._processing:
            await self._error('busy', "A note is still being processed")
            return
        recipient_ref = (content.get('recipient_id') or '').strip()
        if not recipient_ref:
            await self._error('no_recipient', "recipient_id is required")
            return

        recipient, reason = await self._resolve_recipient(recipient_ref)
        if recipient is None:
            await self._error(reason, _RECIPIENT_ERRORS[reason])
            return

        self._mode = 'note'
        self._recipient = recipient
        await self.send_json({
            'type': 'note.ready',
            'recipient': {
                'id': recipient.id,
                'hna': recipient.hna,
                'display_name': recipient.display_name or recipient.local_name,
                'language': recipient.preferred_language or pipeline.DEFAULT_LANGUAGE,
            },
        })

    async def handle_live_begin(self, content):
        """Name the language pair, and which half of the screen was tapped.

        Sent before every turn rather than once per session: either person can
        change their language mid-conversation, and the side alternates with
        each utterance, so there is no state here worth keeping across turns.
        """
        if self._processing:
            await self._error('busy', "A turn is still being processed")
            return

        source = pipeline.normalize_language(content.get('source_lang') or '')
        target = pipeline.normalize_language(content.get('target_lang') or '')
        spoken_by = (content.get('spoken_by') or '').upper()

        if source not in pipeline.LANGUAGE_NAMES or target not in pipeline.LANGUAGE_NAMES:
            await self._error('unsupported_language', "That language is not available")
            return
        if source == target:
            await self._error('same_language', "Pick two different languages")
            return
        if spoken_by not in (live_service.HOST, live_service.GUEST):
            await self._error('invalid_side', "spoken_by must be HOST or GUEST")
            return

        self._mode = 'live'
        self._live = (spoken_by, source, target)
        await self.send_json({
            'type': 'live.ready',
            'spoken_by': spoken_by,
            'source_lang': source,
            'target_lang': target,
        })

    async def handle_ping(self, content):
        await self.send_json({'type': 'pong'})

    async def _handle_audio(self, audio_bytes: bytes):
        if self._processing:
            await self._error('busy', "Still working on the previous recording")
            return
        if self._mode == 'live':
            if self._live is None:
                await self._error('no_direction', "Send live.begin before the audio")
                return
        elif self._recipient is None:
            await self._error('no_recipient', "Send note.begin before the audio")
            return
        if len(audio_bytes) < notes_service.MIN_AUDIO_BYTES:
            await self._error('audio_too_short', "Nothing was recorded")
            return
        if len(audio_bytes) > notes_service.MAX_AUDIO_BYTES:
            await self._error('audio_too_large', "Recording is too large")
            return

        live = self._mode == 'live'
        ceiling = LIVE_TURNS_PER_HOUR if live else NOTES_PER_HOUR
        if not await self._within_rate_limit('live' if live else 'notes', ceiling):
            await self._error('rate_limited', "Too much speech in the last hour")
            return

        self._processing = True
        started = time.monotonic()
        try:
            if live:
                await self._run_live_turn(audio_bytes, started)
            else:
                await self._run_note(audio_bytes, started)
        except notes_service.QuotaExceeded as e:
            await self.send_json({
                'type': 'error',
                'code': 'quota_exceeded',
                'message': "Monthly voice limit reached",
                'minutes_used': round(e.used_seconds / 60.0, 1),
                'minutes_limit': round(e.limit_seconds / 60.0, 1),
            })
        except notes_service.NoteTooLong as e:
            await self._error(
                'note_too_long',
                f"Recording is {e.seconds:.0f}s, longer than the {notes_service.MAX_NOTE_SECONDS:.0f}s limit",
            )
        except live_service.SameLanguage:
            await self._error('same_language', "Pick two different languages")
        except pipeline.EmptyTranscription:
            await self._error('empty_transcription', "Nothing could be heard — try again")
        except ValueError as e:
            await self._error('invalid_audio', str(e))
        except Exception:
            logger.exception("Voice pipeline failed for profile %s (live=%s)",
                             self.profile.id, live)
            await self._error('pipeline_failed', "That could not be sent — try again")
        finally:
            self._processing = False

    async def _run_note(self, audio_bytes: bytes, started: float):
        note = await notes_service.create_note(
            self.profile, self._recipient, audio_bytes, on_status=self._status,
        )
        quota = await database_sync_to_async(notes_service.quota_for)(self.profile)
        await self.send_json({
            'type': 'note',
            'note': notes_service.serialize_note(note, viewer=self.profile),
            'quota': quota.as_dict(),
            'took_ms': int((time.monotonic() - started) * 1000),
        })

    async def _run_live_turn(self, audio_bytes: bytes, started: float):
        spoken_by, source, target = self._live
        turn = await live_service.translate_turn(
            self.profile, audio_bytes, spoken_by=spoken_by,
            source_lang=source, target_lang=target, on_status=self._status,
        )
        quota = await database_sync_to_async(notes_service.quota_for)(self.profile)
        # Metadata first, then the audio it describes: nothing about a live turn
        # is stored, so the client has no id to fetch it by and the frame order
        # is what pairs them.
        await self.send_json({
            'type': 'live.turn',
            'turn': turn.as_dict(),
            'quota': quota.as_dict(),
            'took_ms': int((time.monotonic() - started) * 1000),
        })
        await self.send(bytes_data=turn.audio)

    async def _status(self, stage: str, **extra):
        await self.send_json({'type': 'status', 'status': stage, **extra})

    async def _error(self, code: str, message: str):
        await self.send_json({'type': 'error', 'code': code, 'message': message})

    async def _within_rate_limit(self, bucket: str, ceiling: int) -> bool:
        from parahub.services.redis_pool import get_redis

        def _check():
            try:
                redis = get_redis()
                key = f"voice:{bucket}:rate:{self.profile.id}:{int(time.time()) // 3600}"
                count = redis.incr(key)
                if count == 1:
                    redis.expire(key, 7200)
                return count <= ceiling
            except Exception:
                # A counter that cannot be read must not stop a conversation.
                return True

        return await database_sync_to_async(_check)()

    @database_sync_to_async
    def _resolve_recipient(self, reference: str):
        """Profile for a ULID or a handle, refusing the addresses we must not use.

        A handle is only unique within an instance, so it is looked up on the
        sender's own — voice notes do not cross nodes in v1, and an unscoped
        handle lookup would start picking the wrong person the day one does.
        """
        from identity.models import Profile
        from identity.services.blocks import dm_blocked_between_accounts

        local = Profile.objects.select_related('account', 'instance')
        recipient = (
            local.filter(id=reference).first()
            or local.filter(instance=self.profile.instance,
                            local_name=reference.split('@')[0]).first()
        )
        if recipient is None:
            return None, 'recipient_not_found'
        if recipient.id == self.profile.id:
            return None, 'self_note'
        if dm_blocked_between_accounts(self.profile.account_id, recipient.account_id):
            return None, 'blocked'
        return recipient, ''


_RECIPIENT_ERRORS = {
    'recipient_not_found': "No such person",
    'self_note': "A voice note needs someone on the other end",
    'blocked': "This conversation is not available",
}
