from django.contrib.auth import get_user_model
from rest_framework import status, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from model_registry.models import Model

User = get_user_model()


class ModelCardSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    total_versions = serializers.SerializerMethodField()

    class Meta:
        model = Model
        fields = [
            "id",
            "name",
            "framework",
            "task_type",
            "description",
            "cost_per_run",
            "is_public",
            "owner_username",
            "total_versions",
            "created_at",
        ]

    def get_total_versions(self, obj):
        return obj.versions.count()


class ModelDetailSerializer(ModelCardSerializer):
    readme_markdown = serializers.CharField()

    class Meta(ModelCardSerializer.Meta):
        fields = ModelCardSerializer.Meta.fields + ["readme_markdown"]


class SmallPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ExploreAPIView(APIView):
    """GET /api/models/explore/ — Public model directory."""

    permission_classes = [AllowAny]

    def get(self, request):
        qs = Model.objects.filter(is_public=True).select_related("owner")

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)

        framework = request.query_params.get("framework")
        if framework:
            qs = qs.filter(framework__iexact=framework)

        task = request.query_params.get("task_type")
        if task:
            qs = qs.filter(task_type__iexact=task)

        qs = qs.order_by("-created_at")

        paginator = SmallPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ModelCardSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class UserProfileAPIView(APIView):
    """GET /api/users/@<username>/ — Public profile."""

    permission_classes = [AllowAny]

    def get(self, request, username):
        user = User.objects.filter(username=username).first()
        if not user:
            return Response(
                {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        public_models = Model.objects.filter(owner=user, is_public=True).order_by(
            "-created_at"
        )

        return Response(
            {
                "username": user.username,
                "email": user.email,
                "bio": user.bio,
                "avatar_url": user.avatar_url,
                "joined": user.created_at,
                "total_public_models": public_models.count(),
                "models": ModelCardSerializer(public_models, many=True).data,
            }
        )


class ModelRepoAPIView(APIView):
    """GET /api/models/@<username>/<model_name>/ — Model repository detail."""

    permission_classes = [AllowAny]

    def get(self, request, username, model_name):
        model = (
            Model.objects.filter(owner__username=username, name=model_name)
            .select_related("owner")
            .first()
        )

        if not model:
            return Response(
                {"detail": "Model not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Non-owners can only see public models
        if not model.is_public and (
            not request.user.is_authenticated or request.user != model.owner
        ):
            return Response(
                {"detail": "Model not found"}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(ModelDetailSerializer(model).data)

    def patch(self, request, username, model_name):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
            
        model = Model.objects.filter(owner__username=username, name=model_name).first()

        if not model:
            return Response({"detail": "Model not found"}, status=status.HTTP_404_NOT_FOUND)

        if request.user != model.owner:
            return Response({"detail": "You do not have permission to edit this model"}, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data
        if "description" in data:
            model.description = data["description"]
        if "readme_markdown" in data:
            model.readme_markdown = data["readme_markdown"]
        if "is_public" in data:
            model.is_public = data["is_public"]
        if "cost_per_run" in data:
            model.cost_per_run = data["cost_per_run"]
            
        model.save()
        return Response(ModelDetailSerializer(model).data)


class DashboardSummaryAPIView(APIView):
    """GET /api/dashboard/summary/ — Private creator dashboard summary."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        models_qs = Model.objects.filter(owner=user)

        from billing.models import Wallet

        wallet, _ = Wallet.objects.get_or_create(user=user)

        return Response(
            {
                "username": user.username,
                "email": user.email,
                "total_models": models_qs.count(),
                "public_models": models_qs.filter(is_public=True).count(),
                "wallet_balance": str(wallet.credit_balance),
                "lifetime_earned": str(wallet.lifetime_earned),
                "models": ModelCardSerializer(
                    models_qs.order_by("-created_at"), many=True
                ).data,
            }
        )
