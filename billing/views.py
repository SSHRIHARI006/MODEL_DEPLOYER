from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated

from core.serializers import FiniteDecimalField

from .models import Wallet, LedgerTransaction


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ["credit_balance", "lifetime_earned", "lifetime_spent", "updated_at"]


class LedgerSerializer(serializers.ModelSerializer):
    consumer_username = serializers.CharField(
        source="consumer.username", read_only=True, default=None
    )
    creator_username = serializers.CharField(
        source="creator.username", read_only=True, default=None
    )
    model_name = serializers.CharField(
        source="model.name", read_only=True, default=None
    )

    class Meta:
        model = LedgerTransaction
        fields = [
            "id",
            "transaction_type",
            "amount",
            "description",
            "consumer_username",
            "creator_username",
            "model_name",
            "timestamp",
        ]


class WalletAPIView(APIView):
    """GET wallet balance and recent ledger transactions."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        transactions = LedgerTransaction.objects.filter(
            consumer=request.user
        ) | LedgerTransaction.objects.filter(creator=request.user)
        transactions = transactions.order_by("-timestamp")[:50]

        return Response(
            {
                "wallet": WalletSerializer(wallet).data,
                "transactions": LedgerSerializer(transactions, many=True).data,
            }
        )


class DepositSerializer(serializers.Serializer):
    """A demo deposit is a positive, finite, bounded decimal amount."""

    amount = FiniteDecimalField(
        max_digits=12,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        max_value=Decimal("999999999999.9999"),
    )


class DepositCreditsAPIView(APIView):
    """POST to add simulated credits (development / testing only).

    SEC-05: these are not payments. The endpoint is disabled unless
    ``BILLING_DEMO_DEPOSITS`` is explicitly enabled, and even then only staff
    (or a DEBUG deployment) may call it.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "deposit"

    def post(self, request):
        if not getattr(settings, "BILLING_DEMO_DEPOSITS", False):
            return Response(
                {
                    "error": "Demo credit deposits are disabled on this deployment.",
                    "code": "DEMO_DEPOSITS_DISABLED",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not (request.user.is_staff or getattr(settings, "DEBUG", False)):
            return Response(
                {
                    "error": "Only staff accounts may create demo deposits.",
                    "code": "DEPOSIT_NOT_AUTHORIZED",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        max_amount = Decimal(str(settings.BILLING_MAX_DEPOSIT_AMOUNT))
        if amount > max_amount:
            return Response(
                {
                    "error": f"amount must be at most {max_amount} credits",
                    "code": "DEPOSIT_TOO_LARGE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            wallet, _ = Wallet.objects.select_for_update().get_or_create(
                user=request.user
            )
            wallet.credit_balance += amount
            wallet.save(update_fields=["credit_balance", "updated_at"])

            LedgerTransaction.objects.create(
                consumer=request.user,
                transaction_type=LedgerTransaction.TransactionType.DEPOSIT,
                amount=amount,
                description=f"Manual credit deposit of {amount} credits",
            )

        return Response(
            {
                "message": f"Deposited {amount} credits",
                "new_balance": str(wallet.credit_balance),
            }
        )
