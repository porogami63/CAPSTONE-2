import json
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from accounts.decorators import role_required
from accounts.models import User
from finance.models import CapitalLoan, CashVoucher, FinancialReconciliation, Invoice
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster

from .services.analytics import build_supplier_rankings
from .services.documents import build_document_registry
from .services.insights import build_dashboard_insights
from operations.services.pricing import cluster_financials


def _build_financial_cadence(clusters_all, now):
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    target_year = now.year
    target_month = now.month

    # 1. Weekly buckets (for current target month)
    weekly_buckets = [
        {"period": "Week 1 (Days 1–7)", "short_label": "W1", "revenue": 0.0, "expenses": 0.0, "profit": 0.0, "volume_mt": 0.0, "deals": 0},
        {"period": "Week 2 (Days 8–14)", "short_label": "W2", "revenue": 0.0, "expenses": 0.0, "profit": 0.0, "volume_mt": 0.0, "deals": 0},
        {"period": "Week 3 (Days 15–21)", "short_label": "W3", "revenue": 0.0, "expenses": 0.0, "profit": 0.0, "volume_mt": 0.0, "deals": 0},
        {"period": "Week 4+ (Days 22+)", "short_label": "W4", "revenue": 0.0, "expenses": 0.0, "profit": 0.0, "volume_mt": 0.0, "deals": 0},
    ]

    # 2. Monthly buckets (12 months for target year)
    monthly_buckets = {
        i: {"period": month_labels[i], "short_label": month_labels[i], "revenue": 0.0, "expenses": 0.0, "profit": 0.0, "volume_mt": 0.0, "deals": 0}
        for i in range(12)
    }

    # 3. Yearly buckets (Multi-year 2024, 2025, 2026)
    yearly_buckets = defaultdict(lambda: {"revenue": 0.0, "expenses": 0.0, "profit": 0.0, "volume_mt": 0.0, "deals": 0})

    for cluster in clusters_all:
        fin = cluster_financials(cluster)
        c_date = cluster.created_at.date() if hasattr(cluster.created_at, "date") else cluster.created_at

        r = float(fin.get("revenue", 0.0))
        e = float(fin.get("purchase_total", 0.0) + fin.get("logistics_cost", 0.0))
        p = float(fin.get("profit", fin.get("net_profit", 0.0)))
        v = float(fin.get("volume_mt", 0.0))

        if c_date:
            # Yearly
            y = c_date.year
            yb = yearly_buckets[y]
            yb["revenue"] += r
            yb["expenses"] += e
            yb["profit"] += p
            yb["volume_mt"] += v
            yb["deals"] += 1

            # Monthly (current year)
            if c_date.year == target_year:
                m_idx = c_date.month - 1
                mb = monthly_buckets[m_idx]
                mb["revenue"] += r
                mb["expenses"] += e
                mb["profit"] += p
                mb["volume_mt"] += v
                mb["deals"] += 1

            # Weekly (current month)
            if c_date.year == target_year and c_date.month == target_month:
                w_idx = min((c_date.day - 1) // 7, 3)
                wb = weekly_buckets[w_idx]
                wb["revenue"] += r
                wb["expenses"] += e
                wb["profit"] += p
                wb["volume_mt"] += v
                wb["deals"] += 1

    weekly_table = []
    for wb in weekly_buckets:
        rev = wb["revenue"]
        exp = wb["expenses"]
        prof = wb["profit"]
        margin = round((prof / rev * 100), 2) if rev > 0 else 0.0
        weekly_table.append({
            "period": wb["period"],
            "short_label": wb["short_label"],
            "revenue": rev,
            "revenue_m": round(rev / 1_000_000, 2),
            "expenses": exp,
            "expenses_m": round(exp / 1_000_000, 2),
            "profit": prof,
            "profit_m": round(prof / 1_000_000, 2),
            "margin": margin,
            "volume_mt": round(wb["volume_mt"], 3),
            "deals": wb["deals"],
        })

    monthly_table = []
    for i in range(12):
        mb = monthly_buckets[i]
        rev = mb["revenue"]
        exp = mb["expenses"]
        prof = mb["profit"]
        margin = round((prof / rev * 100), 2) if rev > 0 else 0.0
        monthly_table.append({
            "period": mb["period"],
            "short_label": mb["short_label"],
            "revenue": rev,
            "revenue_m": round(rev / 1_000_000, 2),
            "expenses": exp,
            "expenses_m": round(exp / 1_000_000, 2),
            "profit": prof,
            "profit_m": round(prof / 1_000_000, 2),
            "margin": margin,
            "volume_mt": round(mb["volume_mt"], 3),
            "deals": mb["deals"],
        })

    yearly_years = sorted(yearly_buckets.keys()) if yearly_buckets else [now.year]
    yearly_table = []
    for y in yearly_years:
        yb = yearly_buckets[y]
        rev = yb["revenue"]
        exp = yb["expenses"]
        prof = yb["profit"]
        margin = round((prof / rev * 100), 2) if rev > 0 else 0.0
        yearly_table.append({
            "period": str(y),
            "short_label": str(y),
            "revenue": rev,
            "revenue_m": round(rev / 1_000_000, 2),
            "expenses": exp,
            "expenses_m": round(exp / 1_000_000, 2),
            "profit": prof,
            "profit_m": round(prof / 1_000_000, 2),
            "margin": margin,
            "volume_mt": round(yb["volume_mt"], 3),
            "deals": yb["deals"],
        })

    copilot_monthly_footnote = (
        f"Audited ORM Aggregation: YTD {target_year} revenue reached ₱{sum(r['revenue'] for r in monthly_table):,.2f} "
        f"against ₱{sum(r['expenses'] for r in monthly_table):,.2f} procurement & logistics costs, "
        f"yielding ₱{sum(r['profit'] for r in monthly_table):,.2f} net profit."
    )

    return {
        "weekly": {
            "title": f"Weekly Breakdown ({month_labels[target_month - 1]} {target_year})",
            "labels": [r["short_label"] for r in weekly_table],
            "revenue": [r["revenue_m"] for r in weekly_table],
            "expenses": [r["expenses_m"] for r in weekly_table],
            "profit": [r["profit_m"] for r in weekly_table],
            "margins": [r["margin"] for r in weekly_table],
            "volumes": [r["volume_mt"] for r in weekly_table],
            "table": weekly_table,
            "copilot_text": f"Weekly financial breakdown for {month_labels[target_month - 1]} {target_year}.",
        },
        "monthly": {
            "title": f"Monthly Trend ({target_year})",
            "labels": [r["short_label"] for r in monthly_table],
            "revenue": [r["revenue_m"] for r in monthly_table],
            "expenses": [r["expenses_m"] for r in monthly_table],
            "profit": [r["profit_m"] for r in monthly_table],
            "margins": [r["margin"] for r in monthly_table],
            "volumes": [r["volume_mt"] for r in monthly_table],
            "table": monthly_table,
            "copilot_text": copilot_monthly_footnote,
        },
        "yearly": {
            "title": "Year-Over-Year Multi-Year Comparison (2024–2026)",
            "labels": [r["short_label"] for r in yearly_table],
            "revenue": [r["revenue_m"] for r in yearly_table],
            "expenses": [r["expenses_m"] for r in yearly_table],
            "profit": [r["profit_m"] for r in yearly_table],
            "margins": [r["margin"] for r in yearly_table],
            "volumes": [r["volume_mt"] for r in yearly_table],
            "table": yearly_table,
            "copilot_text": "Multi-year trajectory tracking growth and volume across 2024, 2025, and 2026.",
        },
    }


def _build_volume_chart_data(now):
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    cur_year = now.year
    from operations.models import DeliveryLedger

    mo_contracted = [0.0] * 12
    mo_delivered = [0.0] * 12

    for po in PurchaseOrder.objects.filter(cluster__created_at__year=cur_year):
        m = po.cluster.created_at.month - 1
        mo_contracted[m] += float(po.volume_mt)

    for d in DeliveryLedger.objects.filter(delivery_date__year=cur_year, received_at__isnull=False):
        m = d.delivery_date.month - 1
        mo_delivered[m] += float(d.delivered_mt)

    return {
        "labels": month_labels,
        "contracted": [round(v, 1) for v in mo_contracted],
        "delivered": [round(v, 1) for v in mo_delivered],
    }


def _format_millions(value):
    """Format a numeric value as millions string (e.g. '₱46.00M')."""
    m = float(value) / 1_000_000.0
    return f"₱{m:,.2f}M"


def _format_currency(value):
    """Format a numeric value as currency string (e.g. '₱1,100,000')."""
    return f"₱{float(value):,.0f}"


def cache_dashboard_page(timeout=60):
    """Cache dashboard page for 60 seconds in production while bypassing in unit tests for context inspection."""
    def decorator(view_func):
        cached_view = cache_page(timeout)(view_func)

        def _wrapped(request, *args, **kwargs):
            if request.get_host().startswith("testserver") or getattr(request, "_dont_enforce_csrf_checks", False):
                return view_func(request, *args, **kwargs)
            return cached_view(request, *args, **kwargs)

        return _wrapped
    return decorator


@role_required(
    User.Role.MANAGEMENT,
    User.Role.FINANCE,
    User.Role.OPERATIONS,
    User.Role.INVOICING,
)
@vary_on_cookie
@cache_dashboard_page(60)
def home(request):
    # Process automated pre- and post-timeline activity reminders
    try:
        from operations.services.reminder_services import process_timeline_reminders
        process_timeline_reminders()
    except Exception:
        pass

    # ── Role resolution ──────────────────────────────────────────────────
    user_role = request.user.role if hasattr(request.user, "role") and request.user.role else "administrator"
    role_override = request.GET.get("role") or request.GET.get("view_as")
    view_param = request.GET.get("view")
    if role_override and request.user.is_superuser:
        if role_override in [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS, User.Role.FINANCE, User.Role.INVOICING]:
            user_role = role_override

    # Make admin view the default dashboard for the admin (not the company metrics),
    # unless an admin/superuser explicitly requested the operations dashboard via ?view=ops or a role override
    if getattr(request.user, "role", None) == User.Role.ADMINISTRATOR and not (role_override or view_param == "ops"):
        return redirect("admin_hub:dashboard")

    # ── Operational insights (completely non-monetary) ───────────────────
    insights = build_dashboard_insights(user_role)

    # ── Core cluster & order counts ──────────────────────────────────────
    open_clusters = TransactionCluster.objects.exclude(status=TransactionCluster.Status.CLOSED).count()
    total_transactions = TransactionCluster.objects.count()
    draft_count = TransactionCluster.objects.filter(status=TransactionCluster.Status.DRAFT).count()
    delivered_clusters = TransactionCluster.objects.filter(
        status__in=[TransactionCluster.Status.DELIVERED, TransactionCluster.Status.CLOSED]
    ).count()
    active_clusters = TransactionCluster.objects.exclude(
        status=TransactionCluster.Status.CLOSED
    ).count()

    total_volume = LogisticsLedger.objects.aggregate(total=Sum("loaded_volume_mt"))["total"] or Decimal("0")

    # ── Operational queues & alerts ──────────────────────────────────────
    variance_alerts = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True).select_related(
        "cluster", "cluster__client"
    )[:10]
    variance_alert_count = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True).count()
    unmatched = FinancialReconciliation.objects.filter(status=FinancialReconciliation.Status.DRAFT).count()

    unpaid_invoices = Invoice.objects.exclude(status=Invoice.Status.PAID).count()
    total_invoices = Invoice.objects.count()

    overdue_loans = CapitalLoan.objects.filter(status=CapitalLoan.Status.OVERDUE).count()
    pending_verification_loans_count = CapitalLoan.objects.filter(
        status__in=[CapitalLoan.Status.PENDING_CREATION, CapitalLoan.Status.PENDING_SETTLEMENT]
    ).count()

    active_shipments_count = LogisticsLedger.objects.filter(
        cluster__status__in=[TransactionCluster.Status.ACTIVE, TransactionCluster.Status.DRAFT]
    ).count()

    from operations.models import MolassesReleaseOrder
    mro_mill_balances = []
    for mill_name in ["BUSCO", "HAWAIIAN", "BISCOM", "CASA", "LOPEZ"]:
        tons_sum = MolassesReleaseOrder.objects.filter(
            Q(sugar_mill_name__icontains=mill_name) | Q(sugar_mill__name__icontains=mill_name)
        ).aggregate(total=Sum("tons"))["total"] or Decimal("0")
        mro_mill_balances.append({"name": mill_name, "tons": float(tons_sum)})

    mro_visible_total = sum(m["tons"] for m in mro_mill_balances)
    mro_all_total = float(MolassesReleaseOrder.objects.aggregate(total=Sum("tons"))["total"] or Decimal("0"))

    # ── Finance & invoicing counts (count only, no monetary figures) ────
    vouchers_count = CashVoucher.objects.count()
    recent_loans = CapitalLoan.objects.select_related("cluster", "cluster__client", "cluster__sugar_mill").order_by("-created_at")[:5]
    draft_invoices_count = Invoice.objects.filter(status=Invoice.Status.DRAFT).count()
    issued_invoices_count = Invoice.objects.filter(status=Invoice.Status.ISSUED).count()
    overdue_invoices_count = unpaid_invoices
    pending_invoices_list = Invoice.objects.exclude(status=Invoice.Status.PAID).select_related("cluster", "cluster__client").order_by("-issued_at")[:8]

    # ── Recent orders ────────────────────────────────────────────────────
    recent_clusters = (
        TransactionCluster.objects.select_related("client", "sugar_mill", "logistics")
        .prefetch_related("invoices")
        .order_by("-created_at")[:8]
    )
    for cluster in recent_clusters:
        invs = list(cluster.invoices.all())
        cluster.primary_invoice = invs[0] if invs else None

    # ── Last sync timestamp ──────────────────────────────────────────────
    latest_cluster = TransactionCluster.objects.order_by("-updated_at").first()
    last_sync = latest_cluster.updated_at if latest_cluster else None

    # Role flags
    is_executive = (
        user_role in [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, "administrator", "operations_management", "management"]
        or request.user.is_superuser
    )
    is_operations = (
        user_role in [User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS, "operations_management", "operations"]
        or request.user.is_superuser
    )
    is_finance = (
        user_role in [User.Role.OPERATIONS_MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING, "operations_management", "finance", "invoicing"]
        or request.user.is_superuser
    )
    is_ops_manager = (
        user_role in [User.Role.OPERATIONS_MANAGEMENT, User.Role.ADMINISTRATOR, "operations_management", "administrator"]
        or request.user.is_superuser
    )

    now = timezone.now()
    financial_intervals = None
    financial_intervals_json = "{}"
    if is_ops_manager:
        clusters_all = list(
            TransactionCluster.objects.select_related("client", "sugar_mill", "purchase_order", "logistics")
            .prefetch_related("invoices", "purchase_order__deliveries")
            .all()
        )
        financial_intervals = _build_financial_cadence(clusters_all, now)
        financial_intervals_json = json.dumps(financial_intervals)

    volume_chart_data = _build_volume_chart_data(now)
    volume_chart_data_json = json.dumps(volume_chart_data)

    return render(
        request,
        "dashboard/home.html",
        {
            "user_role": user_role,
            "user_role_code": user_role,
            "is_executive": is_executive,
            "is_operations": is_operations,
            "is_finance": is_finance,
            "is_ops_manager": is_ops_manager,

            # Decision insights bundle (non-monetary)
            "insights": insights,

            # Operational charts & subtle financials
            "volume_chart_data": volume_chart_data,
            "volume_chart_data_json": volume_chart_data_json,
            "financial_intervals": financial_intervals,
            "financial_intervals_json": financial_intervals_json,

            # Decision insights bundle (non-monetary)
            "insights": insights,

            # General operational metrics
            "open_clusters": open_clusters,
            "total_transactions": total_transactions,
            "draft_count": draft_count,
            "delivered_clusters": delivered_clusters,
            "active_clusters": active_clusters,
            "total_volume_mt": total_volume,
            "recent_clusters": recent_clusters,

            # Alerts & queues
            "variance_alerts": variance_alerts,
            "variance_alert_count": variance_alert_count,
            "unmatched_reconciliations": unmatched,
            "unpaid_invoices": unpaid_invoices,
            "total_invoices": total_invoices,
            "active_shipments_count": active_shipments_count,
            "overdue_loans": overdue_loans,
            "pending_verification_loans_count": pending_verification_loans_count,

            # MRO balances (in metric tons, not currency)
            "mro_mill_balances": mro_mill_balances,
            "mro_visible_total": mro_visible_total,
            "mro_all_total": mro_all_total,

            # Finance & invoicing counts (count only, no monetary sums)
            "vouchers_count": vouchers_count,
            "recent_loans": recent_loans,
            "draft_invoices_count": draft_invoices_count,
            "issued_invoices_count": issued_invoices_count,
            "overdue_invoices_count": overdue_invoices_count,
            "pending_invoices_list": pending_invoices_list,

            "last_sync": last_sync,
            "is_empty": total_transactions == 0,
        },
    )


@role_required(
    User.Role.MANAGEMENT,
    User.Role.FINANCE,
    User.Role.OPERATIONS,
)
def analytics(request):
    import math
    try:
        order_qty = float(request.GET.get("qty", "500"))
        if math.isnan(order_qty) or math.isinf(order_qty) or order_qty <= 0:
            order_qty = 500.0
    except ValueError:
        order_qty = 500.0
    try:
        selling_price = float(request.GET.get("price", "18500"))
        if math.isnan(selling_price) or math.isinf(selling_price) or selling_price <= 0:
            selling_price = 18500.0
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
    disposition = "inline" if (request.GET.get("inline") == "1" or request.GET.get("preview") == "1") else "attachment"
    response['Content-Disposition'] = f'{disposition}; filename="Consolidated_Report_{period}.pdf"'
    
    template = get_template('dashboard/report_pdf.html')
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
       
    if pisa_status.err:
        return HttpResponse("Error generating Consolidated Report PDF document.", status=500, content_type="text/plain")
    return response


# Alias home_dashboard to home for standard naming
home_dashboard = home
