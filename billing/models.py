import uuid

from django.conf import settings
from django.db import models


class Wallet(models.Model):
    """One-to-one credit wallet per user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet"
    )
    credit_balance = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    lifetime_earned = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    lifetime_spent = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} — {self.credit_balance} credits"


class LedgerTransaction(models.Model):
    """Immutable audit log of every credit movement."""

    class TransactionType(models.TextChoices):
        INFERENCE = "INFERENCE", "Inference Charge"
        DEPOSIT = "DEPOSIT", "Wallet Credit Deposit"
        PAYOUT = "PAYOUT", "Creator Payout"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    consumer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spent_transactions",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="earned_transactions",
    )
    model = models.ForeignKey(
        "model_registry.Model",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    transaction_type = models.CharField(
        max_length=20, choices=TransactionType.choices
    )
    amount = models.DecimalField(max_digits=10, decimal_places=4)
    creator_share = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    platform_share = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    description = models.CharField(max_length=255, blank=True, default="")

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.transaction_type} — {self.amount} credits"
