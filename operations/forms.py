from pathlib import Path

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
        label="Contract Volume (MT)",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 100.000", "step": "0.001"}),
    )
    unit_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        label="Supplier Sourcing Price (Cost to HTC) (₱/MT)",
        help_text="Price HTC pays to the sugar mill per MT",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 32500.00", "step": "0.01"}),
    )
    selling_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        label="Customer Selling Price (Revenue to HTC) (₱/MT)",
        help_text="Price HTC bills to the customer per MT",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 43500.00", "step": "0.01"}),
    )
    est_trucking_rate = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        label="Est. Land Trucking Rate (₱/MT)",
        help_text="Estimated land trucking rate per MT",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 150.00", "step": "0.01"}),
    )
    est_barge_rate = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        label="Est. Marine Barging Rate (₱/MT)",
        help_text="Estimated marine barging rate per MT",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 350.00", "step": "0.01"}),
    )
    terms = forms.CharField(
        max_length=200,
        required=False,
        label="Commercial & Payment Terms",
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Net 30 days"}),
    )
    brix_level = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        label="Brix Quality Level (%)",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 85.50", "step": "0.01"}),
    )
    chai_specs = forms.CharField(
        max_length=120,
        required=False,
        label="CHAI Specs",
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Standard Grade A Quality"}),
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

        if self.instance and self.instance.pk:
            if hasattr(self.instance, "purchase_order") and self.instance.purchase_order:
                po = self.instance.purchase_order
                self.fields["volume_mt"].initial = po.volume_mt
                self.fields["unit_price"].initial = po.unit_price
                self.fields["selling_price"].initial = po.selling_price
                self.fields["terms"].initial = po.terms
                self.fields["brix_level"].initial = po.brix_level
                self.fields["chai_specs"].initial = po.chai_specs
            if hasattr(self.instance, "logistics") and self.instance.logistics:
                log = self.instance.logistics
                vol = float(log.loaded_volume_mt or 0)
                if vol > 0:
                    if log.tracking_fees:
                        self.fields["est_trucking_rate"].initial = round(float(log.tracking_fees) / vol, 2)
                    if log.barge_fees:
                        self.fields["est_barge_rate"].initial = round(float(log.barge_fees) / vol, 2)

    def clean(self):
        cleaned_data = super().clean()
        vol = cleaned_data.get("volume_mt")
        unit_price = cleaned_data.get("unit_price")
        selling_price = cleaned_data.get("selling_price")
        est_trucking_rate = cleaned_data.get("est_trucking_rate")
        est_barge_rate = cleaned_data.get("est_barge_rate")

        if vol is not None and vol <= 0:
            self.add_error("volume_mt", "Contract volume must be a positive number greater than 0 MT.")

        if unit_price is not None and unit_price <= 0:
            self.add_error("unit_price", "Supplier sourcing price must be a positive amount in ₱/MT.")

        if selling_price is not None:
            if selling_price <= 0:
                self.add_error("selling_price", "Customer selling price must be a positive amount in ₱/MT.")
            elif unit_price is not None and selling_price < unit_price:
                self.add_error("selling_price", "Customer selling price cannot be lower than supplier sourcing price (selling below cost).")

        if est_trucking_rate is not None and est_trucking_rate < 0:
            self.add_error("est_trucking_rate", "Land trucking rate cannot be negative.")

        if est_barge_rate is not None and est_barge_rate < 0:
            self.add_error("est_barge_rate", "Marine barging rate cannot be negative.")

        return cleaned_data


class LogisticsUpdateForm(forms.ModelForm):
    class Meta:
        model = LogisticsLedger
        fields = [
            "trucking_partner",
            "tracking_fees",
            "barge_partner",
            "barge_fees",
            "vessel_id",
            "loaded_volume_mt",
            "received_volume_mt",
            "loaded_at",
            "received_at",
            "partner",
            "waybill_file",
            "dr_file",
        ]
        labels = {
            "trucking_partner": "Trucking Partner (Land Transport)",
            "tracking_fees": "Trucking / Land Freight Rate (₱/MT)",
            "barge_partner": "Barging Partner (Marine Transport)",
            "barge_fees": "Barging Freight Rate (₱/MT)",
            "partner": "Primary Logistics Partner (Fallback)",
        }
        widgets = {
            "trucking_partner": forms.Select(attrs={"class": "form-select-htc"}),
            "barge_partner": forms.Select(attrs={"class": "form-select-htc"}),
            "partner": forms.Select(attrs={"class": "form-select-htc"}),
            "vessel_id": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. LCT LBC-1 / Trip 88"}),
            "tracking_fees": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 420.00"}),
            "barge_fees": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 4200.00"}),
            "loaded_volume_mt": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.001"}),
            "received_volume_mt": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.001"}),
            "loaded_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control-htc"}),
            "received_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control-htc"}),
            "waybill_file": forms.FileInput(attrs={"class": "form-control-htc"}),
            "dr_file": forms.FileInput(attrs={"class": "form-control-htc"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        partners_qs = LogisticsPartner.objects.filter(is_active=True)
        self.fields["partner"].queryset = partners_qs
        self.fields["partner"].required = False
        self.fields["partner"].empty_label = "-- Primary Logistics Partner --"
        self.fields["trucking_partner"].queryset = partners_qs
        self.fields["trucking_partner"].required = False
        self.fields["trucking_partner"].empty_label = "-- Select Trucking Partner --"
        self.fields["barge_partner"].queryset = partners_qs
        self.fields["barge_partner"].required = False
        self.fields["barge_partner"].empty_label = "-- Select Barging Partner --"

    def clean(self):
        cleaned_data = super().clean()
        loaded_vol = cleaned_data.get("loaded_volume_mt")
        received_vol = cleaned_data.get("received_volume_mt")
        loaded_at = cleaned_data.get("loaded_at")
        received_at = cleaned_data.get("received_at")
        tracking_fees = cleaned_data.get("tracking_fees")
        barge_fees = cleaned_data.get("barge_fees")

        if loaded_vol is not None and loaded_vol <= 0:
            self.add_error("loaded_volume_mt", "Loaded volume must be a positive number greater than 0 MT.")

        if received_vol is not None and received_vol < 0:
            self.add_error("received_volume_mt", "Received volume cannot be negative.")

        if loaded_at and received_at and received_at < loaded_at:
            self.add_error("received_at", "Delivery received timestamp cannot be earlier than loading timestamp.")

        if tracking_fees is not None and tracking_fees < 0:
            self.add_error("tracking_fees", "Trucking fee rate cannot be negative.")

        if barge_fees is not None and barge_fees < 0:
            self.add_error("barge_fees", "Barging fee rate cannot be negative.")

        # Defensive file upload validation (Extension & File Size check)
        allowed_exts = {".pdf", ".png", ".jpg", ".jpeg"}
        max_size_bytes = 10 * 1024 * 1024  # 10 MB limit

        for field_name in ["waybill_file", "dr_file"]:
            file_obj = cleaned_data.get(field_name)
            if file_obj and hasattr(file_obj, "name"):
                ext = Path(file_obj.name).suffix.lower()
                if ext not in allowed_exts:
                    self.add_error(
                        field_name,
                        f"Unsupported file format '{ext}'. Only PDF and image scans (.pdf, .png, .jpg, .jpeg) are allowed.",
                    )
                if hasattr(file_obj, "size") and file_obj.size > max_size_bytes:
                    self.add_error(
                        field_name,
                        f"File size ({file_obj.size / (1024*1024):.1f} MB) exceeds maximum 10 MB limit.",
                    )

        return cleaned_data


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
        fields = [
            "mro_number", "sugar_mill", "sugar_mill_name", "planter", "planter_name",
            "tons", "release_date", "trader", "crop_year", "cluster",
            "brix_level", "chai_specs", "notes"
        ]
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
            "brix_level": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 85.50"}),
            "chai_specs": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Verified Brix 85°+"}),
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

