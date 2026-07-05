from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models as gis_models
from django.db import models
from core.models import ULIDModel, Instance


class Account(AbstractUser, ULIDModel):
    """Custom user model for ParaHub."""
    instance = models.ForeignKey(Instance, on_delete=models.PROTECT, related_name="accounts")
    preferences = models.JSONField(default=dict, blank=True)
    mail_password = models.CharField(max_length=256, blank=True, default='')  # Fernet-encrypted
    registration_ip = models.GenericIPAddressField(null=True, blank=True)
    is_test = models.BooleanField(default=False, db_index=True, help_text="Test account, hidden from public listings")
    is_bot = models.BooleanField(default=False, db_index=True, help_text="AI bot account, hidden from public listings")

    def __str__(self):
        return f"{self.username}@{self.instance.domain}"


class Profile(ULIDModel):
    """User profile with extended information."""

    class Language(models.TextChoices):
        ENGLISH = 'en', 'English'
        SPANISH = 'es', 'Español'
        FRENCH = 'fr', 'Français'
        GERMAN = 'de', 'Deutsch'
        PORTUGUESE = 'pt', 'Português'
        RUSSIAN = 'ru', 'Русский'

    class ProfileType(models.TextChoices):
        PERSONAL = 'PERSONAL', 'Personal Profile'
        PSEUDONYMOUS = 'PSEUDONYMOUS', 'Pseudonymous Profile'

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="profiles")
    instance = models.ForeignKey(Instance, on_delete=models.PROTECT, related_name="profiles")
    local_name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=255, blank=True)
    bio = models.CharField(max_length=300, blank=True, help_text="Short bio / about me")

    # Profile type - PERSONAL is default and created automatically on signup
    profile_type = models.CharField(
        max_length=20,
        choices=ProfileType.choices,
        default=ProfileType.PERSONAL,
        db_index=True,
        help_text="Type of profile: personal (main) or pseudonymous"
    )
    is_primary = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Primary profile (created on signup, cannot be deleted)"
    )

    pgp_public_key = models.TextField(blank=True)
    pgp_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)

    ln_address = models.CharField(
        max_length=255,
        blank=True,
        help_text="Lightning address (e.g., user@breez.tips)"
    )
    spark_address = models.CharField(
        max_length=512,
        blank=True,
        help_text="Spark address for direct P2P payments"
    )

    reputation_score = models.DecimalField(max_digits=12, decimal_places=4, default=0.0, db_index=True)
    is_verified_wot = models.BooleanField(default=False, db_index=True)

    location = gis_models.PointField(srid=4326, null=True, blank=True, geography=True)
    antispam_fee_sats = models.BigIntegerField(default=10)

    is_publicly_linked = models.BooleanField(default=True)
    name_public = models.BooleanField(
        default=False,
        help_text=(
            "If True, display_name (real name) is shown to everyone. If False "
            "(default for personal profiles), only the @handle is public; the real "
            "name is revealed to the owner and WoT-verified viewers. Trust on parahub "
            "is identity-linked, but the legal name is only needed at the moment of "
            "commitment (a signed contract), not at browse time."
        ),
    )
    preferred_language = models.CharField(max_length=5, choices=Language.choices, blank=True, default='')
    preferred_currency = models.CharField(max_length=3, default='EUR', help_text="User's preferred currency for marketplace (ISO 4217 code)")
    country_code = models.CharField(
        max_length=2, blank=True, default='', db_index=True,
        help_text="User's country (ISO 3166-1 alpha-2). Auto-detected on first login, can be overridden."
    )

    # Civic polls: declared residency + GDPR Art. 9 consent (see PK/civic-polls-system.md)
    residency_territory = models.ForeignKey(
        'geo.Territory', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='residents',
        help_text="Declared residency (any level; parish preferred). Private: used only for civic poll scoping."
    )
    residency_changed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Last residency change; 30-day cooldown guards against territory poll-shopping"
    )
    civic_opinion_consent = models.BooleanField(
        default=False,
        help_text="Explicit GDPR Art. 9(2)(a) consent to pseudonymized storage of opinion votes"
    )
    civic_opinion_consent_at = models.DateTimeField(null=True, blank=True)

    # Map style preference
    class MapStyle(models.TextChoices):
        OSM_LIBERTY = 'osm-liberty', 'OSM Liberty (Default)'
        POSITRON = 'positron', 'Positron'

    map_style = models.CharField(
        max_length=20,
        choices=MapStyle.choices,
        default=MapStyle.OSM_LIBERTY,
        help_text="Preferred map style for visualization"
    )

    # Global animation preference
    animation_enabled = models.BooleanField(
        default=True,
        help_text="Enable smooth animations in UI (transitions, map flyTo, etc). If disabled, instant transitions."
    )

    # Chat client preference
    class ChatClient(models.TextChoices):
        ELEMENT = 'element', 'Element (Desktop)'
        FLUFFY = 'fluffy', 'FluffyChat (Mobile)'
        CINNY = 'cinny', 'Cinny (Lightweight)'

    preferred_chat_client = models.CharField(
        max_length=20,
        choices=ChatClient.choices,
        default=ChatClient.ELEMENT,
        help_text="Preferred Matrix chat client for /chat route"
    )

    # Invite system
    invite_token = models.CharField(max_length=64, unique=True, blank=True, null=True, db_index=True, help_text="Unique token for inviting new users")
    invite_token_active = models.BooleanField(default=True, help_text="If false, invite token is disabled")
    invited_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='invited_profiles', help_text="Profile that invited this user via invite link")

    # Association support
    support_level = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal('0.1'),
        help_text="Association support percentage: 0, 0.1, or 1.0"
    )
    is_supporter = models.BooleanField(
        default=False, db_index=True,
        help_text="Has donated to the association at least once"
    )

    # Profile photos
    avatar = models.ImageField(
        upload_to='avatars/%Y/%m/',
        blank=True,
        null=True,
        help_text="Profile avatar for UI display (square, max 400x400)"
    )
    id_photo = models.ImageField(
        upload_to='private/id_photos/%Y/%m/',
        blank=True,
        null=True,
        help_text="Formal ID photo for Para-ID badge (passport-style, 3:4 ratio). "
                  "Stored under media/private/ (nginx internal) — served only via the "
                  "gated /profiles/{id}/id-photo/ endpoint to the owner or WoT-verified viewers."
    )
    id_photo_verified = models.BooleanField(
        default=False,
        help_text="AI verified: single face, front-facing, acceptable quality"
    )

    # Notification preferences (empty dict = all enabled)
    notification_prefs = models.JSONField(
        default=dict, blank=True,
        help_text="Per-category push notification preferences. Empty dict = all enabled."
    )

    @property
    def hna(self):
        """Human Network Address."""
        return f"{self.local_name}@{self.instance.domain}"

    def generate_invite_token(self, force_regenerate=False):
        """Generate or refresh invite token.

        Args:
            force_regenerate: If True, always generate new token even if one exists
        """
        if not self.invite_token or force_regenerate:
            import secrets
            self.invite_token = secrets.token_urlsafe(32)
        self.invite_token_active = True
        self.save(update_fields=['invite_token', 'invite_token_active'])
        return self.invite_token

    def toggle_invite_token(self):
        """Toggle invite token active status."""
        self.invite_token_active = not self.invite_token_active
        self.save(update_fields=['invite_token_active'])

    def is_invite_token_valid(self):
        """Check if invite token is valid."""
        return bool(self.invite_token and self.invite_token_active)

    def update_wot_status(self):
        """Recalculate and save is_verified_wot based on active verification count.

        Called automatically by Verification post_save/post_delete signals.
        Can also be called manually to fix stale state.
        """
        count = Verification.objects.filter(
            verified_profile=self,
            is_active=True
        ).count()
        new_status = count >= 3
        if self.is_verified_wot != new_status:
            self.is_verified_wot = new_status
            self.save(update_fields=['is_verified_wot'])
            return True  # status changed
        return False  # no change

    def can_create_additional_profiles(self):
        """Check if this profile can create organization or pseudonymous profiles.

        Only verified WoT members (3+ verifications) or foundation members can create additional profiles.
        """
        return self.is_verified_wot or self.is_foundation_member()

    def name_visible_to(self, viewer_profile=None):
        """Whether `viewer_profile` may see this profile's display_name (real name).

        Public when name_public=True (the opt-out toggle). Otherwise gated to the
        owner and WoT-verified viewers: trust on parahub is identity-linked, but the
        legal name is only needed at the moment of commitment (a signed contract),
        not at browse time — so anonymous / non-WoT viewers see only the @handle.
        """
        return Profile.name_visible(self.name_public, self.id, viewer_profile)

    @staticmethod
    def name_visible(name_public, owner_profile_id, viewer_profile=None):
        """Static twin of name_visible_to for CQRS paths that carry raw columns
        instead of a Profile instance. Keep the gating rule in ONE place."""
        if name_public:
            return True
        if viewer_profile is None:
            return False
        return viewer_profile.id == owner_profile_id or bool(getattr(viewer_profile, 'is_verified_wot', False))

    def can_manage_profile(self, target_profile):
        """Check if this profile can manage the target profile.

        Returns True if:
        - Same profile (can manage self)
        - Same account (all profiles under one account are manageable)
        """
        if self.id == target_profile.id:
            return True
        return self.account_id == target_profile.account_id

    def get_manageable_profiles(self):
        """Get all profiles this profile can manage (including self).

        Returns QuerySet of Profile objects (all profiles under same account).
        """
        return Profile.objects.filter(account=self.account)

    _governing_est_id_cache = {}

    def is_foundation_member(self):
        """
        Check if this profile is a foundation member of the governing association
        of this instance (configured via Constance: GOVERNING_ASSOCIATION_SLUG).

        Foundation members are seed verifiers who can verify other users
        without needing 3+ verifications themselves.

        Returns:
            bool: True if profile is a fundador of the governing Establishment
        """
        from constance import config
        from geo.models import Establishment, EstablishmentMembership
        try:
            slug = config.GOVERNING_ASSOCIATION_SLUG
            # Cache governing association ID to avoid repeated slug lookups
            est_id = Profile._governing_est_id_cache.get(slug)
            if est_id is None:
                est = Establishment.objects.only('id').get(slug=slug)
                est_id = est.id
                Profile._governing_est_id_cache[slug] = est_id
            return EstablishmentMembership.objects.filter(
                profile=self,
                establishment_id=est_id,
                membership_level='fundador'
            ).exists()
        except Establishment.DoesNotExist:
            return False

    def verify_block_reason(self):
        """
        Why this profile cannot verify other users in Web of Trust, or None if it can.
        Single source of truth for can_verify_others() and the UI hint on profile pages.

        Rules:
        - Only PERSONAL profiles can verify (pseudonymous cannot)
        - Foundation members: Can verify immediately (no requirements except PGP key)
        - Standard users: Need 3+ verifications AND WoT verified status AND PGP key

        Returns:
            str | None: 'not_personal', 'no_pgp', 'not_verified', or None if allowed
        """
        # Only personal profiles can verify others
        if self.profile_type != self.ProfileType.PERSONAL:
            return 'not_personal'

        # Must have PGP key to sign verifications
        if not self.pgp_public_key or not self.pgp_fingerprint:
            return 'no_pgp'

        # Foundation members can always verify
        if self.is_foundation_member():
            return None

        # Standard users need 3+ verifications and WoT status
        verification_count = Verification.objects.filter(
            verified_profile=self,
            is_active=True
        ).count()

        if self.is_verified_wot and verification_count >= 3:
            return None

        return 'not_verified'

    def can_verify_others(self):
        """
        Check if this profile has permission to verify other users in Web of Trust.
        See verify_block_reason() for the rules and the specific blocking reason.

        Returns:
            bool: True if can verify other users
        """
        return self.verify_block_reason() is None

    class Meta:
        unique_together = ('instance', 'local_name')
        indexes = [
            models.Index(fields=['account', 'is_primary']),
        ]

    def __str__(self):
        return self.hna


class Verification(ULIDModel):
    """Web of Trust verifications."""

    class VerificationMethod(models.TextChoices):
        IN_PERSON = 'IN_PERSON', 'In Person'
        VIDEO_CALL = 'VIDEO_CALL', 'Video Call'
        DOCUMENTS = 'DOCUMENTS', 'Documents'
        VOUCHED = 'VOUCHED', 'Vouched by Trusted'

    verifier = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="given_verifications")
    verified_profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="received_verifications")
    verification_method = models.CharField(max_length=20, choices=VerificationMethod.choices, default='IN_PERSON')
    signature = models.TextField(blank=True, default='')  # PGP signature (optional for now)
    verified_at = models.DateTimeField(auto_now_add=True, db_index=True, null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        unique_together = ('verifier', 'verified_profile')
        indexes = [
            models.Index(fields=['verified_profile', 'is_active']),
            models.Index(fields=['verifier', 'is_active']),
        ]


class ProfileVerificationPhoto(ULIDModel):
    """
    Private verification photo with face embedding for WoT Sybil defense.

    Photo is NEVER publicly displayed — only shown to verifiers during
    active WoT verification. Face embedding used for deduplication
    against all verified profiles (GDPR Art.9 explicit consent required).
    """
    profile = models.OneToOneField(
        Profile, on_delete=models.CASCADE,
        related_name='verification_photo'
    )
    photo = models.ImageField(
        upload_to='private/verification_photos/%Y/%m/',
        help_text="Private verification photo (only shown to verifiers)"
    )
    face_embedding = models.BinaryField(
        help_text="128-dim face_recognition embedding as float32 bytes (512 bytes)"
    )
    embedding_version = models.SmallIntegerField(
        default=1,
        help_text="Embedding algorithm version (for future re-computation)"
    )
    biometric_consent = models.BooleanField(
        default=False,
        help_text="User explicitly consented to biometric data processing"
    )
    biometric_consent_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp of biometric consent"
    )
    reconfirmation_needed = models.BooleanField(
        default=False,
        help_text="True if photo changed significantly — 3 re-confirmations required"
    )
    reconfirmation_count = models.SmallIntegerField(
        default=0,
        help_text="Re-confirmations received after significant photo change"
    )
    photo_hash = models.CharField(
        max_length=64,
        help_text="SHA256 of the photo file for change detection"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['reconfirmation_needed']),
        ]

    def __str__(self):
        return f"VerificationPhoto({self.profile.hna})"


class SocialRecovery(ULIDModel):
    """Social recovery settings for accounts."""
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="recovery_settings")
    trustee = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="trustee_for")
    encrypted_shard = models.TextField()

    class Meta:
        unique_together = ('account', 'trustee')


class Partner(models.Model):
    """Partner relationships between profiles."""
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="partners")
    partner_profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="partnered_by")
    added_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notes = models.TextField(blank=True, help_text="Private notes about this partner")

    class Meta:
        unique_together = ('profile', 'partner_profile')
        indexes = [
            models.Index(fields=['profile', 'added_at']),
        ]

    def __str__(self):
        return f"{self.profile.hna} → {self.partner_profile.hna}"


class PsychProfile(ULIDModel):
    """Psycho-informatics profile data for Yellow Protocol.

    Form 3: 30 questions to predict opinions/decisions (1-5 scale)
    Form 4: 4-word psycho-hash for Web of Trust matching

    Privacy:
    - form3_data: PRIVATE (system only, never exposed to users)
    - psych_hash_4: PUBLIC (visible in WoT for matching)
    """

    profile = models.OneToOneField(
        Profile,
        on_delete=models.CASCADE,
        related_name="psych_profile",
        help_text="Profile this psycho-informatics data belongs to"
    )

    # Form 3: 30 questions, answers 1-5 scale (PRIVATE)
    form3_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Answers to 30 psycho-informatics questions. Format: {q1: 3, q2: 5, ...}"
    )
    form3_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When Form 3 was completed"
    )

    # Form 4: 4-word psycho-hash (PUBLIC in WoT)
    psych_hash_4 = models.JSONField(
        default=list,
        blank=True,
        help_text="4 words describing personality for WoT matching. Example: ['Visionary', 'Idealist', 'Analyst', 'Empath']"
    )
    psych_hash_4_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When psych_hash_4 was last updated"
    )

    # Optional: AI-generated longer descriptions (for future use)
    psych_hash_8 = models.JSONField(
        default=list,
        blank=True,
        help_text="8-word variant (experimental)"
    )
    psych_hash_32 = models.TextField(
        blank=True,
        help_text="32-word variant for close relationships (experimental)"
    )

    class Meta:
        indexes = [
            models.Index(fields=['profile']),
        ]

    def __str__(self):
        words = ', '.join(self.psych_hash_4) if self.psych_hash_4 else 'not set'
        return f"{self.profile.hna} - Psych: {words}"


class PGPKeyHistory(ULIDModel):
    """
    Audit log for PGP key lifecycle events
    Tracks when keys are created, revoked, or expired
    Provides transparency and security audit trail
    """

    class Action(models.TextChoices):
        CREATED = 'CREATED', 'Key Created'
        REVOKED = 'REVOKED', 'Key Revoked (User Deleted)'
        EXPIRED = 'EXPIRED', 'Key Expired (Replaced by New Key)'

    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='pgp_key_history',
        help_text="Profile that owns this key"
    )
    fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        help_text="PGP key fingerprint"
    )
    public_key = models.TextField(
        help_text="Armored PGP public key (stored for historical verification)"
    )

    # Lifecycle
    action = models.CharField(
        max_length=10,
        choices=Action.choices,
        help_text="What happened to this key"
    )
    action_timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this action occurred"
    )

    # Validity period
    valid_from = models.DateTimeField(
        help_text="When this key became active"
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this key stopped being active (NULL = currently active)"
    )

    # Audit metadata (private)
    created_from_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address where key was generated/uploaded"
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        help_text="Browser user agent"
    )

    class Meta:
        indexes = [
            models.Index(fields=['profile', '-action_timestamp']),
            models.Index(fields=['fingerprint']),
            models.Index(fields=['profile', 'valid_until']),  # Find active keys
        ]
        ordering = ['-action_timestamp']
        verbose_name = 'PGP Key History'
        verbose_name_plural = 'PGP Key Histories'

    def __str__(self):
        status = 'ACTIVE' if self.valid_until is None else 'INACTIVE'
        return f"{self.profile.hna} - {self.fingerprint[:16]}... ({status})"

    @property
    def is_active(self):
        """Check if this key is currently active"""
        return self.valid_until is None

    @property
    def validity_days(self):
        """How many days this key was/has been active"""
        from django.utils import timezone
        end = self.valid_until or timezone.now()
        return (end - self.valid_from).days


class ProfileNote(ULIDModel):
    """Private notes that users can create about other profiles."""

    owner = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='notes_created',
        help_text="Profile that created this note"
    )
    about = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='notes_about',
        help_text="Profile that this note is about"
    )
    note = models.TextField(
        blank=True,
        help_text="Private note content (only visible to owner)"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'about'],
                name='unique_note_per_profile'
            )
        ]
        indexes = [
            models.Index(fields=['owner', 'about']),
        ]

    def __str__(self):
        return f"{self.owner.hna}'s note about {self.about.hna}"