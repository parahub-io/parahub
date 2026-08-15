"""Building, and destroying, a person's voice — the consent-gated half.

A voiceprint is biometric data under GDPR Art. 9: forbidden to process unless the
person explicitly said yes, and revocable at any moment. Everything here is built
around those two sentences.

  - Nothing is retained without an active `VoiceConsent` row. Collection stops the
    instant it is revoked, mid-build included.
  - Only the speaker's **own** recordings are kept. The other side of a
    conversation never opted in and is never stored.
  - Samples are deleted once the refined clone exists; the clone itself is
    deleted on request, remotely as well as here.
  - A clone is never evicted to free a slot for someone else. The sibling project
    this is ported from does that, and deleting a person's voice to make room is
    not a cache policy anyone consented to.

Cloning runs in the background (`parahub.background.spawn`), so a voice note is
never slowed down by it.
"""

import logging
import re
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from voice.models import CONSENT_TEXT_VERSION, VoiceClone, VoiceConsent

logger = logging.getLogger(__name__)

# ElevenLabs rejects samples shorter than ~4.6 s, so 5 s is the floor worth keeping.
SAMPLE_MIN_SECONDS = 5.0
# First clone as soon as there is enough to work with, refined pass at double that.
STAGE1_SECONDS = 60.0
STAGE2_SECONDS = 120.0
# Hard ceiling on retained audio per person — data minimisation, not a cost cap.
MAX_TOTAL_SECONDS = 180.0
# A failed build (provider out of voice slots, key without write permission) waits
# an hour instead of retrying on every note.
RETRY_SECONDS = 3600.0

SAMPLES_ROOT = Path(settings.MEDIA_ROOT) / 'private' / 'voice_samples'

# Both guards live in Redis rather than in process memory: several uvicorn
# workers serve the same person, and two of them building a clone at once would
# leave one voice orphaned on the provider account, burning a voice slot nobody
# can find. A Redis outage degrades to "allowed" — the app is already broken by
# then, and refusing to ever clone would be the worse failure.
_CLONE_LOCK_KEY = 'voice:clone:building:{}'
_CLONE_LOCK_TTL = 900  # longer than any build; released in `finally` anyway
_CLONE_BACKOFF_KEY = 'voice:clone:backoff:{}'


def _redis():
    from parahub.services.redis_pool import get_redis
    return get_redis()


def _claim_build(profile_id: str) -> bool:
    try:
        return bool(_redis().set(_CLONE_LOCK_KEY.format(profile_id), '1',
                                 nx=True, ex=_CLONE_LOCK_TTL))
    except Exception as e:
        logger.warning("Clone lock unavailable for %s (%s) — proceeding", profile_id, e)
        return True


def _release_build(profile_id: str) -> None:
    try:
        _redis().delete(_CLONE_LOCK_KEY.format(profile_id))
    except Exception:
        pass  # the TTL is the backstop


def _is_backed_off(profile_id: str) -> bool:
    try:
        return bool(_redis().exists(_CLONE_BACKOFF_KEY.format(profile_id)))
    except Exception:
        return False


def _back_off(profile_id: str) -> None:
    try:
        _redis().setex(_CLONE_BACKOFF_KEY.format(profile_id), int(RETRY_SECONDS), '1')
    except Exception:
        pass


def _clear_backoff(profile_id: str) -> None:
    try:
        _redis().delete(_CLONE_BACKOFF_KEY.format(profile_id))
    except Exception:
        pass


def _safe_id(value: str) -> str:
    """A ULID is already safe, but it becomes a directory name — prove it."""
    return re.sub(r'[^A-Za-z0-9]', '', str(value or ''))[:26]


def samples_dir(profile_id: str) -> Path:
    return SAMPLES_ROOT / _safe_id(profile_id)


def retained_seconds(profile_id: str) -> float:
    """Total retained speech, read off the filenames.

    Duration is encoded in the name (milliseconds, zero-padded) because there is
    no audio decoder on this host and re-asking the provider for a number we
    already had would cost money.
    """
    total = 0.0
    directory = samples_dir(profile_id)
    try:
        for entry in directory.iterdir():
            try:
                total += int(entry.name.split('-', 1)[0]) / 1000.0
            except (ValueError, IndexError):
                continue
    except OSError:
        return 0.0
    return total


# ===== Consent =====

def active_consent(profile) -> VoiceConsent | None:
    return VoiceConsent.objects.filter(
        profile=profile, revoked_at__isnull=True,
    ).order_by('-granted_at').first()


def grant_consent(profile, *, evidence: dict = None) -> VoiceConsent:
    """Record an explicit opt-in. Re-granting while active is a no-op."""
    existing = active_consent(profile)
    if existing:
        return existing
    consent = VoiceConsent.objects.create(
        profile=profile,
        consent_text_version=CONSENT_TEXT_VERSION,
        evidence=evidence or {},
    )
    logger.info("Voice consent granted by profile %s (text v%s)",
                profile.id, consent.consent_text_version)
    return consent


def revoke_consent(profile) -> None:
    """Withdraw consent: collection stops, the clone and every sample go.

    The consent rows themselves stay — they are the proof that the processing
    which already happened was lawful, and destroying that evidence would leave
    the association unable to answer for it.
    """
    now = timezone.now()
    VoiceConsent.objects.filter(profile=profile, revoked_at__isnull=True).update(revoked_at=now)
    delete_voice(profile, reason='consent revoked')
    logger.info("Voice consent revoked by profile %s", profile.id)


# ===== Clone lifecycle =====

def usable_clone(profile) -> VoiceClone | None:
    """The clone a note may be spoken in, or None.

    Consent is re-checked here rather than trusted from build time: a revoked
    consent must silence the clone even if a row somehow survived.
    """
    clone = VoiceClone.objects.filter(
        profile=profile, status=VoiceClone.Status.ACTIVE,
    ).first()
    if not clone or not clone.voice_id:
        return None
    if not active_consent(profile):
        return None
    return clone


def clone_status(profile) -> dict:
    """What the profile screen shows: consent, progress, clone state."""
    consent = active_consent(profile)
    clone = VoiceClone.objects.filter(profile=profile).first()
    collected = retained_seconds(profile.id)
    return {
        'consent': bool(consent),
        'consent_granted_at': consent.granted_at.isoformat() if consent else None,
        'consent_text_version': consent.consent_text_version if consent else CONSENT_TEXT_VERSION,
        'has_clone': bool(clone and clone.status == VoiceClone.Status.ACTIVE),
        'stage': clone.stage if clone and clone.status == VoiceClone.Status.ACTIVE else 0,
        'collected_seconds': round(collected, 1),
        'next_threshold_seconds': _next_threshold(clone),
        'sample_seconds': round(clone.sample_seconds, 1) if clone else 0.0,
        'last_used_at': clone.last_used_at.isoformat() if clone and clone.last_used_at else None,
    }


def _next_threshold(clone: VoiceClone | None) -> float:
    """Seconds of speech still to collect before the next build, 0 when done."""
    if clone is None or clone.status != VoiceClone.Status.ACTIVE:
        return STAGE1_SECONDS
    if clone.stage < 2:
        return STAGE2_SECONDS
    return 0.0


def _elevenlabs_client(timeout: float = 120.0):
    from elevenlabs.client import ElevenLabs
    from voice.services.pipeline import elevenlabs_key

    key = elevenlabs_key()
    if not key:
        raise RuntimeError("No ElevenLabs key configured")
    return ElevenLabs(api_key=key, timeout=timeout)


def retain_sample(profile, audio_bytes: bytes, seconds: float, ext: str) -> bool:
    """Keep one of the speaker's own recordings as clone material.

    Returns False (and keeps nothing) whenever consent is missing, the clip is
    too short to be usable, the refined clone already exists, or the retention
    ceiling has been reached.
    """
    if seconds < SAMPLE_MIN_SECONDS:
        return False
    if not active_consent(profile):
        return False

    clone = VoiceClone.objects.filter(profile=profile).first()
    if clone and clone.status == VoiceClone.Status.ACTIVE and clone.stage >= 2:
        return False  # refined clone done — stop hoarding audio

    directory = samples_dir(profile.id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if retained_seconds(profile.id) >= MAX_TOTAL_SECONDS:
            return False
        name = f"{int(seconds * 1000):08d}-{uuid.uuid4().hex[:8]}.{ext}"
        (directory / name).write_bytes(audio_bytes)
        return True
    except OSError as e:
        logger.error("Voice sample retention failed for profile %s: %s", profile.id, e)
        return False


def maybe_start_clone(profile) -> None:
    """Queue a background build when enough speech has piled up. Non-blocking."""
    profile_id = profile.id
    if _is_backed_off(profile_id) or not active_consent(profile):
        return

    clone = VoiceClone.objects.filter(profile=profile).first()
    # A REVOKED row means the previous clone was deleted (by its owner or by the
    # provider). Consent is active again and the samples were wiped with it, so
    # this is a fresh start, not a resumed one.
    if clone is not None and clone.status == VoiceClone.Status.REVOKED:
        clone = None

    total = retained_seconds(profile_id)
    if clone is None:
        if total < STAGE1_SECONDS:
            return
        target_stage = 1
    elif clone.stage == 1:
        if total < STAGE2_SECONDS:
            return
        target_stage = 2
    else:
        return

    if not _claim_build(profile_id):
        return

    from parahub.background import spawn
    spawn(lambda: _clone_worker(profile_id, target_stage, total))


def _clone_worker(profile_id: str, target_stage: int, total_seconds: float) -> None:
    """Build the clone from the retained samples. Runs off the request path."""
    from identity.models import Profile

    created_voice_id = ''
    client = None
    try:
        profile = Profile.objects.filter(id=profile_id).first()
        if profile is None or not active_consent(profile):
            return

        directory = samples_dir(profile_id)
        files = sorted(p for p in directory.iterdir() if p.is_file())
        if not files:
            return

        client = _elevenlabs_client()
        handles = [open(path, 'rb') for path in files]
        try:
            voice = client.voices.ivc.create(
                # Named by ULID on purpose: the provider dashboard must not carry
                # a roster of who has a voiceprint here.
                name=f"parahub-{profile_id}",
                files=handles,
                remove_background_noise=True,  # phone-mic audio is never studio-clean
            )
        finally:
            for handle in handles:
                handle.close()
        created_voice_id = voice.voice_id

        # Consent can be withdrawn while the provider is working. If it was, the
        # voice that just came into existence must not outlive that decision.
        profile.refresh_from_db()
        if not active_consent(profile):
            logger.info("Voice consent withdrawn mid-build for %s — discarding %s",
                        profile_id, created_voice_id)
            _delete_remote_voice(client, created_voice_id)
            return

        previous = VoiceClone.objects.filter(profile=profile).first()
        previous_voice_id = previous.voice_id if previous else ''
        VoiceClone.objects.update_or_create(
            profile=profile,
            defaults={
                'voice_id': created_voice_id,
                'stage': target_stage,
                'sample_seconds': total_seconds,
                'status': VoiceClone.Status.ACTIVE,
                'last_used_at': timezone.now(),
            },
        )
        if previous_voice_id and previous_voice_id != created_voice_id:
            _delete_remote_voice(client, previous_voice_id)

        if target_stage >= 2:
            shutil.rmtree(directory, ignore_errors=True)

        _clear_backoff(profile_id)
        logger.info("Voice clone stage %s ready for profile %s: %s (%.0fs of samples)",
                    target_stage, profile_id, created_voice_id, total_seconds)
    except Exception as e:
        # Covers the persistent failures too (provider out of voice slots, key
        # without Voices write) — without a backoff every note would retry.
        _back_off(profile_id)
        logger.error("Voice clone build failed for profile %s: %s", profile_id, e)
        if created_voice_id and client is not None:
            _delete_remote_voice(client, created_voice_id)
    finally:
        _release_build(profile_id)


def _delete_remote_voice(client, voice_id: str) -> bool:
    if not voice_id:
        return True
    try:
        client.voices.delete(voice_id)
        return True
    except Exception as e:
        logger.error("Deleting remote voice %s failed: %s", voice_id, e)
        return False


def delete_voice(profile, *, reason: str = 'user request') -> bool:
    """Remove the clone everywhere: provider, samples, and our own row.

    The row is kept but marked REVOKED rather than deleted, so "this profile once
    had a clone and it was removed on <date>" stays answerable. Returns whether
    the provider confirmed the deletion — a False means a voice may still exist
    upstream and someone has to look.
    """
    clone = VoiceClone.objects.filter(profile=profile).first()
    shutil.rmtree(samples_dir(profile.id), ignore_errors=True)
    if clone is None:
        return True

    removed = True
    if clone.voice_id:
        try:
            removed = _delete_remote_voice(_elevenlabs_client(timeout=30.0), clone.voice_id)
        except Exception as e:
            logger.error("Voice deletion for profile %s could not reach the provider: %s",
                         profile.id, e)
            removed = False

    clone.status = VoiceClone.Status.REVOKED
    clone.save(update_fields=['status', 'updated_at'])
    logger.info("Voice clone %s revoked for profile %s (%s), provider deleted=%s",
                clone.voice_id, profile.id, reason, removed)
    return removed


def drop_unusable_clone(profile, voice_id: str, detail: str = '') -> None:
    """The provider refused this voice — stop trying to speak in it.

    Fires when a voice was deleted upstream or flagged by moderation. The row is
    marked REVOKED and the samples go, so the next note falls back to the stock
    voice instead of failing, and the person can opt in again from a clean slate.
    """
    logger.warning("Voice %s rejected by provider for profile %s (%s) — dropping the clone",
                   voice_id, profile.id, detail[:200])
    VoiceClone.objects.filter(profile=profile, voice_id=voice_id).update(
        status=VoiceClone.Status.REVOKED,
    )
    shutil.rmtree(samples_dir(profile.id), ignore_errors=True)
