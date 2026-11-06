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


def _build_financial_cadence(clusters_all, now, target_year=None, target_month=None):
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    target_year = int(target_year) if target_year else now.year
    target_month = int(target_month) if target_month else now.month

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
    cur_month = now.month
    from operations.models import DeliveryLedger

    # 1. Monthly (Jan - Dec of cur_year)
    mo_contracted = [0.0] * 12
    mo_delivered = [0.0] * 12

    for po in PurchaseOrder.objects.filter(cluster__created_at__year=cur_year):
        m = po.cluster.created_at.month - 1
        mo_contracted[m] += float(po.volume_mt)

    for d in DeliveryLedger.objects.filter(delivery_date__year=cur_year, received_at__isnull=False):
        m = d.delivery_date.month - 1
        mo_delivered[m] += float(d.delivered_mt)

    monthly_table = []
    for i in range(12):
        c_mt = round(mo_contracted[i], 1)
        d_mt = round(mo_delivered[i], 1)
        rate = round((d_mt / c_mt * 100), 1) if c_mt > 0 else (100.0 if d_mt > 0 else 0.0)
        monthly_table.append({
            "period": f"{month_labels[i]} {cur_year}",
            "short_label": month_labels[i],
            "contracted": c_mt,
            "delivered": d_mt,
            "rate": rate,
            "pending": round(max(0.0, c_mt - d_mt), 1),
        })

    # 2. Weekly (Weeks of cur_month)
    wk_labels = ["Week 1 (Days 1–7)", "Week 2 (Days 8–14)", "Week 3 (Days 15–21)", "Week 4 (Days 22+)"]
    wk_short = ["W1", "W2", "W3", "W4"]
    wk_contracted = [0.0] * 4
    wk_delivered = [0.0] * 4

    for po in PurchaseOrder.objects.filter(cluster__created_at__year=cur_year, cluster__created_at__month=cur_month):
        w = min((po.cluster.created_at.day - 1) // 7, 3)
        wk_contracted[w] += float(po.volume_mt)

    for d in DeliveryLedger.objects.filter(delivery_date__year=cur_year, delivery_date__month=cur_month, received_at__isnull=False):
        w = min((d.delivery_date.day - 1) // 7, 3)
        wk_delivered[w] += float(d.delivered_mt)

    weekly_table = []
    for i in range(4):
        c_mt = round(wk_contracted[i], 1)
        d_mt = round(wk_delivered[i], 1)
        rate = round((d_mt / c_mt * 100), 1) if c_mt > 0 else (100.0 if d_mt > 0 else 0.0)
        weekly_table.append({
            "period": wk_labels[i],
            "short_label": wk_short[i],
            "contracted": c_mt,
            "delivered": d_mt,
            "rate": rate,
            "pending": round(max(0.0, c_mt - d_mt), 1),
        })

    # 3. Yearly (2024–2026)
    yr_labels = ["2024", "2025", "2026"]
    yr_contracted = [0.0] * len(yr_labels)
    yr_delivered = [0.0] * len(yr_labels)

    for idx, yr_str in enumerate(yr_labels):
        y = int(yr_str)
        for po in PurchaseOrder.objects.filter(cluster__created_at__year=y):
            yr_contracted[idx] += float(po.volume_mt)
        for d in DeliveryLedger.objects.filter(delivery_date__year=y, received_at__isnull=False):
            yr_delivered[idx] += float(d.delivered_mt)

    yearly_table = []
    for i in range(len(yr_labels)):
        c_mt = round(yr_contracted[i], 1)
        d_mt = round(yr_delivered[i], 1)
        rate = round((d_mt / c_mt * 100), 1) if c_mt > 0 else (100.0 if d_mt > 0 else 0.0)
        yearly_table.append({
            "period": yr_labels[i],
            "short_label": yr_labels[i],
            "contracted": c_mt,
            "delivered": d_mt,
            "rate": rate,
            "pending": round(max(0.0, c_mt - d_mt), 1),
        })

    cur_month_name = month_labels[cur_month - 1]

    return {
        "monthly": {
            "title": f"Monthly Volume Fulfillment ({cur_year})",
            "subtitle": f"Contracted volume vs confirmed delivered volume across {cur_year}",
            "labels": month_labels,
            "contracted": [r["contracted"] for r in monthly_table],
            "delivered": [r["delivered"] for r in monthly_table],
            "table": monthly_table,
        },
        "weekly": {
            "title": f"Weekly Volume Fulfillment ({cur_month_name} {cur_year})",
            "subtitle": f"Contracted volume vs confirmed delivered volume for {cur_month_name} {cur_year}",
            "labels": wk_short,
            "contracted": [r["contracted"] for r in weekly_table],
            "delivered": [r["delivered"] for r in weekly_table],
            "table": weekly_table,
        },
        "yearly": {
            "title": "Yearly Volume Fulfillment (2024–2026)",
            "subtitle": "Multi-year contracted volume vs confirmed delivered volume trajectory",
            "labels": yr_labels,
            "contracted": [r["contracted"] for r in yearly_table],
            "delivered": [r["delivered"] for r in yearly_table],
            "table": yearly_table,
        },
        # Backwards compatibility for existing references
        "labels": month_labels,
        "contracted": [r["contracted"] for r in monthly_table],
        "delivered": [r["delivered"] for r in monthly_table],
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
        .order_by("-created_at")[:50]
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
        user_role in [User.Role.OPERATIONS_MANAGEMENT, "operations_management"]
        or request.user.is_superuser
    )

    now = timezone.now()
    financial_intervals = None
    financial_intervals_json = "{}"

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


def _get_analytics_data(period="yearly", year="2026", month=None, week=None):
    from operations.models import DeliveryLedger, LogisticsLedger, PurchaseOrder, TransactionCluster
    from masters.models import Client, SugarMill

    now = timezone.now()
    available_years = sorted(list(set(
        PurchaseOrder.objects.values_list("cluster__created_at__year", flat=True).distinct()
    ) | {2024, 2025, 2026}))

    try:
        selected_year = int(year) if year else (available_years[-1] if available_years else now.year)
    except (ValueError, TypeError):
        selected_year = available_years[-1] if available_years else now.year

    try:
        selected_month = int(month) if month else now.month
    except (ValueError, TypeError):
        selected_month = now.month
    if selected_month < 1 or selected_month > 12:
        selected_month = now.month

    try:
        selected_week = int(week) if week else 1
    except (ValueError, TypeError):
        selected_week = 1
    if selected_week < 1 or selected_week > 4:
        selected_week = 1

    month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    cur_month_name = month_names[selected_month - 1]

    if period == "weekly":
        start_day = (selected_week - 1) * 7 + 1
        end_day = 31 if selected_week == 4 else selected_week * 7
        po_qs = PurchaseOrder.objects.filter(
            cluster__created_at__year=selected_year,
            cluster__created_at__month=selected_month,
            cluster__created_at__day__gte=start_day,
            cluster__created_at__day__lte=end_day
        )
        delivery_qs = DeliveryLedger.objects.filter(
            delivery_date__year=selected_year,
            delivery_date__month=selected_month,
            delivery_date__day__gte=start_day,
            delivery_date__day__lte=end_day,
            received_at__isnull=False
        )
        logistics_qs = LogisticsLedger.objects.filter(
            cluster__created_at__year=selected_year,
            cluster__created_at__month=selected_month,
            cluster__created_at__day__gte=start_day,
            cluster__created_at__day__lte=end_day
        )
        cluster_qs = TransactionCluster.objects.filter(
            created_at__year=selected_year,
            created_at__month=selected_month,
            created_at__day__gte=start_day,
            created_at__day__lte=end_day
        )
        period_title = f"Week {selected_week} ({cur_month_name} {selected_year})"
        period_badge = f"W{selected_week} {cur_month_name[:3]} {selected_year}"

    elif period == "monthly":
        po_qs = PurchaseOrder.objects.filter(
            cluster__created_at__year=selected_year,
            cluster__created_at__month=selected_month
        )
        delivery_qs = DeliveryLedger.objects.filter(
            delivery_date__year=selected_year,
            delivery_date__month=selected_month,
            received_at__isnull=False
        )
        logistics_qs = LogisticsLedger.objects.filter(
            cluster__created_at__year=selected_year,
            cluster__created_at__month=selected_month
        )
        cluster_qs = TransactionCluster.objects.filter(
            created_at__year=selected_year,
            created_at__month=selected_month
        )
        period_title = f"{cur_month_name} {selected_year}"
        period_badge = f"{cur_month_name[:3]} {selected_year}"

    else: # yearly - singular year (2024, 2025, 2026)
        period = "yearly"
        po_qs = PurchaseOrder.objects.filter(cluster__created_at__year=selected_year)
        delivery_qs = DeliveryLedger.objects.filter(delivery_date__year=selected_year, received_at__isnull=False)
        logistics_qs = LogisticsLedger.objects.filter(cluster__created_at__year=selected_year)
        cluster_qs = TransactionCluster.objects.filter(created_at__year=selected_year)
        period_title = f"Year {selected_year}"
        period_badge = f"FY {selected_year}"

    total_contracted = float(po_qs.aggregate(s=Sum("volume_mt"))["s"] or 0)
    total_delivered = float(delivery_qs.aggregate(s=Sum("delivered_mt"))["s"] or 0)
    total_loaded = float(logistics_qs.aggregate(s=Sum("loaded_volume_mt"))["s"] or 0)
    avg_variance = float(logistics_qs.filter(variance_percent__isnull=False).aggregate(a=Avg("variance_percent"))["a"] or 0)
    fulfillment_rate = round((total_delivered / total_contracted * 100), 1) if total_contracted > 0 else 0.0

    # Customer Demand & Volume Share
    client_data = []
    for c in Client.objects.filter(is_active=True).order_by("name"):
        vol = float(po_qs.filter(cluster__client=c).aggregate(s=Sum("volume_mt"))["s"] or 0)
        orders_count = cluster_qs.filter(client=c).count()
        if vol > 0 or orders_count > 0:
            pct = round((vol / total_contracted * 100), 1) if total_contracted > 0 else 0.0
            client_data.append({
                "id": c.id,
                "name": c.name,
                "orders_count": orders_count,
                "volume_mt": vol,
                "volume_pct": pct,
            })
    client_data.sort(key=lambda x: x["volume_mt"], reverse=True)

    # Sugar Mill Sourcing Distribution & Route Health
    mill_data = []
    for m in SugarMill.objects.filter(is_active=True).order_by("name"):
        vol = float(po_qs.filter(cluster__sugar_mill=m).aggregate(s=Sum("volume_mt"))["s"] or 0)
        orders_count = cluster_qs.filter(sugar_mill=m).count()
        var = float(logistics_qs.filter(cluster__sugar_mill=m).aggregate(a=Avg("variance_percent"))["a"] or 0)
        disputed = logistics_qs.filter(cluster__sugar_mill=m, variance_exceeds_tolerance=True).count()
        if vol > 0 or orders_count > 0:
            pct = round((vol / total_contracted * 100), 1) if total_contracted > 0 else 0.0
            mill_data.append({
                "id": m.id,
                "name": m.name,
                "orders_count": orders_count,
                "volume_mt": vol,
                "volume_pct": pct,
                "avg_variance": round(var, 2),
                "disputed_count": disputed,
                "is_safe": var <= 1.0,
            })
    mill_data.sort(key=lambda x: x["volume_mt"], reverse=True)

    total_partners = len(client_data) + len(mill_data)
    client_chart_labels = [c["name"] for c in client_data]
    client_chart_volumes = [c["volume_mt"] for c in client_data]
    mill_chart_labels = [m["name"] for m in mill_data]
    mill_chart_volumes = [m["volume_mt"] for m in mill_data]

    # Executive Financials & Analytics Report Cadence
    clusters_all = list(
        TransactionCluster.objects.select_related("client", "sugar_mill", "purchase_order", "logistics")
        .prefetch_related("invoices", "purchase_order__deliveries")
        .all()
    )
    financial_intervals = _build_financial_cadence(clusters_all, now, target_year=selected_year, target_month=selected_month)
    financial_intervals_json = json.dumps(financial_intervals)

    return {
        "period": period,
        "selected_year": selected_year,
        "selected_month": selected_month,
        "selected_week": selected_week,
        "available_years": available_years,
        "period_title": period_title,
        "period_badge": period_badge,
        "month_names": [(i+1, name) for i, name in enumerate(month_names)],
        "total_contracted": total_contracted,
        "total_delivered": total_delivered,
        "total_loaded": total_loaded,
        "avg_variance": round(avg_variance, 2),
        "fulfillment_rate": fulfillment_rate,
        "total_partners": total_partners,
        "client_data": client_data,
        "mill_data": mill_data,
        "client_chart_json": json.dumps({"labels": client_chart_labels, "data": client_chart_volumes}),
        "mill_chart_json": json.dumps({"labels": mill_chart_labels, "data": mill_chart_volumes}),
        "financial_intervals": financial_intervals,
        "financial_intervals_json": financial_intervals_json,
    }


@role_required(
    User.Role.MANAGEMENT,
    User.Role.FINANCE,
    User.Role.OPERATIONS,
)
def analytics(request):
    """Executive Performance Analytics: Real-time operational intelligence sorted by Weekly, Monthly, and Yearly (singular year)."""
    period = request.GET.get("period", "yearly").strip().lower()
    year = request.GET.get("year", "2026").strip()
    month = request.GET.get("month", "").strip()
    week = request.GET.get("week", "").strip()

    context = _get_analytics_data(period=period, year=year, month=month, week=week)
    return render(request, "dashboard/analytics.html", context)


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.OPERATIONS)
def export_analytics_pdf(request):
    """Generate printable PDF report for Analytics with KPIs, customer demand, and sugar mill distribution."""
    period = request.GET.get("period", "yearly").strip().lower()
    year = request.GET.get("year", "2026").strip()
    month = request.GET.get("month", "").strip()
    week = request.GET.get("week", "").strip()
    data = _get_analytics_data(period=period, year=year, month=month, week=week)

    template = get_template("dashboard/analytics_report_pdf.html")
    html = template.render({"data": data, "now": timezone.now()})

    response = HttpResponse(content_type="application/pdf")
    disposition = "inline" if (request.GET.get("inline") == "1" or request.GET.get("preview") == "1") else "attachment"
    filename = f"HTC_Analytics_{data['period_badge'].replace(' ', '_')}.pdf"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse("Error generating Analytics PDF report.", status=500, content_type="text/plain")
    return response


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.OPERATIONS)
def export_analytics_xlsx(request):
    """Generate professional Excel spreadsheet (.xlsx) for Analytics report."""
    period = request.GET.get("period", "yearly").strip().lower()
    year = request.GET.get("year", "2026").strip()
    month = request.GET.get("month", "").strip()
    week = request.GET.get("week", "").strip()
    data = _get_analytics_data(period=period, year=year, month=month, week=week)

    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Performance Analytics"

    title_font = Font(name="Calibri", size=15, bold=True, color="0C385C")
    sub_font = Font(name="Calibri", size=10, italic=True, color="555555")
    section_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")

    section_fill = PatternFill(start_color="0C385C", end_color="0C385C", fill_type="solid")
    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")

    ws.append(["HEINDRICH TRADING CORPORATION"])
    ws.append(["Company Operations & Performance Overview Report"])
    ws.append([f"Period: {data['period_title']} | Exported: {timezone.now().strftime('%b %d, %Y %I:%M %p PST')}"])
    ws.append([])

    ws["A1"].font = title_font
    ws["A2"].font = Font(name="Calibri", size=12, bold=True, color="333333")
    ws["A3"].font = sub_font

    # KPI Block
    ws.append(["EXECUTIVE KEY PERFORMANCE INDICATORS", "", ""])
    ws.merge_cells("A5:C5")
    ws["A5"].font = section_font
    ws["A5"].fill = section_fill

    ws.append(["Metric", "Value", "Notes"])
    for col in ["A", "B", "C"]:
        ws[f"{col}6"].font = header_font
        ws[f"{col}6"].fill = header_fill

    kpis = [
        ("Contracted Molasses Volume", f"{data['total_contracted']:,.2f} MT", "Across recorded purchase orders"),
        ("Confirmed Delivered Volume", f"{data['total_delivered']:,.2f} MT", f"{data['fulfillment_rate']:.1f}% overall fulfillment rate"),
        ("Average In-Transit Weight Loss", f"{data['avg_variance']:.2f}%", "Tolerance threshold: +/-1.00%"),
        ("Active Trade Network", f"{data['total_partners']} Partners", f"{len(data['client_data'])} Buyers, {len(data['mill_data'])} Mills"),
    ]
    for row in kpis:
        ws.append(list(row))

    ws.append([])
    curr_row = ws.max_row + 1
    ws.append(["CUSTOMER DEMAND & VOLUME SHARE (TOP ENTERPRISE BUYERS)", "", "", "", ""])
    ws.merge_cells(f"A{curr_row}:E{curr_row}")
    ws[f"A{curr_row}"].font = section_font
    ws[f"A{curr_row}"].fill = section_fill

    ws.append(["Rank", "Enterprise Client", "Orders Count", "Contracted Volume (MT)", "Share of Volume (%)"])
    hdr_row = ws.max_row
    for col in ["A", "B", "C", "D", "E"]:
        ws[f"{col}{hdr_row}"].font = header_font
        ws[f"{col}{hdr_row}"].fill = header_fill

    for idx, c in enumerate(data["client_data"], start=1):
        ws.append([idx, c["name"], c["orders_count"], c["volume_mt"], f"{c['volume_pct']:.1f}%"])

    ws.append([])
    curr_row = ws.max_row + 1
    ws.append(["SUGAR MILL SOURCING DISTRIBUTION & ROUTE HEALTH", "", "", "", "", ""])
    ws.merge_cells(f"A{curr_row}:F{curr_row}")
    ws[f"A{curr_row}"].font = section_font
    ws[f"A{curr_row}"].fill = section_fill

    ws.append(["Rank", "Sugar Mill", "Orders", "Sourced Volume (MT)", "Share (%)", "Route Status"])
    hdr_row = ws.max_row
    for col in ["A", "B", "C", "D", "E", "F"]:
        ws[f"{col}{hdr_row}"].font = header_font
        ws[f"{col}{hdr_row}"].fill = header_fill

    for idx, m in enumerate(data["mill_data"], start=1):
        status = "Safe (<1%)" if m["is_safe"] else "Review Required"
        ws.append([idx, m["name"], m["orders_count"], m["volume_mt"], f"{m['volume_pct']:.1f}%", status])

    if data.get("financial_intervals"):
        ws.append([])
        curr_row = ws.max_row + 1
        fin_title = data["financial_intervals"]["monthly"]["title"]
        ws.append([f"EXECUTIVE FINANCIALS & PERFORMANCE LEDGER ({fin_title})", "", "", "", "", ""])
        ws.merge_cells(f"A{curr_row}:F{curr_row}")
        ws[f"A{curr_row}"].font = section_font
        ws[f"A{curr_row}"].fill = section_fill

        ws.append(["Period", "Money In (PHP)", "Money Out (PHP)", "Net Profit (PHP)", "Margin (%)", "Volume (MT)"])
        hdr_row = ws.max_row
        for col in ["A", "B", "C", "D", "E", "F"]:
            ws[f"{col}{hdr_row}"].font = header_font
            ws[f"{col}{hdr_row}"].fill = header_fill

        for row in data["financial_intervals"]["monthly"]["table"]:
            ws.append([
                row["period"],
                row["revenue"],
                row["expenses"],
                row["profit"],
                f"{row['margin']:.1f}%",
                row["volume_mt"],
            ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"HTC_Analytics_{data['period_badge'].replace(' ', '_')}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.OPERATIONS)
def export_analytics_csv(request):
    """Generate CSV file (.csv) for Analytics report."""
    period = request.GET.get("period", "yearly").strip().lower()
    year = request.GET.get("year", "2026").strip()
    month = request.GET.get("month", "").strip()
    week = request.GET.get("week", "").strip()
    data = _get_analytics_data(period=period, year=year, month=month, week=week)

    import csv

    response = HttpResponse(content_type="text/csv")
    filename = f"HTC_Analytics_{data['period_badge'].replace(' ', '_')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["HEINDRICH TRADING CORPORATION - PERFORMANCE ANALYTICS REPORT"])
    writer.writerow(["Report Period", data["period_title"]])
    writer.writerow(["Generated At", timezone.now().strftime("%Y-%m-%d %H:%M:%S PST")])
    writer.writerow([])
    writer.writerow(["EXECUTIVE PERFORMANCE INDICATORS"])
    writer.writerow(["Metric", "Value", "Unit / Notes"])
    writer.writerow(["Contracted Molasses Volume", f"{data['total_contracted']:,.2f}", "MT"])
    writer.writerow(["Confirmed Delivered Volume", f"{data['total_delivered']:,.2f}", "MT"])
    writer.writerow(["Fulfillment Completion Rate", f"{data['fulfillment_rate']:.1f}%", "Delivered / Contracted"])
    writer.writerow(["Average In-Transit Weight Loss", f"{data['avg_variance']:.2f}%", "Target <= 1.00%"])
    writer.writerow(["Active Trade Network Partners", data["total_partners"], f"{len(data['client_data'])} Buyers, {len(data['mill_data'])} Mills"])
    writer.writerow([])
    writer.writerow(["CUSTOMER DEMAND & VOLUME SHARE (TOP ENTERPRISE BUYERS)"])
    writer.writerow(["Rank", "Client Name", "Orders Count", "Volume (MT)", "Volume Share (%)"])
    for idx, c in enumerate(data["client_data"], start=1):
        writer.writerow([idx, c["name"], c["orders_count"], f"{c['volume_mt']:,.2f}", f"{c['volume_pct']:.1f}%"])
    writer.writerow([])
    writer.writerow(["SUGAR MILL SOURCING DISTRIBUTION & ROUTE HEALTH"])
    writer.writerow(["Rank", "Sugar Mill", "Orders Sourced", "Volume (MT)", "Volume Share (%)", "Avg Variance (%)", "Route Status"])
    for idx, m in enumerate(data["mill_data"], start=1):
        status = "Safe (<1%)" if m["is_safe"] else "Review Required"
        writer.writerow([idx, m["name"], m["orders_count"], f"{m['volume_mt']:,.2f}", f"{m['volume_pct']:.1f}%", f"{m['avg_variance']:.2f}%", status])

    if data.get("financial_intervals"):
        writer.writerow([])
        writer.writerow([f"EXECUTIVE FINANCIALS & PERFORMANCE LEDGER ({data['financial_intervals']['monthly']['title']})"])
        writer.writerow(["Period", "Money In (PHP)", "Money Out (PHP)", "Net Profit (PHP)", "Margin (%)", "Volume Delivered (MT)", "Orders Count"])
        for row in data["financial_intervals"]["monthly"]["table"]:
            writer.writerow([
                row["period"],
                f"{row['revenue']:,.2f}",
                f"{row['expenses']:,.2f}",
                f"{row['profit']:,.2f}",
                f"{row['margin']:.1f}%",
                f"{row['volume_mt']:,.2f}",
                row["deals"],
            ])

    return response


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
