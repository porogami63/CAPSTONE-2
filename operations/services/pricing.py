"""Financial metrics and mathematical formula derivations for transaction clusters."""

import re
from decimal import Decimal

from django.db.models import Sum
from finance.models import CapitalLoan, Invoice


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

    # Batch-based logistics accounting: calculate per delivery batch rather than static upfront blanket
    batch_deliveries = list(po.deliveries.all()) if (po and hasattr(po, "deliveries")) else []
    has_batches = bool(batch_deliveries)
    if has_batches:
        loaded_vol = po.total_delivered_mt
        received_vol = po.total_delivered_mt
        tracking_fees = sum((d.trucking_cost for d in batch_deliveries), Decimal("0.00"))
        barge_fees = sum((d.barge_cost for d in batch_deliveries), Decimal("0.00"))
        logistics_cost = tracking_fees + barge_fees

        # Partner names from latest recorded delivery batch
        latest_delivery = batch_deliveries[0] if batch_deliveries else None
        if latest_delivery:
            if latest_delivery.trucking_partner:
                trucking_partner_name = latest_delivery.trucking_partner.name
            if latest_delivery.barge_partner:
                barge_partner_name = latest_delivery.barge_partner.name
    elif logistics:
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
        "net_profit": float(profit),
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

    already_loaned = Decimal("0")
    loans_count = 0
    if hasattr(cluster, "loans"):
        active_approved_statuses = [
            CapitalLoan.Status.ACTIVE,
            CapitalLoan.Status.OVERDUE,
            CapitalLoan.Status.PENDING_SETTLEMENT,
            CapitalLoan.Status.CLOSED,
        ]
        active_loans = cluster.loans.filter(status__in=active_approved_statuses)
        loans_count = active_loans.count()
        agg = active_loans.aggregate(total=Sum("principal"))["total"]
        if agg:
            already_loaned = Decimal(str(agg)).quantize(two)

    remaining_required = max(Decimal("0"), required - already_loaned)
    is_complete = (loans_count > 0 and already_loaned >= required - two) if required > 0 else (loans_count > 0)
    completion_pct = float(round(min(Decimal("100.0"), (already_loaned / required * Decimal("100"))), 1)) if required > 0 else (100.0 if loans_count > 0 else 0.0)
    remaining_pct = float(round(max(Decimal("0.0"), Decimal("100.0") - Decimal(str(completion_pct))), 1)) if required > 0 else 0.0

    po = getattr(cluster, "purchase_order", None)
    projected_sales = Decimal("0.00")
    if po and po.total_selling_value:
        projected_sales = Decimal(str(po.total_selling_value)).quantize(two)
    elif fin.get("revenue"):
        projected_sales = Decimal(str(fin["revenue"])).quantize(two)

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
        "projected_sales": projected_sales,
        "already_loaned": already_loaned,
        "remaining_required": remaining_required,
        "is_complete": is_complete,
        "completion_pct": completion_pct,
        "remaining_pct": remaining_pct,
        "loans_count": loans_count,
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

    contract_vol = float(po.total_contracted_mt or po.volume_mt) if po else 0.0
    contract_total = round(selling_price * contract_vol, 2)

    already_invoiced = round(sum(float(inv.amount) for inv in invoices), 2)
    invoices_count = len(invoices)
    remaining_balance = max(0.0, round(contract_total - already_invoiced, 2))

    # Calculate actual recorded shipment deliveries
    has_actual_deliveries = bool(po and hasattr(po, "deliveries") and po.deliveries.exists() and po.total_delivered_mt > 0)
    delivered_mt = float(po.total_delivered_mt) if has_actual_deliveries else 0.0

    legacy_received_vol = float(logistics.received_volume_mt) if logistics and logistics.received_volume_mt is not None else 0.0
    received_vol = delivered_mt if has_actual_deliveries else legacy_received_vol
    received_total = round(selling_price * received_vol, 2) if received_vol > 0 else 0.0
    remaining_received_balance = max(0.0, round(received_total - already_invoiced, 2)) if received_vol > 0 else 0.0

    # Auto-suggestion logic:
    # If shipment deliveries have been recorded and are not yet fully billed, automatically suggest the delivered batch value!
    if has_actual_deliveries and remaining_received_balance > 0:
        suggested_full = remaining_received_balance
    elif remaining_balance > 0:
        suggested_full = remaining_balance
    else:
        suggested_full = contract_total

    has_existing_invoice = invoices_count > 0

    is_complete = (invoices_count > 0 and (remaining_balance <= 0.01 or already_invoiced >= contract_total - 0.01)) if contract_total > 0 else (invoices_count > 0)
    completion_pct = round(min(100.0, (already_invoiced / contract_total * 100)), 1) if contract_total > 0 else (100.0 if invoices_count > 0 else 0.0)
    remaining_pct = round(max(0.0, 100.0 - completion_pct), 1)

    # Parse batch delivery costs and billable logistics fees into generated invoices
    batch_deliveries = list(po.deliveries.all()) if (po and hasattr(po, "deliveries")) else []
    total_batch_logistics = sum((d.total_freight_cost for d in batch_deliveries), Decimal("0.00"))
    total_batch_trucking = sum((d.trucking_cost for d in batch_deliveries), Decimal("0.00"))
    total_batch_barge = sum((d.barge_cost for d in batch_deliveries), Decimal("0.00"))

    already_billed_logistics = sum((inv.logistics_fee for inv in invoices if hasattr(inv, "logistics_fee") and inv.logistics_fee), Decimal("0.00"))
    remaining_batch_logistics = max(Decimal("0.00"), total_batch_logistics - already_billed_logistics)

    batch_breakdown = []
    for d in batch_deliveries:
        short_id = str(d.delivery_id)[:8].upper()
        batch_sugar = (d.delivered_mt * Decimal(str(selling_price))).quantize(Decimal("0.01"))
        batch_breakdown.append({
            "delivery_id": str(d.delivery_id),
            "short_id": short_id,
            "delivered_mt": float(d.delivered_mt),
            "delivery_date": d.delivery_date.strftime("%b %d, %Y") if d.delivery_date else "—",
            "sugar_amount": float(batch_sugar),
            "trucking_cost": float(d.trucking_cost),
            "barge_cost": float(d.barge_cost),
            "total_freight_cost": float(d.total_freight_cost),
            "total_billable": float(batch_sugar + d.total_freight_cost),
            "supplier_name": d.supplier.name if d.supplier else "",
            "receiving_location": d.receiving_location,
        })

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
        "is_complete": is_complete,
        "completion_pct": completion_pct,
        "remaining_pct": remaining_pct,
        "received_volume": received_vol,
        "total_delivered_mt": received_vol,
        "received_total": received_total,
        "delivered_total": received_total,
        "remaining_received_balance": remaining_received_balance,
        "suggested_full": suggested_full,
        "suggested_delivered": remaining_received_balance if remaining_received_balance > 0 else received_total,
        "has_deliveries_to_bill": received_vol > 0 and remaining_received_balance > 0,
        "total_batch_logistics": float(total_batch_logistics),
        "total_batch_trucking": float(total_batch_trucking),
        "total_batch_barge": float(total_batch_barge),
        "already_billed_logistics": float(already_billed_logistics),
        "remaining_batch_logistics": float(remaining_batch_logistics),
        "batch_breakdown": batch_breakdown,
        "suggested_with_logistics": round(suggested_full + float(remaining_batch_logistics), 2),
        "has_batch_logistics_to_bill": float(remaining_batch_logistics) > 0,
        "suggested_50_pct": round(suggested_full * 0.5, 2),
        "suggested_25_pct": round(suggested_full * 0.25, 2),
    }


def get_po_logistics_summary(cluster) -> dict:
    """
    Computes key logistics metrics for the PO View Order Details screen:
    - Total Incurred Logistics Expense: Sum of all recorded logistics expenses from dispatched/completed batches to date.
    - Status Indicator: 'Completed' or 'In Progress / Ongoing'.
    - Projected Total Logistics Expense:
      If ongoing: [Total Incurred Logistics Expense] + (Remaining Undelivered PO Items * Average Batch Rate)
      If completed: Total Incurred Logistics Expense.
    """
    from operations.models import PurchaseOrder

    po = getattr(cluster, "purchase_order", None)
    deliveries = list(po.deliveries.all()) if po and hasattr(po, "deliveries") else []

    total_incurred = sum((d.total_freight_cost for d in deliveries), Decimal("0.00"))
    total_trucking_incurred = sum((d.trucking_cost for d in deliveries), Decimal("0.00"))
    total_barge_incurred = sum((d.barge_cost for d in deliveries), Decimal("0.00"))

    total_delivered_mt = po.total_delivered_mt if po else Decimal("0.000")
    contracted = (po.total_contracted_mt or po.volume_mt or Decimal("0.000")) if po else Decimal("0.000")
    remaining_undelivered_mt = po.remaining_mt if po else Decimal("0.000")

    is_completed = (po.po_status == PurchaseOrder.POStatus.COMPLETED) if po else False
    if not is_completed and remaining_undelivered_mt <= Decimal("0.000") and total_delivered_mt > Decimal("0.000"):
        is_completed = True

    status_indicator = "Completed" if is_completed else "In Progress / Ongoing"

    # Average / Estimated Batch Rate per MT (across recorded delivery batches)
    if total_delivered_mt > Decimal("0.000"):
        avg_rate_per_mt = (total_incurred / total_delivered_mt).quantize(Decimal("0.01"))
    else:
        avg_rate_per_mt = Decimal("0.00")

    if is_completed:
        projected_remaining = Decimal("0.00")
        projected_total = total_incurred
    else:
        projected_remaining = (remaining_undelivered_mt * avg_rate_per_mt).quantize(Decimal("0.01"))
        projected_total = (total_incurred + projected_remaining).quantize(Decimal("0.01"))

    return {
        "total_incurred": total_incurred,
        "total_trucking_incurred": total_trucking_incurred,
        "total_barge_incurred": total_barge_incurred,
        "status_indicator": status_indicator,
        "is_completed": is_completed,
        "total_delivered_mt": total_delivered_mt,
        "total_contracted_mt": contracted,
        "remaining_undelivered_mt": remaining_undelivered_mt,
        "avg_rate_per_mt": avg_rate_per_mt,
        "projected_remaining": projected_remaining,
        "projected_total": projected_total,
        "batch_count": len(deliveries),
    }

