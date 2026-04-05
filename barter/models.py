"""
Barter Exchange Models
PostgreSQL persistence for exchange approvals and state
"""

from django.db import models
from core.models import ULIDModel
from identity.models import Profile
from market.models import Item


class Exchange(ULIDModel):
    """
    Multi-party barter exchange discovered from graph

    Stores the exchange chain and approval status.
    The actual graph matching is done in Neo4j, this model
    just tracks which exchanges have been approved/completed.
    """

    # JSON representation of user chain from Neo4j
    # Example: ["01K2SH48YZ...", "01K3AB78CD...", "01K4XY12MN...", "01K2SH48YZ..."]
    user_chain = models.JSONField(
        help_text="List of user ULIDs forming the exchange cycle"
    )

    # Category for this exchange
    category = models.ForeignKey(
        'taxonomy.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exchanges'
    )

    # Status
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        APPROVED = 'APPROVED', 'All Approved'
        REJECTED = 'REJECTED', 'Rejected by Someone'
        COMPLETED = 'COMPLETED', 'Exchange Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )

    completed_at = models.DateTimeField(null=True, blank=True)

    # Optimistic locking
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        participants = len(self.user_chain) - 1  # Subtract duplicated start/end user
        return f"Exchange {self.id}: {participants} participants ({self.status})"

    @property
    def participants(self):
        """Get unique list of participant user IDs"""
        return list(set(self.user_chain[:-1]))  # Exclude last (duplicate of first)

    def check_all_approved(self):
        """Check if all participants have approved and update status"""
        participant_count = len(self.participants)
        approved_count = self.approvals.filter(approved=True).count()

        if approved_count == participant_count:
            self.status = self.Status.APPROVED
            self.save()
            return True
        return False

    def check_any_rejected(self):
        """Check if any participant rejected and update status"""
        if self.approvals.filter(approved=False).exists():
            self.status = self.Status.REJECTED
            self.save()
            return True
        return False


class ExchangeSwap(ULIDModel):
    """
    Individual swap within a multi-party exchange

    Represents one step in the exchange chain:
    User A offers Item X to User B who wants Item Y
    """

    exchange = models.ForeignKey(
        Exchange,
        on_delete=models.CASCADE,
        related_name='swaps'
    )

    # Position in chain (0-indexed)
    order = models.PositiveSmallIntegerField()

    # Users involved
    from_user = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='swaps_offering'
    )
    to_user = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='swaps_receiving'
    )

    # Items involved
    offered_item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='swaps_offered',
        help_text="CREDIT item being offered"
    )
    wanted_item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='swaps_wanted',
        help_text="DEBIT item being wanted"
    )

    class Meta:
        ordering = ['exchange', 'order']
        unique_together = ('exchange', 'order')

    def __str__(self):
        return f"Swap {self.order}: {self.from_user.display_name or self.from_user.id} → {self.to_user.display_name or self.to_user.id}"


class ExchangeApproval(ULIDModel):
    """
    Approval/rejection of exchange by participant

    Each participant must approve for exchange to proceed
    """

    exchange = models.ForeignKey(
        Exchange,
        on_delete=models.CASCADE,
        related_name='approvals'
    )

    user = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='exchange_approvals'
    )

    approved = models.BooleanField(
        null=True,
        blank=True,
        help_text="True=approved, False=rejected, None=pending"
    )

    # Optional: which specific swap this approval is for
    # (in case user is involved in multiple swaps within same exchange)
    swap = models.ForeignKey(
        ExchangeSwap,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approvals'
    )

    # Optional PGP signature for approval
    signature = models.TextField(blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('exchange', 'user')
        indexes = [
            models.Index(fields=['exchange', 'approved']),
        ]

    def __str__(self):
        status = "Approved" if self.approved else ("Rejected" if self.approved is False else "Pending")
        return f"{self.user.display_name or self.user.id}: {status}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Auto-update exchange status
        if self.approved is True:
            self.exchange.check_all_approved()
        elif self.approved is False:
            self.exchange.check_any_rejected()
