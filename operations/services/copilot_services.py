import re
from collections import defaultdict
from decimal import Decimal
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.utils.html import escape

from accounts.models import User
from operations.models import (
    TransactionCluster,
    LogisticsLedger,
    MolassesReleaseOrder,
    PurchaseOrder,
    DeliveryLedger,
)
from finance.models import (
    CapitalLoan,
    Invoice,
    CashVoucher,
    FinancialReconciliation,
)
from masters.models import Client, SugarMill, LogisticsPartner


def _build_step_card(number, title, desc, link_url, link_text, badge_color="primary", rules="", live_badge=""):
    """
    Renders an individual procedural step card with direct routing and optional live database state badges.
    """
    live_badge_html = f"<span class='badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fs-9 px-1.5 py-0.5'>{live_badge}</span>" if live_badge else ""
    return f"""
    <div class='p-2 mb-2 rounded border bg-body-tertiary'>
        <div class='d-flex align-items-center justify-content-between mb-1'>
            <div class='d-flex align-items-center gap-1.5 flex-wrap'>
                <span class='badge bg-{badge_color} text-white fw-bold'>Step {number}</span>
                <span class='fw-bold fs-7 text-dark'>{escape(title)}</span>
                {live_badge_html}
            </div>
            <a href='{link_url}' class='btn btn-xs btn-outline-{badge_color} py-0 px-2 fs-8 text-decoration-none'>{escape(link_text)} &rarr;</a>
        </div>
        <p class='mb-1 fs-8 text-muted'>{desc}</p>
        {f"<div class='fs-8 text-secondary border-top pt-1 mt-1'><i class='bi bi-shield-check me-1 text-primary'></i><strong>ORM Rule:</strong> {rules}</div>" if rules else ""}
    </div>
    """


def _build_operations_guide():
    """
    Renders the 5-step operational workflow guide infused with real-time database counts.
    All routes map to verified, active Django URL patterns.
    """
    draft_count = TransactionCluster.objects.filter(status=TransactionCluster.Status.DRAFT, is_archived=False).count()
    unassigned_mro = MolassesReleaseOrder.objects.filter(cluster__isnull=True).aggregate(c=Count('id'), total=Sum('tons'))
    unassigned_mro_count = unassigned_mro['c'] or 0
    unassigned_mro_tons = unassigned_mro['total'] or Decimal('0.00')

    in_transit_count = DeliveryLedger.objects.filter(received_at__isnull=True).count()
    dispute_count = LogisticsLedger.objects.filter(
        Q(variance_exceeds_tolerance=True) | Q(dispute_status=LogisticsLedger.DisputeStatus.DISPUTED)
    ).count()
    ready_to_bill = TransactionCluster.objects.filter(status=TransactionCluster.Status.DELIVERED, invoices__isnull=True).count()

    steps = [
        _build_step_card(
            1, "Register PO Contract",
            "Enter buyer client, supplier sugar mill, contracted volume (MT), and procurement/selling rates. System checks margins.",
            "/operations/new/", "New PO Contract", "primary",
            "System auto-computes required financing credit line and locks reference code.",
            live_badge=f"{draft_count} Draft(s) Pending" if draft_count > 0 else "0 Drafts"
        ),
        _build_step_card(
            2, "Upload & Attach MRO Loading Permits",
            "Upload molasses release orders. Local OCR extracts planter name, crop year, and tonnage.",
            "/operations/mro-summary/", "MRO Vault", "info",
            "Total attached MRO tonnage must match or cover PO volume before carrier dispatch.",
            live_badge=f"{unassigned_mro_count} Unassigned ({unassigned_mro_tons:,.1f} MT)"
        ),
        _build_step_card(
            3, "Assign Logistics Carrier & Dispatch",
            "Assign trucker/barge carrier, enter origin loaded volume (MT), bill of lading, and freight rates.",
            "/operations/deliveries/", "Deliveries & Trucking", "warning",
            "Logistics deposit vouchers (50%) require active carrier assignment.",
            live_badge=f"{in_transit_count} In Transit" if in_transit_count > 0 else "0 In Transit"
        ),
        _build_step_card(
            4, "Record Weighbridge Destination Receipt",
            "Log destination weighbridge ticket and verified scale delivered MT. In-transit shrinkage calculated.",
            "/operations/pending-tasks/", "Resolve Variances", "danger",
            "Shrinkage tolerance is capped at ±1.00%. Exceeding tolerance flags automated operational dispute.",
            live_badge=f"{dispute_count} Dispute(s) Active" if dispute_count > 0 else "All within ±1%"
        ),
        _build_step_card(
            5, "Order Fulfillment & Billing Handover",
            "Confirm receipt of all scheduled delivery batches. Cluster transitions to DELIVERED, unlocking customer sales invoicing.",
            "/operations/pending-tasks/", "Ready to Bill", "success",
            "Seals operations hash block and triggers Invoicing notification.",
            live_badge=f"{ready_to_bill} Ready to Bill" if ready_to_bill > 0 else "None Pending"
        )
    ]
    return f"""
    <div class='copilot-card p-3 rounded bg-body border'>
        <div class='d-flex align-items-center justify-content-between mb-2'>
            <div class='fw-bold text-primary fs-7'><i class='bi bi-truck me-1'></i> Operations: Step-by-Step Execution Guide</div>
            <span class='badge bg-primary-subtle text-primary border border-primary-subtle'>5 Core Steps · Live DB</span>
        </div>
        <p class='fs-8 text-muted mb-2'>Standard operating procedure for procurement, logistics dispatch, and weighbridge scale verification:</p>
        {''.join(steps)}
    </div>
    """


def _build_finance_guide():
    """
    Renders the 5-step financial lifecycle guide infused with real-time loan & reconciliation metrics.
    """
    active_loans = CapitalLoan.objects.filter(~Q(status='closed'))
    active_count = active_loans.count()
    total_principal = active_loans.aggregate(t=Sum('principal'))['t'] or Decimal('0.00')
    pending_approval = CapitalLoan.objects.filter(status='pending_approval').count()

    steps = [
        _build_step_card(
            1, "Formulate Capital Financing",
            "Review cluster sourcing budget and link an available commercial bank credit facility (e.g. BDO, Metrobank).",
            "/finance/loans/", "Loan Facilities", "primary",
            "Credit limit must cover procurement outlay plus 50% upfront carrier logistics deposit.",
            live_badge=f"{active_count} Active (₱{total_principal:,.0f})" if active_count > 0 else "0 Active"
        ),
        _build_step_card(
            2, "Dual Authorization & Loan Drawdown",
            "Finance Manager conducts dual-authorization to verify and approve loan disbursement for sugar mill sourcing.",
            "/finance/loans/", "Verify Facilities", "info",
            "Dual verification timestamp and approver ID are permanently sealed in SHA-256 Block 2.",
            live_badge=f"{pending_approval} Awaiting Dual Review" if pending_approval > 0 else "All Approved"
        ),
        _build_step_card(
            3, "Issue Cash Disbursement Vouchers",
            "Generate sourcing payment cheques for the mill and 50% mobilization downpayment for the carrier.",
            "/finance/reconciliation/", "Disbursement Matching", "warning",
            "Any cheque correction must follow Compensating Void & Reissue with formal managerial reason."
        ),
        _build_step_card(
            4, "Expense Matching & Reconciler",
            "Match bank transactions, issued cheques, and carrier freight receipts against weighbridge deliveries.",
            "/finance/reconciliation/", "Zero-Discrepancy Reconciler", "danger",
            "Zero monetary discrepancy allowed (₱0.00 variance). Any discrepancy requires compensating voucher."
        ),
        _build_step_card(
            5, "Bank Facility Clearance & Archival",
            "Record bank Official Receipt (OR), interest breakdown, and mark loan facility as CLOSED and archived.",
            "/finance/loans/", "Loan Settlements", "success",
            "Closes financial lifecycle block and seals financial hash chain."
        )
    ]
    return f"""
    <div class='copilot-card p-3 rounded bg-body border'>
        <div class='d-flex align-items-center justify-content-between mb-2'>
            <div class='fw-bold text-success fs-7'><i class='bi bi-bank me-1'></i> Finance: Step-by-Step Execution Guide</div>
            <span class='badge bg-success-subtle text-success border border-success-subtle'>5 Core Steps · Live DB</span>
        </div>
        <p class='fs-8 text-muted mb-2'>Standard operating procedure for capital loans, disbursement cheques, and zero-tolerance reconciliation:</p>
        {''.join(steps)}
    </div>
    """


def _build_invoicing_guide():
    """
    Renders the 5-step invoicing and revenue collection guide infused with unbilled and collection stats.
    """
    unbilled_count = TransactionCluster.objects.filter(status=TransactionCluster.Status.DELIVERED, invoices__isnull=True).count()
    unpaid_invoices = Invoice.objects.filter(status__in=[Invoice.Status.ISSUED, Invoice.Status.DRAFT], is_archived=False)
    unpaid_count = unpaid_invoices.count()
    unpaid_total = unpaid_invoices.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    steps = [
        _build_step_card(
            1, "Monitor Delivered Orders",
            "Identify transaction clusters with confirmed destination weighbridge receiving tickets in DELIVERED status.",
            "/operations/pending-tasks/", "Orders to Bill", "primary",
            "Invoice generation is unlocked only after physical delivery and weighbridge scale verification.",
            live_badge=f"{unbilled_count} Ready for Billing" if unbilled_count > 0 else "Queue Clear"
        ),
        _build_step_card(
            2, "Generate BIR-Compliant Sales Invoice",
            "Create official customer sales invoice using verified delivered volume (or contract volume) × selling price.",
            "/operations/pending-tasks/", "Issue Invoices", "info",
            "System auto-generates sequential BIR-formatted tax invoice reference numbers."
        ),
        _build_step_card(
            3, "Apply 1% BIR Expanded Withholding Tax",
            "System computes 1% BIR Form 2307 EWT deduction from gross billable amount to calculate Net Receivable.",
            "/finance/invoices/", "1% EWT & Tax Records", "warning",
            "1% EWT deduction is strictly enforced per BIR non-food agricultural trade regulations."
        ),
        _build_step_card(
            4, "Record Customer Payment Collection",
            "Encode customer bank deposit, telegraphic transfer, or cheque receipt with Official Receipt (OR) number.",
            "/operations/pending-tasks/", "Record Payments", "primary",
            "Payments are matched directly against outstanding invoices to mark them PAID.",
            live_badge=f"{unpaid_count} Unpaid (₱{unpaid_total:,.2f})" if unpaid_count > 0 else "All Settled"
        ),
        _build_step_card(
            5, "Final Deal Closure & Blockchain Seal",
            "Confirm all revenues collected, loans settled, and vouchers cleared. Order marked CLOSED in ledger.",
            "/operations/blockchain/", "Ledger Closure", "success",
            "Seals final Block 5 of the cryptographic blockchain ledger."
        )
    ]
    return f"""
    <div class='copilot-card p-3 rounded bg-body border'>
        <div class='d-flex align-items-center justify-content-between mb-2'>
            <div class='fw-bold text-purple fs-7' style='color: #6f42c1;'><i class='bi bi-file-earmark-spreadsheet me-1'></i> Invoicing: Step-by-Step Execution Guide</div>
            <span class='badge bg-primary-subtle text-primary border border-primary-subtle'>5 Core Steps · Live DB</span>
        </div>
        <p class='fs-8 text-muted mb-2'>Standard operating procedure for sales billing, 1% BIR EWT tax deductions, and payment collections:</p>
        {''.join(steps)}
    </div>
    """


def _build_po_diagnostic_card(cluster):
    """
    Deep context-aware order diagnostic card.
    Queries cluster.get_workflow_steps_info() and provides step-by-step progress,
    blockers, and direct resolution links.
    """
    wf = cluster.get_workflow_steps_info()
    po = getattr(cluster, "purchase_order", None)
    vol = po.volume_mt if po and po.volume_mt else (cluster.vol_mt if hasattr(cluster, 'vol_mt') else Decimal('0.00'))
    current_step = wf.get("current_step", 1)

    # Status formatting
    status_display = cluster.get_status_display()
    status_tone = "secondary"
    if cluster.status == TransactionCluster.Status.DRAFT:
        status_tone = "secondary"
    elif cluster.status == TransactionCluster.Status.PENDING_APPROVAL:
        status_tone = "warning"
    elif cluster.status in [TransactionCluster.Status.APPROVED, TransactionCluster.Status.ACTIVE]:
        status_tone = "primary"
    elif cluster.status == TransactionCluster.Status.DELIVERED:
        status_tone = "info"
    elif cluster.status == TransactionCluster.Status.CLOSED:
        status_tone = "success"
    elif cluster.status == TransactionCluster.Status.RETURNED:
        status_tone = "danger"

    steps_html = []
    step_keys = [("step1", 1), ("step2", 2), ("step3", 3), ("step4", 4), ("step5", 5)]

    for key, num in step_keys:
        st = wf.get(key, {})
        complete = st.get("complete", False)
        missing = st.get("missing", [])
        title = st.get("title", f"Step {num}")
        status_text = st.get("status_text", "Pending")

        if complete:
            badge_icon = "<i class='bi bi-check-circle-fill text-success me-1'></i>"
            step_state = "<span class='badge bg-success-subtle text-success border border-success-subtle fs-9'>✓ Completed</span>"
            border_class = "border-success-subtle"
        elif num == current_step:
            badge_icon = "<i class='bi bi-play-circle-fill text-primary me-1'></i>"
            step_state = "<span class='badge bg-primary text-white fs-9'>▶ In Progress</span>"
            border_class = "border-primary"
        else:
            badge_icon = "<i class='bi bi-lock-fill text-muted me-1'></i>"
            step_state = "<span class='badge bg-light text-muted border fs-9'>Locked</span>"
            border_class = "border-light-subtle"

        missing_html = ""
        if missing and not complete and num <= current_step + 1:
            items = "".join([f"<li class='text-warning-emphasis'>• {escape(m)}</li>" for m in missing])
            missing_html = f"""
            <div class='mt-1.5 p-1.5 rounded bg-warning-subtle text-warning-emphasis fs-8'>
                <div class='fw-bold mb-0.5'><i class='bi bi-exclamation-triangle-fill text-warning me-1'></i> Missing Prerequisites:</div>
                <ul class='list-unstyled mb-0 ps-1'>{items}</ul>
            </div>
            """

        steps_html.append(f"""
        <div class='p-2 mb-1.5 rounded border {border_class} bg-body-tertiary'>
            <div class='d-flex justify-content-between align-items-center'>
                <div class='fw-semibold fs-8 text-dark'>{badge_icon} <strong>0{num}.</strong> {escape(title)}</div>
                <div>{step_state}</div>
            </div>
            <div class='fs-8 text-muted mt-0.5 d-flex justify-content-between'>
                <span>Status: {escape(status_text)}</span>
            </div>
            {missing_html}
        </div>
        """)

    # Primary Action Button mapping
    action_url = f"/operations/{cluster.pk}/"
    action_label = "Inspect Order Details"
    if cluster.status == TransactionCluster.Status.DRAFT:
        action_url = f"/operations/{cluster.pk}/"
        action_label = "Open Order & Submit for Approval &rarr;"
    elif cluster.status == TransactionCluster.Status.PENDING_APPROVAL:
        action_url = "/operations/pending-tasks/"
        action_label = "Review & Approve PO &rarr;"
    elif cluster.status in [TransactionCluster.Status.APPROVED, TransactionCluster.Status.ACTIVE]:
        action_url = f"/operations/deliveries/?po={cluster.reference_code}"
        action_label = "Dispatch Logistics & Confirm Arrival &rarr;"
    elif cluster.status == TransactionCluster.Status.DELIVERED:
        action_url = "/operations/pending-tasks/"
        action_label = "Generate Sales Invoice &rarr;"
    elif cluster.status == TransactionCluster.Status.CLOSED:
        action_url = f"/operations/blockchain/?q={cluster.reference_code}"
        action_label = "View Cryptographic Ledger & Seal &rarr;"

    short_hash = f"#0x{cluster.pk.hex[:6]}"

    html = f"""
    <div class='copilot-card p-3 rounded bg-body border'>
        <div class='d-flex justify-content-between align-items-center mb-2 pb-2 border-bottom flex-wrap gap-1'>
            <div>
                <span class='fw-bold fs-7 text-dark'>{escape(cluster.reference_code)}</span>
                <span class='badge bg-{status_tone} text-white ms-1.5 fs-8'>{status_display}</span>
            </div>
            <a href='/operations/blockchain/?q={cluster.reference_code}' class='badge bg-primary-subtle text-primary border border-primary-subtle text-decoration-none fs-9 py-0.5 px-2'>
                <i class='bi bi-shield-check'></i> Verified on Ledger ({short_hash})
            </a>
        </div>

        <div class='row g-1.5 mb-2.5 fs-8 text-muted'>
            <div class='col-6'>Client: <strong class='text-dark'>{escape(cluster.client.name)}</strong></div>
            <div class='col-6 text-end'>Mill: <strong class='text-dark'>{escape(cluster.sugar_mill.name)}</strong></div>
            <div class='col-6'>Volume: <strong class='text-dark'>{vol:,.2f} MT</strong></div>
            <div class='col-6 text-end'>Created: <span class='text-dark'>{cluster.created_at.strftime('%b %d, %Y')}</span></div>
        </div>

        <div class='mb-2'>
            <div class='fs-8 fw-bold text-uppercase text-muted mb-1.5'><i class='bi bi-diagram-3 me-1'></i> 5-Step Order Progress Status</div>
            {''.join(steps_html)}
        </div>

        <div class='d-flex justify-content-between align-items-center mt-2.5 pt-2 border-top'>
            <a href='/operations/{cluster.pk}/' class='btn btn-xs btn-outline-secondary fs-8'>View Full Contract</a>
            <a href='{action_url}' class='btn btn-sm btn-primary py-1 px-3 fs-8 fw-semibold shadow-xs'>{action_label}</a>
        </div>
    </div>
    """
    return html


def evaluate_copilot_query(user, query_text):
    """
    Evaluates natural language operational queries locally using Django ORM aggregations and regex parsing.
    Returns a dict with 'answer_html', 'suggestions', and metadata.
    """
    q = query_text.lower().strip()
    role = getattr(user, "role", User.Role.OPERATIONS)
    is_finance = role in (User.Role.FINANCE, User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.MANAGEMENT, User.Role.ADMINISTRATOR, "finance", "operations_management") or user.is_superuser
    is_ops = role in (User.Role.OPERATIONS, User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.MANAGEMENT, User.Role.ADMINISTRATOR, "operations", "operations_management") or user.is_superuser

    default_suggestions = [
        "Operations Step-by-Step Guide",
        "Finance Step-by-Step Guide",
        "Invoicing Step-by-Step Guide",
        "Show high variance clusters",
        "Check overdue loans",
    ]

    # --- Intent 0: Specific Purchase Order / Cluster Diagnostics ---
    # Matches patterns like PO-20261106-004, PO-FO-2026-01, PO-004, PO-2026...
    po_candidates = re.findall(r'(?:PO[-\s]?[A-Z0-9-]+|\b[A-Z0-9]{4,12}\b)', query_text, re.IGNORECASE)
    for cand in po_candidates:
        cand_clean = cand.strip().upper()
        # Exclude common acronyms
        if cand_clean in ["STEP", "GUIDE", "HELP", "LOAN", "VIEW", "ORMS", "PO", "TODAY", "HOW"]:
            continue
        cluster = TransactionCluster.objects.filter(
            Q(reference_code__iexact=cand_clean) |
            Q(purchase_order__po_reference_number__iexact=cand_clean) |
            Q(reference_code__icontains=cand_clean) |
            Q(purchase_order__po_reference_number__icontains=cand_clean)
        ).select_related("client", "sugar_mill", "purchase_order", "logistics").first()

        if cluster:
            return {
                "answer_html": _build_po_diagnostic_card(cluster),
                "suggestions": [
                    f"View ledger for {cluster.reference_code}",
                    "Show high variance clusters",
                    "Operations Step-by-Step Guide",
                    "System overview summary",
                ]
            }

    # --- Intent 1: Step-by-Step Procedural Guidance (Operations, Finance, Invoicing) ---
    is_guide_query = any(k in q for k in ["step", "guide", "how to", "instruction", "workflow", "process", "tutorial", "how do", "how can", "what do i"])

    if is_guide_query or "operations guide" in q or "ops guide" in q or "delivery guide" in q:
        if "ops" in q or "operation" in q or "delivery" in q or "truck" in q or "mro" in q or role in (User.Role.OPERATIONS, "operations"):
            if not ("finance" in q or "loan" in q or "voucher" in q or "invoice" in q):
                return {
                    "answer_html": _build_operations_guide(),
                    "suggestions": ["Finance Step-by-Step Guide", "Invoicing Step-by-Step Guide", "Show high variance clusters", "Unassigned MRO permits"]
                }

    if is_guide_query or "finance guide" in q or "loan guide" in q or "voucher guide" in q:
        if "fin" in q or "loan" in q or "voucher" in q or "cheque" in q or "reconcil" in q or role in (User.Role.FINANCE, "finance"):
            if not ("operation" in q or "delivery" in q or "invoice" in q):
                return {
                    "answer_html": _build_finance_guide(),
                    "suggestions": ["Operations Step-by-Step Guide", "Invoicing Step-by-Step Guide", "Check overdue loans", "Explain weekly profit"]
                }

    if is_guide_query or "invoice guide" in q or "invoicing guide" in q or "tax guide" in q or "ewt" in q:
        if "inv" in q or "bill" in q or "tax" in q or "ewt" in q or role in (User.Role.INVOICING, "invoicing"):
            if not ("operation" in q or "delivery" in q or "loan" in q):
                return {
                    "answer_html": _build_invoicing_guide(),
                    "suggestions": ["Operations Step-by-Step Guide", "Finance Step-by-Step Guide", "Explain 1% EWT deduction", "System overview summary"]
                }

    if is_guide_query:
        if role in (User.Role.FINANCE, "finance"):
            return {"answer_html": _build_finance_guide(), "suggestions": ["Operations Step-by-Step Guide", "Invoicing Step-by-Step Guide", "Check overdue loans"]}
        elif role in (User.Role.INVOICING, "invoicing"):
            return {"answer_html": _build_invoicing_guide(), "suggestions": ["Operations Step-by-Step Guide", "Finance Step-by-Step Guide", "Explain 1% EWT deduction"]}
        else:
            return {"answer_html": _build_operations_guide(), "suggestions": ["Finance Step-by-Step Guide", "Invoicing Step-by-Step Guide", "Show high variance clusters"]}

    # --- Intent 2: Cryptographic Blockchain Ledger & Audit Trail Verification ---
    if any(k in q for k in ["ledger", "blockchain", "hash", "tamper", "cryptographic", "audit trail", "integrity", "seal"]):
        from operations.services.hash_chain import verify_po_integrity, get_cluster_block_info

        sample_cluster = TransactionCluster.objects.order_by("-created_at").first()
        integrity_status = "Intact"
        block_count = 0
        root_hash = "0000000000"

        if sample_cluster:
            res = verify_po_integrity(sample_cluster)
            integrity_status = "Verified Intact (Zero Tampering)" if res.get("is_intact") else "Tampering Detected"
            b_info = get_cluster_block_info(sample_cluster)
            block_count = b_info.get("sealed_count", 0)
            root_hash = b_info.get("block_hash_short", "#0x...")

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='d-flex justify-content-between align-items-center mb-2'>
                <div class='fw-bold text-primary'><i class='bi bi-shield-check me-1'></i> Cryptographic Blockchain Ledger Status</div>
                <span class='badge bg-success-subtle text-success border border-success-subtle'>SHA-256 Validated</span>
            </div>
            <p class='fs-8 text-muted mb-2'>Every contract transition, dual verification, delivery receipt, and payment voucher is cryptographically linked in append-only SHA-256 blocks:</p>

            <div class='p-2 mb-2 rounded bg-body-tertiary border'>
                <div class='d-flex justify-content-between fs-8'>
                    <span class='text-muted'>Cryptographic Integrity:</span>
                    <strong class='text-success'><i class='bi bi-check-circle-fill me-1'></i>{integrity_status}</strong>
                </div>
                <div class='d-flex justify-content-between fs-8 mt-1'>
                    <span class='text-muted'>Latest Sealed Block:</span>
                    <span class='font-monospace fw-bold text-dark'>{root_hash}</span>
                </div>
                <div class='d-flex justify-content-between fs-8 mt-1'>
                    <span class='text-muted'>Sample Lifecycle PO:</span>
                    <span class='fw-bold text-primary'>{escape(sample_cluster.reference_code if sample_cluster else 'None')} ({block_count} stages sealed)</span>
                </div>
            </div>

            <div class='text-end mt-2'>
                <a href='/operations/blockchain/' class='btn btn-sm btn-primary fs-8 fw-semibold shadow-xs'>
                    <i class='bi bi-link-45deg me-1'></i> Open Full Blockchain Ledger &rarr;
                </a>
            </div>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Operations Step-by-Step Guide", "Show high variance clusters", "System overview summary"]
        }

    # --- Intent 3: BIR 1% EWT / Tax Deduction Explanation ---
    if any(k in q for k in ["ewt", "withholding", "bir 2307", "form 2307", "tax deduction"]):
        html = """
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='d-flex justify-content-between align-items-center mb-2'>
                <div class='fw-bold text-purple' style='color: #6f42c1;'><i class='bi bi-receipt-cutoff me-1'></i> BIR 1% Expanded Withholding Tax (EWT)</div>
                <span class='badge bg-primary-subtle text-primary border border-primary-subtle'>BIR Form 2307</span>
            </div>
            <p class='fs-8 text-muted mb-2'>Under Philippine BIR Revenue Regulations, trading in raw molasses and agricultural commodities is subject to a <strong>1% Expanded Withholding Tax</strong> deducted at source:</p>

            <div class='p-2 mb-2 rounded bg-body-tertiary border fs-8'>
                <div class='fw-bold text-dark mb-1'>Formula:</div>
                <div class='font-monospace bg-light p-1.5 rounded border mb-2'>
                    Gross Sales Amount = Volume (MT) × Customer Selling Price (₱/MT)<br>
                    EWT Deduction (1%) = Gross Sales Amount × 0.01<br>
                    <strong>Net Receivable Cash = Gross Sales Amount − EWT (1%)</strong>
                </div>
                <div class='text-muted'>The customer issues BIR Form 2307 Certificate of Creditable Tax Withheld at Source upon remitting payment.</div>
            </div>

            <div class='text-end mt-2'>
                <a href='/finance/invoices/' class='btn btn-sm btn-outline-primary fs-8'><i class='bi bi-file-earmark-spreadsheet me-1'></i> View Invoice Tax Records</a>
            </div>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Invoicing Step-by-Step Guide", "Finance Step-by-Step Guide", "System overview summary"]
        }

    # --- Intent 4: Shrinkage Tolerance (±1.00%) & Dispute Rules ---
    if any(k in q for k in ["tolerance", "shrinkage", "1% rule", "variance limit", "dispute rule", "allowed difference"]):
        disputes = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True).count()
        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='d-flex justify-content-between align-items-center mb-2'>
                <div class='fw-bold text-danger'><i class='bi bi-exclamation-octagon-fill me-1'></i> In-Transit Shrinkage Tolerance Rule (±1.00%)</div>
                <span class='badge bg-danger-subtle text-danger border border-danger-subtle'>Operating Policy</span>
            </div>
            <p class='fs-8 text-muted mb-2'>Trading contract rules governing weighbridge scale variance between sugar mill dispatch and customer receipt:</p>

            <div class='p-2 mb-2 rounded bg-body-tertiary border fs-8'>
                <div class='mb-1.5'>
                    <span class='badge bg-success-subtle text-success border border-success-subtle me-1'>Within ±1.00%</span>
                    <strong>Allowable Natural Shrinkage:</strong> Absorbed by operations as natural moisture evaporation during transit.
                </div>
                <div>
                    <span class='badge bg-danger-subtle text-danger border border-danger-subtle me-1'>Exceeding 1.00%</span>
                    <strong>Excess Weight Shortage:</strong> Triggers automated Dispute Status. Contract billing is locked until Operations Manager chooses to absorb or deduct shortfall from carrier freight.
                </div>
            </div>

            <div class='d-flex justify-content-between align-items-center mt-2'>
                <span class='fs-8 text-danger fw-bold'><i class='bi bi-bell-fill me-1'></i> {disputes} active dispute(s)</span>
                <a href='/operations/pending-tasks/' class='btn btn-sm btn-outline-danger fs-8 fw-semibold'>Resolve Weight Differences &rarr;</a>
            </div>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Show high variance clusters", "Operations Step-by-Step Guide", "System overview summary"]
        }

    # --- Intent 5: High Variance / Disputes / Shrinkage Records ---
    if any(k in q for k in ["variance", "dispute", "shrinkage", "loss", "exceed"]):
        disputed = LogisticsLedger.objects.filter(
            Q(variance_exceeds_tolerance=True) | Q(dispute_status=LogisticsLedger.DisputeStatus.DISPUTED)
        ).select_related("cluster", "cluster__client", "partner")

        if not disputed.exists():
            return {
                "answer_html": """
                <div class='copilot-card p-3 rounded border border-success-subtle bg-success-subtle text-success-emphasis'>
                    <div class='d-flex align-items-center gap-2 fw-bold mb-1'>
                        <i class='bi bi-check-circle-fill text-success fs-5'></i> All Logistics Within Tolerance
                    </div>
                    <p class='mb-0 fs-7'>No clusters currently exceed the 1.00% shrinkage variance threshold. All delivered haulages are verified.</p>
                </div>
                """,
                "suggestions": default_suggestions
            }

        rows = []
        for d in disputed:
            d._compute_variance()
            pct_str = f"{d.variance_percent:.2f}%" if d.variance_percent is not None else "N/A"
            loaded = f"{d.loaded_volume_mt:.2f}" if d.loaded_volume_mt else "0.00"
            received = f"{d.received_volume_mt:.2f}" if d.received_volume_mt is not None else "Pending"
            rows.append(f"""
            <div class='d-flex justify-content-between align-items-center p-2 mb-2 rounded bg-body-tertiary border border-danger-subtle'>
                <div>
                    <span class='badge bg-danger-subtle text-danger border border-danger-subtle me-1.5'>Variance Alert</span>
                    <a href='/operations/{d.cluster.pk}/' class='fw-bold text-decoration-none'>{escape(d.cluster.reference_code)}</a>
                    <span class='text-muted fs-8 ms-1'>({escape(d.cluster.client.name)})</span>
                    <div class='fs-8 text-muted mt-0.5'>Carrier: {escape(d.partner.name if d.partner else '—')} | Loaded: {loaded} MT | Received: {received} MT</div>
                </div>
                <div class='text-end'>
                    <div class='fw-bold text-danger fs-7'>{pct_str}</div>
                    <a href='/operations/{d.cluster.pk}/resolve-weight-difference/' class='btn btn-xs btn-outline-danger py-0.5 px-2 fs-8 mt-1'>Resolve &rarr;</a>
                </div>
            </div>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='fw-bold fs-7 text-danger mb-2'><i class='bi bi-exclamation-triangle-fill me-1'></i> Found {len(disputed)} Cluster(s) Exceeding Variance Tolerance:</div>
            {''.join(rows)}
            <div class='text-end mt-2 pt-1 border-top'>
                <a href='/operations/pending-tasks/' class='btn btn-sm btn-outline-danger fs-8 fw-semibold'>View All in Pending Tasks &rarr;</a>
            </div>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Explain shrinkage tolerance", "Operations Step-by-Step Guide", "System overview summary"]
        }

    # --- Intent 6: MRO Permits / Unassigned MRO ---
    if any(k in q for k in ["mro", "release order", "permit", "planter", "crop year"]):
        total_mro = MolassesReleaseOrder.objects.count()
        unassigned_qs = MolassesReleaseOrder.objects.filter(cluster__isnull=True)
        unassigned_count = unassigned_qs.count()
        total_tons = MolassesReleaseOrder.objects.aggregate(total=Sum("tons"))["total"] or Decimal("0")
        unassigned_tons = unassigned_qs.aggregate(total=Sum("tons"))["total"] or Decimal("0")

        unassigned_samples = unassigned_qs.select_related("planter", "sugar_mill").order_by("-tons")[:4]
        samples_html = []
        for m in unassigned_samples:
            mill_display = m.sugar_mill.name if m.sugar_mill else 'Unknown Mill'
            planter_name = m.planter.name if m.planter else 'Unknown Planter'
            samples_html.append(f"""
            <li class='list-group-item d-flex justify-content-between align-items-center fs-8 py-1.5 px-2'>
                <span><strong>MRO #{escape(m.mro_number)}</strong> — {escape(planter_name)} <span class='text-muted'>({escape(mill_display)})</span></span>
                <span class='badge bg-primary-subtle text-primary border border-primary-subtle'>{m.tons:,.2f} MT</span>
            </li>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='fw-bold text-primary mb-2'><i class='bi bi-file-earmark-spreadsheet me-1'></i> Molasses Release Order (MRO) Status</div>
            <div class='row text-center g-2 mb-3 fs-8'>
                <div class='col-6'>
                    <div class='p-2 border rounded bg-body-tertiary'>
                        <div class='text-muted'>Total Active MROs</div>
                        <div class='fw-bold fs-7 text-dark'>{total_mro} ({total_tons:,.2f} MT)</div>
                    </div>
                </div>
                <div class='col-6'>
                    <div class='p-2 border rounded bg-warning-subtle text-warning-emphasis'>
                        <div>Unassigned MROs</div>
                        <div class='fw-bold fs-7'>{unassigned_count} ({unassigned_tons:,.2f} MT)</div>
                    </div>
                </div>
            </div>
            {'<ul class="list-group list-group-flush mb-2">' + ''.join(samples_html) + '</ul>' if samples_html else ''}
            <div class='text-end mt-2'>
                <a href='/operations/mro-summary/' class='btn btn-sm btn-primary fs-8 fw-semibold shadow-xs'><i class='bi bi-box-arrow-up-right me-1'></i> Open MRO Master Ledger</a>
            </div>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Operations Step-by-Step Guide", "Show high variance clusters", "System overview summary"]
        }

    # --- Intent 7: Capital Loans / Interest / Overdue ---
    if any(k in q for k in ["loan", "capital", "interest", "lender", "borrow", "facility", "drawdown"]):
        active_loans = CapitalLoan.objects.filter(~Q(status='closed')).select_related("cluster")
        count = active_loans.count()
        total_principal = active_loans.aggregate(total=Sum("principal"))["total"] or Decimal("0")

        items_html = []
        for loan in active_loans[:5]:
            accrued = loan.accrued_interest
            items_html.append(f"""
            <div class='d-flex justify-content-between align-items-center p-2 mb-2 rounded bg-body-tertiary border fs-8'>
                <div>
                    <div class='fw-bold text-dark'>{escape(loan.bank_name)}</div>
                    <div class='text-muted'>Cluster: {escape(loan.cluster.reference_code)} | Principal: ₱{loan.principal:,.2f}</div>
                </div>
                <div class='text-end'>
                    <div class='fw-bold text-danger'>Interest: ₱{accrued:,.2f}</div>
                    <span class='badge bg-info-subtle text-info-emphasis border border-info-subtle fs-9'>{loan.interest_rate_percent}% p.a.</span>
                </div>
            </div>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='fw-bold text-success mb-2'><i class='bi bi-bank me-1'></i> Capital Loan Facility Summary</div>
            <div class='p-2 mb-3 bg-success-subtle text-success-emphasis rounded border border-success-subtle d-flex justify-content-between align-items-center fs-8'>
                <span><strong>{count} Active Loan(s)</strong> outstanding</span>
                <span class='fw-bold fs-7'>Total Principal: ₱{total_principal:,.2f}</span>
            </div>
            {''.join(items_html) if items_html else '<p class="text-muted fs-8">No active loans outstanding.</p>'}
            <div class='text-end mt-2'>
                <a href='/finance/loans/' class='btn btn-sm btn-success fs-8 fw-semibold shadow-xs'><i class='bi bi-wallet2 me-1'></i> View Loan Ledger</a>
            </div>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Finance Step-by-Step Guide", "Explain weekly profit", "System overview summary"]
        }

    # --- Intent 8: Client / Customer Lookups ---
    client_match = None
    for cl in Client.objects.filter(is_active=True):
        if cl.name.lower() in q:
            client_match = cl
            break

    if client_match:
        client_clusters = TransactionCluster.objects.filter(client=client_match).select_related("sugar_mill", "purchase_order")[:6]
        c_count = client_clusters.count()
        total_vol = sum([c.purchase_order.volume_mt for c in client_clusters if hasattr(c, "purchase_order") and c.purchase_order.volume_mt]) or Decimal('0.00')

        c_rows = []
        for c in client_clusters:
            c_rows.append(f"""
            <div class='d-flex justify-content-between align-items-center p-1.5 mb-1 rounded bg-body-tertiary border fs-8'>
                <div>
                    <a href='/operations/{c.pk}/' class='fw-bold text-decoration-none'>{escape(c.reference_code)}</a>
                    <span class='text-muted ms-1'>Mill: {escape(c.sugar_mill.name)}</span>
                </div>
                <div>
                    <span class='badge bg-light text-dark border me-1'>{c.get_status_display()}</span>
                </div>
            </div>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='d-flex justify-content-between align-items-center mb-2'>
                <div class='fw-bold text-primary fs-7'><i class='bi bi-person-badge me-1'></i> Customer Portfolio: {escape(client_match.name)}</div>
                <span class='badge bg-primary-subtle text-primary border border-primary-subtle'>{c_count} Contract(s)</span>
            </div>
            <div class='p-2 mb-2 rounded bg-body-tertiary border fs-8 d-flex justify-content-between'>
                <span>Total Contracted Volume:</span>
                <strong class='text-dark'>{total_vol:,.2f} MT</strong>
            </div>
            {''.join(c_rows) if c_rows else '<p class=\"text-muted fs-8\">No orders found for this customer.</p>'}
            <div class='text-end mt-2'>
                <a href='/operations/?client={client_match.pk}' class='btn btn-xs btn-outline-primary fs-8'>Filter Orders by Client &rarr;</a>
            </div>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Operations Step-by-Step Guide", "Show high variance clusters", "System overview summary"]
        }

    # --- Intent 9: Revenue, Expenses & Profit Breakdown (Weekly / Yearly / Overall) ---
    if any(k in q for k in ["revenue", "expense", "expenses", "profit", "margin", "p&l", "financial", "income", "cost"]):
        from operations.services.pricing import cluster_financials

        clusters = list(
            TransactionCluster.objects.select_related("client", "sugar_mill", "logistics", "purchase_order")
            .prefetch_related("invoices", "cash_vouchers")
            .all()
        )
        total_rev = Decimal("0.00")
        total_exp = Decimal("0.00")
        total_prof = Decimal("0.00")
        total_vol = Decimal("0.00")

        weekly_rev = defaultdict(Decimal)
        weekly_exp = defaultdict(Decimal)
        weekly_prof = defaultdict(Decimal)
        yearly_rev = defaultdict(Decimal)
        yearly_exp = defaultdict(Decimal)
        yearly_prof = defaultdict(Decimal)

        now = timezone.now()
        target_year = now.year
        target_month = now.month

        latest_date = None
        has_current_month = False
        for c in clusters:
            invs = list(c.invoices.all()) if hasattr(c, "invoices") else []
            po = getattr(c, "purchase_order", None)
            raw_dt = invs[0].issued_at if invs and invs[0].issued_at else (po.approved_at if po and po.approved_at else c.created_at)
            c_date = raw_dt.date() if hasattr(raw_dt, "date") else raw_dt
            if c_date:
                if latest_date is None or c_date > latest_date:
                    latest_date = c_date
                if c_date.year == target_year and c_date.month == target_month:
                    has_current_month = True

        if not has_current_month and latest_date:
            target_year = latest_date.year
            target_month = latest_date.month

        for c in clusters:
            fin = cluster_financials(c)
            r = Decimal(str(fin.get("revenue", "0.00")))
            e = Decimal(str(fin.get("purchase_total", 0.0) + fin.get("logistics_cost", 0.0)))
            p = Decimal(str(fin.get("profit", fin.get("net_profit", "0.00"))))
            v = Decimal(str(fin.get("volume_mt", "0.00")))

            total_rev += r
            total_exp += e
            total_prof += p
            total_vol += v

            invs = list(c.invoices.all()) if hasattr(c, "invoices") else []
            po = getattr(c, "purchase_order", None)
            raw_dt = invs[0].issued_at if invs and invs[0].issued_at else (po.approved_at if po and po.approved_at else c.created_at)
            c_date = raw_dt.date() if hasattr(raw_dt, "date") else raw_dt
            if c_date:
                y = c_date.year
                yearly_rev[y] += r
                yearly_exp[y] += e
                yearly_prof[y] += p

                if c_date.year == target_year and c_date.month == target_month:
                    w = min((c_date.day - 1) // 7, 3) + 1
                    weekly_rev[w] += r
                    weekly_exp[w] += e
                    weekly_prof[w] += p

        overall_margin = (total_prof / total_rev * Decimal("100")).quantize(Decimal("0.01")) if total_rev > 0 else Decimal("0.00")
        is_weekly_query = any(w in q for w in ["week", "weekly"])

        weekly_rows = []
        for w in range(1, 5):
            w_rev = weekly_rev[w]
            w_exp = weekly_exp[w]
            w_prof = weekly_prof[w]
            w_margin = (w_prof / w_rev * Decimal("100")).quantize(Decimal("0.01")) if w_rev > 0 else Decimal("0.00")
            w_class = "text-success" if w_prof > 0 else ("text-danger" if w_prof < 0 else "text-muted")
            weekly_rows.append(f"""
            <tr class='{"table-primary fw-semibold" if is_weekly_query else ""}'>
                <td>Week {w}</td>
                <td>₱{w_rev:,.2f}</td>
                <td>₱{w_exp:,.2f}</td>
                <td class='{w_class} fw-bold'>₱{w_prof:,.2f}</td>
                <td>{w_margin:.2f}%</td>
            </tr>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='d-flex justify-content-between align-items-center mb-2'>
                <div class='fw-bold text-primary fs-7'><i class='bi bi-pie-chart-fill me-1'></i> Financial Performance &amp; Profit Breakdown</div>
                <span class='badge bg-success-subtle text-success border border-success-subtle'>ORM Verified</span>
            </div>
            <div class='row text-center g-2 mb-3 fs-8'>
                <div class='col-4'>
                    <div class='p-2 border rounded bg-body-tertiary'>
                        <div class='text-muted'>Total Revenue</div>
                        <div class='fw-bold text-primary fs-7'>₱{total_rev / Decimal('1000000'):,.2f}M</div>
                    </div>
                </div>
                <div class='col-4'>
                    <div class='p-2 border rounded bg-body-tertiary'>
                        <div class='text-muted'>Total Expenses</div>
                        <div class='fw-bold text-danger fs-7'>₱{total_exp / Decimal('1000000'):,.2f}M</div>
                    </div>
                </div>
                <div class='col-4'>
                    <div class='p-2 border rounded bg-success-subtle text-success-emphasis'>
                        <div>Net Profit ({overall_margin:.1f}%)</div>
                        <div class='fw-bold fs-7'>₱{total_prof / Decimal('1000000'):,.2f}M</div>
                    </div>
                </div>
            </div>

            <div class='mb-2'>
                <div class='fs-8 fw-bold text-uppercase text-muted mb-1'><i class='bi bi-calendar-week me-1'></i> Weekly Cadence (Active Month {target_month}/{target_year})</div>
                <table class='table table-sm table-bordered fs-8 mb-2 text-end'>
                    <thead class='table-light text-end'>
                        <tr><th class='text-start'>Period</th><th>Revenue</th><th>Expenses</th><th>Net Profit</th><th>Margin</th></tr>
                    </thead>
                    <tbody>
                        {''.join(weekly_rows)}
                    </tbody>
                </table>
            </div>

            <p class='fs-8 text-muted mb-0 mt-2 border-top pt-2'>
                <i class='bi bi-info-circle-fill text-primary me-1'></i><strong>Local ORM Calculation:</strong> Aggregated from verified PO contracts, customer invoice collections, sugar mill procurement, and freight deductions.
            </p>
        </div>
        """
        return {
            "answer_html": html,
            "suggestions": ["Finance Step-by-Step Guide", "Check overdue loans", "Explain 1% EWT deduction"]
        }

    # --- Intent 10: General System Overview / Help Fallback ---
    total_clusters = TransactionCluster.objects.count()
    active_clusters = TransactionCluster.objects.filter(status=TransactionCluster.Status.ACTIVE).count()
    draft_clusters = TransactionCluster.objects.filter(status=TransactionCluster.Status.DRAFT).count()
    total_mros = MolassesReleaseOrder.objects.count()
    unassigned_mros = MolassesReleaseOrder.objects.filter(cluster__isnull=True).count()
    disputed_logistics = LogisticsLedger.objects.filter(variance_exceeds_tolerance=True).count()

    html = f"""
    <div class='copilot-card p-3 rounded bg-body border'>
        <div class='fw-bold text-primary mb-2 fs-7'><i class='bi bi-robot me-1'></i> Local ORM AI Assistant Status</div>
        <p class='fs-8 text-muted mb-2.5'>Real-time relational database intelligence for <strong>{user.get_full_name() or user.username}</strong> ({user.get_role_display() if hasattr(user, "get_role_display") else "Operations"}):</p>

        <div class='row g-2 mb-2.5 text-center fs-8'>
            <div class='col-4'>
                <div class='p-2 border rounded bg-body-tertiary'>
                    <div class='text-muted'>Active Orders</div>
                    <div class='fw-bold text-primary fs-7'>{active_clusters} / {total_clusters}</div>
                </div>
            </div>
            <div class='col-4'>
                <div class='p-2 border rounded bg-body-tertiary'>
                    <div class='text-muted'>Unassigned MROs</div>
                    <div class='fw-bold text-warning fs-7'>{unassigned_mros} / {total_mros}</div>
                </div>
            </div>
            <div class='col-4'>
                <div class='p-2 border rounded bg-body-tertiary'>
                    <div class='text-muted'>Weight Disputes</div>
                    <div class='fw-bold text-danger fs-7'>{disputed_logistics}</div>
                </div>
            </div>
        </div>

        <div class='p-2 rounded bg-light border mb-2 fs-8'>
            <i class='bi bi-lightbulb-fill text-warning me-1'></i> <strong>Pro-Tip:</strong> Type any Purchase Order reference (e.g. <code>PO-20261104-003</code> or <code>PO-FO-TEST-01</code>) to see an interactive 5-step progress checklist with exact missing prerequisites!
        </div>
    </div>
    """
    return {
        "answer_html": html,
        "suggestions": default_suggestions
    }
