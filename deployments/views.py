from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from model_registry.models import ModelVersion

from .models import Deployment
from .serializers import DeploymentCreateSerializer, DeploymentSerializer
from .services import start_deployment_async


class DeploymentCreateAPIView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request):
		serializer = DeploymentCreateSerializer(data=request.data, context={"request": request})
		serializer.is_valid(raise_exception=True)

		model_version = ModelVersion.objects.select_related("model").get(
			id=serializer.validated_data["model_version_id"]
		)

		deployment = Deployment.objects.create(
			model_version=model_version,
			status=Deployment.Status.PENDING,
			runtime_type="container",
		)
		start_deployment_async(str(deployment.id))

		return Response(DeploymentSerializer(deployment).data, status=status.HTTP_202_ACCEPTED)


class DeploymentDetailAPIView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request, deployment_id):
		deployment = Deployment.objects.select_related("model_version__model").filter(
			id=deployment_id,
			model_version__model__owner=request.user,
		).first()
		if not deployment:
			return Response({"error": "Deployment not found"}, status=status.HTTP_404_NOT_FOUND)

		return Response(DeploymentSerializer(deployment).data, status=status.HTTP_200_OK)
