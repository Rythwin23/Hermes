from django.apps import AppConfig

class RoutingConfig(AppConfig):
    name = "apps.routing"

    def ready(self):
        from apps.routing.raptor.model import RaptorModel
        RaptorModel.get()