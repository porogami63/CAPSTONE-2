from django import forms

from finance.models import CapitalLoan, CashVoucher, Invoice, PaymentExpenseMatch
from operations.models import TransactionCluster


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["invoice_number", "amount", "issued_at", "status", "notes"]
        widgets = {"issued_at": forms.DateInput(attrs={"type": "date"})}


class CashVoucherForm(forms.ModelForm):
    class Meta:
        model = CashVoucher
        fields = ["voucher_number", "amount", "purpose", "issued_at"]
        widgets = {"issued_at": forms.DateInput(attrs={"type": "date"})}


class CapitalLoanForm(forms.ModelForm):
    class Meta:
        model = CapitalLoan
        fields = [
            "bank_name",
            "principal",
            "interest_rate_annual",
            "start_date",
            "due_date",
            "status",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class PaymentExpenseMatchForm(forms.ModelForm):
    class Meta:
        model = PaymentExpenseMatch
        fields = ["payment_reference", "expense_type", "amount", "notes"]
