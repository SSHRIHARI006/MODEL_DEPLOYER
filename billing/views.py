from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated

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
            "creator_share",
            "platform_share",
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


class DepositCreditsAPIView(APIView):
    """POST to add mock credits (for development / testing)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount = request.data.get("amount")
        if not amount or float(amount) <= 0:
            return Response(
                {"detail": "amount must be a positive number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from decimal import Decimal

        amount = Decimal(str(amount))
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
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
