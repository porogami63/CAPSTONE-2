from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User
from finance.forms import CapitalLoanForm, CashVoucherForm, InvoiceForm
from finance.models import CapitalLoan, CashVoucher, FinancialReconciliation, Invoice
from masters.models import LogisticsPartner

from .forms import ExcelImportForm, LogisticsUpdateForm, TransactionClusterForm
from .models import LogisticsLedger, PurchaseOrder, TransactionCluster
from .services.excel_import import (
    clear_operational_data,
    import_htc_summary,
    parse_excel_to_preview,
    commit_staged_data,
)
from .services.pricing import cluster_financials


from django.db.models import Q

@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
    User.Role.INVOICING,
)
def cluster_list(request):
    clusters_qs = (
        TransactionCluster.objects.select_related("client", "sugar_mill", "logistics", "logistics__partner")
        .prefetch_related("invoices", "purchase_order")
        .order_by("reference_code")
    )

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if q:
        clusters_qs = clusters_qs.filter(
            Q(reference_code__icontains=q) |
            Q(client__name__icontains=q) |
            Q(sugar_mill__name__icontains=q)
        )
    if status:
        clusters_qs = clusters_qs.filter(status=status)

    clusters = list(clusters_qs)

    total_volume = 0.0
    combined_profit = 0.0
    margin_total = 0.0
    total_transactions = len(clusters)

    for c in clusters:
        c.primary_invoice = c.invoices.first()
        c.purchase_order = getattr(c, "purchase_order", None)
        c.logistics_record = getattr(c, "logistics", None)
        c.partner_name = c.logistics_record.partner.name if c.logistics_record else "—"
        c.received_volume = (
            c.logistics_record.received_volume_mt
            if c.logistics_record and c.logistics_record.received_volume_mt is not None
            else None
        )
        c.variance_text = "—"
        if c.logistics_record and c.logistics_record.variance_percent is not None:
            c.variance_text = f"{c.logistics_record.variance_percent:.2f}%"
        c.notes = c.contract_notes or "No contract notes recorded."

        fin = cluster_financials(c)
        c.vol_mt = fin["volume_mt"]
        c.purchase_price = fin["purchase_price"]
        c.selling_price = fin["selling_price"]
        c.profit = fin["profit"]
        c.profit_m = fin["profit_m"]
        c.margin = fin["margin"]
        c.order_value = fin["order_value"]
        c.revenue = fin["revenue"]
        c.logistics_cost = fin["logistics_cost"]
        c.invoice_number = fin["invoice_number"] or "—"

        c.timeline_progress = 22
        if c.status == TransactionCluster.Status.ACTIVE:
            c.timeline_progress = 48
        elif c.status == TransactionCluster.Status.DELIVERED:
            c.timeline_progress = 74
        elif c.status == TransactionCluster.Status.CLOSED:
            c.timeline_progress = 100

        combined_profit += fin["profit_m"]
        total_volume += fin["volume_mt"]
        margin_total += fin["margin"]

    avg_margin = round(margin_total / total_transactions, 1) if total_transactions else 0.0

    context = {
        "clusters": clusters,
        "total_volume": total_volume,
        "combined_profit": combined_profit,
        "avg_margin": avg_margin,
        "total_transactions": total_transactions,
        "status_choices": TransactionCluster.Status.choices,
        "current_status": status,
        "q": q,
    }
    return render(request, "operations/cluster_list.html", context)


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS, User.Role.FINANCE, User.Role.INVOICING)
def logistics_list(request):
    records = list(
        LogisticsLedger.objects.select_related("cluster", "cluster__client", "cluster__sugar_mill", "partner")
        .order_by("-updated_at", "-loaded_at")
    )

    in_transit = 0
    delivered = 0
    accepted = 0
    pending_review = 0
    disputed = 0

    for record in records:
        loaded = record.loaded_volume_mt or 0
        received = record.received_volume_mt if record.received_volume_mt is not None else 0
        if record.variance_exceeds_tolerance:
            record.lifecycle_state = "Disputed"
            record.lifecycle_class = "alert"
            disputed += 1
        elif not record.loaded_at:
            record.lifecycle_state = "Pending Review"
            record.lifecycle_class = "draft"
            pending_review += 1
        elif not record.received_at:
            record.lifecycle_state = "In Transit"
            record.lifecycle_class = "active"
            in_transit += 1
        elif record.received_volume_mt is not None and loaded > 0 and received >= loaded * 0.995:
            record.lifecycle_state = "Accepted"
            record.lifecycle_class = "delivered"
            accepted += 1
        else:
            record.lifecycle_state = "Delivered"
            record.lifecycle_class = "delivered"
            delivered += 1

        if loaded > 0 and record.received_volume_mt is not None:
            record.progress_percent = min((float(received) / float(loaded)) * 100, 100)
        elif record.loaded_at:
            record.progress_percent = 58
        else:
            record.progress_percent = 12

        record.variance_text = "—"
        if record.variance_percent is not None:
            record.variance_text = f"{record.variance_percent:.2f}%"

    lifecycle_steps = [
        {"label": "Booked", "icon": "bi-file-earmark-text"},
        {"label": "In Transit", "icon": "bi-truck"},
        {"label": "Delivered", "icon": "bi-check2-circle"},
        {"label": "Accepted", "icon": "bi-patch-check"},
        {"label": "Disputed", "icon": "bi-exclamation-triangle"},
    ]

    return render(
        request,
        "operations/logistics_list.html",
        {
            "records": records,
            "in_transit": in_transit,
            "delivered": delivered,
            "accepted": accepted,
            "pending_review": pending_review,
            "disputed": disputed,
            "lifecycle_steps": lifecycle_steps,
        },
    )


@role_required(User.Role.MANAGEMENT)
def import_excel(request):
    preview_mode = False
    summary = None
    staged_rows = None

    if request.method == "POST":
        if "confirm_commit" in request.POST:
            staged_rows = request.session.get("staged_import_data")
            replace_existing = request.session.get("staged_replace_existing", False)
            if staged_rows:
                with transaction.atomic():
                    if replace_existing:
                        clear_operational_data()
                    imported, skipped = commit_staged_data(staged_rows)

                request.session.pop("staged_import_data", None)
                request.session.pop("staged_import_summary", None)
                request.session.pop("staged_replace_existing", None)

                messages.success(
                    request,
                    f"Import completed successfully. {imported} transactions imported, {skipped} skipped.",
                )
                return redirect("operations:cluster_list")
            else:
                messages.error(request, "No staged data found. Please upload the file again.")
                return redirect("operations:import_excel")
        elif "cancel_import" in request.POST:
            request.session.pop("staged_import_data", None)
            request.session.pop("staged_import_summary", None)
            request.session.pop("staged_replace_existing", None)
            messages.info(request, "Import cancelled.")
            return redirect("operations:import_excel")
        else:
            form = ExcelImportForm(request.POST, request.FILES)
            if form.is_valid():
                workbook = form.cleaned_data["workbook"]
                if hasattr(workbook, "seek"):
                    workbook.seek(0)

                res = parse_excel_to_preview(workbook)
                request.session["staged_import_data"] = res["rows"]
                request.session["staged_import_summary"] = res["summary"]
                request.session["staged_replace_existing"] = form.cleaned_data["replace_existing"]

                preview_mode = True
                summary = res["summary"]
                staged_rows = res["rows"]
    else:
        form = ExcelImportForm()
        request.session.pop("staged_import_data", None)
        request.session.pop("staged_import_summary", None)
        request.session.pop("staged_replace_existing", None)

    return render(
        request,
        "operations/import_excel.html",
        {
            "form": form,
            "preview_mode": preview_mode,
            "summary": summary,
            "staged_rows": staged_rows,
        },
    )


@role_required(User.Role.MANAGEMENT)
def clear_database_view(request):
    if request.method == "POST":
        clear_operational_data()
        messages.success(request, "Database cleared successfully. All transactions and related records have been deleted.")
        return redirect("operations:cluster_list")
    return render(request, "operations/clear_database_confirm.html")


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
