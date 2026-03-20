from django.contrib import admin
from .models import APIKey


class APIKeyAdmin(admin.ModelAdmin):
    readonly_fields = ("key",)
    list_display = ("name", "user", "model", "is_active", "created_at")


admin.site.register(APIKey, APIKeyAdmin)