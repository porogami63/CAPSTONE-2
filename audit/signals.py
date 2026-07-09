from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from finance.models import (
    CapitalLoan,
    CashVoucher,
    FinancialReconciliation,
    Invoice,
    PaymentExpenseMatch,
)

from .models import SystemAuditTrail
from .services import log_model_change, model_snapshot

FINANCE_MODELS = (Invoice, CashVoucher, CapitalLoan, FinancialReconciliation, PaymentExpenseMatch)


@receiver(pre_save)
def capture_old_financial_state(sender, instance, **kwargs):
    if sender not in FINANCE_MODELS or not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        instance._audit_old_snapshot = model_snapshot(old)
    except sender.DoesNotExist:
        instance._audit_old_snapshot = {}


@receiver(post_save)
def audit_financial_save(sender, instance, created, **kwargs):
    if sender not in FINANCE_MODELS:
        return
    user = getattr(instance, "_audit_user", None)
    if created:
        log_model_change(instance=instance, user=user, action=SystemAuditTrail.Action.CREATE)
    else:
        old = getattr(instance, "_audit_old_snapshot", {})
        log_model_change(
            instance=instance,
            user=user,
            action=SystemAuditTrail.Action.UPDATE,
            old_snapshot=old,
        )


@receiver(post_delete)
def audit_financial_delete(sender, instance, **kwargs):
    if sender not in FINANCE_MODELS:
        return
    user = getattr(instance, "_audit_user", None)
    old = model_snapshot(instance)
    SystemAuditTrail.objects.create_entry(
        user=user,
        action=SystemAuditTrail.Action.DELETE,
        table_name=instance._meta.label_lower,
        record_id=instance.pk,
        old_values=old,
        new_values={},
    )
