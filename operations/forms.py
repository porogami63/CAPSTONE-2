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
    volume_mt = forms.DecimalField(
        max_digits=14,
        decimal_places=3,
        label="Volume (MT)",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 100.000", "step": "0.001"}),
    )
    unit_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        label="Unit Price (₱/MT)",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 42000.00", "step": "0.01"}),
    )
    terms = forms.CharField(
        max_length=200,
        required=False,
        label="Commercial Terms",
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Net 30, Selling ₱43,500"}),
    )

    class Meta:
        model = TransactionCluster
        fields = ["reference_code", "client", "sugar_mill", "contract_notes", "status"]
        widgets = {
            "reference_code": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. PO-2026-001"}),
            "client": forms.Select(attrs={"class": "form-select-htc"}),
            "sugar_mill": forms.Select(attrs={"class": "form-select-htc"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
            "contract_notes": forms.Textarea(attrs={"class": "form-control-htc", "rows": 3, "placeholder": "Optional internal notes or delivery instructions..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(is_active=True)
        self.fields["sugar_mill"].queryset = SugarMill.objects.filter(is_active=True)
        self.fields["client"].empty_label = "Select Customer (Client)..."
        self.fields["sugar_mill"].empty_label = "Select Supplier (Sugar Mill)..."

        if self.instance and self.instance.pk and hasattr(self.instance, "purchase_order") and self.instance.purchase_order:
            po = self.instance.purchase_order
            self.fields["volume_mt"].initial = po.volume_mt
            self.fields["unit_price"].initial = po.unit_price
            self.fields["terms"].initial = po.terms


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


class MolassesReleaseOrderForm(forms.ModelForm):
    planter_name = forms.CharField(
        label="Planter Name",
        required=False,
        help_text="Type custom planter/association name or select existing planter below",
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. ABSFI, SGABI, BEACO"}),
    )

    class Meta:
        from operations.models import MolassesReleaseOrder
        model = MolassesReleaseOrder
        fields = ["mro_number", "sugar_mill", "sugar_mill_name", "planter", "planter_name", "tons", "release_date", "trader", "crop_year", "cluster", "notes"]
        widgets = {
            "mro_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 000731"}),
            "sugar_mill": forms.Select(attrs={"class": "form-select-htc"}),
            "sugar_mill_name": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. BUSCO, HAWAIIAN, BISCOM, CASA, LOPEZ"}),
            "planter": forms.Select(attrs={"class": "form-select-htc"}),
            "tons": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.00001", "placeholder": "e.g. 913.11889"}),
            "release_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "trader": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "HEINDRICH"}),
            "crop_year": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 2024 - 25 or 2025 - 2026"}),
            "cluster": forms.Select(attrs={"class": "form-select-htc"}),
            "notes": forms.Textarea(attrs={"class": "form-control-htc", "rows": 2, "placeholder": "Optional notes or batch details"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from masters.models import Planter, SugarMill
        from operations.models import TransactionCluster
        self.fields["sugar_mill"].queryset = SugarMill.objects.filter(is_active=True)
        self.fields["sugar_mill"].required = False
        self.fields["sugar_mill"].empty_label = "-- Select Sugar Mill / Supplier --"
        self.fields["planter"].queryset = Planter.objects.filter(is_active=True)
        self.fields["planter"].required = False
        self.fields["planter"].empty_label = "-- Select Existing Planter --"
        self.fields["cluster"].queryset = TransactionCluster.objects.all().order_by("-created_at")
        self.fields["cluster"].empty_label = "-- Optional Linked Contract --"

    def clean(self):
        cleaned_data = super().clean()
        planter = cleaned_data.get("planter")
        planter_name = cleaned_data.get("planter_name", "").strip()

        sugar_mill = cleaned_data.get("sugar_mill")
        sugar_mill_name = cleaned_data.get("sugar_mill_name", "").strip()

        if sugar_mill and not sugar_mill_name:
            cleaned_data["sugar_mill_name"] = sugar_mill.name
        elif not sugar_mill and sugar_mill_name:
            from masters.models import SugarMill
            mill_obj, _ = SugarMill.objects.get_or_create(
                name=sugar_mill_name,
                defaults={"location": sugar_mill_name}
            )
            cleaned_data["sugar_mill"] = mill_obj

        if not planter and not planter_name:
            raise forms.ValidationError("Please select an existing planter or enter a new planter name.")

        if not planter and planter_name:
            from masters.models import Planter
            planter_obj, _ = Planter.objects.get_or_create(
                name=planter_name,
                defaults={"code": planter_name.upper()}
            )
            cleaned_data["planter"] = planter_obj

        return cleaned_data


class MROExcelImportForm(forms.Form):
    file = forms.FileField(
        label="Select MRO Excel/CSV file",
        widget=forms.FileInput(attrs={"class": "form-control-htc", "accept": ".xlsx, .xls, .csv"}),
    )
    crop_year_override = forms.CharField(
        label="Default Crop Year (Optional)",
        required=False,
        help_text="Will apply if crop year column is empty in spreadsheet (e.g. 2024 - 25)",
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 2024 - 25"}),
    )

