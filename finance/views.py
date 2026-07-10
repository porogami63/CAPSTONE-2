from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from accounts.models import User
from operations.models import TransactionCluster

from .forms import PaymentExpenseMatchForm
from .models import CapitalLoan, FinancialReconciliation, Invoice, PaymentExpenseMatch


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def reconciliation_detail(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    reconciliation, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
    form = PaymentExpenseMatchForm()
    total_matched = reconciliation.matches.aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "finance/reconciliation.html",
        {
            "cluster": cluster,
            "reconciliation": reconciliation,
            "form": form,
            "total_matched": total_matched,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def add_match(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    reconciliation, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
    if request.method == "POST":
        form = PaymentExpenseMatchForm(request.POST)
        if form.is_valid():
            match = form.save(commit=False)
            match.reconciliation = reconciliation
            match._audit_user = request.user
            match.save()
            reconciliation.matched_payment_amount = (
                reconciliation.matches.aggregate(total=Sum("amount"))["total"] or 0
            )
            reconciliation._audit_user = request.user
            reconciliation.save()
            messages.success(request, "Payment matched to expense.")
    return redirect("finance:reconciliation", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def loan_list(request):
    loans = CapitalLoan.objects.select_related("cluster", "cluster__client")
    for loan in loans:
        loan.refresh_status()
        loan.save(update_fields=["status"])

    active_loans = []
    active_exposure = 0
    accrued_interest = 0
    overdue_facilities = 0

    for loan in loans:
        active_loans.append(loan)
        if loan.status == loan.Status.ACTIVE:
            active_exposure += loan.principal
        accrued_interest += loan.accrued_interest
        if loan.is_overdue or loan.status == loan.Status.OVERDUE:
            overdue_facilities += 1

        total_days = max((loan.due_date - loan.start_date).days, 1)
        elapsed_days = max((timezone.localdate() - loan.start_date).days, 0)
        loan.timeline_percent = min(max((elapsed_days / total_days) * 100, 8), 100)
        loan.days_remaining = max((loan.due_date - timezone.localdate()).days, 0)

    logistics_deposits = (
        PaymentExpenseMatch.objects.filter(
            expense_type=PaymentExpenseMatch.ExpenseType.LOGISTICS_DEPOSIT,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    return render(
        request,
        "finance/loan_list.html",
        {
            "loans": active_loans,
            "active_exposure": active_exposure,
            "accrued_interest": accrued_interest,
            "logistics_deposits": logistics_deposits,
            "overdue_facilities": overdue_facilities,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING)
def invoice_list(request):
    invoice_rows = list(
        Invoice.objects.select_related("cluster", "cluster__client", "cluster__sugar_mill").order_by("-issued_at", "-created_at")
    )

    today = timezone.localdate()
    total_invoiced = 0
    paid_invoices = 0
    pending_invoices = 0
    overdue_invoices = 0

    for invoice in invoice_rows:
        total_invoiced += invoice.amount
        if invoice.status == Invoice.Status.PAID:
            paid_invoices += 1
        else:
            pending_invoices += 1
            if (today - invoice.issued_at).days >= 14:
                overdue_invoices += 1

        invoice.status_badge = {
            Invoice.Status.DRAFT: "draft",
            Invoice.Status.ISSUED: "active",
            Invoice.Status.PAID: "delivered",
        }.get(invoice.status, "draft")
        invoice.days_open = max((today - invoice.issued_at).days, 0)
        invoice.payable_state = "Paid" if invoice.status == Invoice.Status.PAID else "Pending Payable"

    sales_invoices = invoice_rows
    supplier_invoices = [invoice for invoice in invoice_rows if invoice.status != Invoice.Status.PAID] or invoice_rows

    return render(
        request,
        "finance/invoice_list.html",
        {
            "invoices": invoice_rows,
            "sales_invoices": sales_invoices,
            "supplier_invoices": supplier_invoices,
            "total_invoiced": total_invoiced,
            "paid_invoices": paid_invoices,
            "pending_invoices": pending_invoices,
            "overdue_invoices": overdue_invoices,
        },
    )
