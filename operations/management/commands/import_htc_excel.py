from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.models import User
from operations.services.excel_import import clear_operational_data, import_htc_summary


class Command(BaseCommand):
    help = "Clear operational data and import HTC-2026-SUMMARY.xlsx"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="HTC-2026-SUMMARY.xlsx",
            help="Path to Excel file (default: HTC-2026-SUMMARY.xlsx in project root)",
        )
        parser.add_argument(
            "--keep-users",
            action="store_true",
            default=True,
            help="Preserve user accounts (default: true)",
        )

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path

        if not path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {path}"))
            return

        self.stdout.write("Clearing operational data...")
        clear_operational_data()

        if not User.objects.exists():
            self.stdout.write("Creating default pilot users...")
            for username, role, is_super in [
                ("admin", User.Role.MANAGEMENT, True),
                ("operations", User.Role.OPERATIONS, False),
                ("finance", User.Role.FINANCE, False),
                ("invoicing", User.Role.INVOICING, False),
            ]:
                user = User.objects.create_user(
                    username=username,
                    password="htc2026",
                    role=role,
                    is_staff=is_super,
                    is_superuser=is_super,
                )

        self.stdout.write(f"Importing from {path}...")
        imported, skipped = import_htc_summary(path)
        self.stdout.write(self.style.SUCCESS(f"Imported {imported} transactions, skipped {skipped} rows."))
