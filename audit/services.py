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
