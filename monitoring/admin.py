from django.contrib import admin
from .models import UsageMetric


@admin.register(UsageMetric)
class UsageMetricAdmin(admin.ModelAdmin):
	list_display = ("user", "date", "request_count", "error_count", "avg_latency")
	list_filter = ("date",)
	search_fields = ("user__email",)
	ordering = ("-date",)