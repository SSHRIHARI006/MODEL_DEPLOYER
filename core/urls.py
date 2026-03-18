from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("/admin",admin.site.urls),
    path("",include("webapp.urls")),
    path("api/",include("prediction_gatewaty.urls")),
]
