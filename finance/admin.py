from django.contrib import admin
from django.utils import timezone

from .models import (
    CapitalLoan,
    CashVoucher,
    FinancialReconciliation,
    Invoice,
    PaymentExpenseMatch,
)


class PaymentExpenseMatchInline(admin.TabularInline):
    model = PaymentExpenseMatch
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "cluster", "amount", "status", "issued_at")
    list_filter = ("status",)
    search_fields = ("invoice_number", "cluster__reference_code")


@admin.register(CashVoucher)
class CashVoucherAdmin(admin.ModelAdmin):
    list_display = ("voucher_number", "cluster", "amount", "purpose", "issued_at")
    search_fields = ("voucher_number", "cluster__reference_code")


@admin.register(CapitalLoan)
class CapitalLoanAdmin(admin.ModelAdmin):
    list_display = ("bank_name", "cluster", "principal", "interest_rate_annual", "status", "due_date")
    list_filter = ("status",)


@admin.register(FinancialReconciliation)
class FinancialReconciliationAdmin(admin.ModelAdmin):
    list_display = ("cluster", "status", "matched_payment_amount", "finalized_at")
    inlines = [PaymentExpenseMatchInline]
