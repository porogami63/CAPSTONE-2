from decimal import Decimal
from datetime import date

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from operations.models import TransactionCluster


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"

    cluster = models.ForeignKey(TransactionCluster, on_delete=models.CASCADE, related_name="invoices")
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    issued_at = models.DateField(default=date.today)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.invoice_number


class CashVoucher(models.Model):
    cluster = models.ForeignKey(TransactionCluster, on_delete=models.CASCADE, related_name="cash_vouchers")
    voucher_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    purpose = models.CharField(max_length=200)
    cheque_number = models.CharField(max_length=50, blank=True, help_text="Physical paper cheque reference number")
    cheque_date = models.DateField(null=True, blank=True, help_text="Issue date of physical cheque")
    issued_at = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.voucher_number


class CapitalLoan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        OVERDUE = "overdue", "Overdue"

    cluster = models.ForeignKey(TransactionCluster, on_delete=models.CASCADE, related_name="loans")
    bank_name = models.CharField(max_length=120)
    principal = models.DecimalField(max_digits=14, decimal_places=2)
    interest_rate_annual = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        help_text="Annual interest rate as percent (e.g. 12.5 for 12.5%)",
    )
    start_date = models.DateField()
    due_date = models.DateField()
    cheque_number = models.CharField(max_length=50, blank=True, help_text="Physical paper cheque reference number")
    cheque_date = models.DateField(null=True, blank=True, help_text="Issue date of physical cheque")
    bank_account_number = models.CharField(max_length=50, blank=True, help_text="Originating bank account number")
    logistics_deposit_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("50.00"),
        help_text="Percentage of upfront logistics deposit funded (Default 50%)",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    settlement_receipt_number = models.CharField(max_length=100, blank=True, help_text="Bank Release Advice / Official Receipt Number")
    settlement_date = models.DateField(null=True, blank=True, help_text="Date facility was officially settled")
    settlement_document = models.FileField(upload_to="loan_settlements/", null=True, blank=True, help_text="Scanned soft copy of Bank Release Clearance Advice / Receipt")
    settlement_notes = models.TextField(blank=True, help_text="Notes on final loan settlement")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    @property
    def days_outstanding(self):
        end = date.today()
        if self.status == self.Status.CLOSED:
            end = min(self.due_date, date.today())
        return max((end - self.start_date).days, 0)

    @property
    def daily_interest_cost(self):
        daily_rate = (self.interest_rate_annual / Decimal("100")) / Decimal("365")
        return (self.principal * daily_rate).quantize(Decimal("0.01"))

    @property
    def accrued_interest(self):
        daily_rate = (self.interest_rate_annual / Decimal("100")) / Decimal("365")
        return (self.principal * daily_rate * Decimal(self.days_outstanding)).quantize(Decimal("0.01"))

    @property
    def total_liability(self):
        return self.principal + self.accrued_interest

    @property
    def funded_logistics_deposit(self):
        logistics = getattr(self.cluster, "logistics", None)
        if logistics:
            total_logistics_fee = (logistics.tracking_fees or Decimal("0")) + (logistics.barge_fees or Decimal("0"))
            if total_logistics_fee > Decimal("0"):
                return (total_logistics_fee * (self.logistics_deposit_percentage / Decimal("100"))).quantize(Decimal("0.01"))
            # Fallback to standard 50% calculation based on loaded volume or estimate
            estimated_deposit = (logistics.loaded_volume_mt * Decimal("450.00") * (self.logistics_deposit_percentage / Decimal("100")))
            return estimated_deposit.quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def is_overdue(self):
        return self.status == self.Status.ACTIVE and date.today() > self.due_date

    def refresh_status(self):
        if self.status != self.Status.CLOSED and date.today() > self.due_date:
            self.status = self.Status.OVERDUE
        return self.status

    def __str__(self):
        return f"{self.bank_name} - {self.cluster.reference_code}"


class FinancialReconciliation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINALIZED = "finalized", "Finalized"

    cluster = models.OneToOneField(
        TransactionCluster,
        on_delete=models.CASCADE,
        related_name="reconciliation",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    matched_payment_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reconciliation {self.cluster.reference_code}"


class PaymentExpenseMatch(models.Model):
    class ExpenseType(models.TextChoices):
        SOURCING = "sourcing", "Sourcing"
        TRACKING = "tracking", "Tracking Fees"
        BARGE = "barge", "Barge Fees"
        LOGISTICS_DEPOSIT = "logistics_deposit", "50% Logistics Deposit"
        OTHER = "other", "Other"

    reconciliation = models.ForeignKey(
        FinancialReconciliation,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    payment_reference = models.CharField(max_length=100)
    expense_type = models.CharField(max_length=30, choices=ExpenseType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    matched_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-matched_at"]

    def __str__(self):
        return f"{self.payment_reference} -> {self.get_expense_type_display()}"
