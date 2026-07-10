from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render

from accounts.decorators import role_required
from accounts.models import User
from finance.models import FinancialReconciliation, Invoice
from operations.models import LogisticsLedger, TransactionCluster

from .services.analytics import build_supplier_rankings
from .services.documents import build_document_registry


@role_required(
    User.Role.MANAGEMENT,
    User.Role.FINANCE,
    User.Role.OPERATIONS,
    User.Role.INVOICING,
)
def home(request):
    open_clusters = TransactionCluster.objects.exclude(status=TransactionCluster.Status.CLOSED).count()
    total_transactions = TransactionCluster.objects.count()
    draft_count = TransactionCluster.objects.filter(status=TransactionCluster.Status.DRAFT).count()
    variance_alerts = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True).select_related(
        "cluster", "cluster__client"
    )[:10]
    unmatched = FinancialReconciliation.objects.filter(status=FinancialReconciliation.Status.DRAFT).count()
    unpaid_invoices = Invoice.objects.exclude(status=Invoice.Status.PAID).count()
    total_invoices = Invoice.objects.count()
    total_receivables = Invoice.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_volume = LogisticsLedger.objects.aggregate(total=Sum("loaded_volume_mt"))["total"] or Decimal("0")
    recent_clusters = (
        TransactionCluster.objects.select_related("client", "sugar_mill", "logistics")
        .prefetch_related("invoices")
        .order_by("-created_at")[:12]
    )
    for cluster in recent_clusters:
        cluster.primary_invoice = cluster.invoices.first()
    # Mock Data for Charts (Pilot Demonstration)
    chart_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    revenue_data = [3200000, 3800000, 3500000, 4200000, 4800000, 4600000]
    expenses_data = [2600000, 2900000, 2800000, 3100000, 3400000, 3200000]
    profit_data = [600000, 900000, 700000, 1100000, 1400000, 1400000]

    weekly_labels = ["W1", "W2", "W3", "W4"]
    inflow_data = [1200000, 1500000, 1100000, 1800000]
    outflow_data = [900000, 1200000, 1400000, 1000000]
    net_cash_flow = sum(inflow_data) - sum(outflow_data)
    net_cash_flow_str = f"₱{net_cash_flow:,.0f}"

    return render(
        request,
        "dashboard/home.html",
        {
            "open_clusters": open_clusters,
            "total_transactions": total_transactions,
            "draft_count": draft_count,
            "variance_alerts": variance_alerts,
            "unmatched_reconciliations": unmatched,
            "unpaid_invoices": unpaid_invoices,
            "total_invoices": total_invoices,
            "total_receivables": total_receivables,
            "total_volume_mt": total_volume,
            "recent_clusters": recent_clusters,
            "chart_months": chart_months,
            "revenue_data": revenue_data,
            "expenses_data": expenses_data,
            "profit_data": profit_data,
            "weekly_labels": weekly_labels,
            "inflow_data": inflow_data,
            "outflow_data": outflow_data,
            "net_cash_flow_str": net_cash_flow_str,
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
    return render(
        request,
        "dashboard/analytics.html",
        {
            "engine": engine,
            "order_qty": order_qty,
            "selling_price": selling_price,
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
    return render(request, "dashboard/documents.html", registry)
