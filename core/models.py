from decimal import Decimal

from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.core.exceptions import ValidationError
from ulid import ULID
import re


def generate_ulid():
    """Generate a new ULID as a string."""
    return str(ULID())


class ULIDModel(models.Model):
    """
    Base model with ULID support.
    Provides universal attributes and relations fields for all models,
    enabling a semantic knowledge graph architecture.

    All models inherit from this class to get:
    - ULID-based id field (26 characters, lexicographically sortable)
    - type_name and object_type properties for type identification
    - attributes JSONField for flexible key-value storage
    - relations JSONField for linking to other objects
    - created_at and updated_at timestamps
    """
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=generate_ulid,
        editable=False,
        help_text="ULID (Universally Unique Lexicographically Sortable Identifier)"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Universal fields for semantic graph
    attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Key-value store for intrinsic properties of this object"
    )

    relations = models.JSONField(
        default=list,
        blank=True,
        help_text="List of relationships to other objects. Format: [{type: str, target_id: str, target_type: str}]"
    )

    @property
    def type_name(self):
        """Return the model type name (e.g., 'item', 'profile', 'deal')"""
        return self._meta.model_name

    @property
    def object_type(self):
        """Alias for type_name for API compatibility"""
        return self.type_name

    def add_relation(self, relation_type, target_id, target_type=None):
        """
        Add a new relation to another ULID-identified object.

        Args:
            relation_type: Type of relation (e.g., 'is_component_of', 'manufactured_by')
            target_id: ULID of the target object
            target_type: Optional type of target object (e.g., 'item', 'profile')
        """
        # Validate ULID format (26 chars, base32)
        if not re.match(r'^[0-9A-HJKMNP-TV-Z]{26}$', target_id):
            raise ValidationError(f"Invalid ULID format: {target_id}")

        if not isinstance(self.relations, list):
            self.relations = []

        # Check if relation already exists
        for rel in self.relations:
            if rel.get('type') == relation_type and rel.get('target_id') == target_id:
                return  # Relation already exists

        relation = {
            'type': relation_type,
            'target_id': target_id
        }
        if target_type:
            relation['target_type'] = target_type

        self.relations.append(relation)

    def get_relations_by_type(self, relation_type):
        """
        Get all relations of a specific type.

        Args:
            relation_type: Type of relations to retrieve

        Returns:
            List of relations matching the type
        """
        if not isinstance(self.relations, list):
            return []

        return [r for r in self.relations if r.get('type') == relation_type]

    def remove_relation(self, relation_type, target_id):
        """
        Remove a specific relation.

        Args:
            relation_type: Type of relation to remove
            target_id: ULID of the target object
        """
        if not isinstance(self.relations, list):
            return

        self.relations = [
            r for r in self.relations
            if not (r.get('type') == relation_type and r.get('target_id') == target_id)
        ]

    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            GinIndex(fields=['attributes']),
            GinIndex(fields=['relations'])
        ]


class ProfileMigration(ULIDModel):
    """
    Track profile migration between federation nodes.

    Flow: INITIATED → EXPORTED → SIGNED → COMPLETED
    Requires 4 signatures: old user, new user, old node, new node.
    """
    INITIATED = 'initiated'
    EXPORTED = 'exported'
    SIGNED = 'signed'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (INITIATED, 'Initiated'),
        (EXPORTED, 'Data Exported'),
        (SIGNED, 'Signed by Both'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
    ]

    profile = models.ForeignKey(
        'identity.Profile', on_delete=models.CASCADE,
        related_name='migrations',
    )
    from_hna = models.CharField(max_length=255, help_text="Source HNA (e.g. deploy@parahub.io)")
    to_hna = models.CharField(max_length=255, blank=True, help_text="Destination HNA (e.g. andrey@para.sh)")
    from_node = models.CharField(max_length=255)
    to_node = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=INITIATED)
    reason = models.TextField(blank=True)

    # Signatures (4-party: old user, new user, old node, new node)
    from_user_signature = models.TextField(blank=True, help_text="PGP signature from source profile")
    to_user_signature = models.TextField(blank=True, help_text="PGP signature from destination profile")
    from_node_signature = models.TextField(blank=True, help_text="Node PGP signature from source node")
    to_node_signature = models.TextField(blank=True, help_text="Node PGP signature from destination node")

    # Export & registry
    export_hash = models.CharField(max_length=64, blank=True, help_text="SHA256 of export ZIP")
    git_commit_hash = models.CharField(max_length=40, blank=True)
    continuity_proof = models.CharField(
        max_length=20, blank=True,
        choices=[('same_seed', 'Same BIP39 seed'), ('cross_signed', 'Cross-signed')],
        help_text="How identity continuity is proven",
    )

    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.from_hna} → {self.to_hna or '?'} ({self.status})"


class Like(models.Model):
    """
    Universal like for any ULID-identified object.
    Purely cosmetic — does NOT affect reputation or WoT.
    One like per profile per object.
    """
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=generate_ulid,
        editable=False,
    )
    profile = models.ForeignKey(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='likes',
    )
    target_id = models.CharField(
        max_length=26,
        db_index=True,
        help_text="ULID of the liked object",
    )
    target_type = models.CharField(
        max_length=30,
        db_index=True,
        help_text="Object type: item, profile, establishment, etc.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('profile', 'target_id')
        indexes = [
            models.Index(fields=['target_id']),
            models.Index(fields=['profile', '-created_at']),
        ]

    def __str__(self):
        return f"{self.profile_id} -> {self.target_type}:{self.target_id}"


class Instance(ULIDModel):
    """Represents a federated instance of ParaHub."""
    domain = models.CharField(max_length=255, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    public_key = models.TextField()  # Node PGP public key
    is_active = models.BooleanField(default=True)

    # Federation fields
    registry_git_url = models.URLField(blank=True, help_text="URL to node's federation registry git repo")
    ws_federation_url = models.URLField(blank=True, help_text="WebSocket federation endpoint")
    matrix_server = models.CharField(max_length=255, blank=True, help_text="Matrix homeserver domain")
    pgp_fingerprint = models.CharField(max_length=40, blank=True, help_text="Node PGP key fingerprint")
    trust_level = models.CharField(
        max_length=20, default='local',
        choices=[
            ('local', 'Local (this instance)'),
            ('bootstrap', 'Bootstrap (founding nodes)'),
            ('peer', 'Verified Peer'),
            ('observed', 'Observed (unverified)'),
        ],
    )
    last_seen = models.DateTimeField(null=True, blank=True, help_text="Last federation heartbeat")
    capabilities = models.JSONField(default=list, blank=True, help_text="Node capabilities list")

    def __str__(self):
        return self.domain


class ObjectPhoto(ULIDModel):
    """Universal photo attachment for any ULID-bearing entity."""

    object_id = models.CharField(max_length=26, db_index=True,
                                  help_text="ULID of the target: WorldObject, Item, Establishment, etc.")
    image = models.ImageField(upload_to='photos/%Y/%m/')
    order = models.PositiveSmallIntegerField(default=0)
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                                    related_name='uploaded_photos')

    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['object_id', 'order']),
        ]

    def __str__(self):
        return f"Photo {self.order} for {self.object_id}"


class OwnershipLog(ULIDModel):
    """Tracks ownership changes for WorldObjects (claim/transfer)."""

    object_id = models.CharField(max_length=26, db_index=True,
                                  help_text="ULID of the WorldObject")
    action = models.CharField(max_length=10, choices=[
        ('claim', 'Claimed'),
        ('transfer', 'Transferred'),
    ])
    actor = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                               related_name='ownership_actions')
    previous_owner = models.ForeignKey('identity.Profile', null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        related_name='+')
    new_owner = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                                   related_name='+')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['object_id', '-created_at']),
        ]

    def __str__(self):
        return f"{self.action} {self.object_id} by {self.actor_id}"


class ObjectFile(ULIDModel):
    """Universal file attachment for any ULID-bearing entity (Post, SitePage, etc.)."""

    object_id = models.CharField(max_length=26, db_index=True,
                                  help_text="ULID of the target: Post, SitePage, etc.")
    file = models.FileField(upload_to='files/%Y/%m/')
    filename = models.CharField(max_length=255, help_text="Original filename")
    mime_type = models.CharField(max_length=100)
    size_bytes = models.IntegerField()
    uploaded_by = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                                    related_name='uploaded_files')
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['object_id', 'order']),
        ]

    def __str__(self):
        return f"File '{self.filename}' for {self.object_id}"


class ObjectComment(ULIDModel):
    """Universal comment for any ULID-bearing entity (WorldObject, Item, etc.)."""

    object_id = models.CharField(max_length=26, db_index=True,
                                  help_text="ULID of the target entity")
    author = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                                related_name='comments')
    text = models.TextField(max_length=2000)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['object_id', 'created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.author_id} on {self.object_id}"


class ObjectVideo(ULIDModel):
    """Universal video attachment linking a PeerTube video to any ULID-bearing entity."""

    object_id = models.CharField(max_length=26, db_index=True,
                                  help_text="ULID of the target: Item, Post, Establishment, Profile, etc.")
    peertube_uuid = models.UUIDField(unique=True, db_index=True,
                                       help_text="PeerTube video UUID (source of truth)")
    peertube_url = models.URLField(max_length=512,
                                     help_text="Watch URL: https://video.parahub.io/w/{short_uuid}")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    thumbnail_url = models.URLField(max_length=512, blank=True)
    embed_url = models.URLField(max_length=512, blank=True,
                                  help_text="PeerTube embed URL for iframe")
    hls_url = models.URLField(max_length=512, blank=True,
                                help_text="HLS playlist URL for direct player")
    order = models.PositiveSmallIntegerField(default=0)
    uploaded_by = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                                    related_name='uploaded_videos')
    is_published = models.BooleanField(default=False,
                                        help_text="True once PeerTube finishes transcoding")

    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['object_id', 'order']),
        ]

    def __str__(self):
        return f"Video '{self.title}' for {self.object_id}"


# ── Cooperative investment layer ─────────────────────────────────────────────


class ObjectShare(ULIDModel):
    """Universal ownership/investment share. Attaches to any ULID entity."""

    class ShareType(models.TextChoices):
        EQUITY = 'EQUITY', 'Equity'
        INVESTMENT = 'INVESTMENT', 'Investment'
        REVENUE = 'REVENUE', 'Revenue right'

    object_id = models.CharField(max_length=26, db_index=True,
                                  help_text="ULID of the target: Establishment, EnergyCell, etc.")
    profile = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                                 related_name='shares')
    share_type = models.CharField(max_length=12, choices=ShareType.choices,
                                   default=ShareType.INVESTMENT)
    share_percent = models.DecimalField(max_digits=6, decimal_places=3,
                                         help_text="0.000 – 100.000%")
    invested_amount = models.DecimalField(max_digits=12, decimal_places=2,
                                           null=True, blank=True,
                                           help_text="Amount invested (for INVESTMENT type)")
    invested_currency = models.CharField(max_length=3, default='EUR')
    invested_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['object_id', 'profile', 'share_type'],
                name='unique_share_per_profile_type',
            ),
            models.CheckConstraint(
                condition=models.Q(share_percent__gte=Decimal('0')) & models.Q(share_percent__lte=Decimal('100')),
                name='share_percent_range',
            ),
        ]
        indexes = [
            models.Index(fields=['object_id', 'share_type']),
            models.Index(fields=['profile', 'is_active']),
        ]

    def __str__(self):
        return f"{self.profile_id} {self.share_percent}% ({self.share_type}) in {self.object_id}"


class ObjectDistribution(ULIDModel):
    """Distribution/payout event for an entity's shareholders."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        APPROVED = 'APPROVED', 'Approved'
        DISTRIBUTED = 'DISTRIBUTED', 'Distributed'

    object_id = models.CharField(max_length=26, db_index=True,
                                  help_text="ULID of the entity distributing revenue")
    period_label = models.CharField(max_length=20,
                                     help_text="Period identifier, e.g. '2026-03'")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    merkle_root = models.CharField(max_length=64, blank=True,
                                    help_text="SHA256 Merkle root of all lines for audit")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('identity.Profile', on_delete=models.SET_NULL,
                                    null=True, related_name='+')

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['object_id', 'period_label'],
                name='unique_distribution_per_period',
            ),
        ]
        indexes = [
            models.Index(fields=['object_id', 'status']),
            models.Index(fields=['object_id', '-created_at']),
        ]

    def __str__(self):
        return f"Distribution {self.period_label} for {self.object_id} ({self.status})"


class DistributionLine(ULIDModel):
    """Individual payout within a distribution."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'

    distribution = models.ForeignKey(ObjectDistribution, on_delete=models.CASCADE,
                                      related_name='lines')
    profile = models.ForeignKey('identity.Profile', on_delete=models.CASCADE,
                                 related_name='distribution_lines')
    share_percent = models.DecimalField(max_digits=6, decimal_places=3,
                                         help_text="Snapshot of share at distribution time")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    payment = models.ForeignKey('finance.Payment', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='+',
                                 help_text="Lightning payment if paid via wallet")

    class Meta:
        ordering = ['distribution', '-amount']
        constraints = [
            models.UniqueConstraint(
                fields=['distribution', 'profile'],
                name='unique_line_per_profile',
            ),
        ]
        indexes = [
            models.Index(fields=['distribution', 'status']),
            models.Index(fields=['profile', 'status']),
        ]

    def __str__(self):
        return f"{self.profile_id} {self.amount} {self.distribution.currency} ({self.status})"
