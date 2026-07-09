from celery import shared_task
from .models import LogisticsLedger

@shared_task
def compute_variance_task(ledger_id):
    try:
        ledger = LogisticsLedger.objects.get(id=ledger_id)
        # Avoid triggering the custom save method again that re-dispatches the task
        # so we calculate it here and use update() to save.
        ledger._compute_variance()
        LogisticsLedger.objects.filter(id=ledger_id).update(
            variance_percent=ledger.variance_percent,
            variance_exceeds_tolerance=ledger.variance_exceeds_tolerance
        )
        return f"Variance computed for ledger {ledger_id}: {ledger.variance_percent}%"
    except LogisticsLedger.DoesNotExist:
        return f"Ledger {ledger_id} not found."
