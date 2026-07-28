from django import forms

from finance.models import CapitalLoan, CashVoucher, Invoice, PaymentExpenseMatch
from operations.models import TransactionCluster


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["invoice_number", "amount", "issued_at", "status", "notes"]
        widgets = {
            "invoice_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. INV-2026-001"}),
            "amount": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 1500000.00", "step": "0.01"}),
            "issued_at": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
            "notes": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Optional invoice notes..."}),
        }


class CashVoucherForm(forms.ModelForm):
    class Meta:
        model = CashVoucher
        fields = ["voucher_number", "amount", "purpose", "issued_at"]
        widgets = {
            "voucher_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. CV-2026-001"}),
            "amount": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 25000.00", "step": "0.01"}),
            "purpose": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Barging & Pier Fees"}),
            "issued_at": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
        }


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
            "bank_name": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. BDO Unibank"}),
            "principal": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 5000000.00", "step": "0.01"}),
            "interest_rate_annual": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 12.0000", "step": "0.0001"}),
            "start_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
        }


class PaymentExpenseMatchForm(forms.ModelForm):
    class Meta:
        model = PaymentExpenseMatch
        fields = ["payment_reference", "expense_type", "amount", "notes"]
