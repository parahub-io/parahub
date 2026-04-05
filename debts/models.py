"""
Debts & Clearing System Models
Track mutual debts and enable multi-party debt clearing through barter cycles
"""

from django.db import models
from django.db.models import F
from decimal import Decimal
from core.models import ULIDModel
from identity.models import Profile


class Debt(ULIDModel):
    """
    Peer-to-peer debt tracking with optional clearing via barter cycles

    Workflow:
    1. Debtor creates debt (DRAFT)
    2. Creditor confirms (PENDING_CONFIRMATION -> ACTIVE)
    3. Debt can be repaid manually or via cycle clearing
    4. When remaining_amount = 0 -> FULLY_SETTLED
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft (Not Sent)'
        PENDING_CONFIRMATION = 'PENDING_CONFIRMATION', 'Pending Confirmation'
        ACTIVE = 'ACTIVE', 'Active'
        PARTIALLY_SETTLED = 'PARTIALLY_SETTLED', 'Partially Settled'
        FULLY_SETTLED = 'FULLY_SETTLED', 'Fully Settled'
        CANCELLED = 'CANCELLED', 'Cancelled'

    # Parties
    creditor = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='debts_receivable',
        help_text="Person who is owed money"
    )
    debtor = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='debts_payable',
        help_text="Person who owes money"
    )

    # Amount
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Original debt amount"
    )
    remaining_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Amount still owed (after partial repayments)"
    )
    currency = models.CharField(
        max_length=3,
        default='EUR',
        help_text="ISO 4217 currency code (EUR, USD, RUB, etc.)"
    )

    # Metadata
    description = models.TextField(
        blank=True,
        help_text="What is this debt for?"
    )
    created_by = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='debts_created',
        help_text="Who initiated this debt record"
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )

    # Confirmation timestamps
    confirmed_by_creditor_at = models.DateTimeField(null=True, blank=True)
    confirmed_by_debtor_at = models.DateTimeField(null=True, blank=True)

    # PGP signature
    pgp_signature = models.TextField(blank=True, default='')
    signed_payload = models.JSONField(default=dict, blank=True)

    # Optimistic locking
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['creditor', 'status']),
            models.Index(fields=['debtor', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['currency']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='debt_amount_positive'
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_amount__gte=0),
                name='debt_remaining_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_amount__lte=F('amount')),
                name='debt_remaining_lte_amount'
            ),
        ]

    def __str__(self):
        return f"{self.debtor} owes {self.creditor} {self.remaining_amount} {self.currency}"

    def save(self, *args, **kwargs):
        # Set remaining_amount on creation
        if self._state.adding and not self.remaining_amount:
            self.remaining_amount = self.amount

        # Auto-update status based on remaining_amount
        if self.remaining_amount == 0 and self.status != self.Status.FULLY_SETTLED:
            self.status = self.Status.FULLY_SETTLED
        elif 0 < self.remaining_amount < self.amount and self.status == self.Status.ACTIVE:
            self.status = self.Status.PARTIALLY_SETTLED

        # Increment version on updates
        if not self._state.adding:
            self.version = F('version') + 1

        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """Check if debt can participate in clearing cycles"""
        return self.status in [
            self.Status.ACTIVE,
            self.Status.PARTIALLY_SETTLED
        ] and self.remaining_amount > 0

    @property
    def percent_settled(self):
        """Calculate settlement percentage"""
        if self.amount == 0:
            return Decimal('100.0')
        return ((self.amount - self.remaining_amount) / self.amount) * Decimal('100.0')


class DebtRepayment(ULIDModel):
    """
    Record of partial or full debt repayment

    Can be created manually (cash payment IRL) or automatically via cycle clearing
    Requires confirmation from both parties
    """

    class RepaymentType(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual Repayment'
        CYCLE_CLEARING = 'CYCLE_CLEARING', 'Cycle Clearing'

    debt = models.ForeignKey(
        Debt,
        on_delete=models.CASCADE,
        related_name='repayments'
    )

    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Amount repaid"
    )

    repayment_type = models.CharField(
        max_length=20,
        choices=RepaymentType.choices,
        default=RepaymentType.MANUAL
    )

    # For cycle clearing repayments
    clearing_exchange_id = models.CharField(
        max_length=26,
        blank=True,
        null=True,
        help_text="ULID of Exchange that cleared this debt (if type=CYCLE_CLEARING)"
    )

    # Confirmation timestamp (creditor records repayment)
    confirmed_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # Optional notes
    notes = models.TextField(blank=True)

    # Who initiated this repayment record
    created_by = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='debt_repayments_created'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['debt', '-created_at']),
            models.Index(fields=['clearing_exchange_id']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='repayment_amount_positive'
            ),
        ]

    def __str__(self):
        return f"Repayment {self.amount} for {self.debt.id} ({self.repayment_type})"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        # Update debt remaining_amount immediately when repayment is created
        # (only creditor can create repayment, so it's trustworthy)
        if is_new:
            # Use F() to avoid race conditions
            Debt.objects.filter(id=self.debt_id).update(
                remaining_amount=F('remaining_amount') - self.amount
            )
            # Refresh debt to check if fully settled
            self.debt.refresh_from_db()
            if self.debt.remaining_amount <= 0:
                self.debt.status = Debt.Status.FULLY_SETTLED
                self.debt.save()
            elif self.debt.remaining_amount < self.debt.amount:
                self.debt.status = Debt.Status.PARTIALLY_SETTLED
                self.debt.save()
