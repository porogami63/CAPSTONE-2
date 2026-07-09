from celery import shared_task
from .models import CapitalLoan

@shared_task
def refresh_loan_statuses_task():
    # Only need to check loans that aren't already closed or overdue
    active_loans = CapitalLoan.objects.filter(status=CapitalLoan.Status.ACTIVE)
    updated_count = 0
    for loan in active_loans:
        old_status = loan.status
        loan.refresh_status()
        if loan.status != old_status:
            loan.save(update_fields=['status'])
            updated_count += 1
    return f"Refreshed loan statuses. Updated {updated_count} loans to OVERDUE."
