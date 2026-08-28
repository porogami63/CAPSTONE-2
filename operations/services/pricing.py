"""Financial metrics and mathematical formula derivations for transaction clusters."""

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
    """Return comprehensive volume, pricing, profit, tax breakdown, and explicit mathematical formulas."""
    po = getattr(cluster, "purchase_order", None)
    logistics = getattr(cluster, "logistics", None)
    invoices = list(cluster.invoices.all()) if hasattr(cluster, "invoices") else []
    primary_invoice = invoices[0] if invoices else None

    volume = Decimal("0")
    purchase_price = Decimal("0")
    selling_price = Decimal("0")

    tracking_fees = Decimal("0")
    barge_fees = Decimal("0")
    logistics_cost = Decimal("0")

    loaded_vol = Decimal("0")
    received_vol = Decimal("0")

    trucking_partner_name = "—"
    barge_partner_name = "—"

    if po:
        volume = po.volume_mt or Decimal("0")
        purchase_price = po.unit_price or Decimal("0")
        selling_price = po.selling_price or _parse_selling_from_terms(po.terms) or Decimal("0")

    if logistics:
        loaded_vol = logistics.loaded_volume_mt or Decimal("0")
        received_vol = logistics.received_volume_mt if logistics.received_volume_mt is not None else loaded_vol
        tracking_fees = logistics.tracking_fees or Decimal("0")
        barge_fees = logistics.barge_fees or Decimal("0")
        logistics_cost = logistics.total_logistics_cost

        # Partner names
        if logistics.trucking_partner:
            trucking_partner_name = logistics.trucking_partner.name
        elif logistics.partner:
            trucking_partner_name = logistics.partner.name

        if logistics.barge_partner:
            barge_partner_name = logistics.barge_partner.name
        elif logistics.partner:
            barge_partner_name = logistics.partner.name

    if volume <= 0 and loaded_vol > 0:
        volume = loaded_vol

    revenue = Decimal("0")
    vat_amount = Decimal("0")
    ewt_amount = Decimal("0")
    net_after_tax = Decimal("0")

    if primary_invoice and primary_invoice.amount:
        revenue = primary_invoice.amount
        vat_amount = primary_invoice.vat_amount
        ewt_amount = primary_invoice.ewt_amount
        net_after_tax = primary_invoice.net_amount_after_tax
        if volume > 0 and selling_price <= 0:
            selling_price = revenue / volume
    elif selling_price > 0 and volume > 0:
        revenue = selling_price * volume
        divisor = Decimal("1.12")
        vat_amount = (revenue - (revenue / divisor)).quantize(Decimal("0.01"))
        ewt_amount = ((revenue / divisor) * Decimal("0.01")).quantize(Decimal("0.01"))
        net_after_tax = revenue - ewt_amount

    purchase_total = purchase_price * volume if volume > 0 else Decimal("0")
    if revenue <= 0 and purchase_total > 0:
        revenue = purchase_total

    profit = revenue - purchase_total - logistics_cost
    margin = Decimal("0")
    if revenue > 0:
        margin = (profit / revenue) * Decimal("100")

    # Shrinkage
    shrinkage_mt = max(loaded_vol - received_vol, Decimal("0")) if loaded_vol > 0 and received_vol > 0 else Decimal("0")
    shrinkage_pct = (shrinkage_mt / loaded_vol * Decimal("100")) if loaded_vol > 0 else Decimal("0")

    # Derivations (Step-by-step arithmetic formulas)
    sourcing_formula = f"{volume:,.3f} MT × ₱{purchase_price:,.2f}/MT = ₱{purchase_total:,.2f}"
    freight_formula = f"₱{tracking_fees:,.2f} (Trucking) + ₱{barge_fees:,.2f} (Barging) = ₱{logistics_cost:,.2f}"
    sales_formula = f"{received_vol:,.3f} MT × ₱{selling_price:,.2f}/MT = ₱{revenue:,.2f}"
    vat_formula = f"₱{revenue:,.2f} × (12 / 112) = ₱{vat_amount:,.2f}"
    ewt_formula = f"(₱{revenue:,.2f} / 1.12) × 1% = ₱{ewt_amount:,.2f}"
    net_sales_formula = f"₱{revenue:,.2f} - ₱{ewt_amount:,.2f} = ₱{net_after_tax:,.2f}"
    profit_formula = f"₱{revenue:,.2f} - ₱{purchase_total:,.2f} - ₱{logistics_cost:,.2f} = ₱{profit:,.2f}"

    return {
        "volume_mt": float(volume),
        "loaded_volume_mt": float(loaded_vol),
        "received_volume_mt": float(received_vol),
        "shrinkage_mt": float(shrinkage_mt),
        "shrinkage_pct": float(shrinkage_pct),
        "purchase_price": float(purchase_price),
        "selling_price": float(selling_price),
        "purchase_total": float(purchase_total),
        "tracking_fees": float(tracking_fees),
        "barge_fees": float(barge_fees),
        "logistics_cost": float(logistics_cost),
        "trucking_partner_name": trucking_partner_name,
        "barge_partner_name": barge_partner_name,
        "revenue": float(revenue),
        "vat_amount": float(vat_amount),
        "ewt_amount": float(ewt_amount),
        "net_after_tax": float(net_after_tax),
        "profit": float(profit),
        "profit_m": float(profit) / 1_000_000,
        "margin": float(margin),
        "order_value": float(purchase_total),
        "invoice_status": primary_invoice.get_status_display() if primary_invoice else None,
        "invoice_number": primary_invoice.invoice_number if primary_invoice else None,

        # Formula strings for debrief transparency
        "sourcing_formula": sourcing_formula,
        "freight_formula": freight_formula,
        "sales_formula": sales_formula,
        "vat_formula": vat_formula,
        "ewt_formula": ewt_formula,
        "net_sales_formula": net_sales_formula,
        "profit_formula": profit_formula,
    }
