from django.core.management.base import BaseCommand
from apps.ingestion.loader import load_gtfs


class Command(BaseCommand):
    help = "Charge tous les fichiers GTFS dans la base HERMES_DB."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Chargement GTFS complet..."))

        counts = load_gtfs()

        for collection_name, count in counts.items():
            self.stdout.write(
                self.style.SUCCESS(
                    f"{collection_name}: {count} documents"
                )
            )