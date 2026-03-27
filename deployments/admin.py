from django.contrib import admin
from .models import Deployment


@admin.register(Deployment)
class DeploymentAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"model_version",
		"status",
		"runtime_type",
		"container_name",
		"created_at",
		"updated_at",
	)
	list_filter = ("status", "runtime_type", "created_at")
	search_fields = ("id", "container_name", "image_name", "model_version__model__name")