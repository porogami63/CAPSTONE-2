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


def notify_user(user, title, message, level="info", link=None, category=None):
    if not user:
        return None
    from .models import Notification
    cat = category or Notification.Category.SYSTEM
    return Notification.objects.create(
        recipient=user,
        title=title,
        message=message,
        level=level,
        link=link,
        category=cat,
    )


def notify_roles(roles, title, message, level="info", link=None, exclude_user=None, category=None):
    from accounts.models import User
    from .models import Notification

    users = User.objects.filter(role__in=roles, is_active=True)
    if exclude_user:
        users = users.exclude(pk=exclude_user.pk)

    cat = category or Notification.Category.SYSTEM
    notifications = [
        Notification(
            recipient=u,
            title=title,
            message=message,
            level=level,
            link=link,
            category=cat,
        )
        for u in users
    ]
    return Notification.objects.bulk_create(notifications)


def _get_user_display_info(user_obj):
    """Returns (full_name_or_username, role_display) for an authenticated or system actor."""
    if not user_obj:
        return "System Core", "System"
    name = getattr(user_obj, "get_full_name", lambda: "")() or getattr(user_obj, "username", "System")
    role = (
        user_obj.get_role_display()
        if hasattr(user_obj, "get_role_display")
        else getattr(user_obj, "role", "Staff")
    )
    if isinstance(role, str) and not role:
        role = "Authorized User"
    return name, role


def get_cluster_audit_events(cluster) -> list[dict]:
    """
    Collects chronological audit trail events for a transaction cluster across operations,
    finance, logistics, and SystemAuditTrail, explicitly exposing the actor (person + role)
    and exact mutations/modifications that occurred.
    """
    events = []
    if not cluster:
        return events

    from django.db.models import Q
    from .models import SystemAuditTrail

    c_pk = str(cluster.pk)
    po_ref = str(cluster.reference_code)

    # 1. SystemAuditTrail immutable database logs
    trail_entries = (
        SystemAuditTrail.objects.filter(
            Q(record_id=c_pk)
            | Q(record_id=po_ref)
            | Q(new_values__cluster=c_pk)
            | Q(old_values__cluster=c_pk)
            | Q(new_values__po_ref=po_ref)
        )
        .select_related("user")
        .order_by("-timestamp")
    )

    for entry in trail_entries:
        actor_name, actor_role = _get_user_display_info(entry.user)
        changes = []
        for k, new_v in (entry.new_values or {}).items():
            old_v = (entry.old_values or {}).get(k)
            if old_v != new_v and k not in ["cluster", "id", "updated_at"]:
                changes.append(f"{k.replace('_', ' ').title()}: '{old_v}' → '{new_v}'")

        if entry.action == SystemAuditTrail.Action.CREATE:
            desc = f"Created record with initial parameters ({', '.join(f'{k}={v}' for k, v in list((entry.new_values or {}).items())[:3])})"
        elif entry.action == SystemAuditTrail.Action.UPDATE:
            reason = (entry.new_values or {}).get("reason")
            if reason:
                desc = f"Compensating Adjustment: {', '.join(changes)}. Justification: {reason}"
            else:
                desc = f"Updated: {', '.join(changes)}" if changes else f"Updated {entry.table_name} state"
        else:
            desc = f"Deleted record from {entry.table_name}"

        events.append({
            "date": entry.timestamp,
            "user": entry.user,
            "user_name": actor_name,
            "user_role": actor_role,
            "type": "+" if entry.action == "create" else ("~" if entry.action == "update" else "-"),
            "model": entry.table_name,
            "desc": desc,
            "is_audit_trail": True,
        })

    # 2. Cluster history (HistoricalRecords)
    if hasattr(cluster, "history"):
        for h in cluster.history.all():
            actor_name, actor_role = _get_user_display_info(h.history_user)
            changes = []
            if h.prev_record:
                try:
                    delta = h.diff_against(h.prev_record)
                    for change in delta.changes:
                        if change.field not in ["updated_at"]:
                            changes.append(f"{change.field.replace('_', ' ').title()}: '{change.old}' → '{change.new}'")
                except Exception:
                    pass
            desc = f"Updated: {', '.join(changes)}" if changes else f"Status: {h.status}"
            events.append({
                "date": h.history_date,
                "user": h.history_user,
                "user_name": actor_name,
                "user_role": actor_role,
                "type": h.history_type,
                "model": "Transaction Cluster",
                "desc": desc,
            })

    # 3. Logistics history
    if hasattr(cluster, "logistics") and cluster.logistics and hasattr(cluster.logistics, "history"):
        for h in cluster.logistics.history.all():
            actor_name, actor_role = _get_user_display_info(h.history_user)
            changes = []
            if h.prev_record:
                try:
                    delta = h.diff_against(h.prev_record)
                    for change in delta.changes:
                        if change.field not in ["updated_at"]:
                            changes.append(f"{change.field.replace('_', ' ').title()}: '{change.old}' → '{change.new}'")
                except Exception:
                    pass
            desc = f"Logistics Updated: {', '.join(changes)}" if changes else f"Loaded: {h.loaded_volume_mt} MT, Received: {h.received_volume_mt} MT"
            events.append({
                "date": h.history_date,
                "user": h.history_user,
                "user_name": actor_name,
                "user_role": actor_role,
                "type": h.history_type,
                "model": "Logistics Ledger",
                "desc": desc,
            })

    # 4. Purchase Order history
    po = getattr(cluster, "purchase_order", None)
    if po and hasattr(po, "history"):
        for h in po.history.all():
            actor_name, actor_role = _get_user_display_info(h.history_user)
            changes = []
            if h.prev_record:
                try:
                    delta = h.diff_against(h.prev_record)
                    for change in delta.changes:
                        if change.field not in ["updated_at"]:
                            changes.append(f"{change.field.replace('_', ' ').title()}: '{change.old}' → '{change.new}'")
                except Exception:
                    pass
            desc = f"PO Parameters Updated: {', '.join(changes)}" if changes else f"Contract Volume: {h.volume_mt} MT @ ₱{h.unit_price}"
            events.append({
                "date": h.history_date,
                "user": h.history_user,
                "user_name": actor_name,
                "user_role": actor_role,
                "type": h.history_type,
                "model": "Purchase Order",
                "desc": desc,
            })

    # 5. Invoices history
    if hasattr(cluster, "invoices"):
        for inv in cluster.invoices.all():
            if hasattr(inv, "history"):
                for h in inv.history.all():
                    actor_name, actor_role = _get_user_display_info(h.history_user)
                    events.append({
                        "date": h.history_date,
                        "user": h.history_user,
                        "user_name": actor_name,
                        "user_role": actor_role,
                        "type": h.history_type,
                        "model": f"Invoice {h.invoice_number}",
                        "desc": f"Status: {h.status}, Amount: ₱{h.amount:,.2f}" if h.amount else f"Status: {h.status}",
                    })

    # 6. Cash Vouchers history
    if hasattr(cluster, "cash_vouchers"):
        for v in cluster.cash_vouchers.all():
            if hasattr(v, "history"):
                for h in v.history.all():
                    actor_name, actor_role = _get_user_display_info(h.history_user)
                    changes = []
                    if h.prev_record:
                        try:
                            delta = h.diff_against(h.prev_record)
                            for change in delta.changes:
                                changes.append(f"{change.field.replace('_', ' ').title()}: '{change.old}' → '{change.new}'")
                        except Exception:
                            pass
                    desc = f"Voucher Updated: {', '.join(changes)}" if changes else f"Voucher #{h.voucher_number}: ₱{h.amount:,.2f} ({h.purpose})"
                    events.append({
                        "date": h.history_date,
                        "user": h.history_user,
                        "user_name": actor_name,
                        "user_role": actor_role,
                        "type": h.history_type,
                        "model": f"Voucher #{h.voucher_number}",
                        "desc": desc,
                    })

    # 7. Deliveries history
    if po and hasattr(po, "deliveries"):
        for d in po.deliveries.all():
            if hasattr(d, "history"):
                for h in d.history.all():
                    actor_name, actor_role = _get_user_display_info(h.history_user)
                    changes = []
                    if h.prev_record:
                        try:
                            delta = h.diff_against(h.prev_record)
                            for change in delta.changes:
                                changes.append(f"{change.field.replace('_', ' ').title()}: '{change.old}' → '{change.new}'")
                        except Exception:
                            pass
                    short_id = str(d.delivery_id)[:8].upper()
                    desc = f"Delivery Adjusted: {', '.join(changes)}" if changes else f"Delivered: {h.delivered_mt} MT to {h.receiving_location or 'Client'}"
                    events.append({
                        "date": h.history_date,
                        "user": h.history_user,
                        "user_name": actor_name,
                        "user_role": actor_role,
                        "type": h.history_type,
                        "model": f"Delivery #{short_id}",
                        "desc": desc,
                    })

    # 8. Bank Loans (settlement and verification events)
    if hasattr(cluster, "loans"):
        for loan in cluster.loans.all():
            if loan.created_at:
                c_name, c_role = _get_user_display_info(getattr(loan, "created_by", None))
                events.append({
                    "date": loan.created_at,
                    "user": getattr(loan, "created_by", None),
                    "user_name": c_name,
                    "user_role": c_role,
                    "type": "+",
                    "model": f"Loan ({loan.bank_name})",
                    "desc": f"Loan Principal: ₱{loan.principal:,.2f} @ {loan.interest_rate_annual:.2f}% p.a. Status: {loan.get_status_display()}",
                })
            if loan.verified_at:
                v_name, v_role = _get_user_display_info(loan.verified_by)
                events.append({
                    "date": loan.verified_at,
                    "user": loan.verified_by,
                    "user_name": v_name,
                    "user_role": v_role,
                    "type": "~",
                    "model": f"Loan ({loan.bank_name})",
                    "desc": f"Dual-Authorization Verified & Approved by {v_name} ({v_role})",
                })
            if getattr(loan, "is_archived", False) and getattr(loan, "archived_at", None):
                a_name, a_role = _get_user_display_info(getattr(loan, "archived_by", None))
                events.append({
                    "date": loan.archived_at,
                    "user": getattr(loan, "archived_by", None),
                    "user_name": a_name,
                    "user_role": a_role,
                    "type": "~",
                    "model": f"Loan ({loan.bank_name})",
                    "desc": f"Settled and Archived by {a_name} ({a_role}). Receipt: {loan.settlement_receipt_number or 'N/A'}",
                })

    events.sort(key=lambda x: x["date"], reverse=True)
    return events

