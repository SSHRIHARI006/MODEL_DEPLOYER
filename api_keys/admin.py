from django.contrib import admin
from .models import APIKey


class APIKeyAdmin(admin.ModelAdmin):
    def deactivate_keys(self, request, queryset):
        queryset.update(is_active=False)

    deactivate_keys.short_description = "Deactivate selected API keys"

    def activate_keys(self, request, queryset):
        queryset.update(is_active=True)

    activate_keys.short_description = "Activate selected API keys"

    readonly_fields = ("key",)
    list_display = ("name", "user", "model", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "user__email", "model__name", "model__id")
    actions = ("deactivate_keys", "activate_keys")
    ordering = ("-created_at",)


admin.site.register(APIKey, APIKeyAdmin)