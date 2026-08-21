from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from operations.services.mro_import import import_mro_workbook


class Command(BaseCommand):
    help = "Seed initial Molasses Release Orders from LBC MRO FINAL.xlsx across all supplier sheets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="LBC MRO FINAL.xlsx",
            help="Path to MRO Excel file (default: LBC MRO FINAL.xlsx in project root)",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.is_absolute():
            file_path = Path(settings.BASE_DIR) / file_path

        if not file_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        self.stdout.write(f"Importing Molasses Release Orders across all supplier sheets from {file_path.name}...")
        created, updated = import_mro_workbook(file_path, clear_existing=True)
        self.stdout.write(self.style.SUCCESS(f"Successfully imported MRO data: {created} created, {updated} updated."))
