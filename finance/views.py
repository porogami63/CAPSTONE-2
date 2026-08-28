from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.utils import timezone
from xhtml2pdf import pisa

from accounts.decorators import role_required
from accounts.models import User
from operations.models import TransactionCluster

from .forms import PaymentExpenseMatchForm
from .models import CapitalLoan, CashVoucher, FinancialReconciliation, Invoice, PaymentExpenseMatch


@role_required(
    User.Role.ADMINISTRATOR,
    User.Role.OPERATIONS_MANAGEMENT,
    User.Role.FINANCE,
    User.Role.INVOICING,
    User.Role.OPERATIONS,
)
def reconciliation_detail(request, pk):
    cluster = get_object_or_404(
        TransactionCluster.objects.select_related("client", "sugar_mill", "purchase_order", "logistics"),
        pk=pk,
    )
    reconciliation, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
    form = PaymentExpenseMatchForm()

    from operations.services.pricing import cluster_financials

    fin = cluster_financials(cluster)
    total_target = Decimal(str(fin["revenue"]))
    sourcing_total = Decimal(str(fin["purchase_total"]))
    logistics_total = Decimal(str(fin["logistics_cost"]))
    total_matched = Decimal(str(reconciliation.matches.aggregate(total=Sum("amount"))["total"] or "0"))
    remaining_balance = max(total_target - total_matched, Decimal("0"))
    total_outlay = sourcing_total + logistics_total

    match_pct = float((total_matched / total_target * Decimal("100")).quantize(Decimal("0.1"))) if total_target > 0 else 0.0
    match_pct = min(match_pct, 100.0)

    if match_pct >= 100.0:
        match_status = "RECONCILED"
        match_badge = "success"
    elif match_pct > 0:
        match_status = "PARTIALLY MATCHED"
        match_badge = "warning"
    else:
        match_status = "UNMATCHED"
        match_badge = "secondary"

    return render(
        request,
        "finance/reconciliation.html",
        {
            "cluster": cluster,
            "reconciliation": reconciliation,
            "form": form,
            "total_target": total_target,
            "sourcing_total": sourcing_total,
            "logistics_total": logistics_total,
            "total_matched": total_matched,
            "remaining_balance": remaining_balance,
            "total_outlay": total_outlay,
            "match_pct": match_pct,
            "match_status": match_status,
            "match_badge": match_badge,
            "financials": fin,
        },
    )


@role_required(
    User.Role.ADMINISTRATOR,
    User.Role.OPERATIONS_MANAGEMENT,
    User.Role.FINANCE,
    User.Role.INVOICING,
    User.Role.OPERATIONS,
)
def add_match(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    reconciliation, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
    if request.method == "POST":
        form = PaymentExpenseMatchForm(request.POST)
        if form.is_valid():
            try:
                match = form.save(commit=False)
                match.reconciliation = reconciliation
                match._audit_user = request.user
                match.save()

                reconciliation.matched_payment_amount = (
                    reconciliation.matches.aggregate(total=Sum("amount"))["total"] or Decimal("0")
                )
                reconciliation._audit_user = request.user
                reconciliation.save()

                # Auto-generate corresponding Cash Voucher for payment outlay match
                active_loans = cluster.loans.filter(status__in=[CapitalLoan.Status.ACTIVE, CapitalLoan.Status.CLOSED, CapitalLoan.Status.PENDING_CREATION])
                linked_loan = active_loans.first() if active_loans.exists() else None

                # Generate unique voucher number using match PK & cleaned reference
                clean_ref = "".join(c for c in match.payment_reference if c.isalnum() or c in "-_")[:20]
                if not clean_ref:
                    clean_ref = "REF"
                voucher_num = f"CV-M{match.pk}-{clean_ref}"[:50]
                
                purpose_text = f"Auto-Voucher ({match.get_expense_type_display()}): {match.notes or match.payment_reference}"[:190]

                # Avoid duplicate voucher creation if user edits match
                if not CashVoucher.objects.filter(voucher_number=voucher_num).exists():
                    try:
                        CashVoucher.objects.create(
                            cluster=cluster,
                            loan=linked_loan,
                            voucher_number=voucher_num,
                            amount=match.amount,
                            purpose=purpose_text,
                            issued_at=timezone.localdate(),
                        )
                        messages.success(
                            request,
                            f"Payment matched (₱{match.amount:,.2f}) & Cash Voucher #{voucher_num} automatically generated!",
                        )
                    except Exception:
                        messages.success(request, f"Payment match recorded (₱{match.amount:,.2f}).")
                else:
                    messages.success(request, f"Payment match recorded (₱{match.amount:,.2f}).")
            except Exception as err:
                messages.error(request, f"Error saving payment match: {str(err)}")
        else:
            messages.error(request, "Invalid input. Please check your payment reference and amount fields.")
    return redirect("finance:reconciliation", pk=pk)


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def delete_match(request, cluster_pk, match_pk):
    cluster = get_object_or_404(TransactionCluster, pk=cluster_pk)
    reconciliation = get_object_or_404(FinancialReconciliation, cluster=cluster)
    match = get_object_or_404(PaymentExpenseMatch, pk=match_pk, reconciliation=reconciliation)

    if request.method == "POST":
        ref = match.payment_reference
        amt = match.amount

        # Delete linked auto-generated cash voucher if it exists
        clean_ref = "".join(c for c in ref if c.isalnum() or c in "-_")[:20]
        if not clean_ref:
            clean_ref = "REF"
        voucher_num = f"CV-M{match.pk}-{clean_ref}"[:50]
        CashVoucher.objects.filter(voucher_number=voucher_num).delete()

        match.delete()

        # Recalculate reconciliation total
        reconciliation.matched_payment_amount = (
            reconciliation.matches.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        )
        reconciliation._audit_user = request.user
        reconciliation.save()

        messages.warning(
            request,
            f"Payment match ref '{ref}' (₱{amt:,.2f}) removed by {request.user.get_full_name() or request.user.username}. Reconciliation balances updated.",
        )

    return redirect("finance:reconciliation", pk=cluster_pk)


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.FINANCE)
def loan_list(request):
    loans = list(CapitalLoan.objects.select_related("cluster", "cluster__client", "verified_by").order_by("-created_at"))

    active_exposure = Decimal("0")
    accrued_interest = Decimal("0")
    overdue_facilities = 0
    pending_creation_loans = []
    pending_settlement_loans = []

    for loan in loans:
        if loan.status == CapitalLoan.Status.PENDING_CREATION:
            pending_creation_loans.append(loan)
        elif loan.status == CapitalLoan.Status.PENDING_SETTLEMENT:
            pending_settlement_loans.append(loan)

        if loan.status == CapitalLoan.Status.ACTIVE:
            active_exposure += loan.principal
        accrued_interest += loan.accrued_interest
        if loan.status == CapitalLoan.Status.OVERDUE:
            overdue_facilities += 1

        total_days = max((loan.due_date - loan.start_date).days, 1)
        elapsed_days = max((timezone.localdate() - loan.start_date).days, 0)
        loan.timeline_percent = min(max((elapsed_days / total_days) * 100, 8), 100)
        loan.days_remaining = max((loan.due_date - timezone.localdate()).days, 0)
        loan.logistics_deposit = loan.funded_logistics_deposit
        loan.daily_interest = loan.daily_interest_cost

        # Map timeline classes & status badge styling
        loan.timeline_color_class = "blue"
        if loan.status == CapitalLoan.Status.CLOSED:
            loan.timeline_color_class = "green"
        elif loan.status in (CapitalLoan.Status.OVERDUE, CapitalLoan.Status.REJECTED):
            loan.timeline_color_class = "red"

    logistics_deposits = (
        PaymentExpenseMatch.objects.filter(
            expense_type=PaymentExpenseMatch.ExpenseType.LOGISTICS_DEPOSIT,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    if not logistics_deposits:
        logistics_deposits = sum(float(l.funded_logistics_deposit) for l in loans)

    active_exposure_m = float(active_exposure) / 1000000.0
    logistics_deposits_m = float(logistics_deposits) / 1000000.0

    # Build Cheque Ledger list
    cheques = []
    for idx, loan in enumerate(loans, 1):
        cheques.append({
            "cheque_number": loan.cheque_number or f"CHQ-8849{idx}",
            "issue_date": loan.cheque_date or loan.start_date,
            "bank_name": loan.bank_name,
            "bank_account": loan.bank_account_number or f"0048-2910-{idx}",
            "purpose": f"Bank Loan Facility ({loan.cluster.reference_code})",
            "amount": loan.principal,
            "cluster_ref": loan.cluster.reference_code,
            "cluster_pk": loan.cluster.pk,
            "type": "Capital Loan",
            "status": loan.get_status_display(),
        })

    from .models import CashVoucher
    vouchers = list(CashVoucher.objects.select_related("cluster"))
    for idx, v in enumerate(vouchers, 1):
        cheques.append({
            "cheque_number": v.cheque_number or f"CV-CHQ-70{idx}",
            "issue_date": v.cheque_date or v.issued_at,
            "bank_name": "Operating Account",
            "bank_account": "0048-5512-0",
            "purpose": v.purpose or "Upfront Logistics Deposit",
            "amount": v.amount,
            "cluster_ref": v.cluster.reference_code,
            "cluster_pk": v.cluster.pk,
            "type": "Cash Voucher",
            "status": "Issued",
        })

    return render(
        request,
        "finance/loan_list.html",
        {
            "loans": loans,
            "pending_creation_loans": pending_creation_loans,
            "pending_settlement_loans": pending_settlement_loans,
            "pending_verification_count": len(pending_creation_loans) + len(pending_settlement_loans),
            "cheques": cheques,
            "active_exposure_m": active_exposure_m,
            "accrued_interest": accrued_interest,
            "logistics_deposits_m": logistics_deposits_m,
            "overdue_facilities": overdue_facilities,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def settle_loan(request, pk):
    loan = get_object_or_404(CapitalLoan, pk=pk)
    if request.method == "POST":
        receipt_num = request.POST.get("settlement_receipt_number", "").strip()
        settlement_date_str = request.POST.get("settlement_date")
        settlement_notes = request.POST.get("settlement_notes", "").strip()
        settlement_doc = request.FILES.get("settlement_document")

        loan.status = CapitalLoan.Status.PENDING_SETTLEMENT
        if receipt_num:
            loan.settlement_receipt_number = receipt_num
        if settlement_date_str:
            loan.settlement_date = settlement_date_str
        else:
            loan.settlement_date = timezone.localdate()
        if settlement_notes:
            loan.settlement_notes = settlement_notes
        if settlement_doc:
            loan.settlement_document = settlement_doc

        loan._audit_user = request.user
        loan.save()

        # Post team chat notification
        from chat.views import send_system_notification
        from audit.services import notify_roles
        send_system_notification(
            loan.cluster,
            f"Loan settlement clearance advice #{receipt_num or 'Submitted'} recorded by {request.user.get_full_name() or request.user.username}. Pending Operations/Admin verification.",
            sender_user=request.user,
        )
        notify_roles(
            [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT],
            title=f"Loan Settlement Clearance Pending Approval — {loan.cluster.reference_code}",
            message=f"Finance submitted settlement clearance advice #{receipt_num or 'Recorded'} for {loan.bank_name}. Requires Ops verification.",
            level="warning",
            link="/finance/loans/",
            exclude_user=request.user,
        )

        messages.success(
            request,
            f"Bank loan facility for {loan.cluster.reference_code} submitted for SETTLEMENT VERIFICATION. Bank Clearance Advice #{receipt_num or 'Recorded'}.",
        )
    return redirect("finance:loan_list")


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def verify_loan_creation(request, pk):
    loan = get_object_or_404(CapitalLoan, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "approve").lower()
        notes = request.POST.get("verification_notes", "").strip()

        loan.verified_by = request.user
        loan.verified_at = timezone.now()
        loan.verification_notes = notes

        from chat.views import send_system_notification

        if action == "approve":
            loan.status = CapitalLoan.Status.ACTIVE
            loan.save()
            send_system_notification(
                loan.cluster,
                f"Capital Loan facility ₱{loan.principal:,.2f} CREATION VERIFIED & APPROVED by {request.user.get_full_name() or request.user.username}. Interest tracking active.",
                sender_user=request.user,
            )
            messages.success(request, f"Approved Capital Loan facility for {loan.cluster.reference_code}. Facility is now ACTIVE.")
        else:
            loan.status = CapitalLoan.Status.REJECTED
            loan.save()
            send_system_notification(
                loan.cluster,
                f"Capital Loan creation REJECTED by {request.user.get_full_name() or request.user.username}. Reason: {notes or 'No reason specified'}",
                sender_user=request.user,
            )
            messages.warning(request, f"Rejected Capital Loan creation for {loan.cluster.reference_code}.")

    return redirect("finance:loan_list")


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def verify_loan_settlement(request, pk):
    loan = get_object_or_404(CapitalLoan, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "approve").lower()
        notes = request.POST.get("verification_notes", "").strip()

        loan.verified_by = request.user
        loan.verified_at = timezone.now()
        if notes:
            loan.verification_notes = notes

        from chat.views import send_system_notification

        if action == "approve":
            loan.status = CapitalLoan.Status.CLOSED
            loan.save()
            send_system_notification(
                loan.cluster,
                f"Capital Loan settlement clearance VERIFIED & CLOSED by {request.user.get_full_name() or request.user.username}. Facility is officially SETTLED.",
                sender_user=request.user,
            )
            messages.success(request, f"Verified and closed Capital Loan settlement for {loan.cluster.reference_code}.")
        else:
            loan.status = CapitalLoan.Status.ACTIVE
            loan.save()
            send_system_notification(
                loan.cluster,
                f"Capital Loan settlement REJECTED by {request.user.get_full_name() or request.user.username}. Facility returned to Active status.",
                sender_user=request.user,
            )
            messages.warning(request, f"Rejected settlement for {loan.cluster.reference_code}. Facility returned to Active status.")

    return redirect("finance:loan_list")


from .forms import PaymentExpenseMatchForm, StandaloneInvoiceForm
from .models import CapitalLoan, FinancialReconciliation, Invoice, PaymentExpenseMatch


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING)
def invoice_list(request):
    if request.method == "POST":
        form = StandaloneInvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice._audit_user = request.user
            invoice.save()
            messages.success(
                request,
                f"Sales Invoice {invoice.invoice_number} created and linked to transaction {invoice.cluster.reference_code}.",
            )
            return redirect("finance:invoice_list")
        else:
            messages.error(request, "Error creating invoice. Please check your form input.")
    else:
        form = StandaloneInvoiceForm()

    show_archived = request.GET.get("archived", "").lower() in ("1", "true")
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    client_id = request.GET.get("client", "").strip()
    sort_by = request.GET.get("sort", "newest").strip()

    invoices_qs = Invoice.objects.filter(is_archived=show_archived).select_related("cluster", "cluster__client", "cluster__sugar_mill")

    if q:
        invoices_qs = invoices_qs.filter(
            Q(invoice_number__icontains=q) |
            Q(cluster__reference_code__icontains=q) |
            Q(cluster__client__name__icontains=q) |
            Q(cluster__sugar_mill__name__icontains=q)
        )
    if status_filter:
        invoices_qs = invoices_qs.filter(status=status_filter)
    if client_id:
        invoices_qs = invoices_qs.filter(cluster__client_id=client_id)

    if sort_by == "oldest":
        invoices_qs = invoices_qs.order_by("issued_at", "created_at")
    elif sort_by == "highest_amount":
        invoices_qs = invoices_qs.order_by("-amount")
    elif sort_by == "lowest_amount":
        invoices_qs = invoices_qs.order_by("amount")
    else:
        invoices_qs = invoices_qs.order_by("-issued_at", "-created_at")

    invoice_rows = list(invoices_qs)
    from masters.models import Client
    clients_list = list(Client.objects.filter(is_active=True).order_by("name"))

    today = timezone.localdate()
    total_invoiced = Decimal("0")
    paid_amount = Decimal("0")
    pending_amount = Decimal("0")
    overdue_amount = Decimal("0")

    paid_count = 0
    pending_count = 0
    overdue_count = 0

    for invoice in invoice_rows:
        total_invoiced += invoice.amount

        # Determine status styling
        invoice.status_badge = {
            Invoice.Status.DRAFT: "draft",
            Invoice.Status.ISSUED: "active",
            Invoice.Status.PAID: "delivered",
        }.get(invoice.status, "draft")

        invoice.days_open = max((today - invoice.issued_at).days, 0)
        invoice.payable_state = "Paid" if invoice.status == Invoice.Status.PAID else "Pending"

        if invoice.status == Invoice.Status.PAID:
            paid_amount += invoice.amount
            paid_count += 1
        else:
            pending_amount += invoice.amount
            pending_count += 1
            # Mark overdue if open for 14+ days
            if invoice.days_open >= 14:
                overdue_amount += invoice.amount
                overdue_count += 1
                invoice.payable_state = "Overdue"

    # Percentages
    paid_pct = (float(paid_amount) / float(total_invoiced) * 100.0) if total_invoiced > 0 else 0.0
    pending_pct = (float(pending_amount) / float(total_invoiced) * 100.0) if total_invoiced > 0 else 0.0

    # Format millions for top cards
    total_invoiced_m = float(total_invoiced) / 1000000.0
    paid_amount_m = float(paid_amount) / 1000000.0
    pending_amount_m = float(pending_amount) / 1000000.0
    overdue_amount_m = float(overdue_amount) / 1000000.0

    sales_invoices = invoice_rows
    # Supplier payables representation (unpaid clusters and their POs/reconciliation status)
    supplier_invoices = []
    for c in TransactionCluster.objects.select_related("client", "sugar_mill", "logistics").prefetch_related("invoices"):
        loaded_vol = float(c.logistics.loaded_volume_mt) if hasattr(c, "logistics") and c.logistics else 0.0
        po_price = float(c.purchase_order.unit_price) if hasattr(c, "purchase_order") and c.purchase_order else 0.0
        payable_amount = loaded_vol * po_price

        if payable_amount > 0:
            invs = list(c.invoices.all())
            primary_inv = invs[0] if invs else None
            status = "Paid" if primary_inv and primary_inv.status == Invoice.Status.PAID else ("Overdue" if c.status == TransactionCluster.Status.DELIVERED else "Pending")
            badge = "delivered" if status == "Paid" else ("overdue" if status == "Overdue" else "active")
            supplier_invoices.append({
                "invoice_number": f"SUP-{c.reference_code}",
                "cluster": c,
                "amount": payable_amount,
                "payable_state": status,
                "status_badge": badge,
            })

    return render(
        request,
        "finance/invoice_list.html",
        {
            "invoice_form": form,
            "invoices": invoice_rows,
            "sales_invoices": sales_invoices,
            "supplier_invoices": supplier_invoices,
            "total_invoiced": total_invoiced,
            "total_invoiced_m": total_invoiced_m,
            "paid_amount_m": paid_amount_m,
            "pending_amount_m": pending_amount_m,
            "overdue_amount_m": overdue_amount_m,
            "paid_pct": paid_pct,
            "pending_pct": pending_pct,
            "paid_count": paid_count,
            "pending_count": pending_count,
            "overdue_count": overdue_count,
            "paid_invoices": paid_count,
            "pending_invoices": pending_count,
            "overdue_invoices": overdue_count,
            "clients_list": clients_list,
            "current_q": q,
            "current_status": status_filter,
            "current_client": client_id,
            "current_sort": sort_by,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING)
def download_invoice_pdf(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("cluster", "cluster__client", "cluster__sugar_mill", "cluster__purchase_order"),
        pk=pk,
    )
    template_path = "finance/invoice_pdf.html"
    context = {"invoice": invoice}

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Invoice_{invoice.invoice_number}.pdf"'

    template = get_template(template_path)
    html = template.render(context)

    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse("We had some errors <pre>" + html + "</pre>")
    return response
