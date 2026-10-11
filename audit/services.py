from decimal import Decimal
from uuid import UUID

from django.db.models import Model
from django.forms.models import model_to_dict

from .models import SystemAuditTrail

FINANCIAL_MODELS = {
    "Invoice",
    "CashVoucher",
    "CapitalLoan",
    "FinancialReconciliation",
    "PaymentExpenseMatch",
}


def _serialize(value):
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "name"):
        return str(value.name)
    if hasattr(value, "url"):
        return str(value.url)
    return str(value)


def model_snapshot(instance: Model) -> dict:
    data = model_to_dict(instance)
    return {key: _serialize(val) for key, val in data.items()}


def log_model_change(*, instance, user, action, old_snapshot=None):
    if instance.__class__.__name__ not in FINANCIAL_MODELS:
        return
    SystemAuditTrail.objects.create_entry(
        user=user,
        action=action,
        table_name=instance._meta.label_lower,
        record_id=instance.pk,
        old_values=old_snapshot or {},
        new_values=model_snapshot(instance) if action != SystemAuditTrail.Action.DELETE else {},
    )


def notify_user(user, title, message, level="info", link=None):
    if not user:
        return None
    from .models import Notification
    return Notification.objects.create(
        recipient=user,
        title=title,
        message=message,
        level=level,
        link=link,
    )


def notify_roles(roles, title, message, level="info", link=None, exclude_user=None):
    from accounts.models import User
    from .models import Notification

    users = User.objects.filter(role__in=roles, is_active=True)
    if exclude_user:
        users = users.exclude(pk=exclude_user.pk)

    notifications = [
        Notification(
            recipient=u,
            title=title,
            message=message,
            level=level,
            link=link,
        )
        for u in users
    ]
    return Notification.objects.bulk_create(notifications)


def get_cluster_audit_events(cluster) -> list[dict]:
    """Collects chronological audit trail events for a transaction cluster across operations, finance, and logistics."""
    events = []
    if not cluster:
        return events

    # 1. Cluster history
    if hasattr(cluster, "history"):
        for h in cluster.history.all():
            events.append({
                "date": h.history_date,
                "user": h.history_user,
                "type": h.history_type,
                "model": "Transaction Cluster",
                "desc": f"Status: {h.status}",
            })

    # 2. Logistics history
    if hasattr(cluster, "logistics") and cluster.logistics and hasattr(cluster.logistics, "history"):
        for h in cluster.logistics.history.all():
            events.append({
                "date": h.history_date,
                "user": h.history_user,
                "type": h.history_type,
                "model": "Logistics",
                "desc": f"Loaded: {h.loaded_volume_mt} MT, Received: {h.received_volume_mt} MT",
            })

    # 3. Purchase Order history
    po = getattr(cluster, "purchase_order", None)
    if po and hasattr(po, "history"):
        for h in po.history.all():
            events.append({
                "date": h.history_date,
                "user": h.history_user,
                "type": h.history_type,
                "model": "Purchase Order",
                "desc": f"Volume: {h.volume_mt} MT @ ₱{h.unit_price}",
            })

    # 4. Invoices history
    if hasattr(cluster, "invoices"):
        for inv in cluster.invoices.all():
            if hasattr(inv, "history"):
                for h in inv.history.all():
                    events.append({
                        "date": h.history_date,
                        "user": h.history_user,
                        "type": h.history_type,
                        "model": f"Invoice {h.invoice_number}",
                        "desc": f"Status: {h.status}, Amount: ₱{h.amount:,.2f}" if h.amount else f"Status: {h.status}",
                    })

    # 5. Cash Vouchers history
    if hasattr(cluster, "cash_vouchers"):
        for v in cluster.cash_vouchers.all():
            if hasattr(v, "history"):
                for h in v.history.all():
                    events.append({
                        "date": h.history_date,
                        "user": h.history_user,
                        "type": h.history_type,
                        "model": f"Voucher {h.voucher_number}",
                        "desc": f"Amount: ₱{h.amount:,.2f}, Purpose: {h.purpose}",
                    })

    # 6. Deliveries history
    if po and hasattr(po, "deliveries"):
        for d in po.deliveries.all():
            if hasattr(d, "history"):
                for h in d.history.all():
                    short_id = str(d.delivery_id)[:8].upper()
                    events.append({
                        "date": h.history_date,
                        "user": h.history_user,
                        "type": h.history_type,
                        "model": f"Delivery #{short_id}",
                        "desc": f"Delivered: {h.delivered_mt} MT to {h.receiving_location or 'Client'}",
                    })

    # 7. Bank Loan Events
    if hasattr(cluster, "loans"):
        for loan in cluster.loans.all():
            if loan.created_at:
                events.append({
                    "date": loan.created_at,
                    "user": getattr(loan, "verified_by", None),
                    "type": "+",
                    "model": f"Loan ({loan.bank_name})",
                    "desc": f"Principal: ₱{loan.principal:,.2f}, Status: {loan.get_status_display()}",
                })
            if loan.verified_at:
                events.append({
                    "date": loan.verified_at,
                    "user": loan.verified_by,
                    "type": "~",
                    "model": f"Loan ({loan.bank_name})",
                    "desc": f"Verified & Approved by {loan.verified_by}",
                })

    events.sort(key=lambda x: x["date"], reverse=True)
    return events

