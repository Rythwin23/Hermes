# config/urls.py
from django.urls import path, include

urlpatterns = [
    path("api/", include("apps.network.urls")),
    path("api/", include("apps.routing.urls")),
]