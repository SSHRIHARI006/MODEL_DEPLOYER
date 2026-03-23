from django.contrib import admin
from .models import PredictionLog


@admin.register(PredictionLog)
class PredictionLogAdmin(admin.ModelAdmin):
	list_display = ("uid", "user", "model", "status", "latency_ms", "created_at")
	list_filter = ("status", "created_at", "model")
	search_fields = ("uid", "user__email", "model__name", "model__id", "error_message")
	readonly_fields = (
		"id",
		"uid",
		"user",
		"model",
		"deployment",
		"input_data",
		"output_data",
		"latency_ms",
		"status",
		"error_message",
		"created_at",
	)
	ordering = ("-created_at",)