from django import forms

from masters.models import Client, LogisticsPartner, SugarMill
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster


class ExcelImportForm(forms.Form):
    workbook = forms.FileField(label="Excel workbook")
    replace_existing = forms.BooleanField(
        label="Replace current operational data",
        required=False,
        initial=True,
        help_text="Clears existing transactions, logistics, invoices, and audit rows before importing.",
    )

    def clean_workbook(self):
        workbook = self.cleaned_data["workbook"]
        filename = workbook.name.lower()
        if not filename.endswith((".xlsx", ".xlsm")):
            raise forms.ValidationError("Upload an .xlsx or .xlsm workbook.")
        return workbook


class TransactionClusterForm(forms.ModelForm):
    volume_mt = forms.DecimalField(max_digits=14, decimal_places=3, label="Volume (MT)")
    unit_price = forms.DecimalField(max_digits=12, decimal_places=2, label="Unit price")
    terms = forms.CharField(max_length=200, required=False)

    class Meta:
        model = TransactionCluster
        fields = ["reference_code", "client", "sugar_mill", "contract_notes", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(is_active=True)
        self.fields["sugar_mill"].queryset = SugarMill.objects.filter(is_active=True)


class LogisticsUpdateForm(forms.ModelForm):
    class Meta:
        model = LogisticsLedger
        fields = [
            "partner",
            "vessel_id",
            "loaded_volume_mt",
            "received_volume_mt",
            "loaded_at",
            "received_at",
            "tracking_fees",
            "barge_fees",
        ]
        widgets = {
            "loaded_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "received_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["partner"].queryset = LogisticsPartner.objects.filter(is_active=True)
