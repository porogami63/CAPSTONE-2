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
        is_received = bool(logistics and logistics.received_volume_mt and logistics.received_volume_mt > 0)
        is_delivered = self.status in [self.Status.DELIVERED, self.Status.CLOSED]
        if not has_mro and not is_received and not is_delivered:
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
            s4_missing.append("PO approved by Executive Manager")
        if not is_received and not is_delivered:
            s4_missing.append("Delivery received (Received MT)")
        if not invoices.exists():
            s4_missing.append("Sales invoice recorded")
        else:
            unpaid_count = invoices.exclude(status="paid").count()
            if unpaid_count > 0:
                s4_missing.append(f"{unpaid_count} sales invoice(s) pending payment")

        s4_complete = s2_approved and (len(s4_missing) == 0)

        # Step 5: Finance Settlement & Closure
        s5_missing = []
        if not s4_complete:
            if not invoices.exists():
                s5_missing.append("Sales Invoices must be issued")
            else:
                unpaid_count = invoices.exclude(status="paid").count()
                if unpaid_count > 0:
                    s5_missing.append(f"{unpaid_count} sales invoice(s) pending payment")
                else:
                    s5_missing.append("Sales Invoicing stage must be completed")

        active_loans = loans.exclude(status="closed").exclude(status="rejected")
        if active_loans.exists():
            s5_missing.append(f"{active_loans.count()} active capital loan facility(ies) pending settlement")
        if self.status not in [self.Status.DELIVERED, self.Status.CLOSED]:
            s5_missing.append("Deal status must be marked as Delivered or Closed")

        s5_complete = (len(s5_missing) == 0) and s4_complete

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
    class POStatus(models.TextChoices):
        OPEN = "Open", "Open"
        PARTIALLY_FULFILLED = "Partially Fulfilled", "Partially Fulfilled"
        COMPLETED = "Completed", "Completed"

    cluster = models.OneToOneField(
        TransactionCluster,
        on_delete=models.CASCADE,
        related_name="purchase_order",
    )
    po_reference_number = models.CharField(
        "PO Reference Number",
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Standard customer PO reference number (e.g. PO-20261010-001)",
    )
    total_contracted_mt = models.DecimalField(
        "Total Contracted Quantity (MT)",
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Total contracted volume in Metric Tons (e.g. 10000.000 MT)",
    )
    customer = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_orders",
        help_text="Primary purchasing client / customer",
    )
    po_status = models.CharField(
        "PO Status",
        max_length=30,
        choices=POStatus.choices,
        default=POStatus.OPEN,
        db_index=True,
        help_text="Incremental fulfillment lifecycle status",
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
    def total_delivered_mt(self):
        """Dynamic sum of delivered quantities across all incremental delivery records."""
        total = self.deliveries.aggregate(total=models.Sum("delivered_mt"))["total"]
        return total if total is not None else Decimal("0")

    @property
    def total_dispatched_mt(self):
        """Dynamic sum of dispatched quantities across all incremental delivery records (falling back to delivered_mt if dispatched_mt is null)."""
        total = Decimal("0")
        for d in self.deliveries.all():
            total += d.effective_dispatched_mt
        return total

    def get_initialized_logistics(self, exclude_delivery_id=None):
        """
        Once an order's delivery logistics (rates, providers, mill, and customer) is initialized
        on its first delivery batch, return that locked configuration so subsequent batches or
        edits cannot alter them.
        """
        qs = self.deliveries.select_related("supplier", "trucking_partner", "barge_partner", "carrier").order_by("created_at")
        if exclude_delivery_id:
            qs = qs.exclude(pk=exclude_delivery_id)
        first_batch = qs.first()
        if not first_batch:
            return {"is_initialized": False}

        po_cust = (self.cluster.client if getattr(self, "cluster", None) and self.cluster.client else None) or self.customer

        return {
            "is_initialized": True,
            "source_delivery_id": str(first_batch.delivery_id),
            "carrier": first_batch.carrier,
            "carrier_id": first_batch.carrier_id,
            "supplier": first_batch.supplier,
            "supplier_id": first_batch.supplier_id,
            "supplier_name": first_batch.supplier.name if first_batch.supplier else "",
            "customer": po_cust,
            "customer_id": po_cust.pk if po_cust else None,
            "customer_name": po_cust.name if po_cust else "",
            "trucking_partner": first_batch.trucking_partner,
            "trucking_partner_id": first_batch.trucking_partner_id,
            "trucking_partner_name": first_batch.trucking_partner.name if first_batch.trucking_partner else "",
            "trucking_rate_per_mt": first_batch.trucking_rate_per_mt or Decimal("0.00"),
            "barge_partner": first_batch.barge_partner,
            "barge_partner_id": first_batch.barge_partner_id,
            "barge_partner_name": first_batch.barge_partner.name if first_batch.barge_partner else "",
            "barge_rate_per_mt": first_batch.barge_rate_per_mt or Decimal("0.00"),
            "vessel_or_barge_name": first_batch.vessel_or_barge_name or "",
            "vessel_or_truck": first_batch.vessel_or_truck or "",
        }

    @property
    def remaining_mt(self):
        """Dynamic remaining contracted quantity: remaining_mt = total_contracted_mt - SUM(delivered_mt)"""
        raw_contracted = self.total_contracted_mt if self.total_contracted_mt is not None else (self.volume_mt or Decimal("0"))
        contracted = Decimal(str(raw_contracted or 0))
        remaining = contracted - self.total_delivered_mt
        return max(remaining, Decimal("0"))

    def update_status(self):
        """Automatically updates po_status based on remaining_mt: Completed when 0, Partially Fulfilled when >0, Open when 0 delivered."""
        raw_contracted = self.total_contracted_mt if self.total_contracted_mt is not None else (self.volume_mt or Decimal("0"))
        contracted = Decimal(str(raw_contracted or 0))
        delivered = self.total_delivered_mt
        remaining = contracted - delivered

        if delivered <= Decimal("0"):
            self.po_status = self.POStatus.OPEN
        elif remaining <= Decimal("0"):
            self.po_status = self.POStatus.COMPLETED
        else:
            self.po_status = self.POStatus.PARTIALLY_FULFILLED
        
        self.save(update_fields=["po_status"])

        if self.po_status == self.POStatus.COMPLETED and self.cluster.status not in [TransactionCluster.Status.DELIVERED, TransactionCluster.Status.CLOSED]:
            self.cluster.status = TransactionCluster.Status.DELIVERED
            self.cluster.save(update_fields=["status", "updated_at"])
        elif self.po_status == self.POStatus.PARTIALLY_FULFILLED and self.cluster.status == TransactionCluster.Status.APPROVED:
            self.cluster.status = TransactionCluster.Status.ACTIVE
            self.cluster.save(update_fields=["status", "updated_at"])

    def save(self, *args, **kwargs):
        if not self.po_reference_number and hasattr(self, "cluster") and self.cluster:
            self.po_reference_number = self.cluster.reference_code
        if self.total_contracted_mt is None and self.volume_mt is not None:
            self.total_contracted_mt = self.volume_mt
        elif self.volume_mt is None and self.total_contracted_mt is not None:
            self.volume_mt = self.total_contracted_mt
        if not self.customer_id and hasattr(self, "cluster") and self.cluster:
            self.customer = self.cluster.client
        super().save(*args, **kwargs)

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
        ref = self.po_reference_number or (self.cluster.reference_code if hasattr(self, "cluster") and self.cluster else str(self.id))
        return f"PO {ref} ({self.total_contracted_mt or self.volume_mt} MT) - {self.po_status}"


class DeliveryLedger(models.Model):
    delivery_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="deliveries",
        help_text="Parent Purchase Order Header FK",
    )
    supplier = models.ForeignKey(
        SugarMill,
        on_delete=models.PROTECT,
        related_name="deliveries",
        help_text="Dynamic Sugar Mill / Supplier sourcing this specific shipment batch",
    )
    dispatched_mt = models.DecimalField(
        "Dispatched MT",
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Volume dispatched from origin sugar mill (MT)",
    )
    delivered_mt = models.DecimalField("Delivered MT", max_digits=14, decimal_places=3)
    receiving_location = models.CharField(
        "Receiving Location",
        max_length=200,
        help_text="Customer delivery drop-off point (e.g. ADI, HTC Tank, Balayan)",
    )
    delivery_date = models.DateField("Delivery Date", default=timezone.localdate)
    dispatched_at = models.DateTimeField(
        "Dispatch Date & Time",
        null=True,
        blank=True,
        help_text="Timestamp when shipment departed origin sugar mill",
    )
    received_at = models.DateTimeField(
        "Received Date & Time",
        null=True,
        blank=True,
        help_text="Timestamp when shipment arrived and was accepted at customer destination",
    )
    carrier = models.ForeignKey(
        LogisticsPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_shipments",
        help_text="Logistics / Carrier Partner (Primary)",
    )
    trucking_partner = models.ForeignKey(
        LogisticsPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_trucking_batches",
        verbose_name="Trucking Partner (Land Transport)",
    )
    trucking_rate_per_mt = models.DecimalField(
        "Trucking Rate (₱/MT)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
    )
    flat_trucking_fee = models.DecimalField(
        "Flat Trucking Fee (₱)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        help_text="Flat batch land transport fee if not charged per MT",
    )
    barge_partner = models.ForeignKey(
        LogisticsPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_barge_batches",
        verbose_name="Barging Partner (Marine Transport)",
    )
    vessel_or_barge_name = models.CharField("Vessel / Barge Name", max_length=100, blank=True, default="")
    barge_rate_per_mt = models.DecimalField(
        "Barging Rate (₱/MT)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
    )
    flat_barge_fee = models.DecimalField(
        "Flat Barging Fee (₱)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        help_text="Flat batch marine transport fee if not charged per MT",
    )
    vessel_or_truck = models.CharField("Vessel ID / Truck Plate", max_length=100, blank=True)
    mro_permit = models.ForeignKey(
        "MolassesReleaseOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
        help_text="Optional linked MRO release order permit fulfilled by this delivery batch",
    )
    dr_number = models.CharField("Delivery Receipt (DR) #", max_length=100, blank=True)
    waybill_number = models.CharField("Waybill #", max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-delivery_date", "-created_at"]
        verbose_name = "Delivery Ledger Entry"
        verbose_name_plural = "Delivery Ledger Entries"

    @property
    def receiving_customer(self):
        """Strictly inherited from parent Purchase Order customer (PO Link Lock)."""
        if self.purchase_order:
            return self.purchase_order.customer or (self.purchase_order.cluster.client if self.purchase_order.cluster else None)
        return None

    @property
    def origin_indicator(self):
        """
        Origin Indicator Attribute: Strictly attached to and determined by the
        Receiving Customer (destination specifications/zone), NOT the sugar mill.
        Sugar Mill source is flexible and unconstrained.
        """
        cust = self.receiving_customer
        if cust:
            return getattr(cust, "origin_indicator", f"{cust.name} Destination Zone")
        if self.receiving_location:
            return f"{self.receiving_location} (Destination Spec)"
        return "Destination Zone Unspecified"

    @property
    def effective_dispatched_mt(self):
        """Returns dispatched_mt if recorded, otherwise falls back to delivered_mt."""
        if self.dispatched_mt is not None and Decimal(str(self.dispatched_mt)) > Decimal("0"):
            return Decimal(str(self.dispatched_mt))
        return Decimal(str(self.delivered_mt or "0"))

    @property
    def volume_discrepancy_mt(self):
        """Difference between Volume Delivered and Volume Dispatched (Delivered - Dispatched)."""
        disp = self.effective_dispatched_mt
        deliv = Decimal(str(self.delivered_mt or "0"))
        return (deliv - disp).quantize(Decimal("0.001"))

    @property
    def abs_variance_mt(self):
        """Absolute volume discrepancy in MT."""
        return abs(self.volume_discrepancy_mt)

    @property
    def variance_percent(self):
        """Percentage discrepancy relative to dispatched volume."""
        disp = self.effective_dispatched_mt
        if disp > Decimal("0"):
            return ((self.abs_variance_mt / disp) * Decimal("100")).quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def variance_exceeds_tolerance(self):
        """True if batch volume discrepancy exceeds VARIANCE_TOLERANCE_PERCENT (default 1.0%)."""
        tolerance = Decimal(str(getattr(settings, "VARIANCE_TOLERANCE_PERCENT", 1.0)))
        return self.variance_percent > tolerance

    @property
    def has_volume_discrepancy(self):
        """True if there is any non-zero difference between dispatched and delivered volume."""
        return self.abs_variance_mt > Decimal("0.000")

    @property
    def trucking_cost(self):
        """Calculated land freight cost for this batch strictly on per-MT basis."""
        vol = self.effective_dispatched_mt
        if vol > Decimal("0") and self.trucking_rate_per_mt:
            return (vol * Decimal(str(self.trucking_rate_per_mt))).quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def barge_cost(self):
        """Calculated marine freight cost for this batch strictly on per-MT basis."""
        vol = self.effective_dispatched_mt
        if vol > Decimal("0") and self.barge_rate_per_mt:
            return (vol * Decimal(str(self.barge_rate_per_mt))).quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def total_freight_cost(self):
        """Total combined logistics cost for this batch."""
        return self.trucking_cost + self.barge_cost

    @property
    def is_future_arrival(self):
        """True if arrival date/time is scheduled in the future (ETA)."""
        if self.received_at:
            return self.received_at > timezone.now()
        return False

    @property
    def scanned_mro_document(self):
        """Returns the scanned MRO permit document covering this delivery batch (shared or direct)."""
        if self.mro_permit and self.mro_permit.scanned_document:
            return self.mro_permit.scanned_document
        if self.purchase_order and self.purchase_order.cluster and self.purchase_order.cluster.mro_file:
            return self.purchase_order.cluster.mro_file
        return None

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError

        if self.trucking_rate_per_mt is None:
            self.trucking_rate_per_mt = Decimal("0.00")
        if self.flat_trucking_fee is None:
            self.flat_trucking_fee = Decimal("0.00")
        if self.barge_rate_per_mt is None:
            self.barge_rate_per_mt = Decimal("0.00")
        if self.flat_barge_fee is None:
            self.flat_barge_fee = Decimal("0.00")
        if self.vessel_or_barge_name is None:
            self.vessel_or_barge_name = ""
        if self.vessel_or_truck is None:
            self.vessel_or_truck = ""
        if self.dr_number is None:
            self.dr_number = ""
        if self.waybill_number is None:
            self.waybill_number = ""
        if self.notes is None:
            self.notes = ""

        if self.dispatched_mt is not None and self.dispatched_mt <= Decimal("0"):
            raise ValidationError({"dispatched_mt": "Dispatched quantity must be greater than 0 MT."})

        # Post-Arrival Volume Input: Restrict delivered_mt so it only diverges from dispatched_mt once arrival is confirmed
        if not self.received_at:
            if self.dispatched_mt is not None and self.dispatched_mt > Decimal("0"):
                self.delivered_mt = self.dispatched_mt
        elif self.delivered_mt is None and self.dispatched_mt is not None:
            self.delivered_mt = self.dispatched_mt
        elif self.dispatched_mt is None and self.delivered_mt is not None:
            self.dispatched_mt = self.delivered_mt

        if self.delivered_mt is not None and self.delivered_mt <= Decimal("0"):
            raise ValidationError({"delivered_mt": "Delivered quantity must be greater than 0 MT."})

        if self.purchase_order_id and self.delivered_mt is not None:
            po = self.purchase_order
            raw_contracted = po.total_contracted_mt if po.total_contracted_mt is not None else (po.volume_mt or Decimal("0"))
            contracted = Decimal(str(raw_contracted or 0))
            
            existing_deliveries = po.deliveries.all()
            if self.pk:
                existing_deliveries = existing_deliveries.exclude(pk=self.pk)
            total_other = existing_deliveries.aggregate(t=models.Sum("delivered_mt"))["t"] or Decimal("0")
            available_balance = max(contracted - total_other, Decimal("0"))

            if self.delivered_mt > available_balance:
                ref = po.po_reference_number or (po.cluster.reference_code if po.cluster else "PO")
                raise ValidationError({
                    "delivered_mt": f"Delivered quantity ({self.delivered_mt:,.3f} MT) exceeds the available remaining balance ({available_balance:,.3f} MT) for PO {ref}."
                })

            # Enforce Rate & Provider Immutability once initialized (Source Sugar Mill is flexible)
            if self.pk:
                orig = DeliveryLedger.objects.filter(pk=self.pk).first()
                if orig:
                    errors = {}
                    if orig.received_at is not None and not getattr(self, "_is_compensating_correction", False):
                        if self.delivered_mt is not None and self.delivered_mt != orig.delivered_mt:
                            errors["delivered_mt"] = f"Delivered volume ({orig.delivered_mt:,.3f} MT) has already been verified upon arrival and is sealed against modification. Use Compensating Adjustment to record an authorized correction."
                        if orig.dispatched_mt is not None and self.dispatched_mt != orig.dispatched_mt:
                            errors["dispatched_mt"] = f"Dispatched volume ({orig.dispatched_mt:,.3f} MT) has already been verified upon arrival and is sealed against modification. Use Compensating Adjustment to record an authorized correction."
                    if orig.trucking_partner_id and self.trucking_partner_id != orig.trucking_partner_id:
                        errors["trucking_partner"] = f"Trucking provider ({orig.trucking_partner.name}) is locked once initialized and cannot be changed."
                    if orig.barge_partner_id and self.barge_partner_id != orig.barge_partner_id:
                        errors["barge_partner"] = f"Barging provider ({orig.barge_partner.name}) is locked once initialized and cannot be changed."
                    if (orig.trucking_rate_per_mt or Decimal("0")) > Decimal("0") and (self.trucking_rate_per_mt or Decimal("0")) != (orig.trucking_rate_per_mt or Decimal("0")):
                        errors["trucking_rate_per_mt"] = f"Trucking rate (₱{orig.trucking_rate_per_mt:,.2f}/MT) is locked once initialized and cannot be changed."
                    if (orig.barge_rate_per_mt or Decimal("0")) > Decimal("0") and (self.barge_rate_per_mt or Decimal("0")) != (orig.barge_rate_per_mt or Decimal("0")):
                        errors["barge_rate_per_mt"] = f"Barging rate (₱{orig.barge_rate_per_mt:,.2f}/MT) is locked once initialized and cannot be changed."
                    if errors:
                        raise ValidationError(errors)

            init_cfg = po.get_initialized_logistics(exclude_delivery_id=self.pk)
            if init_cfg.get("is_initialized"):
                errors = {}
                # Source sugar mill can be flexible after initial delivery; default if not set
                if init_cfg.get("supplier_id") and not self.supplier_id:
                    self.supplier_id = init_cfg["supplier_id"]
                if init_cfg.get("trucking_partner_id"):
                    if not self.trucking_partner_id:
                        self.trucking_partner_id = init_cfg["trucking_partner_id"]
                    elif self.trucking_partner_id != init_cfg["trucking_partner_id"]:
                        errors["trucking_partner"] = f"Trucking provider is locked to {init_cfg['trucking_partner_name']} once initialized for this order."
                if init_cfg.get("barge_partner_id"):
                    if not self.barge_partner_id:
                        self.barge_partner_id = init_cfg["barge_partner_id"]
                    elif self.barge_partner_id != init_cfg["barge_partner_id"]:
                        errors["barge_partner"] = f"Barging provider is locked to {init_cfg['barge_partner_name']} once initialized for this order."
                if init_cfg.get("carrier_id") and not self.carrier_id:
                    self.carrier_id = init_cfg["carrier_id"]

                init_trk_rate = Decimal(str(init_cfg.get("trucking_rate_per_mt") or "0.00"))
                if init_trk_rate > Decimal("0.00"):
                    cur_trk_rate = Decimal(str(self.trucking_rate_per_mt or "0.00"))
                    if cur_trk_rate == Decimal("0.00"):
                        self.trucking_rate_per_mt = init_trk_rate
                    elif cur_trk_rate != init_trk_rate:
                        errors["trucking_rate_per_mt"] = f"Trucking rate is locked at ₱{init_trk_rate:,.2f}/MT once initialized for this order."

                init_brg_rate = Decimal(str(init_cfg.get("barge_rate_per_mt") or "0.00"))
                if init_brg_rate > Decimal("0.00"):
                    cur_brg_rate = Decimal(str(self.barge_rate_per_mt or "0.00"))
                    if cur_brg_rate == Decimal("0.00"):
                        self.barge_rate_per_mt = init_brg_rate
                    elif cur_brg_rate != init_brg_rate:
                        errors["barge_rate_per_mt"] = f"Barging rate is locked at ₱{init_brg_rate:,.2f}/MT once initialized for this order."

                if init_cfg.get("vessel_or_barge_name") and not self.vessel_or_barge_name:
                    self.vessel_or_barge_name = init_cfg["vessel_or_barge_name"]
                if init_cfg.get("vessel_or_truck") and not self.vessel_or_truck:
                    self.vessel_or_truck = init_cfg["vessel_or_truck"]

                if errors:
                    raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            orig = DeliveryLedger.objects.filter(pk=self.pk).only("received_at", "delivered_mt").first()
            if orig and orig.received_at is not None:
                if self.delivered_mt is not None and self.delivered_mt != orig.delivered_mt:
                    from django.core.exceptions import ValidationError
                    raise ValidationError(
                        f"Delivered volume ({orig.delivered_mt:,.3f} MT) is sealed upon arrival and cannot be modified."
                    )
        super().save(*args, **kwargs)

    def sync_cluster_logistics(self):
        """Sync delivery batch logistics timestamps, rates, and dispatched/delivered volumes into the cluster's LogisticsLedger."""
        if not self.purchase_order:
            return
        cluster = getattr(self.purchase_order, "cluster", None)
        if not cluster:
            return
        try:
            logistics = cluster.logistics
        except Exception:
            from django.apps import apps
            LogisticsModel = apps.get_model("operations", "LogisticsLedger")
            logistics = LogisticsModel.objects.create(
                cluster=cluster,
                loaded_volume_mt=self.purchase_order.total_dispatched_mt or self.effective_dispatched_mt or Decimal("0.000"),
            )
        if not logistics:
            return

        po = self.purchase_order
        total_disp = po.total_dispatched_mt
        total_deliv = po.total_delivered_mt

        logistics.loaded_volume_mt = total_disp if total_disp > Decimal("0") else total_deliv
        logistics.received_volume_mt = total_deliv

        deliveries = list(po.deliveries.all())
        total_trucking = sum((d.trucking_cost for d in deliveries), Decimal("0.00"))
        total_barge = sum((d.barge_cost for d in deliveries), Decimal("0.00"))

        logistics.tracking_fees = total_trucking
        logistics.barge_fees = total_barge

        if self.trucking_partner:
            logistics.trucking_partner = self.trucking_partner
        if self.barge_partner:
            logistics.barge_partner = self.barge_partner
        if self.vessel_or_barge_name:
            logistics.vessel_id = self.vessel_or_barge_name

        earliest_dispatch = po.deliveries.filter(dispatched_at__isnull=False).order_by("dispatched_at").first()
        if earliest_dispatch and earliest_dispatch.dispatched_at:
            logistics.loaded_at = earliest_dispatch.dispatched_at

        latest_received = po.deliveries.filter(received_at__isnull=False).order_by("-received_at").first()
        if latest_received and latest_received.received_at:
            logistics.received_at = latest_received.received_at

        logistics._compute_variance()
        any_batch_exceeds = any(d.variance_exceeds_tolerance for d in deliveries)
        if any_batch_exceeds and logistics.dispute_status != LogisticsLedger.DisputeStatus.RESOLVED:
            max_batch_var = max((d.variance_percent for d in deliveries), default=Decimal("0.00"))
            if not logistics.variance_percent or logistics.variance_percent < max_batch_var:
                logistics.variance_percent = max_batch_var
            logistics.variance_exceeds_tolerance = True
            logistics.dispute_status = LogisticsLedger.DisputeStatus.DISPUTED

        logistics.save()

    def sync_delivery_expense_vouchers(self):
        """
        Synchronizes delivery batch fulfillment into Finance:
        Automatically generates or updates pending Cash Vouchers and Payment Expense Matches
        for Trucking, Barging, and Sourcing costs laid out based on costs inputted on the PO and delivery.
        """
        if not self.purchase_order:
            return
        cluster = getattr(self.purchase_order, "cluster", None)
        if not cluster:
            return

        from finance.models import CapitalLoan, CashVoucher, FinancialReconciliation, PaymentExpenseMatch

        reconciliation, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
        active_loans = cluster.loans.filter(status__in=[CapitalLoan.Status.ACTIVE, CapitalLoan.Status.PENDING_CREATION, CapitalLoan.Status.CLOSED])
        linked_loan = active_loans.first() if active_loans.exists() else None
        po = self.purchase_order
        short_id = str(self.delivery_id)[:8].upper()

        # 1. Land Trucking Expense
        trk_ref = f"CV-DEL-{short_id}-TRK"
        if self.trucking_cost > Decimal("0.00"):
            trk_partner = self.trucking_partner.name if self.trucking_partner else "Land Freight"
            trk_rate_info = f"₱{self.trucking_rate_per_mt:,.2f}/MT"
            trk_purpose = f"Truck Delivery Batch #{short_id} ({self.effective_dispatched_mt:,.3f} MT @ {trk_rate_info}) — {trk_partner}"[:200]

            existing_trk_voucher = CashVoucher.objects.filter(voucher_number=trk_ref).first()
            trk_status = existing_trk_voucher.status if existing_trk_voucher and existing_trk_voucher.cheque_number else CashVoucher.Status.PENDING

            CashVoucher.objects.update_or_create(
                voucher_number=trk_ref,
                defaults={
                    "cluster": cluster,
                    "loan": linked_loan,
                    "amount": self.trucking_cost,
                    "purpose": trk_purpose,
                    "status": trk_status,
                    "issued_at": self.delivery_date or timezone.localdate(),
                },
            )
            # Only update amount if a match already exists for this voucher
            existing_trk_match = PaymentExpenseMatch.objects.filter(reconciliation=reconciliation, payment_reference=trk_ref).first()
            if existing_trk_match:
                existing_trk_match.amount = self.trucking_cost
                existing_trk_match.save(update_fields=["amount"])
        else:
            CashVoucher.objects.filter(voucher_number=trk_ref).delete()
            PaymentExpenseMatch.objects.filter(reconciliation=reconciliation, payment_reference=trk_ref).delete()

        # 2. Marine Barging Expense
        brg_ref = f"CV-DEL-{short_id}-BRG"
        if self.barge_cost > Decimal("0.00"):
            brg_partner = self.barge_partner.name if self.barge_partner else (self.vessel_or_barge_name or "Sea Freight")
            brg_rate_info = f"₱{self.barge_rate_per_mt:,.2f}/MT"
            brg_purpose = f"Marine Barging Batch #{short_id} ({self.effective_dispatched_mt:,.3f} MT @ {brg_rate_info}) — {brg_partner}"[:200]

            existing_brg_voucher = CashVoucher.objects.filter(voucher_number=brg_ref).first()
            brg_status = existing_brg_voucher.status if existing_brg_voucher and existing_brg_voucher.cheque_number else CashVoucher.Status.PENDING

            CashVoucher.objects.update_or_create(
                voucher_number=brg_ref,
                defaults={
                    "cluster": cluster,
                    "loan": linked_loan,
                    "amount": self.barge_cost,
                    "purpose": brg_purpose,
                    "status": brg_status,
                    "issued_at": self.delivery_date or timezone.localdate(),
                },
            )
            existing_brg_match = PaymentExpenseMatch.objects.filter(reconciliation=reconciliation, payment_reference=brg_ref).first()
            if existing_brg_match:
                existing_brg_match.amount = self.barge_cost
                existing_brg_match.save(update_fields=["amount"])
        else:
            CashVoucher.objects.filter(voucher_number=brg_ref).delete()
            PaymentExpenseMatch.objects.filter(reconciliation=reconciliation, payment_reference=brg_ref).delete()

        # 3. Sugar Sourcing Outlay (from PO unit_price)
        src_ref = f"CV-DEL-{short_id}-SRC"
        sourcing_cost = Decimal("0.00")
        if po.unit_price and po.unit_price > Decimal("0.00") and self.delivered_mt and self.delivered_mt > Decimal("0.00"):
            sourcing_cost = (Decimal(str(self.delivered_mt)) * Decimal(str(po.unit_price))).quantize(Decimal("0.01"))

        if sourcing_cost > Decimal("0.00"):
            supplier_name = self.supplier.name if self.supplier else "Sugar Mill"
            src_purpose = f"Sugar Sourcing Outlay #{short_id} ({self.delivered_mt:,.3f} MT @ ₱{po.unit_price:,.2f}/MT) — {supplier_name}"[:200]
            CashVoucher.objects.update_or_create(
                voucher_number=src_ref,
                defaults={
                    "cluster": cluster,
                    "loan": linked_loan,
                    "amount": sourcing_cost,
                    "purpose": src_purpose,
                    "status": CashVoucher.Status.PENDING,
                    "issued_at": self.delivery_date or timezone.localdate(),
                },
            )
            existing_src_match = PaymentExpenseMatch.objects.filter(reconciliation=reconciliation, payment_reference=src_ref).first()
            if existing_src_match:
                existing_src_match.amount = sourcing_cost
                existing_src_match.save(update_fields=["amount"])
        else:
            CashVoucher.objects.filter(voucher_number=src_ref).delete()
            PaymentExpenseMatch.objects.filter(reconciliation=reconciliation, payment_reference=src_ref).delete()

        # Update reconciliation total
        reconciliation.matched_payment_amount = (
            reconciliation.matches.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
        )
        reconciliation.save(update_fields=["matched_payment_amount", "updated_at"])

    def save(self, *args, **kwargs):
        if self.trucking_rate_per_mt is None:
            self.trucking_rate_per_mt = Decimal("0.00")
        if self.flat_trucking_fee is None:
            self.flat_trucking_fee = Decimal("0.00")
        if self.barge_rate_per_mt is None:
            self.barge_rate_per_mt = Decimal("0.00")
        if self.flat_barge_fee is None:
            self.flat_barge_fee = Decimal("0.00")
        if self.vessel_or_barge_name is None:
            self.vessel_or_barge_name = ""
        if self.vessel_or_truck is None:
            self.vessel_or_truck = ""
        if self.dr_number is None:
            self.dr_number = ""
        if self.waybill_number is None:
            self.waybill_number = ""
        if self.notes is None:
            self.notes = ""
        self.full_clean()
        super().save(*args, **kwargs)
        self.purchase_order.update_status()
        self.sync_cluster_logistics()
        self.sync_delivery_expense_vouchers()

    def delete(self, *args, **kwargs):
        short_id = str(self.delivery_id)[:8].upper()
        del_prefix = f"CV-DEL-{short_id}-"
        from finance.models import CashVoucher, FinancialReconciliation, PaymentExpenseMatch
        CashVoucher.objects.filter(voucher_number__startswith=del_prefix).delete()
        matches = PaymentExpenseMatch.objects.filter(payment_reference__startswith=del_prefix)
        recon_ids = list(matches.values_list("reconciliation_id", flat=True))
        matches.delete()
        for r_id in set(recon_ids):
            recon = FinancialReconciliation.objects.filter(pk=r_id).first()
            if recon:
                recon.matched_payment_amount = (
                    recon.matches.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
                )
                recon.save(update_fields=["matched_payment_amount", "updated_at"])
        po = self.purchase_order
        super().delete(*args, **kwargs)
        if po:
            po.update_status()

    def __str__(self):
        po_ref = self.purchase_order.po_reference_number if self.purchase_order else "Unknown PO"
        return f"Delivery {self.delivery_id} - {po_ref}: {self.delivered_mt} MT via {self.supplier.name} -> {self.receiving_location}"


class LogisticsLedger(models.Model):
    class DisputeStatus(models.TextChoices):
        NONE = "NONE", "None"
        DISPUTED = "DISPUTED", "Disputed — Over Tolerance"
        RESOLVED = "RESOLVED", "Resolved"

    class ResolutionType(models.TextChoices):
        ABSORBED = "ABSORBED", "Absorb Weight Difference (Adjust Invoice)"
        DISPUTED = "DISPUTED", "Dispute & Let Variance Float"
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
        if self.tracking_fees is None:
            self.tracking_fees = Decimal("0.00")
        if self.barge_fees is None:
            self.barge_fees = Decimal("0.00")
        if self.vessel_id is None:
            self.vessel_id = ""
        if self.resolution_notes is None:
            self.resolution_notes = ""
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
    scanned_file = models.FileField(
        upload_to="mro_scans/",
        null=True,
        blank=True,
        help_text="Optional direct scanned soft copy for this MRO permit if not sharing the cluster's consolidated scan",
    )
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

    @property
    def scanned_document(self):
        """
        Returns the attached scanned soft copy.
        If this MRO entry is part of a multi-MRO consolidated upload for a PO cluster,
        it automatically falls back to the cluster's shared scanned document.
        """
        if self.scanned_file:
            return self.scanned_file
        if self.cluster and self.cluster.mro_file:
            return self.cluster.mro_file
        return None

    @property
    def has_scanned_document(self):
        return bool(self.scanned_document)

    @property
    def is_shared_document(self):
        """Returns True if this MRO relies on the PO cluster's consolidated scanned document."""
        return not bool(self.scanned_file) and bool(self.cluster and self.cluster.mro_file)

    @property
    def shared_mro_count(self):
        """Number of MRO entries sharing this cluster's scanned document."""
        if self.cluster and self.cluster.mro_file:
            return self.cluster.mro_releases.count()
        return 1 if self.scanned_file else 0

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


class MROExtractionJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cluster = models.ForeignKey(
        TransactionCluster,
        on_delete=models.CASCADE,
        related_name="mro_ocr_jobs",
        help_text="Target transaction cluster for MRO linking",
    )
    document = models.FileField(
        upload_to="mro_scans/ocr_uploads/%Y/%m/",
        help_text="Uploaded MRO scan file for extraction",
    )
    file_name = models.CharField(max_length=255, blank=True)
    file_size_bytes = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    average_confidence = models.FloatField(null=True, blank=True)
    extracted_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mro_ocr_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "MRO Extraction Job"
        verbose_name_plural = "MRO Extraction Jobs"

    def __str__(self):
        return f"MRO OCR Job {self.id} ({self.status}) for {self.cluster.reference_code}"




