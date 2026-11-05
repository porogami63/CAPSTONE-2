from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django import forms
from django.db import models
from django.utils import timezone

from masters.models import Client, LogisticsPartner, SugarMill
from operations.models import DeliveryLedger, LogisticsLedger, PurchaseOrder, TransactionCluster


class ExcelImportForm(forms.Form):
    workbook = forms.FileField(label="Excel workbook")
    replace_existing = forms.BooleanField(
        label="Replace current operational data",
        required=False,
        initial=True,
        help_text="Clears existing transactions, logistics, invoices, and audit rows before importing.",
    )

    def clean_workbook(self):
        workbook = self.cleaned_data.get("workbook")
        from config.upload_validators import validate_spreadsheet_upload
        return validate_spreadsheet_upload(workbook, label="Workbook")


class TransactionClusterForm(forms.ModelForm):
    volume_mt = forms.DecimalField(
        max_digits=14,
        decimal_places=3,
        label="Order Quantity (MT)",
        help_text="Total order volume in Metric Tons (1 MT = 1,000 kg)",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 100.000", "step": "0.001"}),
    )
    unit_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        label="Buying Price from Supplier (₱/MT)",
        help_text="Price we pay the sugar mill per MT",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 32500.00", "step": "0.01"}),
    )
    selling_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        label="Selling Price to Customer (₱/MT)",
        help_text="Price we bill to the customer per MT",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 43500.00", "step": "0.01"}),
    )
    terms = forms.CharField(
        max_length=200,
        required=False,
        label="Payment Terms",
        help_text="Payment conditions (e.g. 'Net 30 days')",
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Net 30 days"}),
    )
    confirmed_outlier = forms.CharField(required=False, initial="true", widget=forms.HiddenInput())
    price_warning_override = forms.CharField(required=False, initial="true", widget=forms.HiddenInput())
    brix_level = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        label="Sugar Quality (Brix %)",
        help_text="Percentage of sugar solids in molasses (e.g. 85.50%)",
        widget=forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 85.50", "step": "0.01"}),
    )
    CHAI_CHOICES = [
        ("", "-- Select Quality Grade --"),
        ("1.0", "1.0 — Premium Grade A (Brix 85°+)"),
        ("1.5", "1.5 — Superior Grade A- (Brix 83.0° – 84.9°)"),
        ("2.0", "2.0 — Standard Grade B (Brix 80.0° – 82.9°)"),
        ("2.5", "2.5 — Medium Grade B- (Brix 78.0° – 79.9°)"),
        ("3.0", "3.0 — Distillation Grade C (Brix 75.0° – 77.9°)"),
        ("3.5", "3.5 — Utility Grade C- (Brix 72.0° – 74.9°)"),
        ("4.0", "4.0 — Low Grade D (Brix 70.0° – 71.9°)"),
        ("5.0", "5.0 — Substandard (< 70.0° Brix)"),
    ]

    chai_specs = forms.ChoiceField(
        choices=CHAI_CHOICES,
        required=False,
        label="Quality Rating (CHAI Grade)",
        help_text="Standard quality rating grade for molasses",
        widget=forms.Select(attrs={"class": "form-select-htc"}),
    )

    class Meta:
        model = TransactionCluster
        fields = ["reference_code", "client", "sugar_mill", "contract_notes"]
        widgets = {
            "reference_code": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Auto-generated (e.g. PO-20261010-001)"}),
            "client": forms.Select(attrs={"class": "form-select-htc"}),
            "sugar_mill": forms.Select(attrs={"class": "form-select-htc"}),
            "contract_notes": forms.Textarea(attrs={"class": "form-control-htc", "rows": 3, "placeholder": "Optional internal notes or delivery instructions..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from operations.services.reference_generators import generate_po_reference
        self.fields["reference_code"].required = False
        self.fields["client"].queryset = Client.objects.filter(is_active=True)
        self.fields["sugar_mill"].queryset = SugarMill.objects.filter(is_active=True)
        self.fields["client"].empty_label = "Select Customer (Client)..."
        self.fields["sugar_mill"].empty_label = "Select Supplier (Sugar Mill)..."

        if not self.instance or not self.instance.pk:
            if not self.initial.get("reference_code"):
                self.initial["reference_code"] = generate_po_reference()

        if self.instance and self.instance.pk:
            if hasattr(self.instance, "purchase_order") and self.instance.purchase_order:
                po = self.instance.purchase_order
                self.fields["volume_mt"].initial = po.volume_mt
                self.fields["unit_price"].initial = po.unit_price
                self.fields["selling_price"].initial = po.selling_price
                self.fields["terms"].initial = po.terms
                self.fields["brix_level"].initial = po.brix_level
                
                # Normalize chai_specs string to numeric key if needed
                specs_val = (po.chai_specs or "").strip()
                import re
                match = re.search(r"(\d+\.\d+|\d+)", specs_val)
                if match and match.group(1) in dict(self.CHAI_CHOICES):
                    self.fields["chai_specs"].initial = match.group(1)
                else:
                    self.fields["chai_specs"].initial = specs_val

    def clean_reference_code(self):
        ref = self.cleaned_data.get("reference_code", "").strip()
        if not ref:
            from operations.services.reference_generators import generate_po_reference
            ref = generate_po_reference()
        return ref

    def clean(self):
        cleaned_data = super().clean()
        vol = cleaned_data.get("volume_mt")
        unit_price = cleaned_data.get("unit_price")
        selling_price = cleaned_data.get("selling_price")

        if vol is not None and vol <= 0:
            self.add_error("volume_mt", "Contract volume must be a positive number greater than 0 MT.")

        if unit_price is not None and unit_price <= 0:
            self.add_error("unit_price", "Supplier sourcing price must be a positive amount in ₱/MT.")

        if selling_price is not None:
            if selling_price <= 0:
                self.add_error("selling_price", "Customer selling price must be a positive amount in ₱/MT.")
            elif unit_price is not None:
                from operations.services.stats_services import check_price_margin_anomalies
                margin_analysis = check_price_margin_anomalies(unit_price, selling_price)
                self.price_margin_analysis = margin_analysis
                cleaned_data["price_margin_analysis"] = margin_analysis

        brix_level = cleaned_data.get("brix_level")
        if brix_level is not None and (brix_level < 0 or brix_level > 100):
            self.add_error("brix_level", "Brix Quality Level (%) must be a valid percentage between 0 and 100.")

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
            "received_at": "Delivered Date & Time / Vessel ETA",
        }
        help_texts = {
            "received_at": "Actual delivery timestamp or scheduled vessel/truck ETA. Fully editable for schedule adjustments.",
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
        from masters.models import ensure_default_trucking_partners
        ensure_default_trucking_partners()

        partners_qs = LogisticsPartner.objects.filter(is_active=True).order_by("name")
        trucking_q = models.Q(category=LogisticsPartner.Category.TRUCKING)
        barge_q = models.Q(category=LogisticsPartner.Category.BARGING)

        if self.instance and getattr(self.instance, "trucking_partner_id", None):
            trucking_q |= models.Q(pk=self.instance.trucking_partner_id)
        if self.data and self.data.get("trucking_partner"):
            try:
                trucking_q |= models.Q(pk=int(self.data.get("trucking_partner")))
            except (ValueError, TypeError):
                pass

        if self.instance and getattr(self.instance, "barge_partner_id", None):
            barge_q |= models.Q(pk=self.instance.barge_partner_id)
        if self.data and self.data.get("barge_partner"):
            try:
                barge_q |= models.Q(pk=int(self.data.get("barge_partner")))
            except (ValueError, TypeError):
                pass

        self.fields["partner"].queryset = partners_qs
        self.fields["partner"].required = False
        self.fields["partner"].empty_label = "-- Primary Logistics Partner --"
        self.fields["trucking_partner"].queryset = partners_qs.filter(trucking_q).order_by("name")
        self.fields["trucking_partner"].required = False
        self.fields["trucking_partner"].empty_label = "-- Select Trucking Partner (Metro Manila / Greater Luzon) --"
        self.fields["barge_partner"].queryset = partners_qs.filter(barge_q).order_by("name")
        self.fields["barge_partner"].required = False
        self.fields["barge_partner"].empty_label = "-- Select Barging Partner (Marine Transport) --"

    def clean(self):
        cleaned_data = super().clean()
        loaded_vol = cleaned_data.get("loaded_volume_mt")
        received_vol = cleaned_data.get("received_volume_mt")
        loaded_at = cleaned_data.get("loaded_at")
        received_at = cleaned_data.get("received_at")
        tracking_fees = cleaned_data.get("tracking_fees")
        barge_fees = cleaned_data.get("barge_fees")

        # Operations is not gated by financing status to reduce friction.
        # Soft indicator is presented on cluster overview.

        if loaded_vol is not None and loaded_vol <= 0:
            self.add_error("loaded_volume_mt", "Loaded volume must be a positive number greater than 0 MT.")

        if received_vol is not None and received_vol < 0:
            self.add_error("received_volume_mt", "Received volume cannot be negative.")

        now = timezone.now()
        future_threshold = now + timedelta(minutes=15)

        if loaded_at and loaded_at > future_threshold:
            self.add_error("loaded_at", "Loading date and time cannot be set in the future.")

        # Allow received_at to be set in the future for ETA tracking, and remain fully editable.

        if loaded_at and received_at:
            if received_at < loaded_at:
                self.add_error("received_at", "Delivery received timestamp cannot be earlier than loading timestamp.")
            elif loaded_at.date() == received_at.date():
                self.add_error("received_at", "Loading and receiving on the same day is physically impossible. Please verify the dates.")
                
        if received_at and not loaded_at:
            self.add_error("loaded_at", "Loading timestamp must be provided if delivery received timestamp is specified.")

        if loaded_at and loaded_at.year < 2020:
            self.add_error("loaded_at", "Loading timestamp is invalid (cannot be before year 2020).")

        if received_at and received_at.year < 2020:
            self.add_error("received_at", "Delivered timestamp is invalid (cannot be before year 2020).")

        if received_vol is not None and received_vol > 0 and not received_at:
            cleaned_data["received_at"] = now
            if self.instance:
                self.instance.received_at = now

        if tracking_fees is not None and tracking_fees < 0:
            self.add_error("tracking_fees", "Trucking fee rate cannot be negative.")

        if barge_fees is not None and barge_fees < 0:
            self.add_error("barge_fees", "Barging fee rate cannot be negative.")

        from config.upload_validators import validate_document_upload
        from django.core.exceptions import ValidationError

        for field_name in ["waybill_file", "dr_file"]:
            file_obj = cleaned_data.get(field_name)
            if file_obj:
                try:
                    cleaned_data[field_name] = validate_document_upload(file_obj, label=self.fields[field_name].label)
                except ValidationError as e:
                    self.add_error(field_name, e.message)

        return cleaned_data


class DeliveryLedgerForm(forms.ModelForm):
    po_reference_number = forms.CharField(
        label="PO Reference Number",
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = DeliveryLedger
        fields = [
            "purchase_order",
            "supplier",
            "mro_permit",
            "dispatched_mt",
            "delivered_mt",
            "receiving_location",
            "delivery_date",
            "dispatched_at",
            "received_at",
            "carrier",
            "trucking_partner",
            "trucking_rate_per_mt",
            "flat_trucking_fee",
            "barge_partner",
            "vessel_or_barge_name",
            "barge_rate_per_mt",
            "flat_barge_fee",
            "vessel_or_truck",
            "dr_number",
            "waybill_number",
            "notes",
        ]
        labels = {
            "purchase_order": "Purchase Order (PO #)",
            "supplier": "Source Sugar Mill",
            "mro_permit": "Fulfillment MRO Permit",
            "dispatched_mt": "Volume Dispatched (MT)",
            "delivered_mt": "Volume Delivered / Confirmed (MT)",
            "receiving_location": "Delivery Location / Site",
            "delivery_date": "Delivery Date",
            "dispatched_at": "Dispatch Date & Time",
            "received_at": "Arrival Date & Time",
            "carrier": "Carrier (Optional)",
            "trucking_partner": "Trucker (Land Transport Partner)",
            "trucking_rate_per_mt": "Trucking Rate (₱/MT)",
            "flat_trucking_fee": "Fixed Trucking Price (₱)",
            "barge_partner": "Barger (Marine Transport Partner)",
            "vessel_or_barge_name": "Vessel / Barge Name",
            "barge_rate_per_mt": "Barging Rate (₱/MT)",
            "flat_barge_fee": "Fixed Barging Price (₱)",
            "vessel_or_truck": "Truck Plate #",
            "dr_number": "DR Number",
            "waybill_number": "Waybill Number",
            "notes": "Notes / Remarks",
        }
        widgets = {
            "purchase_order": forms.Select(attrs={"class": "form-select-htc", "id": "id_delivery_po", "autocomplete": "off"}),
            "supplier": forms.Select(attrs={"class": "form-select-htc", "id": "id_delivery_supplier", "autocomplete": "off"}),
            "mro_permit": forms.Select(attrs={"class": "form-select-htc", "id": "id_delivery_mro", "autocomplete": "off"}),
            "dispatched_mt": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.001", "placeholder": "e.g. 2000.000", "id": "id_dispatched_mt_vol", "autocomplete": "off"}),
            "delivered_mt": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.001", "placeholder": "e.g. 2000.000", "id": "id_delivery_mt", "autocomplete": "off"}),
            "receiving_location": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Main Plant, Warehouse 2, Silo A", "id": "id_delivery_location", "autocomplete": "off"}),
            "delivery_date": forms.DateInput(attrs={"type": "date", "class": "form-control-htc", "id": "id_delivery_date"}),
            "dispatched_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control-htc", "id": "id_dispatched_at"}),
            "received_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control-htc", "id": "id_received_at"}),
            "carrier": forms.Select(attrs={"class": "form-select-htc"}),
            "trucking_partner": forms.Select(attrs={"class": "form-select-htc", "id": "id_trucking_partner"}),
            "trucking_rate_per_mt": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 450.00", "id": "id_trucking_rate_per_mt"}),
            "flat_trucking_fee": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 50000.00 (Fixed Price)", "id": "id_flat_trucking_fee"}),
            "barge_partner": forms.Select(attrs={"class": "form-select-htc", "id": "id_barge_partner"}),
            "vessel_or_barge_name": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. LCT LBC-1 / Barge 08", "id": "id_vessel_or_barge_name"}),
            "barge_rate_per_mt": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 1200.00", "id": "id_barge_rate_per_mt"}),
            "flat_barge_fee": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 150000.00 (Fixed Price)", "id": "id_flat_barge_fee"}),
            "vessel_or_truck": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Plate NBD-1234", "id": "id_vessel_or_truck"}),
            "dr_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. DR-8890"}),
            "waybill_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. WB-9921"}),
            "notes": forms.Textarea(attrs={"class": "form-control-htc", "rows": 2, "placeholder": "Optional shipment notes..."}),
        }

    receiving_customer = forms.ModelChoiceField(
        queryset=Client.objects.filter(is_active=True).order_by("name"),
        required=False,
        label="Receiving Customer",
        empty_label="-- Select Customer --",
        widget=forms.Select(attrs={"class": "form-select-htc", "id": "id_receiving_customer_select"}),
    )

    def __init__(self, *args, **kwargs):
        initial_po = kwargs.pop("initial_po", None)
        super().__init__(*args, **kwargs)
        
        pos = PurchaseOrder.objects.select_related("cluster", "customer", "cluster__client").order_by("-cluster__created_at")
        self.fields["purchase_order"].queryset = pos
        self.fields["purchase_order"].empty_label = "-- Select Purchase Order --"
        self.fields["purchase_order"].label_from_instance = (
            lambda obj: f"{obj.po_reference_number or obj.cluster.reference_code} — {obj.customer.name if obj.customer else (obj.cluster.client.name if obj.cluster else 'Unknown')} (Rem: {obj.remaining_mt:,.3f} MT | {obj.po_status})"
        )
        
        self.fields["supplier"].queryset = SugarMill.objects.filter(is_active=True).order_by("name")
        self.fields["supplier"].empty_label = "-- Select Sugar Mill --"
        
        from masters.models import ensure_default_trucking_partners
        ensure_default_trucking_partners()

        logistics_qs = LogisticsPartner.objects.filter(is_active=True).order_by("name")
        trucking_q = models.Q(category=LogisticsPartner.Category.TRUCKING)
        barge_q = models.Q(category=LogisticsPartner.Category.BARGING)

        if self.instance and getattr(self.instance, "trucking_partner_id", None):
            trucking_q |= models.Q(pk=self.instance.trucking_partner_id)
        if self.data and self.data.get("trucking_partner"):
            try:
                trucking_q |= models.Q(pk=int(self.data.get("trucking_partner")))
            except (ValueError, TypeError):
                pass

        if self.instance and getattr(self.instance, "barge_partner_id", None):
            barge_q |= models.Q(pk=self.instance.barge_partner_id)
        if self.data and self.data.get("barge_partner"):
            try:
                barge_q |= models.Q(pk=int(self.data.get("barge_partner")))
            except (ValueError, TypeError):
                pass

        self.fields["carrier"].queryset = logistics_qs
        self.fields["carrier"].required = False
        self.fields["carrier"].empty_label = "-- Select Carrier (Optional) --"

        self.fields["trucking_partner"].queryset = logistics_qs.filter(trucking_q).order_by("name")
        self.fields["trucking_partner"].required = False
        self.fields["trucking_partner"].empty_label = "-- Select Trucking Partner (Metro Manila / Greater Luzon) --"

        self.fields["barge_partner"].queryset = logistics_qs.filter(barge_q).order_by("name")
        self.fields["barge_partner"].required = False
        self.fields["barge_partner"].empty_label = "-- Select Barging Partner (Marine Transport) --"

        clients_qs = Client.objects.filter(is_active=True).order_by("name")
        self.fields["receiving_customer"].queryset = clients_qs
        # Customer Immutability (PO Link Lock)
        self.fields["receiving_customer"].disabled = True
        self.fields["receiving_customer"].widget.attrs.update({
            "class": "form-select-htc bg-slate-100 cursor-not-allowed pointer-events-none",
            "title": "Customer is strictly locked to the linked Purchase Order (PO Link Lock)",
        })
        self.fields["receiving_customer"].help_text = "Locked to linked PO customer (PO Link Lock)"

        from operations.models import MolassesReleaseOrder
        self.fields["mro_permit"].required = False
        self.fields["mro_permit"].empty_label = "-- Select Linked MRO Permit (Optional) --"
        if initial_po and hasattr(initial_po, "cluster") and initial_po.cluster:
            self.fields["mro_permit"].queryset = initial_po.cluster.mro_releases.all()
        else:
            self.fields["mro_permit"].queryset = MolassesReleaseOrder.objects.all().order_by("-created_at")[:50]

        if not initial_po and self.data and self.data.get("purchase_order"):
            try:
                initial_po = PurchaseOrder.objects.select_related("cluster", "customer", "cluster__client", "cluster__sugar_mill").filter(pk=int(self.data.get("purchase_order"))).first()
            except (ValueError, TypeError):
                pass

        self.fields["dispatched_mt"].required = False
        self.logistics_locked = False
        self.initialized_logistics = {"is_initialized": False}

        if initial_po:
            if hasattr(initial_po, "cluster") and initial_po.cluster and initial_po.cluster.client_id:
                if initial_po.customer_id != initial_po.cluster.client_id:
                    initial_po.customer = initial_po.cluster.client
                    initial_po.save(update_fields=["customer"])
            self.fields["purchase_order"].initial = initial_po
            self.initial["purchase_order"] = initial_po.pk
            cust = (initial_po.cluster.client if hasattr(initial_po, "cluster") and initial_po.cluster and initial_po.cluster.client else None) or initial_po.customer
            if cust:
                self.fields["receiving_customer"].queryset = Client.objects.filter(pk=cust.pk)
                self.fields["receiving_customer"].empty_label = None
                self.fields["receiving_customer"].initial = cust
                self.initial["receiving_customer"] = cust.pk
                if not self.initial.get("receiving_location"):
                    default_site = f"{cust.name} Main Site"
                    self.fields["receiving_location"].initial = default_site
                    self.initial["receiving_location"] = default_site
            mill = getattr(initial_po.cluster, "sugar_mill", None) if hasattr(initial_po, "cluster") and initial_po.cluster else None
            if mill:
                self.fields["supplier"].initial = mill
                if not self.is_bound:
                    self.initial["supplier"] = mill.pk
                else:
                    self.initial.setdefault("supplier", mill.pk)

            # Pre-fill and lock initialized barger / trucker and fixed price / rate if already initialized on this PO
            init_cfg = initial_po.get_initialized_logistics(exclude_delivery_id=self.instance.pk if self.instance and self.instance.pk else None)
            self.initialized_logistics = init_cfg
            if init_cfg.get("is_initialized"):
                self.logistics_locked = True
                if init_cfg.get("trucking_partner_id"):
                    self.fields["trucking_partner"].initial = init_cfg["trucking_partner_id"]
                    self.initial["trucking_partner"] = init_cfg["trucking_partner_id"]
                    self.fields["trucking_partner"].widget.attrs.update({
                        "class": "form-select-htc bg-slate-100 pointer-events-none",
                        "data-locked": "true",
                        "title": "Locked — Trucker was initialized on first delivery for this PO",
                    })
                if init_cfg.get("barge_partner_id"):
                    self.fields["barge_partner"].initial = init_cfg["barge_partner_id"]
                    self.initial["barge_partner"] = init_cfg["barge_partner_id"]
                    self.fields["barge_partner"].widget.attrs.update({
                        "class": "form-select-htc bg-slate-100 pointer-events-none",
                        "data-locked": "true",
                        "title": "Locked — Barger was initialized on first delivery for this PO",
                    })
                for rate_field in ["trucking_rate_per_mt", "flat_trucking_fee", "barge_rate_per_mt", "flat_barge_fee"]:
                    val = init_cfg.get(rate_field)
                    if val is not None and val > Decimal("0.00"):
                        self.fields[rate_field].initial = val
                        self.initial[rate_field] = val
                        self.fields[rate_field].widget.attrs.update({
                            "readonly": "readonly",
                            "class": "form-control-htc bg-slate-100 cursor-not-allowed",
                            "data-locked": "true",
                            "title": "Locked — Fixed price / rate was initialized on first delivery for this PO",
                        })
                for txt_field in ["vessel_or_barge_name", "vessel_or_truck"]:
                    val = init_cfg.get(txt_field)
                    if val:
                        self.fields[txt_field].initial = val
                        self.initial[txt_field] = val
        elif self.instance and getattr(self.instance, "purchase_order_id", None):
            inst_po = self.instance.purchase_order
            cust = (inst_po.cluster.client if getattr(inst_po, "cluster", None) and inst_po.cluster.client else None) or inst_po.customer
            if cust:
                self.fields["receiving_customer"].initial = cust
                self.initial["receiving_customer"] = cust.pk

    def clean(self):
        cleaned_data = super().clean()
        po = cleaned_data.get("purchase_order")
        delivered_mt = cleaned_data.get("delivered_mt")
        rec_loc = cleaned_data.get("receiving_location")
        supplier = cleaned_data.get("supplier")
        delivery_date = cleaned_data.get("delivery_date")
        dispatched_at = cleaned_data.get("dispatched_at")
        received_at = cleaned_data.get("received_at")
        trucking_rate = cleaned_data.get("trucking_rate_per_mt")
        flat_trucking = cleaned_data.get("flat_trucking_fee")
        barge_rate = cleaned_data.get("barge_rate_per_mt")
        flat_barge = cleaned_data.get("flat_barge_fee")

        # 1. Customer Immutability (PO Link Lock):
        # Receiving Customer MUST strictly match the Customer associated with the linked Purchase Order.
        if po:
            po_customer = (po.cluster.client if getattr(po, "cluster", None) and po.cluster.client else None) or po.customer
            if po_customer:
                cleaned_data["receiving_customer"] = po_customer
                if po.customer_id != po_customer.pk:
                    po.customer = po_customer
                    po.save(update_fields=["customer"])
        rec_cust = cleaned_data.get("receiving_customer")

        # 2. Purchase Order Validation
        if not po:
            self.add_error("purchase_order", "Please select a valid Purchase Order contract.")

        # 3. Receiving Location Validation & Auto-Fill (also prevent stale default site from another customer)
        if rec_cust:
            loc_str = (rec_loc or "").strip()
            is_stale_other_customer_site = False
            if loc_str and not loc_str.lower().startswith(rec_cust.name.lower()):
                lower_loc = loc_str.lower()
                if lower_loc.endswith("main site") or lower_loc.endswith("main facility"):
                    other_clients = Client.objects.exclude(pk=rec_cust.pk).values_list("name", flat=True)
                    for oc_name in other_clients:
                        if oc_name and lower_loc.startswith(oc_name.lower()):
                            is_stale_other_customer_site = True
                            break
            if not loc_str or is_stale_other_customer_site:
                rec_loc = f"{rec_cust.name} Main Site"
                cleaned_data["receiving_location"] = rec_loc

        if not rec_loc or not rec_loc.strip():
            self.add_error("receiving_location", "Delivery drop-off destination / receiving site is required.")
        else:
            cleaned_data["receiving_location"] = rec_loc.strip()

        # 3. Source Mill Supplier Validation
        if po and not supplier:
            mill = getattr(po.cluster, "sugar_mill", None) if hasattr(po, "cluster") and po.cluster else None
            if mill:
                cleaned_data["supplier"] = mill
                supplier = mill

        if not cleaned_data.get("supplier"):
            self.add_error("supplier", "Source Sugar Mill / Supplier is required.")

        # 4. Dispatched & Delivered Quantity Validation
        dispatched_mt = cleaned_data.get("dispatched_mt")
        if dispatched_mt is not None and dispatched_mt <= 0:
            self.add_error("dispatched_mt", "Dispatched quantity must be greater than 0 MT.")
        elif dispatched_mt is not None and dispatched_mt > Decimal("100000.000"):
            self.add_error("dispatched_mt", "Dispatched quantity exceeds maximum batch limit (100,000 MT).")

        if delivered_mt is None and dispatched_mt is not None and dispatched_mt > 0:
            delivered_mt = dispatched_mt
            cleaned_data["delivered_mt"] = delivered_mt
        elif dispatched_mt is None and delivered_mt is not None and delivered_mt > 0:
            dispatched_mt = delivered_mt
            cleaned_data["dispatched_mt"] = dispatched_mt

        if delivered_mt is None:
            self.add_error("delivered_mt", "Delivered quantity is required.")
        elif delivered_mt <= 0:
            self.add_error("delivered_mt", "Delivered quantity must be greater than 0 MT.")
        elif delivered_mt > Decimal("100000.000"):
            self.add_error("delivered_mt", "Delivered quantity exceeds maximum batch limit (100,000 MT).")

        if po and delivered_mt is not None and delivered_mt > 0:
            contracted = po.total_contracted_mt if po.total_contracted_mt is not None else (po.volume_mt or Decimal("0"))
            existing = po.deliveries.all()
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            total_other = existing.aggregate(t=models.Sum("delivered_mt"))["t"] or Decimal("0")
            available = max(contracted - total_other, Decimal("0"))

            if available <= Decimal("0") and (not self.instance or not self.instance.pk):
                po_ref = po.po_reference_number or (po.cluster.reference_code if po.cluster else "PO")
                self.add_error(
                    "delivered_mt",
                    f"PO {po_ref} is already 100% fulfilled. Remaining deliverable balance is 0.000 MT."
                )
            elif delivered_mt > available:
                po_ref = po.po_reference_number or (po.cluster.reference_code if po.cluster else "PO")
                self.add_error(
                    "delivered_mt",
                    f"Delivered quantity ({delivered_mt:,.3f} MT) exceeds the remaining available balance ({available:,.3f} MT) for PO {po_ref}."
                )

        # 5. Date & Timestamp Validation (Future arrival dates / ETAs explicitly supported)
        if delivery_date:
            if delivery_date.year < 2020 or delivery_date.year > 2100:
                self.add_error("delivery_date", "Delivery date must be within years 2020 to 2100.")

        if dispatched_at:
            if dispatched_at.year < 2020 or dispatched_at.year > 2100:
                self.add_error("dispatched_at", "Departure dispatch timestamp must be within years 2020 to 2100.")

        if received_at:
            # Note: Future arrival dates / ETAs are fully allowed and valid as vessel/truck arrivals are tentative
            if received_at.year < 2020 or received_at.year > 2100:
                self.add_error("received_at", "Arrival timestamp must be within years 2020 to 2100.")

            if dispatched_at and received_at < dispatched_at:
                self.add_error(
                    "received_at",
                    "Arrival timestamp cannot be earlier than departure dispatch timestamp."
                )

        # 6. Logistics Fee Validations (non-negative) & Fixed Price / Carrier Lock Enforcement
        if trucking_rate is not None and trucking_rate < 0:
            self.add_error("trucking_rate_per_mt", "Trucking rate cannot be negative.")
        if flat_trucking is not None and flat_trucking < 0:
            self.add_error("flat_trucking_fee", "Flat trucking fee cannot be negative.")
        if barge_rate is not None and barge_rate < 0:
            self.add_error("barge_rate_per_mt", "Barging rate cannot be negative.")
        if flat_barge is not None and flat_barge < 0:
            self.add_error("flat_barge_fee", "Flat barge fee cannot be negative.")

        if po:
            init_cfg = po.get_initialized_logistics(exclude_delivery_id=self.instance.pk if self.instance and self.instance.pk else None)
            if init_cfg.get("is_initialized"):
                if init_cfg.get("trucking_partner"):
                    sub_trk = cleaned_data.get("trucking_partner")
                    if not sub_trk:
                        cleaned_data["trucking_partner"] = init_cfg["trucking_partner"]
                    elif sub_trk.pk != init_cfg["trucking_partner_id"]:
                        self.add_error("trucking_partner", f"Trucker is locked to {init_cfg['trucking_partner_name']} once initialized for this PO.")
                if init_cfg.get("barge_partner"):
                    sub_brg = cleaned_data.get("barge_partner")
                    if not sub_brg:
                        cleaned_data["barge_partner"] = init_cfg["barge_partner"]
                    elif sub_brg.pk != init_cfg["barge_partner_id"]:
                        self.add_error("barge_partner", f"Barger is locked to {init_cfg['barge_partner_name']} once initialized for this PO.")
                if init_cfg.get("carrier") and not cleaned_data.get("carrier"):
                    cleaned_data["carrier"] = init_cfg["carrier"]

                for r_field, label_str in [
                    ("trucking_rate_per_mt", "Trucking rate"),
                    ("flat_trucking_fee", "Fixed trucking price"),
                    ("barge_rate_per_mt", "Barging rate"),
                    ("flat_barge_fee", "Fixed barging price"),
                ]:
                    init_val = Decimal(str(init_cfg.get(r_field) or "0.00"))
                    if init_val > Decimal("0.00"):
                        sub_val = Decimal(str(cleaned_data.get(r_field) or "0.00"))
                        if sub_val == Decimal("0.00"):
                            cleaned_data[r_field] = init_val
                        elif sub_val != init_val:
                            self.add_error(r_field, f"{label_str} is locked at ₱{init_val:,.2f} once initialized for this PO and cannot be changed.")

                for t_field in ["vessel_or_barge_name", "vessel_or_truck"]:
                    if init_cfg.get(t_field) and not cleaned_data.get(t_field):
                        cleaned_data[t_field] = init_cfg[t_field]

        # 7. String fields sanitization
        for field_name in ["vessel_or_truck", "vessel_or_barge_name", "dr_number", "waybill_number"]:
            val = cleaned_data.get(field_name)
            if val and isinstance(val, str):
                cleaned_data[field_name] = val.strip()

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
            "brix_level", "chai_specs", "notes", "scanned_file"
        ]
        labels = {
            "scanned_file": "Direct Permit Scan (Optional if sharing PO consolidated scan)",
        }
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
            "scanned_file": forms.FileInput(attrs={"class": "form-control-htc", "accept": ".pdf,image/*"}),
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
            self.instance.sugar_mill = mill_obj

        # Operations is not gated by financing status to reduce friction.
        # Soft indicator is presented on cluster overview.

        if not planter and not planter_name:
            raise forms.ValidationError("Please select an existing planter or enter a new planter name.")

        if not planter and planter_name:
            from masters.models import Planter
            planter_obj, _ = Planter.objects.get_or_create(
                name=planter_name,
                defaults={"code": planter_name.upper()}
            )
            cleaned_data["planter"] = planter_obj
            self.instance.planter = planter_obj

        brix_level = cleaned_data.get("brix_level")
        if brix_level is not None and (brix_level < 0 or brix_level > 100):
            self.add_error("brix_level", "Brix Level (%) must be a valid percentage between 0 and 100.")

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

    def clean_file(self):
        file_obj = self.cleaned_data.get("file")
        from config.upload_validators import validate_spreadsheet_upload
        return validate_spreadsheet_upload(file_obj, label="MRO File", legacy=True)


class CHAIRecordForm(forms.ModelForm):
    class Meta:
        from operations.models import CHAIRecord
        model = CHAIRecord
        fields = [
            "chai_number", "chai_value", "title", "sugar_mill", "cluster",
            "brix_level", "purity_percent", "total_sugars_percent", "tested_at",
            "inspector", "status", "remarks"
        ]
        widgets = {
            "chai_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Auto-generated (e.g. CHAI-20260925-001)"}),
            "chai_value": forms.Select(attrs={"class": "form-select-htc"}),
            "title": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Verified High Brix Distillation Quality"}),
            "sugar_mill": forms.Select(attrs={"class": "form-select-htc"}),
            "cluster": forms.Select(attrs={"class": "form-select-htc"}),
            "brix_level": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "85.00"}),
            "purity_percent": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 78.50"}),
            "total_sugars_percent": forms.NumberInput(attrs={"class": "form-control-htc", "step": "0.01", "placeholder": "e.g. 55.00"}),
            "tested_at": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "inspector": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. QC Analyst / Lab Inspector Name"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
            "remarks": forms.Textarea(attrs={"class": "form-control-htc", "rows": 3, "placeholder": "Detailed chemical quality analysis and laboratory remarks..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from masters.models import SugarMill
        from operations.models import TransactionCluster
        from operations.services.reference_generators import generate_chai_number

        self.fields["chai_number"].required = False
        self.fields["sugar_mill"].queryset = SugarMill.objects.filter(is_active=True)
        self.fields["sugar_mill"].empty_label = "-- Select Sugar Mill / Supplier --"
        self.fields["cluster"].queryset = TransactionCluster.objects.filter(is_archived=False).order_by("-created_at")
        self.fields["cluster"].empty_label = "-- Optional Linked Deal --"

        if not self.instance or not self.instance.pk:
            if not self.initial.get("chai_number"):
                self.initial["chai_number"] = generate_chai_number()

    def clean_chai_number(self):
        val = self.cleaned_data.get("chai_number", "").strip()
        if not val:
            from operations.services.reference_generators import generate_chai_number
            val = generate_chai_number()
        return val

    def clean(self):
        cleaned_data = super().clean()
        
        for field in ["brix_level", "purity_percent", "total_sugars_percent"]:
            val = cleaned_data.get(field)
            if val is not None and (val < 0 or val > 100):
                self.add_error(field, f"{self.fields[field].label} must be a valid percentage between 0 and 100.")
                
        return cleaned_data

