import csv
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User
from finance.forms import CapitalLoanForm, CashVoucherForm, InvoiceForm
from finance.models import CapitalLoan, CashVoucher, FinancialReconciliation, Invoice
from django.http import HttpResponse
from masters.models import LogisticsPartner, Planter

from .forms import ExcelImportForm, LogisticsUpdateForm, TransactionClusterForm, MolassesReleaseOrderForm, MROExcelImportForm
from .models import LogisticsLedger, PurchaseOrder, TransactionCluster, MolassesReleaseOrder, normalize_crop_year
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
    show_archived = request.GET.get("archived", "").lower() in ("1", "true")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    client_id = request.GET.get("client", "").strip()
    mill_id = request.GET.get("mill", "").strip()
    sort_by = request.GET.get("sort", "newest").strip()

    clusters_qs = (
        TransactionCluster.objects.filter(is_archived=show_archived)
        .select_related("client", "sugar_mill", "logistics", "logistics__partner")
        .prefetch_related("invoices", "purchase_order")
    )

    if q:
        clusters_qs = clusters_qs.filter(
            Q(reference_code__icontains=q) |
            Q(client__name__icontains=q) |
            Q(sugar_mill__name__icontains=q)
        )
    if status:
        clusters_qs = clusters_qs.filter(status=status)
    if client_id:
        clusters_qs = clusters_qs.filter(client_id=client_id)
    if mill_id:
        clusters_qs = clusters_qs.filter(sugar_mill_id=mill_id)

    if sort_by == "oldest":
        clusters_qs = clusters_qs.order_by("created_at")
    else:
        clusters_qs = clusters_qs.order_by("-created_at")

    clusters = list(clusters_qs)

    from masters.models import Client, SugarMill
    clients_list = list(Client.objects.filter(is_active=True).order_by("name"))
    mills_list = list(SugarMill.objects.filter(is_active=True).order_by("name"))

    total_volume = 0.0
    combined_profit = 0.0
    total_revenue = 0.0
    total_profit = 0.0
    total_transactions = len(clusters)

    for c in clusters:
        invs = list(c.invoices.all())
        c.primary_invoice = invs[0] if invs else None
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
        total_revenue += fin["revenue"]
        total_profit += fin["profit"]

    if sort_by == "highest_profit":
        clusters.sort(key=lambda x: x.profit, reverse=True)
    elif sort_by == "highest_volume":
        clusters.sort(key=lambda x: x.vol_mt, reverse=True)

    avg_margin = round((total_profit / total_revenue) * 100, 1) if total_revenue > 0 else 0.0

    context = {
        "clusters": clusters,
        "total_volume": total_volume,
        "combined_profit": combined_profit,
        "avg_margin": avg_margin,
        "total_transactions": total_transactions,
        "status_choices": TransactionCluster.Status.choices,
        "clients_list": clients_list,
        "mills_list": mills_list,
        "current_status": status,
        "current_client": client_id,
        "current_mill": mill_id,
        "current_sort": sort_by,
        "q": q,
    }
    return render(request, "operations/cluster_list.html", context)


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
    User.Role.INVOICING,
)
def logistics_list(request):
    show_archived = request.GET.get("archived", "").lower() in ("1", "true")
    q = request.GET.get("q", "").strip()
    partner_id = request.GET.get("partner", "").strip()
    status_filter = request.GET.get("status", "").strip()

    ledgers_qs = LogisticsLedger.objects.filter(is_archived=show_archived).select_related("cluster", "cluster__client", "partner").order_by("-updated_at")

    if q:
        ledgers_qs = ledgers_qs.filter(
            Q(cluster__reference_code__icontains=q) |
            Q(cluster__client__name__icontains=q) |
            Q(vessel_id__icontains=q) |
            Q(partner__name__icontains=q)
        )
    if partner_id:
        ledgers_qs = ledgers_qs.filter(partner_id=partner_id)

    ledgers = list(ledgers_qs)

    in_transit_count = 0
    delivered_count = 0
    accepted_count = 0
    pending_review_count = 0
    disputed_count = 0

    shipments = []
    for log in ledgers:
        # Run variance calculations for each ledger on page load to ensure data accuracy
        log._compute_variance()
        
        status = "loading"
        sh_status_display = "Loading"
        
        if log.cluster.status == TransactionCluster.Status.DRAFT:
            status = "loading"
            sh_status_display = "Loading"
            in_transit_count += 1
        elif log.cluster.status == TransactionCluster.Status.ACTIVE:
            status = "transit"
            sh_status_display = "In Transit"
            in_transit_count += 1
        elif log.cluster.status == TransactionCluster.Status.DELIVERED:
            if log.variance_exceeds_tolerance:
                status = "disputed"
                sh_status_display = "Disputed — Over Tolerance"
                disputed_count += 1
            elif log.variance_percent and log.variance_percent > 0:
                status = "pending_review"
                sh_status_display = "Pending Review — In Tolerance"
                pending_review_count += 1
                delivered_count += 1
            else:
                status = "delivered"
                sh_status_display = "Delivered — No Loss"
                delivered_count += 1
                accepted_count += 1
        elif log.cluster.status == TransactionCluster.Status.CLOSED:
            status = "accepted"
            sh_status_display = "Accepted"
            accepted_count += 1
            delivered_count += 1

        # Shrinkage
        shrinkage_mt = 0.0
        shrinkage_pct = 0.0
        if log.loaded_volume_mt and log.received_volume_mt is not None:
            shrinkage_mt = float(log.loaded_volume_mt - log.received_volume_mt)
            if float(log.loaded_volume_mt) > 0:
                shrinkage_pct = (shrinkage_mt / float(log.loaded_volume_mt)) * 100.0

        # Progress bar percent (how much loaded is received)
        prog_pct = 0
        if log.loaded_volume_mt > 0:
            if log.received_volume_mt is not None:
                prog_pct = int((float(log.received_volume_mt) / float(log.loaded_volume_mt)) * 100.0)
            else:
                prog_pct = 0

        # Headroom/over-limit
        headroom = max(2.0 - shrinkage_pct, 0.0)
        over_limit = max(shrinkage_pct - 2.0, 0.0)

        item = {
            "ledger": log,
            "sh_code": "SH-" + log.cluster.reference_code.split("-").pop(),
            "ref_code": log.cluster.reference_code,
            "customer": log.cluster.client.name,
            "partner_name": log.partner.name if log.partner else "—",
            "vessel_id": log.vessel_id or "—",
            "status": status,
            "sh_status_display": sh_status_display,
            "loaded_mt": float(log.loaded_volume_mt),
            "received_mt": float(log.received_volume_mt) if log.received_volume_mt is not None else "Pending",
            "shrinkage_mt": shrinkage_mt,
            "shrinkage_pct": shrinkage_pct,
            "prog_pct": prog_pct,
            "headroom": headroom,
            "over_limit": over_limit,
            "pk": log.cluster.pk,
        }

        # Apply status_filter if specified
        if status_filter:
            if status_filter == "transit" and status not in ("loading", "transit"):
                continue
            elif status_filter == "pending_review" and status != "pending_review":
                continue
            elif status_filter == "disputed" and status != "disputed":
                continue
            elif status_filter == "accepted" and status not in ("accepted", "delivered"):
                continue

        shipments.append(item)

    transit_shipments = [s for s in shipments if s["status"] in ("loading", "transit")]
    pending_shipments = [s for s in shipments if s["status"] == "pending_review"]
    disputed_shipments = [s for s in shipments if s["status"] == "disputed"]
    accepted_shipments = [s for s in shipments if s["status"] in ("accepted", "delivered")]

    available_partners = LogisticsPartner.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "operations/logistics_list.html",
        {
            "shipments": shipments,
            "transit_shipments": transit_shipments,
            "pending_shipments": pending_shipments,
            "disputed_shipments": disputed_shipments,
            "accepted_shipments": accepted_shipments,
            "in_transit_count": in_transit_count,
            "delivered_count": delivered_count,
            "accepted_count": accepted_count,
            "pending_review_count": pending_review_count,
            "disputed_count": disputed_count,
            "tolerance_threshold": settings.VARIANCE_TOLERANCE_PERCENT,
            "available_partners": available_partners,
            "current_q": q,
            "current_partner": partner_id,
            "current_status": status_filter,
        },
    )


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
    User.Role.INVOICING,
)
def export_logistics_csv(request):
    show_archived = request.GET.get("archived", "").lower() in ("1", "true")
    q = request.GET.get("q", "").strip()
    partner_id = request.GET.get("partner", "").strip()

    ledgers_qs = LogisticsLedger.objects.filter(is_archived=show_archived).select_related("cluster", "cluster__client", "partner").order_by("-updated_at")

    if q:
        ledgers_qs = ledgers_qs.filter(
            Q(cluster__reference_code__icontains=q) |
            Q(cluster__client__name__icontains=q) |
            Q(vessel_id__icontains=q) |
            Q(partner__name__icontains=q)
        )
    if partner_id:
        ledgers_qs = ledgers_qs.filter(partner_id=partner_id)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="HTC_Logistics_Master_Ledger.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Shipment Code",
        "Contract Reference PO",
        "Customer / Client",
        "Logistics Partner",
        "Vessel ID / Trip",
        "Loaded Volume (MT)",
        "Received Volume (MT)",
        "Shrinkage (MT)",
        "Shrinkage (%)",
        "Variance Exceeded",
        "Cluster Status",
        "Last Updated",
    ])

    for log in ledgers_qs:
        log._compute_variance()
        shrinkage_mt = 0.0
        shrinkage_pct = 0.0
        if log.loaded_volume_mt and log.received_volume_mt is not None:
            shrinkage_mt = float(log.loaded_volume_mt - log.received_volume_mt)
            if float(log.loaded_volume_mt) > 0:
                shrinkage_pct = (shrinkage_mt / float(log.loaded_volume_mt)) * 100.0

        sh_code = "SH-" + log.cluster.reference_code.split("-").pop()
        writer.writerow([
            sh_code,
            log.cluster.reference_code,
            log.cluster.client.name,
            log.partner.name if log.partner else "—",
            log.vessel_id or "—",
            float(log.loaded_volume_mt),
            float(log.received_volume_mt) if log.received_volume_mt is not None else "Pending",
            round(shrinkage_mt, 2),
            round(shrinkage_pct, 2),
            "YES" if log.variance_exceeds_tolerance else "NO",
            log.cluster.get_status_display(),
            log.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        ])

    return response


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
        return redirect("dashboard:home")
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
                    selling_price=form.cleaned_data.get("selling_price"),
                    terms=form.cleaned_data.get("terms", ""),
                    brix_level=form.cleaned_data.get("brix_level"),
                    chai_specs=form.cleaned_data.get("chai_specs", ""),
                    approved_at=timezone.now(),
                )
                default_partner = LogisticsPartner.objects.filter(is_active=True).first()
                vol = form.cleaned_data["volume_mt"]
                est_trucking_rate = form.cleaned_data.get("est_trucking_rate") or Decimal("0")
                est_barge_rate = form.cleaned_data.get("est_barge_rate") or Decimal("0")
                tracking_fee = vol * est_trucking_rate
                barge_fee = vol * est_barge_rate
                if default_partner:
                    LogisticsLedger.objects.create(
                        cluster=cluster,
                        partner=default_partner,
                        loaded_volume_mt=vol,
                        tracking_fees=tracking_fee,
                        barge_fees=barge_fee,
                    )
                FinancialReconciliation.objects.create(cluster=cluster)
            messages.success(request, f"Transaction cluster {cluster.reference_code} created.")
            return redirect("operations:cluster_detail", pk=cluster.pk)
    else:
        form = TransactionClusterForm()
    return render(request, "operations/cluster_form.html", {"form": form, "title": "New Transaction"})


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def cluster_edit(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST":
        form = TransactionClusterForm(request.POST, instance=cluster)
        if form.is_valid():
            with transaction.atomic():
                cluster = form.save()
                po = getattr(cluster, "purchase_order", None)
                if po:
                    po.volume_mt = form.cleaned_data["volume_mt"]
                    po.unit_price = form.cleaned_data["unit_price"]
                    po.selling_price = form.cleaned_data.get("selling_price")
                    po.terms = form.cleaned_data.get("terms", "")
                    po.brix_level = form.cleaned_data.get("brix_level")
                    po.chai_specs = form.cleaned_data.get("chai_specs", "")
                    po.save()
                log = getattr(cluster, "logistics", None)
                if log:
                    vol = form.cleaned_data["volume_mt"]
                    est_trucking_rate = form.cleaned_data.get("est_trucking_rate")
                    est_barge_rate = form.cleaned_data.get("est_barge_rate")
                    if est_trucking_rate is not None:
                        log.tracking_fees = vol * est_trucking_rate
                    if est_barge_rate is not None:
                        log.barge_fees = vol * est_barge_rate
                    log.loaded_volume_mt = vol
                    log.save()
            messages.success(request, f"Updated contract parameters for {cluster.reference_code}.")
            return redirect("operations:cluster_detail", pk=cluster.pk)
    else:
        form = TransactionClusterForm(instance=cluster)
    return render(request, "operations/cluster_form.html", {"form": form, "object": cluster, "title": f"Edit {cluster.reference_code}"})


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
    loan_form = CapitalLoanForm(user=request.user)

    # Collect Audit Trail
    audit_events = []
    
    for h in cluster.history.all():
        audit_events.append({"date": h.history_date, "user": h.history_user, "type": h.history_type, "model": "Transaction Cluster", "desc": f"Status: {h.status}"})
        
    if hasattr(cluster, 'logistics'):
        for h in cluster.logistics.history.all():
            audit_events.append({"date": h.history_date, "user": h.history_user, "type": h.history_type, "model": "Logistics", "desc": f"Loaded: {h.loaded_volume_mt}, Received: {h.received_volume_mt}"})
            
    if hasattr(cluster, 'purchase_order'):
        for h in cluster.purchase_order.history.all():
            audit_events.append({"date": h.history_date, "user": h.history_user, "type": h.history_type, "model": "Purchase Order", "desc": f"Vol: {h.volume_mt} MT @ P{h.unit_price}"})

    for inv in cluster.invoices.all():
        for h in inv.history.all():
            audit_events.append({"date": h.history_date, "user": h.history_user, "type": h.history_type, "model": f"Invoice {h.invoice_number}", "desc": f"Status: {h.status}, Amount: {h.amount}"})

    for v in cluster.cash_vouchers.all():
        for h in v.history.all():
            audit_events.append({"date": h.history_date, "user": h.history_user, "type": h.history_type, "model": f"Voucher {h.voucher_number}", "desc": f"Amount: {h.amount}"})

    audit_events.sort(key=lambda x: x["date"], reverse=True)
    debrief = cluster_financials(cluster)

    return render(
        request,
        "operations/cluster_detail.html",
        {
            "cluster": cluster,
            "logistics_form": logistics_form,
            "invoice_form": invoice_form,
            "voucher_form": voucher_form,
            "loan_form": loan_form,
            "audit_events": audit_events,
            "debrief": debrief,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def update_logistics(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    logistics = get_object_or_404(LogisticsLedger, cluster=cluster)
    if request.method == "POST":
        form = LogisticsUpdateForm(request.POST, request.FILES, instance=logistics)
        if form.is_valid():
            form.save()
            logistics._compute_variance()
            if logistics.variance_exceeds_tolerance:
                messages.warning(
                    request,
                    f"Variance alert: {logistics.variance_percent:.2f}% exceeds 1% tolerance.",
                )
                from audit.services import notify_roles
                notify_roles(
                    [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.MANAGEMENT],
                    title=f"Shrinkage Tolerance Alert — {cluster.reference_code}",
                    message=f"Receiving volume for {cluster.reference_code} incurred a variance of {logistics.variance_percent:.2f}%. Dispute flag active.",
                    level="danger",
                    link=f"/operations/{cluster.pk}/",
                    exclude_user=request.user,
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
        # Enforce prerequisite: Cluster must have a linked Capital Loan Facility
        active_loans = cluster.loans.filter(status__in=[CapitalLoan.Status.ACTIVE, CapitalLoan.Status.CLOSED, CapitalLoan.Status.PENDING_CREATION])
        if not active_loans.exists():
            messages.error(
                request,
                f"Prerequisite Error: Cash Vouchers / Outlays CANNOT be issued for deal {cluster.reference_code} until a Capital Loan Facility is created and linked.",
            )
            return redirect("operations:cluster_detail", pk=pk)

        form = CashVoucherForm(request.POST)
        if form.is_valid():
            voucher = form.save(commit=False)
            voucher.cluster = cluster
            voucher.loan = active_loans.first()
            voucher._audit_user = request.user
            voucher.save()
            messages.success(request, f"Cash voucher {voucher.voucher_number} recorded and linked to facility.")
        else:
            messages.error(request, "Error issuing cash voucher. Please check your inputs.")
    return redirect("operations:cluster_detail", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def add_loan(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST":
        form = CapitalLoanForm(request.POST, user=request.user)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.cluster = cluster
            loan._audit_user = request.user

            # If user is authorized (Admin / Ops Mgmt) and explicitly selected ACTIVE, verify immediately.
            # Otherwise, force PENDING_CREATION for verification workflow.
            from accounts.permissions import user_has_perm
            if user_has_perm(request.user, "verify_loan") and form.cleaned_data.get("status") == CapitalLoan.Status.ACTIVE:
                loan.status = CapitalLoan.Status.ACTIVE
                loan.verified_by = request.user
                loan.verified_at = timezone.now()
                loan.verification_notes = "Pre-approved active facility on creation."
            else:
                loan.status = CapitalLoan.Status.PENDING_CREATION

            loan.save()

            from chat.views import send_system_notification
            from audit.services import notify_roles
            if loan.status == CapitalLoan.Status.PENDING_CREATION:
                send_system_notification(
                    cluster,
                    f"Capital loan facility ₱{loan.principal:,.2f} from {loan.bank_name} logged by {request.user.get_full_name() or request.user.username}. Pending Operations/Admin verification.",
                    sender_user=request.user,
                )
                notify_roles(
                    [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT],
                    title=f"New Loan Facility Pending Approval — {loan.bank_name}",
                    message=f"A ₱{loan.principal:,.2f} loan facility for {cluster.reference_code} requires verification.",
                    level="warning",
                    link="/finance/loans/",
                    exclude_user=request.user,
                )
                messages.success(request, f"Capital loan facility from {loan.bank_name} recorded and submitted for VERIFICATION.")
            else:
                send_system_notification(
                    cluster,
                    f"Capital loan facility ₱{loan.principal:,.2f} from {loan.bank_name} logged as ACTIVE by {request.user.get_full_name() or request.user.username}.",
                    sender_user=request.user,
                )
                messages.success(request, f"Capital loan facility from {loan.bank_name} recorded as ACTIVE facility.")
        else:
            messages.error(request, f"Failed to record loan facility: {form.errors.as_text()}")
    return redirect("operations:cluster_detail", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.INVOICING, User.Role.FINANCE)
def update_invoice_status(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in Invoice.Status.values:
            invoice.status = new_status
            invoice._audit_user = request.user
            invoice.save(update_fields=["status"])
            messages.success(
                request,
                f"Invoice {invoice.invoice_number} status updated to {invoice.get_status_display()}.",
            )
    return redirect("operations:cluster_detail", pk=invoice.cluster.pk)


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def resolve_dispute(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    logistics = get_object_or_404(LogisticsLedger, cluster=cluster)

    if request.method == "POST":
        res_type = request.POST.get("resolution_type")
        notes = request.POST.get("resolution_notes", "").strip()

        if res_type in LogisticsLedger.ResolutionType.values:
            logistics.dispute_status = LogisticsLedger.DisputeStatus.RESOLVED
            logistics.resolution_type = res_type
            logistics.resolution_notes = notes
            logistics.variance_exceeds_tolerance = False
            logistics._audit_user = request.user
            logistics.save()

            # Execute financial adjustments based on choice
            if res_type == LogisticsLedger.ResolutionType.BILLING_ADJUSTED:
                if hasattr(cluster, "purchase_order") and logistics.received_volume_mt:
                    new_val = Decimal(str(logistics.received_volume_mt)) * Decimal(str(cluster.purchase_order.unit_price))
                    for inv in cluster.invoices.all():
                        inv.amount = new_val
                        inv._audit_user = request.user
                        inv.save(update_fields=["amount"])
                    messages.success(request, f"Dispute resolved: Invoices adjusted to received volume value (₱{new_val:,.2f}).")
                else:
                    messages.success(request, "Dispute resolved: Invoices set for billing adjustment.")
            elif res_type == LogisticsLedger.ResolutionType.BARGE_PENALTY:
                if hasattr(cluster, "purchase_order") and logistics.loaded_volume_mt and logistics.received_volume_mt:
                    shortage_mt = Decimal(str(logistics.loaded_volume_mt)) - Decimal(str(logistics.received_volume_mt))
                    penalty_val = shortage_mt * Decimal(str(cluster.purchase_order.unit_price))
                    logistics.barge_fees = max(Decimal("0"), Decimal(str(logistics.barge_fees)) - penalty_val)
                    logistics.save(update_fields=["barge_fees"])
                    messages.success(request, f"Dispute resolved: ₱{penalty_val:,.2f} shortage penalty applied.")
                else:
                    messages.success(request, "Dispute resolved: Shortage penalty applied.")
            elif res_type == LogisticsLedger.ResolutionType.CONCEDED:
                messages.success(request, "Dispute resolved: Conceded variance and proceeding with deal as-is.")
            elif res_type == LogisticsLedger.ResolutionType.WAIVED:
                messages.success(request, "Dispute resolved: Management waiver approved for brix / evaporation loss.")

            cluster.status = TransactionCluster.Status.DELIVERED
            cluster._audit_user = request.user
            cluster.save(update_fields=["status", "updated_at"])

    next_url = request.META.get("HTTP_REFERER")
    if next_url and "/operations/" in next_url:
        return redirect(next_url)
    return redirect("operations:cluster_detail", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def archive_cluster(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST":
        now = timezone.now()
        cluster.is_archived = True
        cluster.archived_at = now
        cluster._audit_user = request.user
        cluster.save(update_fields=["is_archived", "archived_at"])

        # Also archive associated invoices and logistics
        cluster.invoices.update(is_archived=True, archived_at=now)
        if hasattr(cluster, "logistics"):
            cluster.logistics.is_archived = True
            cluster.logistics.archived_at = now
            cluster.logistics.save(update_fields=["is_archived", "archived_at"])

        messages.success(request, f"Transaction cluster {cluster.reference_code} has been archived.")
    return redirect("operations:cluster_list")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def unarchive_cluster(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST":
        cluster.is_archived = False
        cluster.archived_at = None
        cluster._audit_user = request.user
        cluster.save(update_fields=["is_archived", "archived_at"])

        cluster.invoices.update(is_archived=False, archived_at=None)
        if hasattr(cluster, "logistics"):
            cluster.logistics.is_archived = False
            cluster.logistics.archived_at = None
            cluster.logistics.save(update_fields=["is_archived", "archived_at"])

        messages.success(request, f"Transaction cluster {cluster.reference_code} restored to active list.")
    return redirect("operations:archive_list")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def bulk_archive_completed(request):
    if request.method == "POST":
        now = timezone.now()
        completed_clusters = TransactionCluster.objects.filter(
            is_archived=False,
            status__in=[TransactionCluster.Status.CLOSED, TransactionCluster.Status.DELIVERED],
        )
        count = 0
        for cluster in completed_clusters:
            # Check if invoices are paid
            invoices = cluster.invoices.all()
            all_paid = all(inv.status == Invoice.Status.PAID for inv in invoices) if invoices else True
            if cluster.status == TransactionCluster.Status.CLOSED or all_paid:
                cluster.is_archived = True
                cluster.archived_at = now
                cluster.save(update_fields=["is_archived", "archived_at"])
                cluster.invoices.update(is_archived=True, archived_at=now)
                if hasattr(cluster, "logistics"):
                    cluster.logistics.is_archived = True
                    cluster.logistics.archived_at = now
                    cluster.logistics.save(update_fields=["is_archived", "archived_at"])
                count += 1

        messages.success(request, f"Archived {count} completed transactions, invoices, and logistics records.")
    return redirect("operations:cluster_list")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def archive_list(request):
    q = request.GET.get("q", "").strip()
    archived_clusters = (
        TransactionCluster.objects.filter(is_archived=True)
        .select_related("client", "sugar_mill", "logistics", "logistics__partner")
        .prefetch_related("invoices", "purchase_order")
        .order_by("-archived_at")
    )
    if q:
        archived_clusters = archived_clusters.filter(
            Q(reference_code__icontains=q) |
            Q(client__name__icontains=q) |
            Q(sugar_mill__name__icontains=q)
        )

    archived_invoices = Invoice.objects.filter(is_archived=True).select_related("cluster", "cluster__client")
    archived_logistics = LogisticsLedger.objects.filter(is_archived=True).select_related("cluster", "cluster__client")

    context = {
        "archived_clusters": archived_clusters,
        "archived_invoices": archived_invoices,
        "archived_logistics": archived_logistics,
        "q": q,
        "total_archived_count": len(archived_clusters),
    }
    return render(request, "operations/archive_list.html", context)


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def upload_mro(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    if request.method == "POST" and request.FILES.get("mro_file"):
        cluster.mro_file = request.FILES["mro_file"]
        cluster._audit_user = request.user
        cluster.save(update_fields=["mro_file"])
        messages.success(request, f"Scanned MRO document uploaded for {cluster.reference_code}.")
    else:
        messages.error(request, "Please select a valid PDF or scanned document to upload.")
    
    redirect_url = request.META.get("HTTP_REFERER")
    if redirect_url:
        return redirect(redirect_url)
    return redirect("operations:cluster_detail", pk=pk)


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS_MANAGER,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
    User.Role.INVOICING,
)
def mro_summary_view(request):
    crop_year_filter = request.GET.get("crop_year", "").strip()
    planter_filter = request.GET.get("planter", "").strip()
    mill_filter = request.GET.get("mill", "").strip()
    q = request.GET.get("q", "").strip()

    mro_qs = MolassesReleaseOrder.objects.select_related("planter", "sugar_mill", "cluster").all()

    # Get available filter dropdown options
    available_crop_years = (
        MolassesReleaseOrder.objects.values_list("crop_year", flat=True)
        .distinct()
        .order_by("-crop_year")
    )
    available_planters = Planter.objects.filter(mro_releases__isnull=False).distinct()
    available_mills = (
        MolassesReleaseOrder.objects.exclude(sugar_mill_name="")
        .values_list("sugar_mill_name", flat=True)
        .distinct()
        .order_by("sugar_mill_name")
    )

    if crop_year_filter:
        norm_cy = normalize_crop_year(crop_year_filter)
        mro_qs = mro_qs.filter(Q(crop_year=crop_year_filter) | Q(crop_year=norm_cy))

    if planter_filter:
        mro_qs = mro_qs.filter(planter_id=planter_filter)

    if mill_filter:
        mro_qs = mro_qs.filter(Q(sugar_mill_name__iexact=mill_filter) | Q(sugar_mill__name__icontains=mill_filter))

    if q:
        mro_qs = mro_qs.filter(
            Q(mro_number__icontains=q) |
            Q(planter__name__icontains=q) |
            Q(trader__icontains=q) |
            Q(crop_year__icontains=q) |
            Q(sugar_mill_name__icontains=q)
        )

    # Compute metric KPIs
    total_tons = mro_qs.aggregate(total=Sum("tons"))["total"] or Decimal("0")
    total_mro_count = mro_qs.values("mro_number").distinct().count()
    distinct_mills_count = mro_qs.values("sugar_mill_name").distinct().count()
    item_count = mro_qs.count()

    # Calculate subtotal per MRO + Supplier + Crop Year group to reproduce column G "TOTAL" in the Excel sheet
    mro_subtotals = {}
    for item in mro_qs:
        key = (item.mro_number, item.sugar_mill_name, item.crop_year)
        mro_subtotals[key] = mro_subtotals.get(key, Decimal("0")) + item.tons

    # Decorate items with group subtotal indicators
    grouped_items = []
    mro_group_items = {}

    for item in mro_qs:
        key = (item.mro_number, item.sugar_mill_name, item.crop_year)
        if key not in mro_group_items:
            mro_group_items[key] = []
        mro_group_items[key].append(item)

    # Build flat list with group totals attached
    for key, items in mro_group_items.items():
        group_subtotal = mro_subtotals[key]
        for idx, item in enumerate(items):
            is_last = (idx == len(items) - 1)
            grouped_items.append({
                "item": item,
                "is_last_in_mro": is_last,
                "mro_group_subtotal": group_subtotal if is_last else None,
                "rowspan": len(items) if idx == 0 else 0,
            })

    create_form = MolassesReleaseOrderForm(initial={"trader": "HEINDRICH", "crop_year": crop_year_filter or "2024 - 25", "sugar_mill_name": mill_filter or "BUSCO"})
    import_form = MROExcelImportForm(initial={"crop_year_override": crop_year_filter or "2024 - 25"})

    context = {
        "grouped_items": grouped_items,
        "total_tons": total_tons,
        "total_mro_count": total_mro_count,
        "distinct_mills_count": distinct_mills_count,
        "item_count": item_count,
        "available_crop_years": available_crop_years,
        "available_planters": available_planters,
        "available_mills": available_mills,
        "current_crop_year": crop_year_filter,
        "current_planter": planter_filter,
        "current_mill": mill_filter,
        "q": q,
        "create_form": create_form,
        "import_form": import_form,
    }
    return render(request, "operations/mro_summary.html", context)


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.OPERATIONS)
def mro_create_view(request):
    if request.method == "POST":
        form = MolassesReleaseOrderForm(request.POST)
        if form.is_valid():
            mro = form.save()
            messages.success(request, f"MRO Release Order entry #{mro.mro_number} ({mro.display_sugar_mill}) saved successfully.")
            return redirect("operations:mro_summary")
        else:
            messages.error(request, "Error saving MRO entry. Please check the form values.")
    return redirect("operations:mro_summary")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.OPERATIONS)
def mro_edit_view(request, pk):
    mro = get_object_or_404(MolassesReleaseOrder, pk=pk)
    if request.method == "POST":
        form = MolassesReleaseOrderForm(request.POST, instance=mro)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated MRO #{mro.mro_number} ({mro.display_sugar_mill}).")
            return redirect("operations:mro_summary")
        else:
            messages.error(request, "Error updating MRO entry.")
    return redirect("operations:mro_summary")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.OPERATIONS)
def mro_delete_view(request, pk):
    mro = get_object_or_404(MolassesReleaseOrder, pk=pk)
    mro_num = mro.mro_number
    planter_name = mro.planter.name
    mro.delete()
    messages.success(request, f"Deleted MRO item #{mro_num} ({planter_name}).")
    return redirect("operations:mro_summary")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.OPERATIONS)
def mro_import_excel_view(request):
    if request.method == "POST":
        form = MROExcelImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            crop_override = form.cleaned_data.get("crop_year_override", "").strip() or "2024 - 25"

            from .services.mro_import import import_mro_workbook
            try:
                created, updated = import_mro_workbook(file, default_crop_year=crop_override)
                messages.success(request, f"Successfully imported MRO data across supplier sheets! ({created} created, {updated} updated)")
            except Exception as e:
                messages.error(request, f"Error importing MRO spreadsheet: {str(e)}")

    return redirect("operations:mro_summary")


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS_MANAGER,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
    User.Role.INVOICING,
)
def mro_export_csv_view(request):
    crop_year_filter = request.GET.get("crop_year", "").strip()
    planter_filter = request.GET.get("planter", "").strip()
    mill_filter = request.GET.get("mill", "").strip()
    q = request.GET.get("q", "").strip()

    mro_qs = MolassesReleaseOrder.objects.select_related("planter", "sugar_mill").all()
    if crop_year_filter:
        norm_cy = normalize_crop_year(crop_year_filter)
        mro_qs = mro_qs.filter(Q(crop_year=crop_year_filter) | Q(crop_year=norm_cy))
    if planter_filter:
        mro_qs = mro_qs.filter(planter_id=planter_filter)
    if mill_filter:
        mro_qs = mro_qs.filter(Q(sugar_mill_name__iexact=mill_filter) | Q(sugar_mill__name__icontains=mill_filter))
    if q:
        mro_qs = mro_qs.filter(
            Q(mro_number__icontains=q) |
            Q(planter__name__icontains=q) |
            Q(trader__icontains=q) |
            Q(sugar_mill_name__icontains=q)
        )

    import csv
    response = HttpResponse(content_type="text/csv")
    filename = f"MRO_Release_Summary_{mill_filter or 'All_Suppliers'}_{crop_year_filter or 'All'}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["SUPPLIER / MILL", "PLANTERS", "TONS", "DATE", "TRADER", "MRO #", "CROP YEAR"])

    for item in mro_qs:
        writer.writerow([
            item.display_sugar_mill,
            item.planter.name,
            f"{item.tons:.5f}",
            item.release_date.strftime("%m/%d/%Y") if item.release_date else "",
            item.trader,
            item.mro_number,
            item.crop_year,
        ])

    return response





