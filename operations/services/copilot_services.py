import re
from collections import defaultdict
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
    is_admin_or_mgmt = role in (User.Role.ADMINISTRATOR, User.Role.MANAGEMENT, User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS_MANAGER, "administrator", "operations_management") or user.is_superuser
    is_finance = role in (User.Role.FINANCE, User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.MANAGEMENT, User.Role.ADMINISTRATOR, "finance", "operations_management") or user.is_superuser
    is_ops = role in (User.Role.OPERATIONS, User.Role.OPERATIONS_MANAGEMENT, User.Role.OPERATIONS_MANAGER, User.Role.MANAGEMENT, User.Role.ADMINISTRATOR, "operations", "operations_management") or user.is_superuser

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

    # --- Intent 5: Revenue, Expenses & Profit Breakdown (Weekly / Yearly / Overall) ---
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
        weekly_vol = defaultdict(Decimal)
        weekly_deals = defaultdict(int)

        yearly_rev = defaultdict(Decimal)
        yearly_exp = defaultdict(Decimal)
        yearly_prof = defaultdict(Decimal)
        yearly_vol = defaultdict(Decimal)
        yearly_deals = defaultdict(int)

        now = timezone.now()
        target_year = now.year
        target_month = now.month

        # Find latest transaction month if no activity in current month
        has_current_month = False
        latest_dt = None
        for c in clusters:
            invs = list(c.invoices.all()) if hasattr(c, "invoices") else []
            po = getattr(c, "purchase_order", None)
            dt = invs[0].issued_at if invs and invs[0].issued_at else (po.approved_at if po and po.approved_at else c.created_at)
            if dt:
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
                if dt.year == target_year and dt.month == target_month:
                    has_current_month = True

        if not has_current_month and latest_dt:
            target_year = latest_dt.year
            target_month = latest_dt.month

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
            dt = invs[0].issued_at if invs and invs[0].issued_at else (po.approved_at if po and po.approved_at else c.created_at)
            if dt:
                y = dt.year
                yearly_rev[y] += r
                yearly_exp[y] += e
                yearly_prof[y] += p
                yearly_vol[y] += v
                yearly_deals[y] += 1

                if dt.year == target_year and dt.month == target_month:
                    w = min((dt.day - 1) // 7, 3) + 1
                    weekly_rev[w] += r
                    weekly_exp[w] += e
                    weekly_prof[w] += p
                    weekly_vol[w] += v
                    weekly_deals[w] += 1

        overall_margin = (total_prof / total_rev * Decimal("100")).quantize(Decimal("0.01")) if total_rev > 0 else Decimal("0.00")

        is_weekly_query = any(w in q for w in ["week", "weekly"])
        is_yearly_query = any(y in q for y in ["year", "yearly", "annual"])

        # Build Weekly Breakdown Table HTML
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

        # Build Yearly Breakdown Table HTML
        yearly_rows = []
        for y in sorted(yearly_rev.keys()):
            y_rev = yearly_rev[y]
            y_exp = yearly_exp[y]
            y_prof = yearly_prof[y]
            y_margin = (y_prof / y_rev * Decimal("100")).quantize(Decimal("0.01")) if y_rev > 0 else Decimal("0.00")
            y_class = "text-success" if y_prof > 0 else ("text-danger" if y_prof < 0 else "text-muted")
            yearly_rows.append(f"""
            <tr class='{"table-primary fw-semibold" if is_yearly_query else ""}'>
                <td>{y}</td>
                <td>₱{y_rev:,.2f}</td>
                <td>₱{y_exp:,.2f}</td>
                <td class='{y_class} fw-bold'>₱{y_prof:,.2f}</td>
                <td>{y_margin:.2f}%</td>
            </tr>
            """)

        view_focus_note = ""
        if is_weekly_query:
            view_focus_note = f"<div class='badge bg-primary text-white mb-2 fs-8'><i class='bi bi-calendar-week me-1'></i> Weekly Interval Focus (Active Month: {target_month}/{target_year})</div>"
        elif is_yearly_query:
            view_focus_note = "<div class='badge bg-info text-dark mb-2 fs-8'><i class='bi bi-calendar3 me-1'></i> Multi-Year Performance Trend Focus</div>"

        html = f"""
        <div class='copilot-card p-3 rounded bg-body border'>
            <div class='d-flex justify-content-between align-items-center mb-2'>
                <div class='fw-bold text-primary'><i class='bi bi-pie-chart-fill me-1'></i> Financial Performance &amp; Profit Breakdown</div>
                <span class='badge bg-success-subtle text-success border border-success-subtle'>ORM Verified</span>
            </div>
            {view_focus_note}
            <div class='row text-center g-2 mb-3 fs-7'>
                <div class='col-4'>
                    <div class='p-2 border rounded bg-body-tertiary'>
                        <div class='text-muted fs-8'>Total Revenue</div>
                        <div class='fw-bold text-primary fs-6'>₱{total_rev / Decimal('1000000'):,.2f}M</div>
                    </div>
                </div>
                <div class='col-4'>
                    <div class='p-2 border rounded bg-body-tertiary'>
                        <div class='text-muted fs-8'>Total Expenses</div>
                        <div class='fw-bold text-danger fs-6'>₱{total_exp / Decimal('1000000'):,.2f}M</div>
                    </div>
                </div>
                <div class='col-4'>
                    <div class='p-2 border rounded bg-success-subtle text-success-emphasis'>
                        <div class='fs-8'>Net Profit ({overall_margin:.1f}%)</div>
                        <div class='fw-bold fs-6'>₱{total_prof / Decimal('1000000'):,.2f}M</div>
                    </div>
                </div>
            </div>

            <!-- Interval Breakdown Sub-Tables -->
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

            <div class='mb-2'>
                <div class='fs-8 fw-bold text-uppercase text-muted mb-1'><i class='bi bi-calendar3 me-1'></i> Yearly Cadence Overview</div>
                <table class='table table-sm table-bordered fs-8 mb-2 text-end'>
                    <thead class='table-light text-end'>
                        <tr><th class='text-start'>Year</th><th>Revenue</th><th>Expenses</th><th>Net Profit</th><th>Margin</th></tr>
                    </thead>
                    <tbody>
                        {''.join(yearly_rows)}
                    </tbody>
                </table>
            </div>

            <p class='fs-8 text-muted mb-0 mt-2 border-top pt-2'>
                <i class='bi bi-info-circle-fill text-primary me-1'></i><strong>Local ORM Explanation:</strong> Operating figures are calculated from verified PO contracts, customer invoice collections, sugar mill procurement, and incremental freight batches.
            </p>
        </div>
        """
        suggestions_fin = [
            "Explain weekly profit",
            "Explain yearly profit",
            "Show high variance clusters",
            "Check overdue loans",
        ]
        return {"answer_html": html, "suggestions": suggestions_fin}

    # --- Intent 6: General System Overview / Help ---
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
