import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from masters.models import Client, LogisticsPartner, Planter, SugarMill


class TransactionCluster(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        RETURNED = "returned", "Returned / Rejected"
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
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_clusters")
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="rejected_clusters")
    rejection_comments = models.TextField(blank=True, default="", help_text="Mandatory reason for returning / rejecting the transaction")
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    mro_file = models.FileField(upload_to="mro_scans/", null=True, blank=True, help_text="Scanned soft copy of Molasses Release Order (PDF/Image)")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference_code

    def get_archival_blockers(self):
        """Returns a list of human-readable reasons why this transaction cluster cannot be archived yet."""
        blockers = []

        # 1. Cluster Status Check
        if self.status not in [self.Status.CLOSED, self.Status.DELIVERED]:
            blockers.append(f"Status is '{self.get_status_display()}' (Must be Delivered or Closed)")

        # 2. Invoicing & Collection Check
        invoices = self.invoices.all()
        if not invoices.exists():
            blockers.append("No sales invoice has been generated for this transaction")
        else:
            unpaid_invoices = [inv.invoice_number for inv in invoices if inv.status != "paid"]
            if unpaid_invoices:
                blockers.append(f"Unpaid invoice(s): {', '.join(unpaid_invoices)}")

        # 3. Logistics & Dispute Settlement Check
        if hasattr(self, "logistics") and self.logistics:
            if self.logistics.dispute_status == "DISPUTED":
                blockers.append("Logistics variance dispute is still active/unresolved")
            if self.logistics.received_at is None:
                blockers.append("Logistics delivery receipt is incomplete")

        # 4. Financing & Capital Loan Closure Check
        active_loans = self.loans.exclude(status="closed")
        if active_loans.exists():
            loan_banks = [f"{loan.bank_name} ({loan.get_status_display()})" for loan in active_loans]
            blockers.append(f"Unsettled capital loan(s): {', '.join(loan_banks)}")

        return blockers

    @property
    def is_archivable(self):
        """Returns True if the cluster satisfies all prerequisites for archiving."""
        return len(self.get_archival_blockers()) == 0

    def get_workflow_steps_info(self):
        """
        Calculates step-by-step completion status and missing prerequisites
        to advance across all 5 transaction workflow stages.
        """
        po = getattr(self, "purchase_order", None)
        logistics = getattr(self, "logistics", None)
        invoices = self.invoices.all()
        loans = self.loans.all()

        linked_mro_count = 0
        if hasattr(self, "mro_links"):
            linked_mro_count = self.mro_links.count()

        # Step 1: PO Input & Commercial Terms
        s1_missing = []
        if not po:
            s1_missing.append("Purchase Order details not created")
        else:
            if not po.volume_mt or po.volume_mt <= 0:
                s1_missing.append("Contract Volume (MT) required")
            if not po.unit_price or po.unit_price <= 0:
                s1_missing.append("Supplier Sourcing Price (₱/MT) required")
            if not po.selling_price or po.selling_price <= 0:
                s1_missing.append("Customer Selling Price (₱/MT) required")
        s1_complete = len(s1_missing) == 0

        # Step 2: Executive Approval
        s2_missing = []
        if not s1_complete:
            s2_missing.append("PO Input details must be complete first")
        if self.status == self.Status.DRAFT:
            s2_missing.append("Transaction PO must be submitted for approval")
        elif self.status == self.Status.RETURNED:
            s2_missing.append("Returned PO requires revision and re-submission")
        elif self.status == self.Status.PENDING_APPROVAL:
            s2_missing.append("Pending Executive Approval review")

        s2_approved = self.status in [self.Status.APPROVED, self.Status.ACTIVE, self.Status.DELIVERED, self.Status.CLOSED] or self.approved_at is not None

        # Step 3: Logistics & Receiving
        s3_missing = []
        if not s2_approved:
            s3_missing.append("PO must be approved by Executive Manager")

        has_mro = bool(self.mro_file) or (linked_mro_count > 0)
        if not has_mro:
            s3_missing.append("MRO Release Permit / scanned copy linked")

        if not logistics or not (logistics.partner or logistics.trucking_partner or logistics.barge_partner):
            s3_missing.append("Logistics carrier / partner assigned")
        if not logistics or not logistics.loaded_volume_mt or logistics.loaded_volume_mt <= 0:
            s3_missing.append("Loaded MT dispatch recorded")
        if not logistics or not logistics.received_volume_mt or logistics.received_volume_mt <= 0:
            s3_missing.append("Received MT delivery receipt recorded")
        if logistics and logistics.dispute_status == logistics.DisputeStatus.DISPUTED:
            s3_missing.append("Variance dispute exceeds tolerance (>1.0%) — resolution required")

        s3_complete = s2_approved and (len(s3_missing) == 0)

        # Step 4: Sales Invoicing
        s4_missing = []
        if not s2_approved:
            s4_missing.append("PO must be approved by Executive Manager")
        if not (logistics and logistics.received_volume_mt and logistics.received_volume_mt > 0):
            s4_missing.append("Logistics delivery receiving (Received MT) recorded")
        if logistics and not (logistics.waybill_file or logistics.dr_file):
            s4_missing.append("Supporting Waybill or Delivery Receipt (DR) scan attached")
        if not invoices.exists():
            s4_missing.append("Sales Invoice issued & recorded")
        else:
            unpaid_count = invoices.exclude(status="paid").count()
            if unpaid_count > 0:
                s4_missing.append(f"{unpaid_count} sales invoice(s) pending payment collection")

        s4_complete = s2_approved and (len(s4_missing) == 0)

        # Step 5: Finance Settlement & Closure
        s5_missing = []
        if not s4_complete:
            s5_missing.append("Sales Invoices must be fully issued and paid")
        active_loans = loans.exclude(status="closed")
        if active_loans.exists():
            s5_missing.append(f"{active_loans.count()} active capital loan facility(ies) pending settlement")
        if self.status not in [self.Status.DELIVERED, self.Status.CLOSED]:
            s5_missing.append("Deal status must be marked as Delivered or Closed")

        s5_complete = len(s5_missing) == 0 and s4_complete

        if s5_complete:
            current_step = 5
        elif s4_complete:
            current_step = 5
        elif s3_complete:
            current_step = 4
        elif s2_approved:
            current_step = 3
        elif s1_complete and self.status == self.Status.PENDING_APPROVAL:
            current_step = 2
        else:
            current_step = 1

        return {
            "step1": {
                "number": 1,
                "title": "PO Input",
                "label": "PO Input & Specs",
                "complete": s1_complete,
                "missing": s1_missing,
                "status_text": "Complete" if s1_complete else "Incomplete",
            },
            "step2": {
                "number": 2,
                "title": "Executive Approval",
                "label": "PO Approval",
                "complete": s2_approved,
                "missing": s2_missing,
                "status_text": "Approved" if s2_approved else ("Pending Review" if self.status == self.Status.PENDING_APPROVAL else ("Returned" if self.status == self.Status.RETURNED else "Draft PO")),
            },
            "step3": {
                "number": 3,
                "title": "Logistics & Receiving",
                "label": "Logistics Ledger",
                "complete": s3_complete,
                "missing": s3_missing,
                "status_text": "Received" if (logistics and logistics.received_volume_mt) else ("In Transit" if (logistics and logistics.loaded_volume_mt) else "Pending Dispatch"),
            },
            "step4": {
                "number": 4,
                "title": "Sales Invoicing",
                "label": "Sales Invoicing",
                "complete": s4_complete,
                "missing": s4_missing,
                "status_text": "Invoice Paid" if (invoices.exists() and not [inv for inv in invoices if inv.status != 'paid']) else ("Invoice Issued" if invoices.exists() else "Pending Billing"),
            },
            "step5": {
                "number": 5,
                "title": "Finance Settlement",
                "label": "Deal Settlement",
                "complete": s5_complete,
                "missing": s5_missing,
                "status_text": "Deal Closed" if s5_complete else "Pending Settlement",
            },
            "current_step": current_step,
        }




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
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_pos")
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="rejected_pos")
    rejection_comments = models.TextField(blank=True, default="", help_text="Mandatory comments detailing rejection/return reason")
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


class CHAIRecord(models.Model):
    CHAI_CHOICES = [
        (Decimal("1.0"), "CHAI 1.0 — Premium Grade A (Brix 85°+ / High Fermentable Sugar)"),
        (Decimal("1.5"), "CHAI 1.5 — Superior Grade A- (Brix 83.0° - 84.9°)"),
        (Decimal("2.0"), "CHAI 2.0 — Standard Commercial Grade B (Brix 80.0° - 82.9°)"),
        (Decimal("2.5"), "CHAI 2.5 — Medium Commercial Grade B- (Brix 78.0° - 79.9°)"),
        (Decimal("3.0"), "CHAI 3.0 — Industrial Distillation Grade C (Brix 75.0° - 77.9°)"),
        (Decimal("3.5"), "CHAI 3.5 — Utility Grade C- (Brix 72.0° - 74.9°)"),
        (Decimal("4.0"), "CHAI 4.0 — Low Grade D (Brix 70.0° - 71.9°)"),
        (Decimal("5.0"), "CHAI 5.0 — Substandard / Off-Spec (< 70.0° Brix)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chai_number = models.CharField("CHAI Record Code", max_length=50, unique=True, db_index=True)
    chai_value = models.DecimalField(
        "Numerical CHAI Grade",
        max_digits=4,
        decimal_places=1,
        choices=CHAI_CHOICES,
        default=Decimal("1.0"),
        help_text="Standard numerical quality grade (1.0 to 5.0)",
    )
    title = models.CharField("Quality Title / Summary", max_length=200, help_text="e.g. Verified High Brix Distillation Quality")
    cluster = models.ForeignKey(
        TransactionCluster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chai_records",
        help_text="Optional linked contract transaction deal",
    )
    sugar_mill = models.ForeignKey(
        SugarMill,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chai_records",
        help_text="Tested Sugar Mill / Supplier",
    )
    brix_level = models.DecimalField("Brix Level (%)", max_digits=5, decimal_places=2, default=Decimal("85.00"))
    purity_percent = models.DecimalField("Apparent Purity (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    total_sugars_percent = models.DecimalField("Total Sugars (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    tested_at = models.DateField("Inspection Date", default=timezone.localdate)
    inspector = models.CharField("Inspector / Analyst", max_length=120, blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=[("approved", "Approved / Verified"), ("pending", "Pending Verification"), ("rejected", "Rejected / Off-Spec")],
        default="approved",
    )
    remarks = models.TextField("Inspection Notes", blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_chai_records")
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="rejected_chai_records")
    rejection_comments = models.TextField("Rejection Comments", blank=True, default="", help_text="Mandatory reason for returning / rejecting CHAI certificate")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-tested_at", "-created_at"]
        verbose_name = "CHAI Record"
        verbose_name_plural = "CHAI Records"

    def __str__(self):
        return f"{self.chai_number} — CHAI {self.chai_value:.1f}"



