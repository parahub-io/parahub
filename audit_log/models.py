"""
Audit Log models for cryptographic proof persistence.

Models store metadata for immutable proofs (OpenTimestamps, Matrix messages).
Actual proof files stored in Git repository or external systems.
"""
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class AuditBatch(models.Model):
    """A batch git commit + OTS stamp covering multiple TimestampProofs"""

    git_commit_hash = models.CharField(max_length=40, unique=True)
    git_commit_file = models.TextField()  # e.g. 'batch_commits/2026-02-22_143000.txt'
    ots_proof = models.BinaryField(null=True)  # .ots file for the commit hash file
    stamped_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True)
    bitcoin_block = models.IntegerField(null=True)
    event_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-stamped_at']
        indexes = [
            models.Index(fields=['git_commit_hash'], name='audit_batch_git_commit_idx'),
            models.Index(fields=['-stamped_at'], name='audit_batch_stamped_at_idx'),
            models.Index(fields=['verified_at'], name='audit_batch_verified_at_idx'),
        ]

    def __str__(self):
        return f"AuditBatch {self.git_commit_hash[:8]} ({self.event_count} events)"


class TimestampProof(models.Model):
    """OpenTimestamps proof for contract/debt/verification"""

    # Generic relation to any model (Contract, Debt, Verification)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=26)  # ULID
    content_object = GenericForeignKey('content_type', 'object_id')

    # Proof data
    data_hash = models.CharField(max_length=64, unique=True)  # SHA256 of signed data
    data_json = models.TextField(null=True, blank=True)  # Original JSON (needed for ots verify)
    ots_proof = models.BinaryField(null=True, blank=True)  # legacy per-object .ots; NULL if batch

    # Batch anchoring (new): NULL = legacy or pending
    batch = models.ForeignKey(AuditBatch, null=True, on_delete=models.SET_NULL, related_name='proofs')
    git_event_path = models.CharField(max_length=200, null=True)  # relative path in events/

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)  # When .ots became verified (legacy)
    bitcoin_block = models.IntegerField(null=True, blank=True)  # Block height after verification (legacy)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['data_hash']),
        ]

    def __str__(self):
        return f"OTS proof for {self.content_type.model} {self.object_id[:8]}"


class MatrixRoomReference(models.Model):
    """Matrix room for contract/debt dispute resolution"""

    # Generic relation
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=26)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Matrix data
    room_id = models.CharField(max_length=255, unique=True)  # !abcdef:matrix.parahub.io
    event_id = models.CharField(max_length=255, null=True)  # Event ID of pinned proof message

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    is_encrypted = models.BooleanField(default=True)  # E2E encryption
    purpose = models.CharField(max_length=50, choices=[
        ('system_notifications', 'System Notifications'),
        ('dispute', 'Dispute Resolution'),
        ('proof_backup', 'Proof Backup'),
    ])

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['room_id']),
        ]

    def __str__(self):
        return f"Matrix room {self.room_id} for {self.content_type.model} {self.object_id[:8]}"


class PGPKeyPublication(models.Model):
    """Track PGP key publications to public Git repository"""

    profile = models.ForeignKey('identity.Profile', on_delete=models.CASCADE, related_name='pgp_publications')

    # Key data
    fingerprint = models.CharField(max_length=40)
    public_key = models.TextField()  # ASCII armored key

    # Git tracking
    published_at = models.DateTimeField(auto_now_add=True)
    git_commit_hash = models.CharField(max_length=40)  # Git commit SHA

    # Revocation
    revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['profile', '-published_at']),
            models.Index(fields=['fingerprint']),
        ]

    def __str__(self):
        return f"PGP key {self.fingerprint[:8]} for {self.profile.id[:8]}"


class GiteaCommentSnapshot(models.Model):
    """
    Immutable snapshot of a Gitea issue comment for non-repudiation.

    When a comment is created/edited on any Gitea issue (CMS drafts, contracts,
    etc.), a webhook fires and this model captures the full text. Even if the
    author later deletes/edits the comment in Gitea, we retain the original.

    A TimestampProof (GenericFK → this model) anchors each snapshot to Bitcoin
    via the existing batch_ots_stamp timer (~10 min).
    """

    gitea_comment_id = models.BigIntegerField(db_index=True,
        help_text="Gitea's internal comment ID")
    gitea_repo = models.CharField(max_length=200,
        help_text="Full repo path, e.g. cms-editorial/parahub-associacao")
    gitea_issue_number = models.PositiveIntegerField()

    # Author — link to Parahub profile if Gitea user maps via OIDC SSO
    author_profile = models.ForeignKey(
        'identity.Profile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    author_username = models.CharField(max_length=100,
        help_text="Gitea username at time of comment")

    text = models.TextField(help_text="Full comment body at this version")
    version = models.PositiveIntegerField(default=1,
        help_text="Increments on edit: v1=created, v2+=edited")
    deleted_in_gitea = models.BooleanField(default=False,
        help_text="True if comment was later deleted in Gitea")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['gitea_comment_id', 'version']),
            models.Index(fields=['gitea_repo', 'gitea_issue_number']),
        ]

    def __str__(self):
        return (
            f"Comment {self.gitea_comment_id} v{self.version} "
            f"on {self.gitea_repo}#{self.gitea_issue_number}"
        )


class ProofExport(models.Model):
    """Track user data exports for audit trail"""

    profile = models.ForeignKey('identity.Profile', on_delete=models.CASCADE, related_name='proof_exports')

    export_type = models.CharField(max_length=50, choices=[
        ('full', 'Full Account Export'),
        ('contract', 'Single Contract Export'),
        ('debt', 'Single Debt Export'),
        ('verifications', 'Verifications Export'),
    ])

    # What was exported
    object_ids = models.JSONField(default=list)  # List of exported object IDs

    # Export metadata
    created_at = models.DateTimeField(auto_now_add=True)
    file_hash = models.CharField(max_length=64, null=True)  # SHA256 of exported ZIP

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['profile', '-created_at']),
        ]

    def __str__(self):
        return f"{self.export_type} export for {self.profile.id[:8]} at {self.created_at}"
