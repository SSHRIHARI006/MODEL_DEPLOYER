from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from model_registry.models import ModelVersion
from runners.factory import RunnerFactory

from .models import Deployment
from .serializers import DeploymentCreateSerializer, DeploymentSerializer
from .services import start_deployment_async


class DeploymentCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Deployment.objects.select_related("model_version__model").filter(
            model_version__model__owner=request.user
        )
        model_id = request.query_params.get("model_id")
        if model_id:
            queryset = queryset.filter(model_version__model_id=model_id)

        queryset = queryset.order_by("-created_at")
        serializer = DeploymentSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DeploymentCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        model_version = ModelVersion.objects.select_related("model").get(
            id=serializer.validated_data["model_version_id"]
        )

        # REL-07: Block duplicate active deployments per model version
        active = Deployment.objects.filter(
            model_version=model_version,
            status__in=[
                Deployment.Status.PENDING,
                Deployment.Status.BUILDING,
                Deployment.Status.RUNNING,
            ],
        ).first()
        if active:
            return Response(
                {
                    "error": "An active deployment already exists for this model version",
                    "deployment_id": str(active.id),
                    "status": active.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            deployment = Deployment.objects.create(
                model_version=model_version,
                status=Deployment.Status.PENDING,
                runtime_type="container",
            )
        except IntegrityError:
            active = Deployment.objects.filter(
                model_version=model_version,
                status__in=[
                    Deployment.Status.PENDING,
                    Deployment.Status.BUILDING,
                    Deployment.Status.RUNNING,
                ],
            ).first()
            return Response(
                {
                    "error": "An active deployment already exists for this model version",
                    "deployment_id": str(active.id) if active else None,
                    "status": active.status if active else None,
                },
                status=status.HTTP_409_CONFLICT,
            )

        task = start_deployment_async(str(deployment.id))
        response_data = DeploymentSerializer(deployment).data
        task_id = getattr(task, "id", None)
        if isinstance(task_id, str):
            response_data["task_id"] = task_id

        return Response(response_data, status=status.HTTP_202_ACCEPTED)


class DeploymentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, deployment_id):
        deployment = (
            Deployment.objects.select_related("model_version__model")
            .filter(
                id=deployment_id,
                model_version__model__owner=request.user,
            )
            .first()
        )
        if not deployment:
            return Response(
                {"error": "Deployment not found"}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            DeploymentSerializer(deployment).data, status=status.HTTP_200_OK
        )

    def delete(self, request, deployment_id):
        deployment = (
            Deployment.objects.select_related("model_version__model")
            .filter(
                id=deployment_id,
                model_version__model__owner=request.user,
            )
            .first()
        )
        if not deployment:
            return Response(
                {"error": "Deployment not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if deployment.status in (
            Deployment.Status.PENDING,
            Deployment.Status.BUILDING,
            Deployment.Status.RUNNING,
        ):
            deployment.transition_to(Deployment.Status.STOPPED)
            deployment.stopped_at = timezone.now()
            deployment.save(update_fields=["status", "stopped_at", "updated_at"])
            runner = RunnerFactory.get_runner(
                framework=deployment.model_version.model.framework
            )
            try:
                runner.teardown({"model_id": str(deployment.model_version_id)})
            except Exception:
                pass

        deployment.delete()
        return Response(
            {"message": "Deployment deleted successfully"}, status=status.HTTP_200_OK
        )


class DeploymentStopAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, deployment_id):
        deployment = (
            Deployment.objects.select_related("model_version__model")
            .filter(
                id=deployment_id,
                model_version__model__owner=request.user,
            )
            .first()
        )
        if not deployment:
            return Response(
                {"error": "Deployment not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if deployment.status == Deployment.Status.STOPPED:
            return Response(
                DeploymentSerializer(deployment).data, status=status.HTTP_200_OK
            )

        deployment.transition_to(Deployment.Status.STOPPED)
        deployment.stopped_at = timezone.now()
        deployment.save(update_fields=["status", "stopped_at", "updated_at"])

        runner = RunnerFactory.get_runner(
            framework=deployment.model_version.model.framework
        )
        try:
            runner.teardown({"model_id": str(deployment.model_version_id)})
        except Exception:
            pass

        return Response(
            DeploymentSerializer(deployment).data, status=status.HTTP_200_OK
        )
