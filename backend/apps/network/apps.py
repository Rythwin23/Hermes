from django.apps import AppConfig


class NetworkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.network"

    def ready(self):
        # Keep the GTFS snapshot lazy: loading it in ready() creates a large
        # memory spike at startup even when routing is not used yet.
        return