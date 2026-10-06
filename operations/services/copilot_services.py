import re
from decimal import Decimal
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.utils.html import escape

from accounts.models import User
from operations.models import TransactionCluster, LogisticsLedger, MolassesReleaseOrder, PurchaseOrder
from finance.models import CapitalLoan, Invoice, CashVoucher, FinancialReconciliation
from masters.models import Client, SugarMill, LogisticsPartner


def evaluate_copilot_query(user, query_text):
    """
    Evaluates natural language operational queries locally using Django ORM aggregations.
    Returns a dict with 'answer_html', 'suggestions', and metadata.
    """
    q = query_text.lower().strip()
    role = getattr(user, "role", User.Role.OPERATIONS)
    is_admin_or_mgmt = role in (User.Role.ADMINISTRATOR, User.Role.MANAGEMENT, User.Role.OPERATIONS_MANAGER) or user.is_superuser
    is_finance = role in (User.Role.FINANCE, User.Role.MANAGEMENT, User.Role.ADMINISTRATOR) or user.is_superuser
    is_ops = role in (User.Role.OPERATIONS, User.Role.OPERATIONS_MANAGER, User.Role.MANAGEMENT, User.Role.ADMINISTRATOR) or user.is_superuser

    suggestions = [
        "Show high variance clusters",
        "Check overdue loans",
        "Unassigned MRO permits",
        "System overview summary"
    ]

    # --- Intent 1: High Variance / Disputes / Shrinkage ---
    if any(k in q for k in ["variance", "dispute", "shrinkage", "loss", "exceed"]):
        if not is_ops and not is_finance:
            return {
                "answer_html": "<div class='alert alert-warning p-2 mb-0'><i class='bi bi-shield-lock me-1'></i> Access Restricted: Your role does not have permission to view logistics variance records.</div>",
                "suggestions": suggestions
            }

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
                "suggestions": suggestions
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
                    <span class='badge bg-danger me-2'>Alert</span>
                    <a href='/operations/{d.cluster.pk}/' class='fw-bold text-decoration-none'>{escape(d.cluster.reference_code)}</a>
                    <span class='text-muted fs-7 ms-2'>({escape(d.cluster.client.name)})</span>
                    <div class='fs-7 text-muted mt-1'>Loaded: {loaded} MT | Received: {received} MT</div>
                </div>
                <div class='text-end'>
                    <div class='fw-bold text-danger fs-6'>{pct_str}</div>
                    <a href='/operations/{d.cluster.pk}/' class='btn btn-xs btn-outline-danger py-0 px-2 fs-7 mt-1'><i class='bi bi-search me-1'></i> Inspect</a>
                </div>
            </div>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='fw-bold fs-7 text-danger mb-2'><i class='bi bi-exclamation-triangle-fill me-1'></i> Found {len(disputed)} Cluster(s) Exceeding Variance Tolerance:</div>
            {''.join(rows)}
        </div>
        """
        return {"answer_html": html, "suggestions": suggestions}

    # --- Intent 2: MRO Permits / Unassigned MRO ---
    if any(k in q for k in ["mro", "release order", "permit", "planter", "crop year"]):
        if not is_ops:
            return {
                "answer_html": "<div class='alert alert-warning p-2 mb-0'><i class='bi bi-shield-lock me-1'></i> Access Restricted: MRO records are restricted to Operations and Management staff.</div>",
                "suggestions": suggestions
            }

        total_mro = MolassesReleaseOrder.objects.count()
        unassigned_qs = MolassesReleaseOrder.objects.filter(cluster__isnull=True)
        unassigned_count = unassigned_qs.count()
        total_tons = MolassesReleaseOrder.objects.aggregate(total=Sum("tons"))["total"] or Decimal("0")
        unassigned_tons = unassigned_qs.aggregate(total=Sum("tons"))["total"] or Decimal("0")

        unassigned_samples = unassigned_qs.select_related("planter").order_by("-tons")[:4]
        samples_html = []
        for m in unassigned_samples:
            mill_display = m.display_sugar_mill if hasattr(m, 'display_sugar_mill') else m.sugar_mill.name if m.sugar_mill else 'Unknown'
            samples_html.append(f"""
            <li class='list-group-item d-flex justify-content-between align-items-center fs-7 py-1 px-2'>
                <span><strong>MRO #{escape(m.mro_number)}</strong> — {escape(m.planter.name if m.planter else 'Unknown')} ({escape(mill_display)})</span>
                <span class='badge bg-primary rounded-pill'>{m.tons:.2f} MT</span>
            </li>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='fw-bold text-primary mb-2'><i class='bi bi-file-earmark-spreadsheet me-1'></i> Molasses Release Order (MRO) Status</div>
            <div class='row text-center g-2 mb-3 fs-7'>
                <div class='col-6'>
                    <div class='p-2 border rounded bg-body-tertiary'>
                        <div class='text-muted fs-8'>Total Active MROs</div>
                        <div class='fw-bold fs-6'>{total_mro} ({total_tons:,.2f} MT)</div>
                    </div>
                </div>
                <div class='col-6'>
                    <div class='p-2 border rounded bg-warning-subtle text-warning-emphasis'>
                        <div class='fs-8'>Unassigned MROs</div>
                        <div class='fw-bold fs-6'>{unassigned_count} ({unassigned_tons:,.2f} MT)</div>
                    </div>
                </div>
            </div>
            {'<ul class="list-group list-group-flush mb-2">' + ''.join(samples_html) + '</ul>' if samples_html else ''}
            <div class='text-end mt-2'>
                <a href='/operations/mro-summary/' class='btn btn-sm btn-outline-primary fs-7'><i class='bi bi-arrow-right-circle me-1'></i> Open MRO Master Ledger</a>
            </div>
        </div>
        """
        return {"answer_html": html, "suggestions": suggestions}

    # --- Intent 3: Capital Loans / Interest / Overdue ---
    if any(k in q for k in ["loan", "capital", "interest", "lender", "borrow", "overdue"]):
        if not is_finance:
            return {
                "answer_html": "<div class='alert alert-warning p-2 mb-0'><i class='bi bi-shield-lock me-1'></i> Access Restricted: Financial loan records are restricted to Finance and Management roles.</div>",
                "suggestions": suggestions
            }

        active_loans = CapitalLoan.objects.filter(~Q(status='closed')).select_related("cluster")
        count = active_loans.count()
        total_principal = active_loans.aggregate(total=Sum("principal"))["total"] or Decimal("0")

        items_html = []
        for loan in active_loans[:5]:
            accrued = loan.accrued_interest
            items_html.append(f"""
            <div class='d-flex justify-content-between align-items-center p-2 mb-2 rounded bg-body-tertiary border'>
                <div>
                    <div class='fw-bold fs-7'>{escape(loan.bank_name)}</div>
                    <div class='fs-8 text-muted'>Cluster: {escape(loan.cluster.reference_code)} | Principal: ₱{loan.principal:,.2f}</div>
                </div>
                <div class='text-end'>
                    <div class='fs-7 fw-bold text-warning'>Interest: ₱{accrued:,.2f}</div>
                    <span class='badge bg-info text-dark fs-8'>{loan.interest_rate_percent}% p.a.</span>
                </div>
            </div>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='fw-bold text-success mb-2'><i class='bi bi-bank me-1'></i> Capital Loan Facility Summary</div>
            <div class='p-2 mb-3 bg-success-subtle text-success-emphasis rounded border border-success-subtle d-flex justify-content-between align-items-center fs-7'>
                <span><strong>{count} Active Loan(s)</strong> outstanding</span>
                <span class='fw-bold fs-6'>Total Principal: ₱{total_principal:,.2f}</span>
            </div>
            {''.join(items_html) if items_html else '<p class="text-muted fs-7">No active loans outstanding.</p>'}
            <div class='text-end mt-2'>
                <a href='/finance/loans/' class='btn btn-sm btn-outline-success fs-7'><i class='bi bi-wallet2 me-1'></i> View Loan Ledger</a>
            </div>
        </div>
        """
        return {"answer_html": html, "suggestions": suggestions}

    # --- Intent 4: Cluster Search / Client / Customer / Mill ---
    if any(k in q for k in ["cluster", "client", "customer", "mill", "contract"]):
        clusters = TransactionCluster.objects.select_related("client", "sugar_mill", "logistics", "purchase_order").all()[:5]
        cluster_rows = []
        for c in clusters:
            vol = c.purchase_order.volume_mt if hasattr(c, "purchase_order") else Decimal("0")
            status_badge = f"<span class='badge bg-primary'>{escape(c.get_status_display())}</span>"
            cluster_rows.append(f"""
            <div class='d-flex justify-content-between align-items-center p-2 mb-1 rounded bg-body-tertiary border fs-7'>
                <div>
                    <a href='/operations/{c.pk}/' class='fw-bold text-decoration-none'>{escape(c.reference_code)}</a>
                    <span class='text-muted ms-2'>({escape(c.client.name)} / {escape(c.sugar_mill.name)})</span>
                </div>
                <div>
                    <span class='me-2 fw-semibold'>{vol:.2f} MT</span>
                    {status_badge}
                </div>
            </div>
            """)

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='fw-bold mb-2'><i class='bi bi-diagram-3 me-1'></i> Recent Operational Clusters</div>
            {''.join(cluster_rows)}
            <div class='text-end mt-2'>
                <a href='/operations/' class='btn btn-sm btn-outline-primary fs-7'><i class='bi bi-list-task me-1'></i> View All Clusters</a>
            </div>
        </div>
        """
        return {"answer_html": html, "suggestions": suggestions}

    # --- Intent 5: General System Overview / Help ---
    total_clusters = TransactionCluster.objects.count()
    active_clusters = TransactionCluster.objects.filter(status=TransactionCluster.Status.ACTIVE).count()
    total_mros = MolassesReleaseOrder.objects.count()
    unassigned_mros = MolassesReleaseOrder.objects.filter(cluster__isnull=True).count()

    html = f"""
    <div class='copilot-card p-3 rounded bg-body border'>
        <div class='fw-bold text-primary mb-2'><i class='bi bi-robot me-1'></i> HTC Copilot Operational Summary</div>
        <p class='fs-7 text-muted mb-3'>Here is an immediate operational status summary based on your role <strong>({user.get_role_display() if hasattr(user, "get_role_display") else "User"})</strong>:</p>
        
        <div class='row g-2 mb-3 text-center fs-7'>
            <div class='col-6'>
                <div class='p-2 border rounded bg-body-tertiary'>
                    <div class='text-muted fs-8'>Active Contracts</div>
                    <div class='fw-bold text-primary fs-6'>{active_clusters} / {total_clusters}</div>
                </div>
            </div>
            <div class='col-6'>
                <div class='p-2 border rounded bg-body-tertiary'>
                    <div class='text-muted fs-8'>Unassigned MROs</div>
                    <div class='fw-bold text-warning fs-6'>{unassigned_mros} / {total_mros}</div>
                </div>
            </div>
        </div>

        <div class='p-2 rounded bg-light-subtle border mb-2 fs-7'>
            <i class='bi bi-lightbulb text-warning me-1'></i> <strong>Suggested Prompts:</strong> You can ask me about high variance dispatches, loan accruals, MRO balances, or client volume stats!
        </div>
    </div>
    """
    return {"answer_html": html, "suggestions": suggestions}
