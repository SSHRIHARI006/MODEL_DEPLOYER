from django.contrib import admin
from .models import Model, ModelVersion

admin.site.register(Model)
admin.site.register(ModelVersion)