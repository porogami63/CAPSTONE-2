from django.core.management.base import BaseCommand
from operations.services.reminder_services import process_timeline_reminders


class Command(BaseCommand):
    help = "Evaluates scheduled operational timelines and sends automated pre-activity and post-activity reminders."

    def handle(self, *args, **options):
        self.stdout.write("Processing scheduled activity timeline reminders...")
        count = process_timeline_reminders()
        self.stdout.write(self.style.SUCCESS(f"Successfully processed timeline reminders ({count} notifications evaluated)."))
