import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from masters.models import Client, LogisticsPartner, Planter, SugarMill


class TransactionCluster(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        DELIVERED = "delivered", "Delivered"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_code = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="clusters")
    sugar_mill = models.ForeignKey(SugarMill, on_delete=models.PROTECT, related_name="clusters")
    contract_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    mro_file = models.FileField(upload_to="mro_scans/", null=True, blank=True, help_text="Scanned soft copy of Molasses Release Order (PDF/Image)")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference_code


class PurchaseOrder(models.Model):
    cluster = models.OneToOneField(
        TransactionCluster,
        on_delete=models.CASCADE,
        related_name="purchase_order",
    )
    volume_mt = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField("Supplier Sourcing Price (₱/MT)", max_digits=12, decimal_places=2)
    selling_price = models.DecimalField("Customer Selling Price (₱/MT)", max_digits=12, decimal_places=2, null=True, blank=True, help_text="Unit price billed to customer")
    terms = models.CharField(max_length=200, blank=True)
    brix_level = models.DecimalField("Brix Level (%)", max_digits=5, decimal_places=2, null=True, blank=True, help_text="Target / Verified Brix % quality level")
    chai_specs = models.CharField("CHAI Specs", max_length=120, blank=True, help_text="Chemical / CHAI specifications")
    approved_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    @property
    def total_value(self):
        """Sourcing product cost paid to supplier."""
        return (self.volume_mt or Decimal("0")) * (self.unit_price or Decimal("0"))

    @property
    def total_selling_value(self):
        """Gross sales revenue billed to customer."""
        if self.selling_price and self.volume_mt:
            return self.volume_mt * self.selling_price
        return Decimal("0")

    def __str__(self):
        return f"PO for {self.cluster.reference_code}"


class LogisticsLedger(models.Model):
    class DisputeStatus(models.TextChoices):
        NONE = "NONE", "None"
        DISPUTED = "DISPUTED", "Disputed — Over Tolerance"
        RESOLVED = "RESOLVED", "Resolved"

    class ResolutionType(models.TextChoices):
        CONCEDED = "CONCEDED", "Concede & Proceed As-Is"
        BILLING_ADJUSTED = "BILLING_ADJUSTED", "Adjust Billing to Received Volume"
        BARGE_PENALTY = "BARGE_PENALTY", "Deduct Shortage Penalty from Logistics"
        WAIVED = "WAIVED", "Management Waiver (Brix / Evaporation)"

    cluster = models.OneToOneField(
        TransactionCluster,
        on_delete=models.CASCADE,
        related_name="logistics",
    )
    partner = models.ForeignKey(LogisticsPartner, on_delete=models.PROTECT, null=True, blank=True)
    trucking_partner = models.ForeignKey(
        LogisticsPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trucking_ledgers",
        help_text="Land Transport / Trucking Service Provider",
    )
    barge_partner = models.ForeignKey(
        LogisticsPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="barge_ledgers",
        help_text="Marine Transport / Barging Service Provider",
    )
    vessel_id = models.CharField(max_length=100, blank=True)
    loaded_volume_mt = models.DecimalField(max_digits=14, decimal_places=3)
    received_volume_mt = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    loaded_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    tracking_fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    barge_fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    variance_percent = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    variance_exceeds_tolerance = models.BooleanField(default=False)
    dispute_status = models.CharField(
        max_length=20,
        choices=DisputeStatus.choices,
        default=DisputeStatus.NONE,
    )
    resolution_type = models.CharField(
        max_length=30,
        choices=ResolutionType.choices,
        null=True,
        blank=True,
    )
    resolution_notes = models.TextField(blank=True, default="")
    waybill_file = models.FileField(upload_to="waybills/", null=True, blank=True, help_text="Scanned soft copy of Waybill")
    dr_file = models.FileField(upload_to="delivery_receipts/", null=True, blank=True, help_text="Scanned soft copy of Delivery Receipt (DR)")
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self._compute_variance()
        super().save(*args, **kwargs)
        # Dispatch background task for variance calculation
        from .tasks import compute_variance_task
        compute_variance_task.delay(self.id)

    def _compute_variance(self):
        tolerance = Decimal(str(getattr(settings, "VARIANCE_TOLERANCE_PERCENT", 1.0)))
        if self.loaded_volume_mt is not None and self.received_volume_mt is not None:
            loaded_dec = Decimal(str(self.loaded_volume_mt))
            received_dec = Decimal(str(self.received_volume_mt))
            if loaded_dec > Decimal("0"):
                diff = abs(loaded_dec - received_dec)
                self.variance_percent = (diff / loaded_dec) * Decimal("100")
                if self.dispute_status == self.DisputeStatus.RESOLVED:
                    self.variance_exceeds_tolerance = False
                else:
                    self.variance_exceeds_tolerance = self.variance_percent > tolerance
                    if self.variance_exceeds_tolerance:
                        self.dispute_status = self.DisputeStatus.DISPUTED
            else:
                self.variance_percent = Decimal("0")
                self.variance_exceeds_tolerance = False
        else:
            self.variance_percent = None
            self.variance_exceeds_tolerance = False

    @property
    def total_logistics_cost(self):
        return self.tracking_fees + self.barge_fees

    def __str__(self):
        return f"Logistics for {self.cluster.reference_code}"


class MolassesReleaseOrder(models.Model):
    mro_number = models.CharField("MRO #", max_length=50, db_index=True)
    planter = models.ForeignKey(Planter, on_delete=models.PROTECT, related_name="mro_releases")
    sugar_mill = models.ForeignKey(
        SugarMill,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mro_releases",
        help_text="Issuing Sugar Mill / Supplier",
    )
    sugar_mill_name = models.CharField("Supplier / Sugar Mill", max_length=120, blank=True, help_text="Supplier/Mill name fallback")
    tons = models.DecimalField("Tons (MT)", max_digits=14, decimal_places=5)
    release_date = models.DateField("Date", null=True, blank=True)
    trader = models.CharField("Trader", max_length=120, default="HEINDRICH")
    crop_year = models.CharField("Crop Year", max_length=30, db_index=True)
    cluster = models.ForeignKey(
        TransactionCluster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mro_releases",
        help_text="Optional transaction cluster contract linkage",
    )
    brix_level = models.DecimalField("Brix Level (%)", max_digits=5, decimal_places=2, null=True, blank=True, help_text="Brix quality level")
    chai_specs = models.CharField("CHAI Specs", max_length=120, blank=True, help_text="Chemical / CHAI quality specs")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["sugar_mill_name", "-crop_year", "mro_number", "planter__name", "id"]
        verbose_name = "Molasses Release Order"
        verbose_name_plural = "Molasses Release Orders"

    @property
    def display_sugar_mill(self):
        if self.sugar_mill:
            return self.sugar_mill.name
        return self.sugar_mill_name or "Unknown Mill"

    def save(self, *args, **kwargs):
        if self.crop_year:
            self.crop_year = normalize_crop_year(self.crop_year)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"MRO {self.mro_number} - {self.display_sugar_mill} - {self.planter.name} ({self.tons} MT)"


def normalize_crop_year(raw):
    if not raw:
        return "2024 - 2025"
    s = str(raw).strip()
    digits = re.findall(r"\b\d{2,4}\b", s)
    if len(digits) >= 2:
        y1 = int(digits[0])
        y2 = int(digits[1])
        if y1 < 100:
            y1 += 2000
        if y2 < 100:
            y2 += 2000
        return f"{y1} - {y2}"
    return s



