from django.contrib import admin
from .models import Model, ModelVersion


class ModelVersionInline(admin.TabularInline):
	model = ModelVersion
	extra = 0
	fields = ("version", "status", "artifact_path", "created_at")
	readonly_fields = ("created_at",)


@admin.register(Model)
class ModelAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "framework", "task_type", "owner", "created_at")
	list_filter = ("framework", "task_type", "created_at")
	search_fields = ("id", "name", "owner__email")
	readonly_fields = ("created_at",)
	inlines = [ModelVersionInline]
	ordering = ("-created_at",)


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
	list_display = ("id", "model", "version", "status", "created_at")
	list_filter = ("status", "created_at")
	search_fields = ("model__name", "model__id", "version")
	readonly_fields = ("created_at",)
	ordering = ("-created_at",)