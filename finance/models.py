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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
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
    def accrued_interest(self):
        daily_rate = (self.interest_rate_annual / Decimal("100")) / Decimal("365")
        return (self.principal * daily_rate * Decimal(self.days_outstanding)).quantize(Decimal("0.01"))

    @property
    def total_liability(self):
        return self.principal + self.accrued_interest

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
