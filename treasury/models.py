from django.db import models
from django.utils import timezone
from core.models import ULIDModel
from identity.models import Profile
from geo.models import Establishment


class BudgetCategory(ULIDModel):
    """Budget category for participatory budget allocation."""

    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE,
                                       related_name='budget_categories',
                                       help_text="Establishment this category belongs to")
    name = models.CharField(max_length=120, help_text="English name (reference data pattern)")
    slug = models.SlugField(max_length=80, help_text="For i18n lookup: treasury.category.<slug>")
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="lucide icon name")
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by_poll_id = models.CharField(max_length=26, blank=True, help_text="Poll that created this category")
    deactivated_by_poll_id = models.CharField(max_length=26, blank=True, help_text="Poll that deactivated this")
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'treasury_budget_category'
        ordering = ['order', 'name']
        verbose_name_plural = 'Budget categories'
        constraints = [
            models.UniqueConstraint(fields=['establishment', 'slug'], name='unique_category_per_establishment'),
        ]

    def __str__(self):
        return self.name


class BudgetAllocation(ULIDModel):
    """Individual member's budget allocation (one vote per profile per establishment)."""

    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE,
                                       related_name='budget_allocations',
                                       help_text="Establishment this allocation belongs to")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='budget_allocations')
    allocations = models.JSONField(
        default=dict,
        help_text='{"category_id": Decimal percentage}, sum = 100.0'
    )
    pgp_signature = models.TextField(blank=True)
    signed_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'treasury_budget_allocation'
        constraints = [
            models.UniqueConstraint(fields=['profile', 'establishment'], name='unique_allocation_per_profile_establishment'),
        ]

    def __str__(self):
        return f"{self.profile.hna} allocation ({self.establishment.slug})"


class BudgetEpoch(ULIDModel):
    """Monthly budget snapshot (frozen allocations)."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        FINALIZED = 'finalized', 'Finalized'

    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE,
                                       related_name='budget_epochs',
                                       help_text="Establishment this epoch belongs to")
    label = models.CharField(max_length=20, help_text="e.g. 2026-03")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    frozen_allocations = models.JSONField(
        default=list,
        help_text='[{category_id, slug, name, median_percent, voter_count}]'
    )
    total_eligible = models.IntegerField(default=0)
    total_participants = models.IntegerField(default=0)
    merkle_root = models.CharField(max_length=64, blank=True)
    individual_allocations_snapshot = models.JSONField(
        default=list,
        help_text='[{profile_id, hna, allocations, pgp_signature}]'
    )
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'treasury_budget_epoch'
        ordering = ['-start_date']
        constraints = [
            models.UniqueConstraint(fields=['establishment', 'label'], name='unique_epoch_per_establishment'),
        ]

    def __str__(self):
        return f"Epoch {self.label} ({self.status}) — {self.establishment.slug}"


class Expense(ULIDModel):
    """Tracked expense for an establishment — budget vs actual spending."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE,
                                       related_name='expenses',
                                       help_text="Establishment this expense belongs to")
    category = models.ForeignKey(BudgetCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='expenses',
                                  help_text="Budget category this expense falls under")
    created_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True,
                                    related_name='created_expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount in EUR")
    description = models.TextField(help_text="What was this expense for")
    receipt_url = models.URLField(blank=True, help_text="URL to receipt image/document")
    date = models.DateField(help_text="Date of the expense")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    epoch_label = models.CharField(max_length=20, blank=True, help_text="Budget epoch label (YYYY-MM)")

    class Meta:
        db_table = 'treasury_expense'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['establishment', 'date']),
            models.Index(fields=['establishment', 'status']),
            models.Index(fields=['category', 'date']),
        ]

    def __str__(self):
        return f"{self.amount}€ — {self.description[:50]} ({self.establishment.slug})"


class TreasuryAuditLog(ULIDModel):
    """Merkle-chain audit log for treasury actions."""

    class Action(models.TextChoices):
        ALLOCATION_UPDATED = 'allocation_updated', 'Allocation Updated'
        EPOCH_FINALIZED = 'epoch_finalized', 'Epoch Finalized'
        CATEGORY_CREATED = 'category_created', 'Category Created'
        CATEGORY_DEACTIVATED = 'category_deactivated', 'Category Deactivated'
        EXPENSE_CREATED = 'expense_created', 'Expense Created'
        EXPENSE_APPROVED = 'expense_approved', 'Expense Approved'

    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE,
                                       related_name='treasury_audit_logs',
                                       help_text="Establishment this log belongs to")
    action = models.CharField(max_length=30, choices=Action.choices)
    actor = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='treasury_audit_actions',
                              help_text="null for system actions (epoch freeze)")
    previous_log_hash = models.CharField(max_length=64, null=True, blank=True)
    current_log_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    pgp_signature = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'treasury_audit_log'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['action', 'timestamp']),
        ]

    def __str__(self):
        actor_name = self.actor.hna if self.actor else 'system'
        return f"{self.action} by {actor_name} at {self.timestamp}"
