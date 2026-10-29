# pyrefly: ignore [missing-import]
from django.contrib import admin
from .models import APIKey


class APIKeyAdmin(admin.ModelAdmin):
    def deactivate_keys(self, request, queryset):
        queryset.update(is_active=False)

    deactivate_keys.short_description = "Deactivate selected API keys"

    def activate_keys(self, request, queryset):
        queryset.update(is_active=True)

    activate_keys.short_description = "Activate selected API keys"

    # SEC-07: only a hash is stored, so there is no key material to display.
    readonly_fields = ("key_hash", "key_prefix", "created_at")
    list_display = (
        "name",
        "key_prefix",
        "user",
        "model",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "user__email", "model__name", "model__id")
    actions = ("deactivate_keys", "activate_keys")
    ordering = ("-created_at",)


admin.site.register(APIKey, APIKeyAdmin)
