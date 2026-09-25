from datetime import timedelta
from django.utils import timezone
from accounts.models import User
from audit.services import notify_roles


def process_timeline_reminders():
    """
    Evaluates scheduled operational timelines and dispatches automated pre-activity
    and post-activity (overdue) notifications based on agreed company timelines.
    """
    from operations.models import TransactionCluster, LogisticsLedger
    from finance.models import Invoice

    now = timezone.now()
    today = timezone.localdate()
    sent_count = 0

    # 1. PRE-ACTIVITY REMINDERS: Invoices due in 3 days
    three_days_hence = today + timedelta(days=3)
    due_soon_invoices = Invoice.objects.filter(
        status=Invoice.Status.ISSUED,
        due_date=three_days_hence,
        is_archived=False,
    ).select_related("cluster", "cluster__client")

    for inv in due_soon_invoices:
        notify_roles(
            [User.Role.FINANCE, User.Role.INVOICING, User.Role.OPERATIONS_MANAGEMENT],
            title=f"Pre-Activity Reminder: Invoice Due Soon — {inv.invoice_number}",
            message=f"Upcoming Payment Timeline: Invoice {inv.invoice_number} (₱{inv.amount:,.2f} for {inv.cluster.client.name}) is due in 3 days on {inv.due_date.strftime('%b %d, %Y')}.",
            level="info",
            link=f"/operations/{inv.cluster.pk}/",
        )
        sent_count += 1

    # 2. POST-ACTIVITY OVERDUE REMINDERS: Invoices past due date or issued over 30 days ago
    thirty_days_ago = today - timedelta(days=30)
    overdue_invoices = Invoice.objects.filter(
        status=Invoice.Status.ISSUED,
        is_archived=False,
    ).select_related("cluster", "cluster__client")

    for inv in overdue_invoices:
        is_past_due = (inv.due_date and inv.due_date < today) or (inv.issued_at and inv.issued_at <= thirty_days_ago)
        if is_past_due:
            due_str = inv.due_date.strftime("%b %d, %Y") if inv.due_date else inv.issued_at.strftime("%b %d, %Y")
            notify_roles(
                [User.Role.FINANCE, User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT],
                title=f"Overdue Payment Alert — Invoice {inv.invoice_number}",
                message=f"Timeline Exceeded: Invoice {inv.invoice_number} (₱{inv.amount:,.2f}) has surpassed its agreed payment timeline ({due_str}). Immediate follow-up required.",
                level="danger",
                link=f"/operations/{inv.cluster.pk}/",
            )
            sent_count += 1

    # 3. POST-ACTIVITY OVERDUE REMINDERS: Logistics loaded > 5 days ago without receipt
    five_days_ago = now - timedelta(days=5)
    overdue_logistics = LogisticsLedger.objects.filter(
        loaded_at__lte=five_days_ago,
        received_volume_mt__isnull=True,
        is_archived=False,
    ).select_related("cluster", "partner")

    for log in overdue_logistics:
        notify_roles(
            [User.Role.OPERATIONS_MANAGEMENT, User.Role.ADMINISTRATOR, User.Role.OPERATIONS],
            title=f"Overdue Shipment Receiving Alert — {log.cluster.reference_code}",
            message=f"Logistics Timeline Exceeded: Shipment for {log.cluster.reference_code} loaded on {log.loaded_at.strftime('%b %d, %Y')} has been in transit over 5 days without receipt confirmation.",
            level="warning",
            link=f"/operations/{log.cluster.pk}/",
        )
        sent_count += 1

    # 4. IDLE PENDING APPROVAL REMINDERS: Transactions pending approval for > 48 hours
    forty_eight_hours_ago = now - timedelta(hours=48)
    idle_clusters = TransactionCluster.objects.filter(
        status=TransactionCluster.Status.PENDING_APPROVAL,
        submitted_at__lte=forty_eight_hours_ago,
        is_archived=False,
    )

    for cl in idle_clusters:
        notify_roles(
            [User.Role.OPERATIONS_MANAGEMENT, User.Role.ADMINISTRATOR],
            title=f"Pending Approval Reminder — {cl.reference_code}",
            message=f"Approval Timeline Idle: Transaction {cl.reference_code} has been pending executive review for over 48 hours.",
            level="warning",
            link=f"/operations/{cl.pk}/",
        )
        sent_count += 1

    return sent_count
