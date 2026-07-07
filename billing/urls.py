from django.urls import path

from .views import WalletAPIView, DepositCreditsAPIView

urlpatterns = [
    path("wallet/", WalletAPIView.as_view(), name="wallet"),
    path("wallet/deposit/", DepositCreditsAPIView.as_view(), name="wallet-deposit"),
]
