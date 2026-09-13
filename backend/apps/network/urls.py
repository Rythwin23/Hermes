from django.urls import path

from . import views


urlpatterns = [
    # ROUTES
    path("routes", views.routes_list, name="route-list"),
    path("routes/<str:route_id>", views.route_detail, name="route-detail"),

    # STOPS
    path("stops", views.stops_list, name="stop-list"),
    path("stops/<str:stop_id>", views.stop_detail, name="stop-detail"),
]
