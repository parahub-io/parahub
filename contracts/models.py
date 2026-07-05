"""
P2P contract models: dual-PGP signing, reviews, arbitration.

Extracted from identity/models.py (2026-07-04). The move is state-only: every
model keeps its original ``identity_*`` db_table (including the two M2M through
tables), so the shared database was not touched. identity's migration history
still CREATES these tables on a fresh database — do not squash identity
migrations past identity.0009 without moving the table creation into this app.
"""

from django.db import models

from core.models import ULIDModel


class Contract(ULIDModel):
    """
    P2P contracts with dual PGP signatures

    Workflow:
    1. Creator creates contract with file SHA256 and signs it (PENDING_PARTNER)
    2. Partner signs the contract (SIGNED)

    File contents never leave client - only SHA256 is stored on server
    """

    class Status(models.TextChoices):
        PENDING_PARTNER = 'PENDING_PARTNER', 'Awaiting Partner Signature'
        SIGNED = 'SIGNED', 'Signed by Both Parties'
        COMPLETED = 'COMPLETED', 'Completed (Work Done)'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class Kind(models.TextChoices):
        SALE = 'SALE', 'Sale / one-off deal'
        RENTAL = 'RENTAL', 'Rental (asset returns)'

    # Parties
    creator = models.ForeignKey(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='contracts_created',
        help_text="Profile that created the contract"
    )
    partner = models.ForeignKey(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='contracts_received',
        help_text="Partner profile"
    )
    arbiter = models.ForeignKey(
        'identity.Profile',
        on_delete=models.SET_NULL,
        related_name='contracts_arbitrating',
        null=True,
        blank=True,
        help_text="Optional arbitrator for dispute resolution"
    )

    # Property subject
    subject_property = models.ForeignKey(
        'iot.Property', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contracts',
        help_text="Property this contract pertains to (sale, rental, etc.)"
    )

    # WorldObject subject
    world_object = models.ForeignKey(
        'geo.WorldObject', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contracts',
        help_text="WorldObject (building/POI) this contract pertains to"
    )

    # Contract data
    title = models.CharField(
        max_length=255,
        help_text="Contract title/description"
    )
    file_sha256 = models.CharField(
        max_length=64,
        help_text="SHA256 hash of contract file (computed client-side)"
    )

    # Private contract body — the actual agreement text composed in-app (write
    # mode). Stored server-side and returned ONLY to the parties (+ arbiter) via
    # the party-restricted contract endpoints — never public/federated. Blank for
    # legacy hash-only / upload-mode contracts (which exist only as a file_sha256
    # the parties hold offline). NOT part of get_canonical_text(): the body is
    # bound to the contract by file_sha256 (which hashes exactly this text), so
    # existing signatures stay valid and the hash still proves the body.
    document_text = models.TextField(
        blank=True,
        default='',
        help_text="Private contract body (HTML); blank for legacy hash-only/upload contracts"
    )
    document_format = models.CharField(
        max_length=10,
        default='html',
        help_text="Format of document_text: 'html' (TipTap) or 'markdown'"
    )

    # Signatures
    creator_signature = models.TextField(
        help_text="PGP signature of creator (signing canonical JSON)"
    )
    partner_signature = models.TextField(
        blank=True,
        null=True,
        help_text="PGP signature of partner (signing canonical JSON)"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PARTNER,
        db_index=True
    )

    # Sale vs rental. SALE deactivates linked items on completion (the asset
    # changes hands); RENTAL leaves them active (the asset returns to the owner
    # and stays available). NOT part of the signed canonical text, so existing
    # signatures stay valid; the rental terms live on the linked Booking.
    kind = models.CharField(
        max_length=10,
        choices=Kind.choices,
        default=Kind.SALE,
        db_index=True,
        help_text="SALE consumes the item on completion; RENTAL returns it to availability"
    )

    # Timestamps
    creator_signed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When creator signed the contract"
    )
    partner_signed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When partner signed the contract"
    )

    # Completion tracking (both parties must confirm)
    creator_completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When creator marked contract as completed"
    )
    partner_completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When partner marked contract as completed"
    )

    # Linked items
    items = models.ManyToManyField(
        'market.Item',
        blank=True,
        related_name='contracts',
        db_table='identity_contract_items',
        help_text="Items being exchanged in this contract"
    )

    # Arbitration
    arbitration_room_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Matrix room ID for arbitration discussion"
    )
    arbitration_initiated_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When arbitration was initiated"
    )
    arbitration_initiator = models.ForeignKey(
        'identity.Profile',
        on_delete=models.SET_NULL,
        related_name='initiated_arbitrations',
        null=True,
        blank=True,
        help_text="Profile that initiated arbitration"
    )

    # Arbitration escalation
    arbitration_level = models.SmallIntegerField(
        default=1,
        help_text="Arbitration level: 1=P2P, 2=Institutional (CAC), 3=Court"
    )
    arbitration_escalated_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When arbitration was escalated to the next level"
    )
    arbitration_escalated_by = models.ForeignKey(
        'identity.Profile',
        on_delete=models.SET_NULL,
        related_name='escalated_arbitrations',
        null=True,
        blank=True,
        help_text="Profile that escalated the arbitration"
    )

    class Meta:
        db_table = 'identity_contract'
        indexes = [
            models.Index(fields=['creator', 'status', '-created_at']),
            models.Index(fields=['partner', 'status', '-created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.creator.hna} ↔ {self.partner.hna})"

    @property
    def is_signed(self):
        """Check if both parties have signed"""
        return self.status == self.Status.SIGNED and bool(self.partner_signature)

    @property
    def is_fully_completed(self):
        """Check if both parties have marked contract as completed"""
        return bool(self.creator_completed_at) and bool(self.partner_completed_at)

    def get_canonical_text(self):
        """Generate canonical JSON for signing (without created_at to avoid sync issues)"""
        import json

        data = {
            'title': self.title,
            'creator_id': self.creator.id,
            'partner_id': self.partner.id,
            'file_sha256': self.file_sha256
        }

        # Include arbiter if specified
        if self.arbiter_id:
            data['arbiter_id'] = self.arbiter_id

        return json.dumps(data, sort_keys=True, separators=(',', ':'))


class ContractReview(ULIDModel):
    """Reviews for completed contracts."""
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='reviews',
        help_text="Contract being reviewed"
    )
    reviewer = models.ForeignKey(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='contract_reviews_given',
        help_text="Profile giving the review"
    )
    reviewed = models.ForeignKey(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='contract_reviews_received',
        help_text="Profile being reviewed (the other party)"
    )
    rating = models.SmallIntegerField(
        help_text="Rating 1-5 stars"
    )
    comment = models.TextField(
        blank=True,
        help_text="Optional review comment"
    )

    class Meta:
        db_table = 'identity_contractreview'
        unique_together = ('contract', 'reviewer')
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by {self.reviewer.hna} for contract {self.contract.title}"


class ArbiterProfile(ULIDModel):
    """Extended profile for arbiters with specializations and fee info."""
    profile = models.OneToOneField(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='arbiter_profile'
    )
    specializations = models.ManyToManyField(
        'taxonomy.Category',
        blank=True,
        related_name='arbiter_profiles',
        db_table='identity_arbiterprofile_specializations',
        help_text="Arbiter specialization categories"
    )
    fee_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="Arbitration fee amount"
    )
    fee_currency = models.CharField(
        max_length=3, default='EUR',
        help_text="Fee currency (ISO 4217)"
    )
    bio = models.TextField(
        blank=True,
        help_text="Arbiter biography/description"
    )
    is_active = models.BooleanField(
        default=True, db_index=True,
        help_text="Whether this arbiter is currently available"
    )

    class Meta:
        db_table = 'identity_arbiterprofile'

    def __str__(self):
        return f"Arbiter: {self.profile.hna}"


class ArbitrationVerdict(ULIDModel):
    """Verdict for a contract arbitration — one verdict per contract."""

    class VerdictType(models.TextChoices):
        FAVOR_CREATOR = 'FAVOR_CREATOR', 'In Favor of Creator'
        FAVOR_PARTNER = 'FAVOR_PARTNER', 'In Favor of Partner'
        PARTIAL = 'PARTIAL', 'Partial (Split)'
        DISMISSED = 'DISMISSED', 'Dismissed'

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name='verdict'
    )
    arbiter = models.ForeignKey(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='verdicts_given'
    )
    verdict_type = models.CharField(
        max_length=20,
        choices=VerdictType.choices,
        help_text="Type of verdict"
    )
    summary = models.TextField(
        help_text="Arbiter's reasoning and decision summary"
    )
    amount_awarded = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Amount awarded (if applicable)"
    )
    currency = models.CharField(
        max_length=3, blank=True,
        help_text="Currency of amount awarded"
    )
    creator_arbiter_rating = models.SmallIntegerField(
        null=True, blank=True,
        help_text="Creator's rating of the arbiter (1-5)"
    )
    partner_arbiter_rating = models.SmallIntegerField(
        null=True, blank=True,
        help_text="Partner's rating of the arbiter (1-5)"
    )

    class Meta:
        db_table = 'identity_arbitrationverdict'
        indexes = [
            models.Index(fields=['arbiter']),
        ]

    def __str__(self):
        return f"Verdict for {self.contract.title}: {self.verdict_type}"
