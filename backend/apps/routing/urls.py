from django.urls import path

from . import views


urlpatterns = [
	path("raptor/test", views.raptor_test, name="raptor-test"),
]
