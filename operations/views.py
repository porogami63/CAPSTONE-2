from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User
from finance.forms import CapitalLoanForm, CashVoucherForm, InvoiceForm
from finance.models import CapitalLoan, CashVoucher, FinancialReconciliation, Invoice
from masters.models import LogisticsPartner

from .forms import LogisticsUpdateForm, TransactionClusterForm
from .models import LogisticsLedger, PurchaseOrder, TransactionCluster


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
    User.Role.INVOICING,
)
def cluster_list(request):
    clusters = (
        TransactionCluster.objects.select_related("client", "sugar_mill", "logistics", "logistics__partner")
        .prefetch_related("invoices")
        .order_by("reference_code")
    )
    for c in clusters:
        c.primary_invoice = c.invoices.first()
    return render(request, "operations/cluster_list.html", {"clusters": clusters})


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def cluster_create(request):
    if request.method == "POST":
        form = TransactionClusterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                cluster = form.save()
                PurchaseOrder.objects.create(
                    cluster=cluster,
                    volume_mt=form.cleaned_data["volume_mt"],
                    unit_price=form.cleaned_data["unit_price"],
                    terms=form.cleaned_data.get("terms", ""),
                    approved_at=timezone.now(),
                )
                default_partner = LogisticsPartner.objects.filter(is_active=True).first()
                if default_partner:
                    LogisticsLedger.objects.create(
                        cluster=cluster,
                        partner=default_partner,
                        loaded_volume_mt=form.cleaned_data["volume_mt"],
                    )
                FinancialReconciliation.objects.create(cluster=cluster)
            messages.success(request, f"Transaction cluster {cluster.reference_code} created.")
            return redirect("operations:cluster_detail", pk=cluster.pk)
    else:
        form = TransactionClusterForm()
    return render(request, "operations/cluster_form.html", {"form": form, "title": "New Transaction"})


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
    User.Role.INVOICING,
)
def cluster_detail(request, pk):
    cluster = get_object_or_404(
        TransactionCluster.objects.select_related(
            "client",
            "sugar_mill",
            "purchase_order",
            "logistics",
            "logistics__partner",
            "reconciliation",
        ).prefetch_related("invoices", "cash_vouchers", "loans", "reconciliation__matches"),
        pk=pk,
    )
    logistics_form = LogisticsUpdateForm(instance=getattr(cluster, "logistics", None))
    invoice_form = InvoiceForm()
    voucher_form = CashVoucherForm()
    loan_form = CapitalLoanForm()
    return render(
        request,
        "operations/cluster_detail.html",
        {
            "cluster": cluster,
            "logistics_form": logistics_form,
            "invoice_form": invoice_form,
            "voucher_form": voucher_form,
            "loan_form": loan_form,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def update_logistics(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    logistics = get_object_or_404(LogisticsLedger, cluster=cluster)
    if request.method == "POST":
        form = LogisticsUpdateForm(request.POST, instance=logistics)
        if form.is_valid():
            form.save()
            logistics._compute_variance()
            if logistics.variance_exceeds_tolerance:
                messages.warning(
                    request,
                    f"Variance alert: {logistics.variance_percent:.2f}% exceeds 1% tolerance.",
                )
            else:
                messages.success(request, "Logistics updated.")
            cluster.status = TransactionCluster.Status.DELIVERED
            cluster.save(update_fields=["status", "updated_at"])
    return redirect("operations:cluster_detail", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.INVOICING, User.Role.FINANCE)
def add_invoice(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST":
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.cluster = cluster
            invoice._audit_user = request.user
            invoice.save()
            messages.success(request, f"Invoice {invoice.invoice_number} recorded.")
    return redirect("operations:cluster_detail", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def add_voucher(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST":
        form = CashVoucherForm(request.POST)
        if form.is_valid():
            voucher = form.save(commit=False)
            voucher.cluster = cluster
            voucher._audit_user = request.user
            voucher.save()
            messages.success(request, f"Cash voucher {voucher.voucher_number} recorded.")
    return redirect("operations:cluster_detail", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def add_loan(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST":
        form = CapitalLoanForm(request.POST)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.cluster = cluster
            loan._audit_user = request.user
            loan.save()
            messages.success(request, f"Capital loan from {loan.bank_name} recorded.")
    return redirect("operations:cluster_detail", pk=pk)
