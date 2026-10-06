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
        volume = Decimal(str(po.volume_mt)) if po.volume_mt is not None else Decimal("0")
        purchase_price = Decimal(str(po.unit_price)) if po.unit_price is not None else Decimal("0")
        selling_price = Decimal(str(po.selling_price)) if po.selling_price is not None else (_parse_selling_from_terms(po.terms) or Decimal("0"))

    if logistics:
        loaded_vol = Decimal(str(logistics.loaded_volume_mt)) if logistics.loaded_volume_mt is not None else Decimal("0")
        received_vol = Decimal(str(logistics.received_volume_mt)) if logistics.received_volume_mt is not None else loaded_vol
        tracking_fees = Decimal(str(logistics.tracking_fees)) if logistics.tracking_fees is not None else Decimal("0")
        barge_fees = Decimal(str(logistics.barge_fees)) if logistics.barge_fees is not None else Decimal("0")
        logistics_cost = Decimal(str(logistics.total_logistics_cost))

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


LOGISTICS_DOWN_PAYMENT_PCT = Decimal("50")


def loan_requirement_data(cluster) -> dict:
    """Minimum capital a loan must cover for a transaction.

    Required principal = 50% down payment on Trucking + 50% down payment on Freight (barging)
    + 100% of Sourcing cost. Trucking and Freight are kept as separate line items.
    """
    fin = cluster_financials(cluster)
    two = Decimal("0.01")
    pct = LOGISTICS_DOWN_PAYMENT_PCT / Decimal("100")

    sourcing = Decimal(str(fin["purchase_total"])).quantize(two)
    trucking = Decimal(str(fin["tracking_fees"])).quantize(two)
    freight = Decimal(str(fin["barge_fees"])).quantize(two)
    trucking_dp = (trucking * pct).quantize(two)
    freight_dp = (freight * pct).quantize(two)
    required = sourcing + trucking_dp + freight_dp

    return {
        "cluster_id": str(cluster.pk),
        "ref": cluster.reference_code,
        "volume_mt": fin["volume_mt"],
        "down_payment_pct": float(LOGISTICS_DOWN_PAYMENT_PCT),
        "sourcing": sourcing,
        "trucking": trucking,
        "freight": freight,
        "trucking_down_payment": trucking_dp,
        "freight_down_payment": freight_dp,
        "required": required,
        "has_data": required > 0,
        "formula": (
            f"₱{sourcing:,.2f} (Sourcing, 100%) + ₱{trucking_dp:,.2f} (Trucking {LOGISTICS_DOWN_PAYMENT_PCT:g}% of ₱{trucking:,.2f}) "
            f"+ ₱{freight_dp:,.2f} (Freight {LOGISTICS_DOWN_PAYMENT_PCT:g}% of ₱{freight:,.2f}) = ₱{required:,.2f}"
        ),
    }


def get_invoice_suggestion_data(cluster) -> dict:
    """Computes suggestive pricing insights for sales invoice issuance based on initial PO selling price and partial invoice history."""
    po = getattr(cluster, "purchase_order", None)
    logistics = getattr(cluster, "logistics", None)
    invoices = list(cluster.invoices.all()) if hasattr(cluster, "invoices") else []

    selling_price = float(po.selling_price) if po and po.selling_price else 0.0
    if selling_price <= 0 and po and po.terms:
        parsed = _parse_selling_from_terms(po.terms)
        if parsed:
            selling_price = float(parsed)

    contract_vol = float(po.volume_mt) if po and po.volume_mt else 0.0
    contract_total = round(selling_price * contract_vol, 2)

    already_invoiced = round(sum(float(inv.amount) for inv in invoices), 2)
    invoices_count = len(invoices)
    remaining_balance = max(0.0, round(contract_total - already_invoiced, 2))

    received_vol = float(logistics.received_volume_mt) if logistics and logistics.received_volume_mt is not None else 0.0
    received_total = round(selling_price * received_vol, 2) if received_vol > 0 else 0.0
    remaining_received_balance = max(0.0, round(received_total - already_invoiced, 2)) if received_vol > 0 else 0.0

    suggested_full = remaining_balance if (already_invoiced > 0 or remaining_balance > 0) else contract_total

    has_existing_invoice = invoices_count > 0

    return {
        "cluster_id": str(cluster.id) if hasattr(cluster, "id") else None,
        "ref": cluster.reference_code,
        "client_name": cluster.client.name if hasattr(cluster, "client") and cluster.client else "Customer",
        "selling_price": selling_price,
        "contract_volume": contract_vol,
        "contract_total": contract_total,
        "already_invoiced": already_invoiced,
        "invoices_count": invoices_count,
        "has_existing_invoice": has_existing_invoice,
        "incremental_required": has_existing_invoice,
        "remaining_balance": remaining_balance,
        "received_volume": received_vol,
        "received_total": received_total,
        "remaining_received_balance": remaining_received_balance,
        "suggested_full": suggested_full,
        "suggested_received": remaining_received_balance if remaining_received_balance > 0 else received_total,
        "suggested_50_pct": round(suggested_full * 0.5, 2),
        "suggested_25_pct": round(suggested_full * 0.25, 2),
    }

