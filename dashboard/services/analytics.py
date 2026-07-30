"""Predictive margin engine using historical supplier and logistics data."""

from decimal import Decimal

from django.db.models import Avg, Count, Sum

from masters.models import Client, SugarMill
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster


def _avg_shrinkage_percent(mill_id) -> float:
    records = LogisticsLedger.objects.filter(
        cluster__sugar_mill_id=mill_id,
        variance_percent__isnull=False,
    )
    avg = records.aggregate(v=Avg("variance_percent"))["v"]
    return float(avg or 0.41)


def _avg_lead_days(mill_id) -> int:
    records = LogisticsLedger.objects.filter(
        cluster__sugar_mill_id=mill_id,
        loaded_at__isnull=False,
        received_at__isnull=False,
    )
    total_days = 0
    count = 0
    for record in records[:50]:
        delta = record.received_at - record.loaded_at
        total_days += max(delta.days, 1)
        count += 1
    return max(round(total_days / count), 3) if count else 7


def build_supplier_rankings(order_qty: float, selling_price: float) -> dict:
    order_qty = max(order_qty, 1.0)
    selling_price = max(selling_price, 1.0)

    mills = SugarMill.objects.filter(is_active=True).annotate(
        txn_count=Count("clusters"),
        total_volume=Sum("clusters__purchase_order__volume_mt"),
    )

    rankings = []
    for mill in mills:
        po_stats = PurchaseOrder.objects.filter(cluster__sugar_mill=mill).aggregate(
            avg_purchase=Avg("unit_price"),
            avg_logistics=Avg("cluster__logistics__tracking_fees"),
        )
        avg_purchase = float(po_stats["avg_purchase"] or 0)
        if avg_purchase <= 0:
            continue

        avg_logistics = float(po_stats["avg_logistics"] or 0)
        logistics_per_mt = avg_logistics / order_qty if order_qty else 0
        shrinkage_pct = _avg_shrinkage_percent(mill.id)
        deliverable = order_qty * (1 - shrinkage_pct / 100)
        projected_loss = order_qty - deliverable

        supplier_cost = avg_purchase * order_qty + logistics_per_mt * order_qty
        gross_revenue = selling_price * deliverable
        net_profit = gross_revenue - supplier_cost
        net_margin = (net_profit / gross_revenue * 100) if gross_revenue > 0 else 0

        reliability = min(95, 60 + float(mill.txn_count or 0) * 4)
        price_edge = max(0, min(100, (20000 - avg_purchase) / 200))
        lead_days = _avg_lead_days(mill.id)
        lead_score = max(0, min(100, 100 - lead_days * 5))
        shrink_score = max(0, min(100, 100 - shrinkage_pct * 20))
        score = round((net_margin * 2 + reliability + shrink_score + price_edge + lead_score) / 6)

        rankings.append(
            {
                "id": mill.id,
                "name": mill.name,
                "location": mill.location or "Philippines",
                "purchase_price": avg_purchase,
                "supplier_cost": supplier_cost,
                "deliverable_volume": deliverable,
                "projected_loss": projected_loss,
                "shrinkage_pct": shrinkage_pct,
                "gross_revenue": gross_revenue,
                "net_profit": net_profit,
                "net_profit_m": net_profit / 1_000_000,
                "net_margin": net_margin,
                "lead_days": lead_days,
                "score": score,
                "txn_count": mill.txn_count or 0,
                "total_volume": float(mill.total_volume or 0),
                "reliability": reliability,
                "note": _supplier_note(mill.name, net_margin, shrinkage_pct),
            }
        )

    rankings.sort(key=lambda r: r["net_margin"], reverse=True)
    for idx, row in enumerate(rankings):
        row["rank"] = idx + 1
        row["is_best"] = idx == 0

    best = rankings[0] if rankings else None
    return {
        "order_qty": order_qty,
        "selling_price": selling_price,
        "rankings": rankings[:6],
        "best": best,
        "top_three": rankings[:3],
    }


def _supplier_note(name: str, margin: float, shrinkage: float) -> str:
    if margin >= 15:
        return f"{name} offers strong margin with consistent delivery history."
    if shrinkage > 1:
        return f"{name} shows elevated shrinkage — monitor variance on large orders."
    return f"{name} is price-competitive but margin is below target on current sell price."


def partner_stats() -> dict:
    from finance.models import Invoice

    clients = []
    for client in Client.objects.filter(is_active=True).annotate(
        txn_count=Count("clusters"),
        total_volume=Sum("clusters__purchase_order__volume_mt"),
    ):
        invoices = Invoice.objects.filter(cluster__client=client)
        total_invoiced = float(invoices.aggregate(total=Sum("amount"))["total"] or 0)
        paid_invoiced = float(invoices.filter(status=Invoice.Status.PAID).aggregate(total=Sum("amount"))["total"] or 0)
        pending_invoiced = total_invoiced - paid_invoiced
        paid_ratio = round((paid_invoiced / total_invoiced * 100), 1) if total_invoiced > 0 else 100.0

        clients.append(
            {
                "id": client.id,
                "name": client.name,
                "tin": client.tin or "N/A",
                "address": client.address or "Philippines",
                "contact_person": client.contact_person or "Not specified",
                "contact_phone": client.contact_phone or "N/A",
                "type": "Major Buyer",
                "txn_count": client.txn_count or 0,
                "total_volume": float(client.total_volume or 0),
                "total_invoiced": total_invoiced,
                "paid_invoiced": paid_invoiced,
                "pending_invoiced": pending_invoiced,
                "paid_ratio": paid_ratio,
                "is_active": client.is_active,
                "avatar_url": client.avatar.url if client.avatar else "",
            }
        )

    suppliers = []
    for mill in SugarMill.objects.filter(is_active=True).annotate(
        txn_count=Count("clusters"),
        total_volume=Sum("clusters__purchase_order__volume_mt"),
    ):
        shrinkage_pct = _avg_shrinkage_percent(mill.id)
        lead_days = _avg_lead_days(mill.id)
        reliability = min(95, round(60 + float(mill.txn_count or 0) * 4))

        suppliers.append(
            {
                "id": mill.id,
                "name": mill.name,
                "location": mill.location or "Philippines",
                "contact_person": mill.contact_person or "Not specified",
                "contact_phone": mill.contact_phone or "N/A",
                "type": "Sugar Mill" if "URC" not in mill.name.upper() else "Import Source",
                "txn_count": mill.txn_count or 0,
                "total_volume": float(mill.total_volume or 0),
                "shrinkage_pct": shrinkage_pct,
                "lead_days": lead_days,
                "reliability": reliability,
                "is_active": mill.is_active,
                "avatar_url": mill.avatar.url if mill.avatar else "",
            }
        )

    return {"clients": clients, "suppliers": suppliers}
