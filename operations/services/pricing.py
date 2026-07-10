"""Financial metrics for transaction clusters derived from stored records."""

import re
from decimal import Decimal

from finance.models import Invoice


def _parse_selling_from_terms(terms: str) -> Decimal | None:
    if not terms:
        return None
    match = re.search(r"Selling\s*₱?\s*([\d,.]+)", terms, re.IGNORECASE)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except Exception:
        return None


def cluster_financials(cluster) -> dict:
    """Return volume, pricing, profit, and margin for a transaction cluster."""
    po = getattr(cluster, "purchase_order", None)
    logistics = getattr(cluster, "logistics", None)
    primary_invoice = cluster.invoices.first() if hasattr(cluster, "invoices") else None

    volume = Decimal("0")
    purchase_price = Decimal("0")
    selling_price = Decimal("0")
    logistics_cost = Decimal("0")

    if po:
        volume = po.volume_mt or Decimal("0")
        purchase_price = po.unit_price or Decimal("0")
        selling_price = _parse_selling_from_terms(po.terms) or Decimal("0")

    if volume <= 0 and logistics:
        volume = logistics.loaded_volume_mt or Decimal("0")

    if logistics:
        logistics_cost = logistics.total_logistics_cost

    revenue = Decimal("0")
    if primary_invoice and primary_invoice.amount:
        revenue = primary_invoice.amount
        if volume > 0 and selling_price <= 0:
            selling_price = revenue / volume
    elif selling_price > 0 and volume > 0:
        revenue = selling_price * volume

    purchase_total = purchase_price * volume if volume > 0 else Decimal("0")
    if revenue <= 0 and purchase_total > 0:
        revenue = purchase_total

    profit = revenue - purchase_total - logistics_cost
    margin = Decimal("0")
    if revenue > 0:
        margin = (profit / revenue) * Decimal("100")

    return {
        "volume_mt": float(volume),
        "purchase_price": float(purchase_price),
        "selling_price": float(selling_price),
        "revenue": float(revenue),
        "purchase_total": float(purchase_total),
        "logistics_cost": float(logistics_cost),
        "profit": float(profit),
        "profit_m": float(profit) / 1_000_000,
        "margin": float(margin),
        "order_value": float(purchase_total),
        "invoice_status": primary_invoice.get_status_display() if primary_invoice else None,
        "invoice_number": primary_invoice.invoice_number if primary_invoice else None,
    }
