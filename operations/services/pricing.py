"""Financial metrics and mathematical formula derivations for transaction clusters."""

import re
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
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
    # Consider all non-returned invoices with an amount
    valid_invoices = [inv for inv in invoices if inv.amount and getattr(inv, "status", None) != "returned"]
    primary_invoice = valid_invoices[0] if valid_invoices else (invoices[0] if invoices else None)

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
        loaded_vol = po.total_dispatched_mt if hasattr(po, "total_dispatched_mt") and po.total_dispatched_mt > Decimal("0") else po.total_delivered_mt
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

    if valid_invoices:
        revenue = sum((Decimal(str(inv.amount)) for inv in valid_invoices), Decimal("0"))
        vat_amount = sum((Decimal(str(inv.vat_amount)) for inv in valid_invoices if inv.vat_amount is not None), Decimal("0"))
        ewt_amount = sum((Decimal(str(inv.ewt_amount)) for inv in valid_invoices if inv.ewt_amount is not None), Decimal("0"))
        net_after_tax = sum((Decimal(str(inv.net_amount_after_tax)) for inv in valid_invoices if inv.net_amount_after_tax is not None), Decimal("0"))
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
    if len(valid_invoices) > 1:
        inv_breakdown = " + ".join(f"₱{inv.amount:,.2f} [{inv.invoice_number}]" for inv in valid_invoices)
        sales_formula = f"{inv_breakdown} = ₱{revenue:,.2f} ({len(valid_invoices)} Invoices)"
    elif len(valid_invoices) == 1 and selling_price > 0:
        expected_calc = (received_vol * selling_price).quantize(Decimal("0.01")) if received_vol > 0 else Decimal("0")
        if expected_calc > 0 and abs(revenue - expected_calc) <= Decimal("1.00"):
            sales_formula = f"{received_vol:,.3f} MT × ₱{selling_price:,.2f}/MT = ₱{revenue:,.2f}"
        else:
            sales_formula = f"{valid_invoices[0].invoice_number}: ₱{revenue:,.2f}"
    else:
        sales_formula = f"{received_vol:,.3f} MT × ₱{selling_price:,.2f}/MT = ₱{revenue:,.2f}"

    vat_formula = f"₱{revenue:,.2f} × (12 / 112) = ₱{vat_amount:,.2f}"
    ewt_formula = f"(₱{revenue:,.2f} / 1.12) × 1% = ₱{ewt_amount:,.2f}"
    net_sales_formula = f"₱{revenue:,.2f} - ₱{ewt_amount:,.2f} = ₱{net_after_tax:,.2f}"
    profit_formula = f"₱{revenue:,.2f} - ₱{purchase_total:,.2f} - ₱{logistics_cost:,.2f} = ₱{profit:,.2f}"

    invoice_numbers = [inv.invoice_number for inv in valid_invoices if inv.invoice_number] or [inv.invoice_number for inv in invoices if inv.invoice_number]
    invoice_number_display = ", ".join(invoice_numbers) if invoice_numbers else (primary_invoice.invoice_number if primary_invoice else None)

    if len(valid_invoices) > 1:
        statuses = set(inv.status for inv in valid_invoices)
        if len(statuses) == 1:
            invoice_status = valid_invoices[0].get_status_display()
        elif any(inv.status == "paid" for inv in valid_invoices):
            invoice_status = "Partially Paid"
        else:
            invoice_status = "Multiple Invoices"
    elif primary_invoice:
        invoice_status = primary_invoice.get_status_display()
    else:
        invoice_status = None

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
        "invoice_status": invoice_status,
        "invoice_number": invoice_number_display,
        "invoices_count": len(valid_invoices) if valid_invoices else len(invoices),

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


def get_logistics_reconciliation_ledger(cluster) -> dict:
    """Computes a dynamic running ledger tracking the 2-milestone logistics workflow:

    1. Down Payment (50%): Released/reconciled upfront upon order placement or logistics booking.
    2. Final Balance (50% Post-Delivery): Released/reconciled only after physical receipt and confirmation of delivered goods.
    3. Dynamic Batch Reconciliation: Tracks per-batch confirmed deliveries, balance released per batch, and remaining undisbursed funds.
    """
    fin = cluster_financials(cluster)
    two = Decimal("0.01")
    pct_dp = LOGISTICS_DOWN_PAYMENT_PCT / Decimal("100")

    sourcing = Decimal(str(fin["purchase_total"])).quantize(two)
    trucking = Decimal(str(fin["tracking_fees"])).quantize(two)
    freight = Decimal(str(fin["barge_fees"])).quantize(two)
    logistics_total = (trucking + freight).quantize(two)

    # Milestone 1: 50% Upfront Down Payment Budget
    dp_budget = (logistics_total * pct_dp).quantize(two)
    # Milestone 2: 50% Post-Delivery Balance Pool
    balance_pool_budget = (logistics_total - dp_budget).quantize(two)
    suggested_loan = (sourcing + logistics_total).quantize(two)

    reconciliation = getattr(cluster, "reconciliation", None)
    matches = list(reconciliation.matches.all()) if reconciliation else []

    # Matches allocated to Milestone 1 (50% Upfront Down Payment)
    dp_matches = [
        m for m in matches
        if m.expense_type == "logistics_deposit"
        or m.payment_reference.startswith("DEP-")
        or m.payment_reference.startswith("CV-LOG-DP")
    ]
    dp_paid = sum((m.amount for m in dp_matches), Decimal("0.00")).quantize(two)
    dp_remaining = max(Decimal("0.00"), dp_budget - dp_paid)
    dp_pct = round(float(dp_paid / dp_budget * 100), 1) if dp_budget > 0 else 100.0
    if dp_paid >= (dp_budget - two) and dp_budget > 0:
        dp_status = "Paid"
        dp_badge = "success"
    elif dp_paid > Decimal("0.00"):
        dp_status = "Partially Paid"
        dp_badge = "warning"
    else:
        dp_status = "Pending Upfront Payment"
        dp_badge = "secondary"

    # Dynamic Batch Deliveries Breakdown
    po = getattr(cluster, "purchase_order", None)
    deliveries = list(po.deliveries.all().order_by("delivery_date", "created_at")) if (po and hasattr(po, "deliveries")) else []

    batch_rows = []
    total_batch_freight = Decimal("0.00")
    total_batch_balances_reconciled = Decimal("0.00")
    today = timezone.localdate()

    for d in deliveries:
        short_id = str(d.delivery_id)[:8].upper()
        b_truck = d.trucking_cost
        b_barge = d.barge_cost
        b_total = (b_truck + b_barge).quantize(two)
        total_batch_freight += b_total

        b_dp_covered = (b_total * pct_dp).quantize(two)
        b_bal_due = (b_total - b_dp_covered).quantize(two)

        # Check physical receipt confirmation
        is_confirmed = bool(d.received_at or (d.delivery_date and d.delivery_date <= today))
        if d.received_at:
            confirmation_date_display = d.received_at.strftime("%b %d, %Y %H:%M")
        elif d.delivery_date:
            confirmation_date_display = d.delivery_date.strftime("%b %d, %Y")
        else:
            confirmation_date_display = "—"

        # Find matches for this batch's final balance
        b_matches = [
            m for m in matches
            if short_id in m.payment_reference and m not in dp_matches
        ]
        b_reconciled = sum((m.amount for m in b_matches), Decimal("0.00")).quantize(two)
        total_batch_balances_reconciled += b_reconciled
        b_remaining = max(Decimal("0.00"), b_bal_due - b_reconciled)

        if b_reconciled >= (b_bal_due - two) and b_bal_due > 0:
            b_status = "Reconciled (100% Paid)"
            b_badge = "success"
        elif is_confirmed:
            b_status = "Delivered — Ready for Balance Match"
            b_badge = "primary"
        else:
            b_status = "In Transit — Pending Receipt Confirmation"
            b_badge = "secondary"

        batch_rows.append({
            "delivery_id": str(d.delivery_id),
            "short_id": short_id,
            "dr_number": d.dr_number or "—",
            "delivered_mt": float(d.delivered_mt),
            "location": d.receiving_location or "Destination",
            "delivery_date": d.delivery_date.strftime("%b %d, %Y") if d.delivery_date else "—",
            "received_at": d.received_at.strftime("%b %d, %Y %H:%M") if d.received_at else None,
            "is_confirmed": is_confirmed,
            "confirmation_date_display": confirmation_date_display,
            "trucking_cost": float(b_truck),
            "barge_cost": float(b_barge),
            "batch_logistics_cost": float(b_total),
            "batch_downpayment_covered": float(b_dp_covered),
            "batch_balance_due": float(b_bal_due),
            "reconciled_amount": float(b_reconciled),
            "remaining_due": float(b_remaining),
            "status": b_status,
            "badge": b_badge,
            "suggested_match_ref": f"BAL-DEL-{short_id}",
            "suggested_match_label": f"Batch #{short_id} 50% Balance",
        })

    # Milestone 2: 50% Post-Delivery Balance Pool Tracking
    general_bal_matches = [
        m for m in matches
        if (m.expense_type in ["logistics_balance", "trucking", "barge"] or m.payment_reference.startswith("BAL-"))
        and m not in dp_matches
    ]
    pool_reconciled = max(
        total_batch_balances_reconciled,
        sum((m.amount for m in general_bal_matches), Decimal("0.00")).quantize(two),
    )
    pool_remaining = max(Decimal("0.00"), balance_pool_budget - pool_reconciled)
    pool_pct = round(float(pool_reconciled / balance_pool_budget * 100), 1) if balance_pool_budget > 0 else 100.0

    if pool_reconciled >= (balance_pool_budget - two) and balance_pool_budget > 0:
        pool_status = "Fully Reconciled"
        pool_badge = "success"
    elif pool_reconciled > Decimal("0.00"):
        pool_status = "Partially Reconciled"
        pool_badge = "warning"
    else:
        pool_status = "Pending Delivery Reconciliations"
        pool_badge = "secondary"

    total_logistics_reconciled = dp_paid + pool_reconciled
    total_undisbursed = max(Decimal("0.00"), logistics_total - total_logistics_reconciled)

    return {
        "cluster_ref": cluster.reference_code,
        "sourcing_price": float(sourcing),
        "logistics_price": float(logistics_total),
        "trucking_price": float(trucking),
        "barge_price": float(freight),
        "suggested_loan_amount": float(suggested_loan),
        "loan_formula": f"₱{sourcing:,.2f} (Sourcing, 100%) + ₱{logistics_total:,.2f} (Logistics, 100%) = ₱{suggested_loan:,.2f}",

        # Milestone 1: 50% Upfront Down Payment
        "down_payment_budget": float(dp_budget),
        "down_payment_paid": float(dp_paid),
        "down_payment_remaining": float(dp_remaining),
        "down_payment_pct_paid": dp_pct,
        "down_payment_status": dp_status,
        "down_payment_badge": dp_badge,

        # Milestone 2: 50% Post-Delivery Balance Pool
        "final_balance_pool": float(balance_pool_budget),
        "balance_pool_reconciled": float(pool_reconciled),
        "balance_pool_remaining": float(pool_remaining),
        "balance_pool_pct_reconciled": pool_pct,
        "balance_pool_status": pool_status,
        "balance_pool_badge": pool_badge,

        # Overall Undisbursed Logistics Funds
        "total_logistics_budget": float(logistics_total),
        "total_logistics_reconciled": float(total_logistics_reconciled),
        "total_undisbursed_funds": float(total_undisbursed),

        # Batches
        "batches": batch_rows,
        "has_batches": len(batch_rows) > 0,
        "batches_count": len(batch_rows),
    }


def loan_requirement_data(cluster) -> dict:
    """Calculate suggested loan amount and logistics payment milestones.

    Suggested Loan Amount Rule:
    Suggested Loan Amount = (100% * Sourcing Price) + (100% * Logistics Price).
    No discounts, partial ratios, or LTV reductions are applied to the suggested loan amount.

    Logistics Payment & Reconciliation Rules:
    Split the total Logistics Payment into two equal 50% milestones:
    1. Down Payment (50%): Released/reconciled upfront upon order placement or logistics booking.
    2. Final Balance (50% Post-Delivery): Released/reconciled only after physical receipt and confirmation of delivered goods.
    """
    fin = cluster_financials(cluster)
    two = Decimal("0.01")
    pct = LOGISTICS_DOWN_PAYMENT_PCT / Decimal("100")

    sourcing = Decimal(str(fin["purchase_total"])).quantize(two)
    trucking = Decimal(str(fin["tracking_fees"])).quantize(two)
    freight = Decimal(str(fin["barge_fees"])).quantize(two)
    logistics_total = (trucking + freight).quantize(two)

    # 100% Sourcing + 100% Logistics (Suggested Loan Amount)
    required = (sourcing + logistics_total).quantize(two)

    # Milestone 1: 50% Upfront Down Payment
    trucking_dp = (trucking * pct).quantize(two)
    freight_dp = (freight * pct).quantize(two)
    logistics_dp = (logistics_total * pct).quantize(two)

    # Milestone 2: 50% Post-Delivery Balance Pool
    logistics_balance = (logistics_total - logistics_dp).quantize(two)

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

    ledger = get_logistics_reconciliation_ledger(cluster)

    return {
        "cluster_id": str(cluster.pk),
        "ref": cluster.reference_code,
        "volume_mt": fin["volume_mt"],
        "down_payment_pct": float(LOGISTICS_DOWN_PAYMENT_PCT),
        "sourcing": sourcing,
        "sourcing_price": sourcing,
        "trucking": trucking,
        "freight": freight,
        "logistics_total": logistics_total,
        "logistics_price": logistics_total,
        "trucking_down_payment": trucking_dp,
        "freight_down_payment": freight_dp,
        "logistics_down_payment": logistics_dp,
        "logistics_balance": logistics_balance,
        "required": required,
        "suggested_loan_amount": required,
        "projected_sales": projected_sales,
        "already_loaned": already_loaned,
        "remaining_required": remaining_required,
        "is_complete": is_complete,
        "completion_pct": completion_pct,
        "remaining_pct": remaining_pct,
        "loans_count": loans_count,
        "has_data": required > 0,
        "formula": (
            f"₱{sourcing:,.2f} (Sourcing, 100%) + ₱{logistics_total:,.2f} "
            f"(Logistics, 100%: ₱{trucking:,.2f} Trucking + ₱{freight:,.2f} Barging) = ₱{required:,.2f}"
        ),
        "ledger": ledger,
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

    valid_invoices = [inv for inv in invoices if getattr(inv, "status", None) != "returned"]
    already_invoiced = round(sum(float(inv.amount) for inv in valid_invoices if inv.amount), 2)
    invoices_count = len(valid_invoices)
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
        "suggested_delivered": remaining_received_balance if remaining_received_balance > 0 else 0.0,
        "has_deliveries_to_bill": received_vol > 0 and remaining_received_balance > 0 and not has_existing_invoice,
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


def get_executive_financial_summary(cluster) -> dict:
    """Computes a comprehensive Total PO Expense Audit covering:
    - Money Spent for Sourcing (Sugar Mill procurement)
    - Money Spent for Delivery / Land Trucking (referenced from delivery batches)
    - Money Spent for Barge / Marine Freight (referenced from delivery batches)
    - Per-Delivery-Batch Expense & Disbursement Reference Breakdown
    - Total PO Expenses Incurred vs. Money Spent vs. Remaining Unpaid Balance
    """
    fin = cluster_financials(cluster)
    two = Decimal("0.01")
    po = getattr(cluster, "purchase_order", None)
    deliveries = list(po.deliveries.select_related("supplier", "trucking_partner", "barge_partner", "carrier").all()) if (po and hasattr(po, "deliveries")) else []

    unit_price = (po.unit_price if po and po.unit_price else Decimal("0.00")).quantize(two)
    sourcing_budget = Decimal(str(fin["purchase_total"])).quantize(two)

    # Batch-referenced delivery (trucking) and barge expenses
    batch_trucking_incurred = sum((d.trucking_cost for d in deliveries), Decimal("0.00")).quantize(two)
    batch_barge_incurred = sum((d.barge_cost for d in deliveries), Decimal("0.00")).quantize(two)
    batch_sourcing_incurred = sum(((d.delivered_mt * unit_price).quantize(two) for d in deliveries), Decimal("0.00")).quantize(two)
    total_delivered_mt = sum((d.delivered_mt for d in deliveries), Decimal("0.000"))

    trucking_budget = Decimal(str(fin["tracking_fees"])).quantize(two)
    barge_budget = Decimal(str(fin["barge_fees"])).quantize(two)
    logistics_budget = (trucking_budget + barge_budget).quantize(two)
    total_budget = (sourcing_budget + logistics_budget).quantize(two)

    reconciliation = getattr(cluster, "reconciliation", None)
    matches = list(reconciliation.matches.all()) if reconciliation else []

    # 1. Money Spent for Sourcing
    sourcing_matches = [
        m for m in matches
        if m.expense_type == "sourcing"
        or m.payment_reference.startswith("PO-SRC-")
        or "-SRC" in m.payment_reference
    ]
    sourcing_reconciled = sum((m.amount for m in sourcing_matches), Decimal("0.00")).quantize(two)
    sourcing_remaining_pool = max(Decimal("0.00"), sourcing_budget - sourcing_reconciled)

    # 2. Money Spent for Delivery (Trucking) & Barge (Marine)
    logistics_matches = [m for m in matches if m not in sourcing_matches]
    logistics_reconciled = sum((m.amount for m in logistics_matches), Decimal("0.00")).quantize(two)
    logistics_remaining_pool = max(Decimal("0.00"), logistics_budget - logistics_reconciled)

    trucking_matches = [
        m for m in logistics_matches
        if m.expense_type == "trucking" or "TRK" in (m.payment_reference or "")
    ]
    barge_matches = [
        m for m in logistics_matches
        if m not in trucking_matches and (m.expense_type == "barge" or "BRG" in (m.payment_reference or ""))
    ]
    other_log_matches = [
        m for m in logistics_matches
        if m not in trucking_matches and m not in barge_matches
    ]

    trucking_reconciled = sum((m.amount for m in trucking_matches), Decimal("0.00")).quantize(two)
    barge_reconciled = sum((m.amount for m in barge_matches), Decimal("0.00")).quantize(two)
    other_log_reconciled = sum((m.amount for m in other_log_matches), Decimal("0.00")).quantize(two)

    # Allocate any generic logistics match across trucking/barge proportionally
    if other_log_reconciled > Decimal("0.00"):
        if logistics_budget > Decimal("0.00"):
            trk_share = (other_log_reconciled * (trucking_budget / logistics_budget)).quantize(two)
            brg_share = (other_log_reconciled - trk_share).quantize(two)
            trucking_reconciled = (trucking_reconciled + trk_share).quantize(two)
            barge_reconciled = (barge_reconciled + brg_share).quantize(two)
        else:
            trucking_reconciled = (trucking_reconciled + other_log_reconciled).quantize(two)

    trucking_dp_paid = sum(
        (m.amount for m in trucking_matches if (m.payment_reference or "").startswith("DEP-") or m.expense_type == "logistics_deposit"),
        Decimal("0.00"),
    ).quantize(two)
    barge_dp_paid = sum(
        (m.amount for m in barge_matches if (m.payment_reference or "").startswith("DEP-") or m.expense_type == "logistics_deposit"),
        Decimal("0.00"),
    ).quantize(two)

    trucking_remaining_pool = max(Decimal("0.00"), trucking_budget - trucking_reconciled)
    barge_remaining_pool = max(Decimal("0.00"), barge_budget - barge_reconciled)

    # DP status & Post-delivery balance
    dp_target = (logistics_budget * Decimal("0.50")).quantize(two)
    dp_paid = sum(
        (m.amount for m in logistics_matches if (m.payment_reference or "").startswith("DEP-") or m.expense_type == "logistics_deposit"),
        Decimal("0.00"),
    ).quantize(two)
    dp_reconciled = dp_paid >= (dp_target - two) and dp_target > Decimal("0.00")

    if not dp_reconciled and dp_target > Decimal("0.00"):
        logistics_suggested = min(max(Decimal("0.00"), dp_target - dp_paid), logistics_remaining_pool)
        dp_note = "50% Down Payment"
    else:
        net_50_max = (logistics_budget * Decimal("0.50")).quantize(two)
        logistics_suggested = min(logistics_remaining_pool, net_50_max)
        dp_note = "Net 50% Max"

    sourcing_suggested = sourcing_remaining_pool
    total_reconciled = (sourcing_reconciled + logistics_reconciled).quantize(two)
    total_suggested = (sourcing_suggested + logistics_suggested).quantize(two)
    total_remaining_pool = max(Decimal("0.00"), total_budget - total_reconciled)

    # 3. Per-Delivery-Batch Expense Audit Breakdown
    batch_expenses = []
    rem_trk_dp = trucking_dp_paid
    rem_brg_dp = barge_dp_paid
    rem_src_paid = sourcing_reconciled

    for idx, d in enumerate(deliveries, start=1):
        short_id = str(d.delivery_id)[:8].upper()
        b_src_cost = (d.delivered_mt * unit_price).quantize(two)
        b_trk_cost = d.trucking_cost.quantize(two)
        b_brg_cost = d.barge_cost.quantize(two)
        b_freight_cost = d.total_freight_cost.quantize(two)
        b_total_cost = (b_src_cost + b_freight_cost).quantize(two)

        # Direct batch matches
        direct_trk = sum(
            (m.amount for m in trucking_matches if short_id in (m.payment_reference or "")),
            Decimal("0.00"),
        ).quantize(two)
        direct_brg = sum(
            (m.amount for m in barge_matches if short_id in (m.payment_reference or "")),
            Decimal("0.00"),
        ).quantize(two)
        direct_other = sum(
            (m.amount for m in other_log_matches if short_id in (m.payment_reference or "")),
            Decimal("0.00"),
        ).quantize(two)

        # Allocate DP share (up to 50% of batch trucking/barge)
        trk_dp_alloc = min(rem_trk_dp, (b_trk_cost * Decimal("0.50")).quantize(two))
        rem_trk_dp = max(Decimal("0.00"), rem_trk_dp - trk_dp_alloc)

        brg_dp_alloc = min(rem_brg_dp, (b_brg_cost * Decimal("0.50")).quantize(two))
        rem_brg_dp = max(Decimal("0.00"), rem_brg_dp - brg_dp_alloc)

        src_alloc = min(rem_src_paid, b_src_cost)
        rem_src_paid = max(Decimal("0.00"), rem_src_paid - src_alloc)

        b_trk_spent = min(b_trk_cost, (trk_dp_alloc + direct_trk).quantize(two)) if b_trk_cost > Decimal("0.00") else direct_trk
        b_brg_spent = min(b_brg_cost, (brg_dp_alloc + direct_brg).quantize(two)) if b_brg_cost > Decimal("0.00") else direct_brg
        b_log_spent = (b_trk_spent + b_brg_spent + direct_other).quantize(two)
        b_total_spent = (src_alloc + b_log_spent).quantize(two)
        b_unpaid = max(Decimal("0.00"), b_total_cost - b_total_spent)

        if b_total_cost > Decimal("0.00") and b_total_spent >= (b_total_cost - two):
            b_status = "Reconciled"
            b_badge = "success"
        elif b_total_spent > Decimal("0.00"):
            b_status = "Partially Paid"
            b_badge = "warning"
        else:
            b_status = "Unpaid / Pending"
            b_badge = "secondary"

        trk_partner_name = (
            d.trucking_partner.name if d.trucking_partner
            else (d.carrier.name if d.carrier else "Land Carrier")
        )
        brg_partner_name = (
            d.barge_partner.name if d.barge_partner
            else (getattr(d, "vessel_or_barge_name", "") or "Marine Barge")
        )

        batch_expenses.append({
            "index": idx,
            "short_id": short_id,
            "dr_number": d.dr_number or f"DR-{short_id}",
            "delivery_date": d.delivery_date,
            "supplier_name": d.supplier.name if d.supplier else (cluster.sugar_mill.name if cluster.sugar_mill else "Sugar Mill"),
            "receiving_location": d.receiving_location or "Destination",
            "delivered_mt": d.delivered_mt,
            "trucking_partner_name": trk_partner_name,
            "barge_partner_name": brg_partner_name,
            "sourcing_cost": b_src_cost,
            "sourcing_spent": src_alloc,
            "trucking_cost": b_trk_cost,
            "trucking_spent": b_trk_spent,
            "barge_cost": b_brg_cost,
            "barge_spent": b_brg_spent,
            "total_freight_cost": b_freight_cost,
            "logistics_spent": b_log_spent,
            "total_batch_cost": b_total_cost,
            "total_batch_spent": b_total_spent,
            "remaining_unpaid": b_unpaid,
            "status": b_status,
            "badge": b_badge,
        })

    return {
        "sourcing_budget": sourcing_budget,
        "sourcing_delivered_cost": batch_sourcing_incurred,
        "sourcing_reconciled": sourcing_reconciled,
        "sourcing_suggested": sourcing_suggested,
        "sourcing_remaining_pool": sourcing_remaining_pool,

        "trucking_budget": trucking_budget,
        "batch_trucking_incurred": batch_trucking_incurred,
        "trucking_reconciled": trucking_reconciled,
        "trucking_dp_paid": trucking_dp_paid,
        "trucking_remaining_pool": trucking_remaining_pool,

        "barge_budget": barge_budget,
        "batch_barge_incurred": batch_barge_incurred,
        "barge_reconciled": barge_reconciled,
        "barge_dp_paid": barge_dp_paid,
        "barge_remaining_pool": barge_remaining_pool,

        "logistics_budget": logistics_budget,
        "logistics_reconciled": logistics_reconciled,
        "logistics_suggested": logistics_suggested,
        "logistics_remaining_pool": logistics_remaining_pool,
        "dp_paid": dp_paid,
        "dp_target": dp_target,
        "dp_reconciled": dp_reconciled,
        "dp_note": dp_note,

        "total_budget": total_budget,
        "total_reconciled": total_reconciled,
        "total_suggested": total_suggested,
        "total_remaining_pool": total_remaining_pool,

        "batch_count": len(deliveries),
        "total_delivered_mt": total_delivered_mt,
        "batch_expenses": batch_expenses,
    }


def get_opex_audit_log(cluster) -> list[dict]:
    """Generates a chronological, timestamped Operational Expense Audit Log according to schema:
    1. Timestamp: YYYY-MM-DD HH:MM:SS UTC
    2. Event Type: [Loan Origination | DP Reconciliation | Batch Delivery Payout | Price Warning Override]
    3. Line Item: Category / vendor name
    4. Receiving Customer: Linked customer name (locked to linked PO)
    5. Origin Indicator: Tagged to the Receiving Customer location/destination
    6. Gross / Reconciled Amount: Initial loan origination / transaction disbursement
    7. Remaining Balance Pool: Outstanding funds after event deduction
    8. Status: [Pending | Reconciled | Partial Release | Warning Flagged]
    """
    fin = cluster_financials(cluster)
    two = Decimal("0.01")
    sourcing_budget = Decimal(str(fin["purchase_total"])).quantize(two)
    trucking_budget = Decimal(str(fin["tracking_fees"])).quantize(two)
    barge_budget = Decimal(str(fin["barge_fees"])).quantize(two)
    logistics_budget = (trucking_budget + barge_budget).quantize(two)
    total_budget = (sourcing_budget + logistics_budget).quantize(two)

    po = getattr(cluster, "purchase_order", None)
    customer_obj = getattr(po, "customer", None) or getattr(cluster, "client", None)
    receiving_customer_name = customer_obj.name if customer_obj else "—"
    origin_indicator_tag = getattr(customer_obj, "origin_indicator", f"{receiving_customer_name} Destination Zone") if customer_obj else "Destination Zone"

    loans = list(cluster.loans.all().order_by("created_at")) if hasattr(cluster, "loans") else []
    first_loan = loans[0] if loans else None
    if first_loan and getattr(first_loan, "created_at", None):
        origination_time = first_loan.created_at
    elif cluster and getattr(cluster, "created_at", None):
        origination_time = cluster.created_at
    elif po and getattr(po, "po_date", None):
        origination_time = timezone.datetime.combine(po.po_date, timezone.datetime.min.time(), tzinfo=timezone.utc)
    else:
        origination_time = timezone.now()

    reconciliation = getattr(cluster, "reconciliation", None)
    matches = list(reconciliation.matches.all().order_by("matched_at", "id")) if reconciliation else []

    audit_log = []
    cum_reconciled = Decimal("0.00")
    net_remaining = total_budget

    # 1. Price Warning Override Event (if flagged on cluster or PO)
    has_price_override = False
    override_reason = ""
    if po and po.unit_price and po.selling_price and po.unit_price > po.selling_price:
        has_price_override = True
        delta = po.unit_price - po.selling_price
        override_reason = f"Negative Margin Override (Buying ₱{po.unit_price:,.2f} > Selling ₱{po.selling_price:,.2f}, -₱{delta:,.2f})"
    elif cluster and "Price Warning Override" in (cluster.contract_notes or ""):
        has_price_override = True
        override_reason = "Underwriter Price Warning Override Logged"

    if has_price_override:
        audit_log.append({
            "timestamp": origination_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "timestamp_raw": origination_time,
            "event_type": "Price Warning Override",
            "line_item": f"Pricing Exception: {override_reason}",
            "receiving_customer": receiving_customer_name,
            "origin_indicator": origin_indicator_tag,
            "gross_amount": float(total_budget),
            "reconciled_amount": 0.0,
            "cumulative_reconciled": 0.0,
            "net_remaining_pool": float(net_remaining),
            "remaining_balance_pool": float(net_remaining),
            "status": "Warning Flagged",
            "badge": "danger",
        })

    # 2. Loan Origination Event
    audit_log.append({
        "timestamp": origination_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_raw": origination_time,
        "event_type": "Loan Origination",
        "line_item": f"Approved PO ({po.po_reference_number if po else cluster.reference_code})",
        "receiving_customer": receiving_customer_name,
        "origin_indicator": origin_indicator_tag,
        "gross_amount": float(total_budget),
        "reconciled_amount": 0.0,
        "cumulative_reconciled": 0.0,
        "net_remaining_pool": float(net_remaining),
        "remaining_balance_pool": float(net_remaining),
        "status": "Pending",
        "badge": "secondary",
    })

    # 3. Historical Reconciled Payments
    for m in matches:
        amt = m.amount.quantize(two)
        cum_reconciled = (cum_reconciled + amt).quantize(two)
        net_remaining = max(Decimal("0.00"), total_budget - cum_reconciled).quantize(two)

        ref = m.payment_reference or ""
        exp_type = m.expense_type or ""
        event_time = m.matched_at or m.created_at or origination_time

        if ref.startswith("DEP-") or exp_type == "logistics_deposit":
            event_type = "DP Reconciliation"
            if "TRK" in ref or exp_type == "trucking":
                line_item = "Trucking & Land Delivery (50% DP)"
                gross = trucking_budget
            elif "BRG" in ref or exp_type == "barge":
                line_item = "Marine Barging & Vessel Charter (50% DP)"
                gross = barge_budget
            else:
                line_item = "Trucking & Barging (50% DP)"
                gross = logistics_budget
            status = "Reconciled"
            badge = "primary"
        elif ref.startswith("BAL-DEL-") or ref.startswith("CV-DEL-") or exp_type == "logistics_balance":
            event_type = "Batch Delivery Payout"
            short_id = ref.replace("BAL-DEL-", "").replace("CV-DEL-", "").split("-")[0]
            if "TRK" in ref or exp_type == "trucking":
                line_item = f"Trucking - Batch #{short_id}"
                gross = trucking_budget
            elif "BRG" in ref or exp_type == "barge":
                line_item = f"Barging - Batch #{short_id}"
                gross = barge_budget
            elif "SRC" in ref or exp_type == "sourcing":
                line_item = f"Sourcing - Batch #{short_id}"
                gross = sourcing_budget
            else:
                line_item = f"Delivery Balance - Batch #{short_id}"
                gross = logistics_budget
            status = "Reconciled"
            badge = "success"
        elif exp_type == "sourcing" or ref.startswith("PO-SRC-"):
            event_type = "Sourcing Settlement"
            line_item = f"Sourcing Vendor ({cluster.sugar_mill.name if cluster.sugar_mill else 'Supplier'})"
            gross = sourcing_budget
            status = "Reconciled"
            badge = "success"
        else:
            event_type = "Adjustment"
            line_item = f"{m.get_expense_type_display()} ({ref})"
            gross = amt
            status = "Reconciled"
            badge = "info"

        audit_log.append({
            "timestamp": event_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "timestamp_raw": event_time,
            "event_type": event_type,
            "line_item": line_item,
            "receiving_customer": receiving_customer_name,
            "origin_indicator": origin_indicator_tag,
            "gross_amount": float(gross),
            "reconciled_amount": float(amt),
            "cumulative_reconciled": float(cum_reconciled),
            "net_remaining_pool": float(net_remaining),
            "remaining_balance_pool": float(net_remaining),
            "status": status,
            "badge": badge,
        })

    # 4. Payout Suggestions (Pending post-delivery balance)
    exec_summary = get_executive_financial_summary(cluster)
    if exec_summary["logistics_suggested"] > Decimal("0.00"):
        sugg_time = timezone.now()
        audit_log.append({
            "timestamp": sugg_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "timestamp_raw": sugg_time,
            "event_type": "Payout Suggestion",
            "line_item": f"Post-Delivery Balance ({exec_summary['dp_note']})",
            "receiving_customer": receiving_customer_name,
            "origin_indicator": origin_indicator_tag,
            "gross_amount": float(exec_summary["logistics_budget"]),
            "reconciled_amount": 0.0,
            "cumulative_reconciled": float(cum_reconciled),
            "net_remaining_pool": float(exec_summary["logistics_remaining_pool"]),
            "remaining_balance_pool": float(exec_summary["logistics_remaining_pool"]),
            "status": "Pending",
            "badge": "warning",
        })

    return audit_log
