import json
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User
from finance.models import CapitalLoan, CashVoucher, FinancialReconciliation, Invoice
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster

from .services.analytics import build_supplier_rankings
from .services.documents import build_document_registry


def _format_millions(value):
    """Format a numeric value as millions string (e.g. '₱46.00M')."""
    m = float(value) / 1_000_000.0
    return f"₱{m:,.2f}M"


def _format_currency(value):
    """Format a numeric value as currency string (e.g. '₱1,100,000')."""
    return f"₱{float(value):,.0f}"


@role_required(
    User.Role.MANAGEMENT,
    User.Role.FINANCE,
    User.Role.OPERATIONS,
    User.Role.INVOICING,
)
def home(request):
    # ── Core cluster metrics ─────────────────────────────────────────────
    open_clusters = TransactionCluster.objects.exclude(status=TransactionCluster.Status.CLOSED).count()
    total_transactions = TransactionCluster.objects.count()
    draft_count = TransactionCluster.objects.filter(status=TransactionCluster.Status.DRAFT).count()

    # ── Variance alerts ──────────────────────────────────────────────────
    variance_alerts = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True).select_related(
        "cluster", "cluster__client"
    )[:10]
    variance_alert_count = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True).count()

    # ── Financial reconciliation ─────────────────────────────────────────
    unmatched = FinancialReconciliation.objects.filter(status=FinancialReconciliation.Status.DRAFT).count()

    # ── Invoice aggregations ─────────────────────────────────────────────
    unpaid_invoices = Invoice.objects.exclude(status=Invoice.Status.PAID).count()
    total_invoices = Invoice.objects.count()
    total_receivables = Invoice.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    paid_receivables = Invoice.objects.filter(status=Invoice.Status.PAID).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    pending_receivables = total_receivables - paid_receivables

    # ── Volume & Cluster Financials ─────────────────────────────────────
    total_volume = LogisticsLedger.objects.aggregate(total=Sum("loaded_volume_mt"))["total"] or Decimal("0")

    from operations.services.pricing import cluster_financials

    total_revenue = Decimal("0")
    total_expenses = Decimal("0")

    clusters_all = list(
        TransactionCluster.objects.select_related("client", "sugar_mill", "purchase_order", "logistics")
        .prefetch_related("invoices")
        .all()
    )

    for cluster in clusters_all:
        fin = cluster_financials(cluster)
        total_revenue += Decimal(str(fin["revenue"]))
        total_expenses += Decimal(str(fin["purchase_total"])) + Decimal(str(fin["logistics_cost"]))

    net_profit = total_revenue - total_expenses

    # ── Delivery Status ──────────────────────────────────────────────────
    delivered_clusters = TransactionCluster.objects.filter(
        status__in=[TransactionCluster.Status.DELIVERED, TransactionCluster.Status.CLOSED]
    ).count()
    active_clusters = TransactionCluster.objects.exclude(
        status=TransactionCluster.Status.CLOSED
    ).count()

    # ── Loan exposure & verification queue ──────────────────────────────
    active_loans = CapitalLoan.objects.filter(status=CapitalLoan.Status.ACTIVE)
    overdue_loans = CapitalLoan.objects.filter(status=CapitalLoan.Status.OVERDUE).count()
    pending_verification_loans_count = CapitalLoan.objects.filter(
        status__in=[CapitalLoan.Status.PENDING_CREATION, CapitalLoan.Status.PENDING_SETTLEMENT]
    ).count()
    total_loan_exposure = active_loans.aggregate(total=Sum("principal"))["total"] or Decimal("0")

    # ── Monthly chart data ───────────────────────────────────────────────
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    revenue_by_month = defaultdict(float)
    expense_by_month = defaultdict(float)

    for cluster in clusters_all:
        fin = cluster_financials(cluster)
        po = getattr(cluster, "purchase_order", None)
        invs = list(cluster.invoices.all()) if hasattr(cluster, "invoices") else []
        primary_inv = invs[0] if invs else None

        if primary_inv and primary_inv.issued_at:
            m_idx = primary_inv.issued_at.month - 1
        elif po and po.approved_at:
            m_idx = po.approved_at.month - 1
        else:
            m_idx = cluster.created_at.month - 1

        revenue_by_month[m_idx] += float(fin["revenue"])
        expense_by_month[m_idx] += float(fin["purchase_total"] + fin["logistics_cost"])

    # Determine which months have data
    all_months_with_data = sorted(set(list(revenue_by_month.keys()) + list(expense_by_month.keys())))
    if all_months_with_data:
        chart_months = [month_labels[i] for i in all_months_with_data]
        revenue_data = [round(revenue_by_month[i] / 1_000_000, 2) for i in all_months_with_data]
        expenses_data = [round(expense_by_month[i] / 1_000_000, 2) for i in all_months_with_data]
        profit_data = [round(revenue_by_month[i] / 1_000_000 - expense_by_month[i] / 1_000_000, 2) for i in all_months_with_data]
    else:
        chart_months = month_labels[:6]
        revenue_data = [0] * 6
        expenses_data = [0] * 6
        profit_data = [0] * 6

    # ── Weekly cash flow (from recent invoices and vouchers) ──────────────
    now = timezone.now()
    weekly_labels = ["W1", "W2", "W3", "W4"]
    inflow_data = [0, 0, 0, 0]
    outflow_data = [0, 0, 0, 0]

    # Inflows: paid invoices in the current month
    current_month_invoices = Invoice.objects.filter(
        issued_at__year=now.year,
        issued_at__month=now.month,
    )
    for inv in current_month_invoices:
        week_idx = min((inv.issued_at.day - 1) // 7, 3)
        inflow_data[week_idx] += round(float(inv.amount) / 1_000_000, 2)

    # Outflows: cash vouchers in the current month
    current_month_vouchers = CashVoucher.objects.filter(
        issued_at__year=now.year,
        issued_at__month=now.month,
    )
    for v in current_month_vouchers:
        week_idx = min((v.issued_at.day - 1) // 7, 3)
        outflow_data[week_idx] += round(float(v.amount) / 1_000_000, 2)

    net_cash_flow = sum(inflow_data) - sum(outflow_data)
    net_cash_flow_raw = float(total_revenue - total_expenses)
    net_cash_flow_str = _format_currency(net_cash_flow_raw) if total_transactions > 0 else "₱0"

    # ── Recent clusters ──────────────────────────────────────────────────
    recent_clusters = (
        TransactionCluster.objects.select_related("client", "sugar_mill", "logistics")
        .prefetch_related("invoices")
        .order_by("-created_at")[:12]
    )
    for cluster in recent_clusters:
        invs = list(cluster.invoices.all())
        cluster.primary_invoice = invs[0] if invs else None

    # ── Last sync timestamp ──────────────────────────────────────────────
    latest_cluster = TransactionCluster.objects.order_by("-updated_at").first()
    last_sync = latest_cluster.updated_at if latest_cluster else None

    # ── Formatted display values ─────────────────────────────────────────
    revenue_display = _format_millions(total_revenue)
    expenses_display = _format_millions(total_expenses)
    profit_display = _format_millions(net_profit)
    pending_display = _format_millions(pending_receivables)

    # ── Role-Specific Custom Metrics & Queues ─────────────────────────────
    user_role = request.user.role if hasattr(request.user, "role") and request.user.role else "administrator"
    role_override = request.GET.get("role") or request.GET.get("view_as")
    if role_override in [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING]:
        user_role = role_override

    # Operations role metrics
    active_shipments_count = LogisticsLedger.objects.filter(
        cluster__status__in=[TransactionCluster.Status.ACTIVE, TransactionCluster.Status.DRAFT]
    ).count()
    disputed_shortages_count = variance_alert_count
    
    from operations.models import MolassesReleaseOrder
    mro_mill_balances = []
    for mill_name in ["BUSCO", "HAWAIIAN", "BISCOM", "CASA", "LOPEZ"]:
        tons_sum = MolassesReleaseOrder.objects.filter(
            Q(sugar_mill_name__icontains=mill_name) | Q(sugar_mill__name__icontains=mill_name)
        ).aggregate(total=Sum("tons"))["total"] or Decimal("0")
        mro_mill_balances.append({"name": mill_name, "tons": float(tons_sum)})

    # Finance role metrics
    vouchers_count = CashVoucher.objects.count()
    vouchers_total = CashVoucher.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    vouchers_display = _format_millions(vouchers_total)
    loans_total_display = _format_millions(total_loan_exposure)
    recent_loans = CapitalLoan.objects.select_related("cluster").order_by("-created_at")[:5]

    # Invoicing role metrics
    draft_invoices_count = Invoice.objects.filter(status=Invoice.Status.DRAFT).count()
    issued_invoices_count = Invoice.objects.filter(status=Invoice.Status.ISSUED).count()
    overdue_invoices_count = unpaid_invoices
    pending_invoices_list = Invoice.objects.exclude(status=Invoice.Status.PAID).select_related("cluster", "cluster__client").order_by("-issued_at")[:8]

    return render(
        request,
        "dashboard/home.html",
        {
            # Role-scoped access flags
            "is_executive": request.user.role in [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, "administrator", "operations_management"] or request.user.is_superuser,
            "is_operations": request.user.role in [User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS, "operations_management"],
            "is_finance": request.user.role in [User.Role.FINANCE, User.Role.INVOICING, "finance", "invoicing"],
            # Core & Status card values
            "user_role": user_role,
            "open_clusters": open_clusters,
            "total_transactions": total_transactions,
            "draft_count": draft_count,
            "variance_alerts": variance_alerts,
            "variance_alert_count": variance_alert_count,
            "unmatched_reconciliations": unmatched,
            "unpaid_invoices": unpaid_invoices,
            "total_invoices": total_invoices,
            "total_receivables": total_receivables,
            "total_volume_mt": total_volume,
            "recent_clusters": recent_clusters,
            # Formatted card display strings
            "revenue_display": revenue_display,
            "expenses_display": expenses_display,
            "profit_display": profit_display,
            "pending_display": pending_display,
            "overdue_loans": overdue_loans,
            # Delivery stats
            "delivered_clusters": delivered_clusters,
            "active_clusters": active_clusters,
            # Operations specific
            "active_shipments_count": active_shipments_count,
            "disputed_shortages_count": disputed_shortages_count,
            "mro_mill_balances": mro_mill_balances,
            # Finance specific
            "vouchers_count": vouchers_count,
            "vouchers_display": vouchers_display,
            "overdue_loans": overdue_loans,
            "pending_verification_loans_count": pending_verification_loans_count,
            "total_loan_exposure": total_loan_exposure,
            "total_loan_exposure_fmt": _format_millions(total_loan_exposure),
            "loans_total_display": loans_total_display,
            "recent_loans": recent_loans,
            # Invoicing specific
            "draft_invoices_count": draft_invoices_count,
            "unpaid_invoices": unpaid_invoices,
            "issued_invoices_count": issued_invoices_count,
            "overdue_invoices_count": overdue_invoices_count,
            "pending_invoices_list": pending_invoices_list,
            # Chart data (JSON-safe)
            "chart_months_json": json.dumps(chart_months),
            "revenue_data_json": json.dumps(revenue_data),
            "expenses_data_json": json.dumps(expenses_data),
            "profit_data_json": json.dumps(profit_data),
            "weekly_labels_json": json.dumps(weekly_labels),
            "inflow_data_json": json.dumps(inflow_data),
            "outflow_data_json": json.dumps(outflow_data),
            "net_cash_flow_str": net_cash_flow_str,
            # Last sync
            "last_sync": last_sync,
            # Is empty flag for empty state
            "is_empty": total_transactions == 0,
        },
    )


@role_required(
    User.Role.MANAGEMENT,
    User.Role.FINANCE,
    User.Role.OPERATIONS,
)
def analytics(request):
    try:
        order_qty = float(request.GET.get("qty", "500"))
    except ValueError:
        order_qty = 500.0
    try:
        selling_price = float(request.GET.get("price", "18500"))
    except ValueError:
        selling_price = 18500.0

    engine = build_supplier_rankings(order_qty, selling_price)

    # Historical Logistics & Shrinkage Trends
    mill_shrinkage = []
    from masters.models import SugarMill, Client
    for mill in SugarMill.objects.filter(is_active=True):
        ledgers = LogisticsLedger.objects.filter(cluster__sugar_mill=mill, variance_percent__isnull=False)
        avg_var = ledgers.aggregate(v=Avg("variance_percent"))["v"] or 0.0
        disputed_cnt = ledgers.filter(variance_exceeds_tolerance=True).count()
        mill_shrinkage.append({
            "name": mill.name,
            "avg_variance": round(float(avg_var), 2),
            "disputed_count": disputed_cnt,
        })

    # Client Revenue Distribution
    client_revenues = []
    for client in Client.objects.filter(is_active=True):
        rev = Invoice.objects.filter(cluster__client=client).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        if rev > 0:
            client_revenues.append({
                "name": client.name,
                "revenue": float(rev),
                "revenue_m": round(float(rev) / 1_000_000, 2),
            })

    return render(
        request,
        "dashboard/analytics.html",
        {
            "engine": engine,
            "order_qty": order_qty,
            "selling_price": selling_price,
            "mill_shrinkage": mill_shrinkage,
            "client_revenues": client_revenues,
            "mill_shrinkage_json": json.dumps(mill_shrinkage),
            "client_revenues_json": json.dumps(client_revenues),
        },
    )


@role_required(
    User.Role.MANAGEMENT,
    User.Role.FINANCE,
    User.Role.OPERATIONS,
    User.Role.INVOICING,
)
def documents(request):
    query = request.GET.get("q", "").strip()
    registry = build_document_registry(query)
    registry = build_document_registry(query)
    return render(request, "dashboard/documents.html", registry)

from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.FINANCE)
def download_consolidated_report(request, period):
    now = timezone.now()
    if period == 'day':
        start_date = now - timedelta(days=1)
    elif period == 'week':
        start_date = now - timedelta(weeks=1)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    elif period == 'year':
        start_date = now - timedelta(days=365)
    else:
        start_date = now - timedelta(days=3650) # All time
        period = 'all time'

    clusters = TransactionCluster.objects.filter(created_at__gte=start_date)
    logistics = LogisticsLedger.objects.filter(cluster__created_at__gte=start_date)
    invoices = Invoice.objects.filter(issued_at__gte=start_date.date())
    
    total_transactions = clusters.count()
    total_volume = logistics.aggregate(total=Sum("loaded_volume_mt"))["total"] or Decimal("0")
    total_revenue = invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    
    # Calculate approximate expenses (Logistics tracking + PO) for net profit
    total_tracking = logistics.aggregate(t=Sum("tracking_fees"))["t"] or Decimal("0")
    po_total = PurchaseOrder.objects.filter(cluster__created_at__gte=start_date).aggregate(t=Sum("volume_mt"))["t"] or Decimal("0")
    total_procurement = Decimal("0")
    for po in PurchaseOrder.objects.filter(cluster__created_at__gte=start_date):
        total_procurement += po.volume_mt * po.unit_price
    
    net_profit = total_revenue - (total_procurement + total_tracking)

    context = {
        'period': period,
        'total_transactions': total_transactions,
        'total_revenue': total_revenue,
        'total_volume': total_volume,
        'net_profit': net_profit,
        'clusters': clusters,
        'logistics': logistics,
        'invoices': invoices,
    }
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Consolidated_Report_{period}.pdf"'
    
    template = get_template('dashboard/report_pdf.html')
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
       
    if pisa_status.err:
       return HttpResponse('We had some errors generating the PDF.')
    return response
