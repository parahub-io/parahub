"""Voice notes: a spoken message that arrives in the listener's language.

Two people write nothing. Each records in their own language; the recipient hears
the message in theirs, spoken in the sender's own cloned voice, and reads both
texts. Asynchronous by design — a walkie-talkie with a delay, not a call.

Four rows carry the feature:

- ``VoiceConsent`` — append-only proof that voice processing was lawful at the
  time it happened. A voiceprint is biometric data (GDPR Art. 9), so the consent
  record has to outlive the clone it authorised: rows are never deleted, revoke
  only stamps ``revoked_at``.
- ``VoiceClone`` — the ElevenLabs voice built from the profile's own recordings.
  One per profile, deletable by its owner at any time.
- ``VoiceNote`` — the message itself. The **texts are the record** and are kept
  indefinitely; the synthesised audio is a rendering of them and expires.
- ``VoiceLiveTurn`` — the meter for live, face-to-face mode, and nothing else:
  how many seconds were spoken and between which two languages. No text, no
  audio, no second party — see the class docstring.

Volume is a few dozen rows a day, so PostgreSQL is the right home — the CQRS rule
is about GPS-class write frequency, not about conversations.

Everything here hangs off the account's **primary** profile, never the active
pseudonymous one: a voiceprint identifies a person, so attaching it to a
pseudonym would hand out exactly the link that pseudonym exists to withhold.
"""

from django.db import models

from core.models import ULIDModel
from identity.models import Profile

# Bumped whenever the wording a user agreed to changes, so an old grant is never
# silently re-read as agreement to new terms.
CONSENT_TEXT_VERSION = '1'


class VoiceConsent(ULIDModel):
    """One explicit grant (or its revocation) of voice-cloning consent.

    Append-only: a revoked row stays as evidence that the processing which
    already happened was authorised. `evidence` keeps what the grant was made
    from — the UI locale, the consent copy's version, the request's IP — because
    "they clicked yes" is only defensible if we can say what "yes" was next to.
    """

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='voice_consents',
    )
    granted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    consent_text_version = models.CharField(max_length=16, default=CONSENT_TEXT_VERSION)
    evidence = models.JSONField(
        default=dict, blank=True,
        help_text="Context of the grant: locale, user agent, IP, consent copy",
    )

    class Meta:
        db_table = 'voice_consents'
        indexes = [
            models.Index(fields=['profile', '-granted_at']),
        ]

    def __str__(self):
        state = 'revoked' if self.revoked_at else 'active'
        return f"VoiceConsent({self.profile_id}, {state})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


def has_active_consent(profile) -> bool:
    """True when this profile currently allows its voice to be processed."""
    return VoiceConsent.objects.filter(
        profile=profile, revoked_at__isnull=True,
    ).exists()


class VoiceClone(ULIDModel):
    """The ElevenLabs voice built from a profile's own speech.

    Built in two passes: a fast clone once enough audio has piled up, then a
    refined one, after which the retained samples are deleted (§ retention). A
    clone is never evicted to make room for someone else's — deleting a person's
    voice without being asked is not a cache policy.
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        REVOKED = 'REVOKED', 'Revoked'

    profile = models.OneToOneField(
        Profile, on_delete=models.CASCADE, related_name='voice_clone',
    )
    provider = models.CharField(max_length=32, default='elevenlabs')
    voice_id = models.CharField(max_length=64, db_index=True)
    stage = models.PositiveSmallIntegerField(
        default=1, help_text="1 = first clone, 2 = refined clone (samples deleted)",
    )
    sample_seconds = models.FloatField(
        default=0.0, help_text="Seconds of speech the clone was built from",
    )
    key_hash = models.CharField(
        max_length=32, blank=True, default='',
        help_text=(
            "Fingerprint of the provider account the voice lives on; empty = the "
            "platform account. A clone is only ever touched with the key that can "
            "reach it, so a future bring-your-own key can neither read nor delete "
            "a voice on another account."
        ),
    )
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.ACTIVE, db_index=True,
    )
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'voice_clones'

    def __str__(self):
        return f"VoiceClone({self.profile_id}, {self.voice_id}, stage {self.stage})"

    @property
    def is_usable(self) -> bool:
        return self.status == self.Status.ACTIVE and bool(self.voice_id)


class VoiceNote(ULIDModel):
    """One spoken message: what was said, what was heard, and in whose voice.

    ``source_text``/``target_text`` are the canonical record of the exchange and
    are kept — a literal translation is what makes a voice note usable as
    evidence in a dispute later. The mp3 under ``audio_path`` is a rendering and
    expires at ``audio_expires_at``; the note stays readable after that.
    """

    sender = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='sent_voice_notes',
    )
    recipient = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='received_voice_notes',
    )

    source_lang = models.CharField(max_length=8, blank=True, default='')
    target_lang = models.CharField(max_length=8, blank=True, default='')
    source_text = models.TextField(blank=True, default='')
    target_text = models.TextField(blank=True, default='')

    audio_seconds = models.FloatField(
        default=0.0, help_text="Length of the recording the sender made (quota unit)",
    )
    voice_id_used = models.CharField(max_length=64, blank=True, default='')
    audio_path = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Path under MEDIA_ROOT; served only through the gated endpoint",
    )
    audio_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    stt_model = models.CharField(max_length=64, blank=True, default='')
    translation_model = models.CharField(max_length=64, blank=True, default='')
    tts_model = models.CharField(max_length=64, blank=True, default='')

    delivered_at = models.DateTimeField(null=True, blank=True)
    played_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'voice_notes'
        indexes = [
            # Thread view: every note between two people, newest first.
            models.Index(fields=['sender', 'recipient', '-id']),
            models.Index(fields=['recipient', 'sender', '-id']),
            # Monthly quota: seconds sent by one profile since a date.
            models.Index(fields=['sender', 'created_at']),
            # Inbox badge.
            models.Index(fields=['recipient', 'played_at']),
        ]

    def __str__(self):
        return f"VoiceNote({self.sender_id} -> {self.recipient_id}, {self.audio_seconds:.1f}s)"

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_path)


class VoiceLiveTurn(ULIDModel):
    """What is left of one utterance in live, face-to-face mode: its length.

    Live mode is one phone lying between two people, and the second person has
    no account here. They agreed to nothing, so nothing they said is written
    down — not the audio, not the transcript, not the translation. That is the
    same rule the clone already follows ("only the speaker's own recordings are
    ever retained"), applied to the one place where the other side's speech
    passes through the server at all.

    A row still has to exist, because the providers are billed either way: the
    quota is the sum of what a profile has sent, and an unmetered mode would be
    a hole in it. So this is the smallest thing that can be metered — seconds
    and a language pair, both sides charged to the profile whose phone it is.
    Which of the two people spoke is kept because it decides whose voice spoke
    the answer, and because a session that is 90 % guest is a different product
    from one that is 90 % host.
    """

    class Side(models.TextChoices):
        HOST = 'HOST', 'Host'      # the account holder, whose quota this spends
        GUEST = 'GUEST', 'Guest'   # the person across the table, no account

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='voice_live_turns',
    )
    spoken_by = models.CharField(max_length=5, choices=Side.choices, default=Side.HOST)
    source_lang = models.CharField(max_length=8, blank=True, default='')
    target_lang = models.CharField(max_length=8, blank=True, default='')
    audio_seconds = models.FloatField(
        default=0.0, help_text="Length of the utterance (quota unit)",
    )
    voice_id_used = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        db_table = 'voice_live_turns'
        indexes = [
            # Monthly quota: seconds spoken on this profile's phone since a date.
            models.Index(fields=['profile', 'created_at']),
        ]

    def __str__(self):
        return (f"VoiceLiveTurn({self.profile_id}, {self.spoken_by}, "
                f"{self.source_lang}->{self.target_lang}, {self.audio_seconds:.1f}s)")
