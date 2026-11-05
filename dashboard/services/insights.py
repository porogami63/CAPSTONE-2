"""
Decision-support insights for the dashboard.

IMPORTANT: Nothing in this module may compute or return monetary values
(revenue, expenses, profit, invoice amounts, loan principal, etc.). The panel
review flagged peso figures on the dashboard as too sensitive. Every metric
here is a count, a volume in metric tons, a percentage of volume, or a number
of days, so the dashboard can still drive decisions without exposing money.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from finance.models import CapitalLoan, Invoice
from operations.models import (
    DeliveryLedger,
    LogisticsLedger,
    MolassesReleaseOrder,
    PurchaseOrder,
    TransactionCluster,
)

EXECUTIVE_ROLES = {"administrator", "operations_management", "management"}
OPERATIONS_ROLES = {"operations"}
FINANCE_ROLES = {"finance"}
INVOICING_ROLES = {"invoicing"}

# A delivery batch still not confirmed this many days after dispatch is "overdue".
OVERDUE_ARRIVAL_DAYS = 3


def role_group(role):
    role = (role or "").lower()
    if role in EXECUTIVE_ROLES:
        return "executive"
    if role in OPERATIONS_ROLES:
        return "operations"
    if role in FINANCE_ROLES:
        return "finance"
    if role in INVOICING_ROLES:
        return "invoicing"
    return "executive"


def _contracted_mt(po):
    raw = po.total_contracted_mt if po.total_contracted_mt is not None else po.volume_mt
    return Decimal(str(raw or 0))


def _pct(part, whole):
    whole = Decimal(str(whole or 0))
    if whole <= 0:
        return 0
    return int(round(float(Decimal(str(part or 0)) / whole * 100)))


# ─────────────────────────────────────────────────────────────────────────────
# Raw counts (shared by to-do list and indicators)
# ─────────────────────────────────────────────────────────────────────────────
def _collect_counts():
    now = timezone.now()
    today = timezone.localdate()

    in_transit = DeliveryLedger.objects.filter(received_at__isnull=True)
    overdue_cutoff = now - timedelta(days=OVERDUE_ARRIVAL_DAYS)
    overdue_arrivals = in_transit.filter(dispatched_at__lt=overdue_cutoff).count()

    open_disputes = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True, is_archived=False)

    confirmed = list(DeliveryLedger.objects.filter(received_at__isnull=False).only(
        "dispatched_mt", "delivered_mt"
    ))
    over_tolerance = sum(1 for d in confirmed if d.variance_exceeds_tolerance)

    return {
        "pending_approval": TransactionCluster.objects.filter(
            status=TransactionCluster.Status.PENDING_APPROVAL
        ).count(),
        "returned_orders": TransactionCluster.objects.filter(
            status=TransactionCluster.Status.RETURNED
        ).count(),
        "draft_orders": TransactionCluster.objects.filter(status=TransactionCluster.Status.DRAFT).count(),
        "active_orders": TransactionCluster.objects.exclude(
            status__in=[TransactionCluster.Status.CLOSED, TransactionCluster.Status.DRAFT]
        ).filter(is_archived=False).count(),
        "in_transit": in_transit.count(),
        "overdue_arrivals": overdue_arrivals,
        "open_disputes": open_disputes.count(),
        "confirmed_batches": len(confirmed),
        "over_tolerance_batches": over_tolerance,
        "unlinked_mros": MolassesReleaseOrder.objects.filter(cluster__isnull=True).count(),
        "invoices_draft": Invoice.objects.filter(status=Invoice.Status.DRAFT).count(),
        "invoices_issued": Invoice.objects.filter(status=Invoice.Status.ISSUED).count(),
        "invoices_overdue": Invoice.objects.filter(
            status=Invoice.Status.ISSUED, due_date__isnull=False, due_date__lt=today
        ).count(),
        "invoices_returned": Invoice.objects.filter(status=Invoice.Status.RETURNED).count(),
        "loans_pending_verification": CapitalLoan.objects.filter(
            status__in=[CapitalLoan.Status.PENDING_CREATION, CapitalLoan.Status.PENDING_SETTLEMENT]
        ).count(),
        "loans_overdue": CapitalLoan.objects.filter(status=CapitalLoan.Status.OVERDUE).count(),
        "loans_due_30": CapitalLoan.objects.filter(
            status=CapitalLoan.Status.ACTIVE, due_date__gte=today, due_date__lte=today + timedelta(days=30)
        ).count(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# "What needs your attention" — role-specific to-do list
# ─────────────────────────────────────────────────────────────────────────────
def _task(count, title, hint, action_label, url, tone="amber"):
    return {
        "count": count,
        "title": title,
        "hint": hint,
        "action_label": action_label,
        "url": url,
        "tone": tone,
    }


def build_todo_list(group, c):
    ops_tasks = [
        _task(c["overdue_arrivals"], "Overdue arrivals",
              f"Deliveries dispatched more than {OVERDUE_ARRIVAL_DAYS} days ago and still not confirmed.",
              "Confirm arrivals", reverse("operations:deliveries_list"), "red"),
        _task(c["open_disputes"], "Weight differences to resolve",
              "Shipments where the received weight is over the 1% allowed difference.",
              "Review", reverse("operations:pending_tasks"), "red"),
        _task(c["in_transit"] - c["overdue_arrivals"], "Deliveries in transit",
              "Confirm each arrival and the delivered volume once the truck or barge arrives.",
              "Open deliveries", reverse("operations:deliveries_list")),
        _task(c["returned_orders"], "Orders sent back for changes",
              "An approver returned these orders. Edit and resubmit them.",
              "Fix orders", reverse("operations:cluster_list") + "?status=returned", "red"),
        _task(c["unlinked_mros"], "Release permits not linked to an order",
              "Link each MRO permit to the order it covers.",
              "Link permits", reverse("operations:mro_summary")),
    ]
    approver_tasks = [
        _task(c["pending_approval"], "Orders waiting for your approval",
              "Review and approve or return new purchase orders.",
              "Review orders", reverse("operations:pending_tasks"), "red"),
        _task(c["loans_pending_verification"], "Loans waiting for verification",
              "Verify new loan facilities or settlements.",
              "Verify loans", reverse("finance:loan_list"), "red"),
    ]
    finance_tasks = [
        _task(c["loans_overdue"], "Overdue loans",
              "These loans are past their due date.",
              "Open loans", reverse("finance:loan_list"), "red"),
        _task(c["loans_due_30"], "Loans due within 30 days",
              "Prepare settlement documents ahead of the due date.",
              "Plan settlements", reverse("finance:loan_list")),
        _task(c["loans_pending_verification"], "Loans awaiting verification",
              "Waiting on the Operations Manager to verify.",
              "View loans", reverse("finance:loan_list"), "blue"),
        _task(c["invoices_overdue"], "Invoices past due",
              "Issued invoices that passed their due date and are not yet paid.",
              "Follow up", reverse("finance:invoice_list"), "red"),
    ]
    invoicing_tasks = [
        _task(c["invoices_returned"], "Invoices returned for correction",
              "Fix and resubmit these invoices.",
              "Fix invoices", reverse("finance:invoice_list"), "red"),
        _task(c["invoices_draft"], "Draft invoices to issue",
              "Check the details and issue these invoices to customers.",
              "Issue invoices", reverse("finance:invoice_list")),
        _task(c["invoices_overdue"], "Invoices past due",
              "Remind customers about unpaid invoices.",
              "Follow up", reverse("finance:invoice_list"), "red"),
    ]

    if group == "operations":
        tasks = ops_tasks
    elif group == "finance":
        tasks = finance_tasks
    elif group == "invoicing":
        tasks = invoicing_tasks
    else:
        tasks = approver_tasks + ops_tasks[:2] + finance_tasks[:1]

    # Show only items that actually need action, most urgent first, max 5.
    tone_rank = {"red": 0, "amber": 1, "blue": 2}
    tasks = [t for t in tasks if t["count"] > 0]
    tasks.sort(key=lambda t: (tone_rank.get(t["tone"], 3), -t["count"]))
    return tasks[:5]


# ─────────────────────────────────────────────────────────────────────────────
# Health indicators (4 per role, no money)
# ─────────────────────────────────────────────────────────────────────────────
def _indicator(label, value, caption, url, state="ok"):
    return {"label": label, "value": value, "caption": caption, "url": url, "state": state}


def build_indicators(group, c, fulfillment):
    weight_rate = _pct(c["over_tolerance_batches"], c["confirmed_batches"])
    at_risk = sum(1 for f in fulfillment["orders"] if f["at_risk"])

    ind = {
        "active_orders": _indicator(
            "Active orders", c["active_orders"],
            f"{at_risk} at risk of delay" if at_risk else "All on track",
            reverse("operations:cluster_list"), "warn" if at_risk else "ok"),
        "fulfillment": _indicator(
            "Volume fulfilled", f"{fulfillment['overall_pct']}%",
            f"{fulfillment['delivered_mt']:,.0f} of {fulfillment['contracted_mt']:,.0f} MT delivered",
            reverse("operations:deliveries_list"),
            "ok" if fulfillment["overall_pct"] >= 50 else "neutral"),
        "in_transit": _indicator(
            "In transit", c["in_transit"],
            f"{c['overdue_arrivals']} overdue" if c["overdue_arrivals"] else "None overdue",
            reverse("operations:deliveries_list"), "bad" if c["overdue_arrivals"] else "ok"),
        "weight": _indicator(
            "Weight difference rate", f"{weight_rate}%",
            f"{c['open_disputes']} open issue{'s' if c['open_disputes'] != 1 else ''}",
            reverse("operations:logistics_list"),
            "bad" if c["open_disputes"] else ("warn" if weight_rate > 5 else "ok")),
        "approvals": _indicator(
            "Waiting for approval", c["pending_approval"] + c["loans_pending_verification"],
            f"{c['pending_approval']} orders · {c['loans_pending_verification']} loans",
            reverse("operations:pending_tasks"),
            "warn" if (c["pending_approval"] + c["loans_pending_verification"]) else "ok"),
        "invoices_open": _indicator(
            "Invoices awaiting payment", c["invoices_issued"],
            f"{c['invoices_overdue']} past due" if c["invoices_overdue"] else "None past due",
            reverse("finance:invoice_list"), "bad" if c["invoices_overdue"] else "ok"),
        "invoices_draft": _indicator(
            "Draft invoices", c["invoices_draft"],
            f"{c['invoices_returned']} returned for correction" if c["invoices_returned"] else "Ready to issue",
            reverse("finance:invoice_list"), "warn" if c["invoices_draft"] else "ok"),
        "loans_due": _indicator(
            "Loans due in 30 days", c["loans_due_30"],
            f"{c['loans_overdue']} overdue" if c["loans_overdue"] else "None overdue",
            reverse("finance:loan_list"), "bad" if c["loans_overdue"] else ("warn" if c["loans_due_30"] else "ok")),
    }

    layout = {
        "executive": ["active_orders", "approvals", "fulfillment", "weight"],
        "operations": ["active_orders", "in_transit", "fulfillment", "weight"],
        "finance": ["loans_due", "approvals", "invoices_open", "fulfillment"],
        "invoicing": ["invoices_draft", "invoices_open", "active_orders", "fulfillment"],
    }
    return [ind[k] for k in layout.get(group, layout["executive"])]


# ─────────────────────────────────────────────────────────────────────────────
# Order fulfillment progress (MT only)
# ─────────────────────────────────────────────────────────────────────────────
def build_fulfillment(limit=6):
    pos = (
        PurchaseOrder.objects.select_related("cluster", "cluster__client")
        .prefetch_related("deliveries")
        .exclude(cluster__status__in=[TransactionCluster.Status.CLOSED, TransactionCluster.Status.DRAFT])
        .filter(cluster__is_archived=False)
    )
    rows = []
    total_contracted = Decimal("0")
    total_delivered = Decimal("0")
    now = timezone.now()
    for po in pos:
        contracted = _contracted_mt(po)
        if contracted <= 0:
            continue
        deliveries = list(po.deliveries.all())
        delivered = sum((Decimal(str(d.delivered_mt or 0)) for d in deliveries if d.received_at), Decimal("0"))
        pct = min(_pct(delivered, contracted), 100)
        last_activity = max(
            [d.received_at or d.dispatched_at for d in deliveries if (d.received_at or d.dispatched_at)],
            default=None,
        )
        # At risk: started but no movement for 14+ days and under 100%.
        stale = last_activity is None or (now - last_activity).days >= 14
        at_risk = pct < 100 and stale and po.cluster.status in (
            TransactionCluster.Status.APPROVED, TransactionCluster.Status.ACTIVE
        )
        total_contracted += contracted
        total_delivered += min(delivered, contracted)
        rows.append({
            "pk": po.cluster.pk,
            "ref": po.po_reference_number or po.cluster.reference_code,
            "customer": po.cluster.client.name if po.cluster.client else "—",
            "contracted_mt": float(contracted),
            "delivered_mt": float(delivered),
            "pct": pct,
            "at_risk": at_risk,
        })

    # Show orders that need attention first, then least complete.
    rows.sort(key=lambda r: (not r["at_risk"], r["pct"]))
    return {
        "orders": rows,
        "top": rows[:limit],
        "overall_pct": min(_pct(total_delivered, total_contracted), 100),
        "contracted_mt": float(total_contracted),
        "delivered_mt": float(total_delivered),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Provider performance (shortage rate per trucking / barge provider)
# ─────────────────────────────────────────────────────────────────────────────
def build_provider_performance(limit=5):
    stats = defaultdict(lambda: {"batches": 0, "over": 0, "shortage_mt": Decimal("0")})
    qs = DeliveryLedger.objects.filter(received_at__isnull=False).select_related(
        "trucking_partner", "barge_partner"
    )
    for d in qs:
        providers = {p.name for p in (d.trucking_partner, d.barge_partner) if p}
        diff = Decimal(str(d.effective_dispatched_mt or 0)) - Decimal(str(d.delivered_mt or 0))
        for name in providers:
            s = stats[name]
            s["batches"] += 1
            if d.variance_exceeds_tolerance:
                s["over"] += 1
            if diff > 0:
                s["shortage_mt"] += diff

    rows = [
        {
            "name": name,
            "batches": s["batches"],
            "issue_rate": _pct(s["over"], s["batches"]),
            "shortage_mt": float(s["shortage_mt"]),
        }
        for name, s in stats.items()
    ]
    rows.sort(key=lambda r: (-r["issue_rate"], -r["shortage_mt"]))
    return rows[:limit]


def build_dashboard_insights(role):
    group = role_group(role)
    counts = _collect_counts()
    fulfillment = build_fulfillment()
    return {
        "role_group": group,
        "todo_items": build_todo_list(group, counts),
        "indicators": build_indicators(group, counts, fulfillment),
        "fulfillment": fulfillment,
        "providers": build_provider_performance() if group in ("executive", "operations") else [],
        "counts": counts,
    }

