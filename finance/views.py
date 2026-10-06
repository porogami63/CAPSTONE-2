import json
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

from .forms import PaymentExpenseMatchForm, StandaloneInvoiceForm, StandaloneLoanForm
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
    loans_qs = cluster.loans.all()
    if loans_qs.exists():
        total_target = loans_qs.aggregate(total=Sum("principal"))["total"] or Decimal("0")
    else:
        total_target = Decimal(str(fin["purchase_total"]))

    sourcing_total = Decimal(str(fin["purchase_total"]))
    trucking_total = Decimal(str(fin["tracking_fees"]))
    barge_total = Decimal(str(fin["barge_fees"]))
    logistics_total = Decimal(str(fin["logistics_cost"]))

    matches_qs = reconciliation.matches.all()
    matched_sourcing = matches_qs.filter(expense_type=PaymentExpenseMatch.ExpenseType.SOURCING).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    matched_trucking = matches_qs.filter(expense_type__in=["trucking", "tracking"]).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    matched_barge = matches_qs.filter(expense_type=PaymentExpenseMatch.ExpenseType.BARGE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    matched_deposit = matches_qs.filter(expense_type=PaymentExpenseMatch.ExpenseType.LOGISTICS_DEPOSIT).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    matched_freight = matched_trucking + matched_barge

    total_matched = Decimal(str(matches_qs.aggregate(total=Sum("amount"))["total"] or "0"))
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
            "trucking_total": trucking_total,
            "barge_total": barge_total,
            "logistics_total": logistics_total,
            "matched_sourcing": matched_sourcing,
            "matched_trucking": matched_trucking,
            "matched_barge": matched_barge,
            "matched_freight": matched_freight,
            "matched_deposit": matched_deposit,
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

                from operations.services.reference_generators import generate_cv_reference
                voucher_num = generate_cv_reference(cluster.reference_code)
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
def loan_requirement(request, pk):
    """JSON: minimum principal for a cluster = 50% (Trucking + Freight) + 100% Sourcing."""
    from django.http import JsonResponse
    from operations.services.pricing import loan_requirement_data

    cluster = get_object_or_404(
        TransactionCluster.objects.select_related("client", "sugar_mill", "purchase_order", "logistics"),
        pk=pk,
    )
    data = loan_requirement_data(cluster)
    payload = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in data.items()}
    payload["cluster_created"] = timezone.localtime(cluster.created_at).date().isoformat()
    return JsonResponse(payload)


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.FINANCE)
def loan_list(request):
    bound_loan_form = None
    if request.method == "POST":
        from accounts.permissions import user_has_perm
        if user_has_perm(request.user, "add_loan"):
            form = StandaloneLoanForm(request.POST, user=request.user)
            if form.is_valid():
                loan = form.save(commit=False)
                if loan.status == CapitalLoan.Status.ACTIVE:
                    loan.verified_by = request.user
                    loan.verified_at = timezone.now()
                loan._audit_user = request.user
                loan.save()

                from chat.views import send_system_notification
                from audit.services import notify_roles

                if loan.status == CapitalLoan.Status.ACTIVE:
                    send_system_notification(
                        loan.cluster,
                        f"Capital Loan facility ₱{loan.principal:,.2f} ({loan.bank_name}) created & ACTIVE by {request.user.get_full_name() or request.user.username}.",
                        sender_user=request.user,
                    )
                    messages.success(
                        request,
                        f"Capital Loan facility of ₱{loan.principal:,.2f} ({loan.bank_name}) created and linked to transaction {loan.cluster.reference_code}.",
                    )
                else:
                    send_system_notification(
                        loan.cluster,
                        f"New Capital Loan proposal ₱{loan.principal:,.2f} ({loan.bank_name}) submitted by {request.user.get_full_name() or request.user.username}. Pending Ops/Admin verification.",
                        sender_user=request.user,
                    )
                    notify_roles(
                        [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT],
                        title=f"New Loan Proposal Pending Approval — {loan.cluster.reference_code}",
                        message=f"Finance submitted a loan facility proposal of ₱{loan.principal:,.2f} from {loan.bank_name}. Action required: Review & Approve.",
                        level="warning",
                        link="/finance/loans/",
                        exclude_user=request.user,
                    )
                    messages.success(
                        request,
                        f"Capital Loan facility of ₱{loan.principal:,.2f} submitted for creation approval and linked to transaction {loan.cluster.reference_code}.",
                    )
                return redirect("finance:loan_list")
            else:
                bound_loan_form = form
                for field_name, errors in form.errors.items():
                    label = "Loan" if field_name == "__all__" else (
                        form.fields[field_name].label or field_name.replace("_", " ").title()
                    )
                    for error in errors:
                        messages.error(request, f"{label}: {error}")

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

    loan_form = bound_loan_form or StandaloneLoanForm(user=request.user)

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
            "loan_form": loan_form,
            "reopen_loan_modal": bound_loan_form is not None,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def settle_loan(request, pk):
    loan = get_object_or_404(CapitalLoan, pk=pk)
    if request.method == "POST":
        if loan.status != CapitalLoan.Status.ACTIVE:
            messages.error(request, "Only ACTIVE loans can be submitted for settlement clearance.")
            return redirect("finance:loan_list")

        receipt_num = request.POST.get("settlement_receipt_number", "").strip()
        settlement_date_str = request.POST.get("settlement_date")
        settlement_notes = request.POST.get("settlement_notes", "").strip()
        settlement_doc = request.FILES.get("settlement_document")

        if settlement_doc:
            from config.upload_validators import validate_document_upload
            from django.core.exceptions import ValidationError
            try:
                settlement_doc = validate_document_upload(settlement_doc, label="Settlement Document")
            except ValidationError as e:
                messages.error(request, e.message)
                return redirect("finance:loan_list")

        loan.status = CapitalLoan.Status.PENDING_SETTLEMENT
        if receipt_num:
            loan.settlement_receipt_number = receipt_num
        if settlement_date_str:
            from datetime import datetime
            try:
                loan.settlement_date = datetime.strptime(settlement_date_str, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "Invalid date format for settlement date.")
                return redirect("finance:loan_list")
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
        if loan.status != CapitalLoan.Status.PENDING_CREATION:
            messages.error(request, "Only loans pending creation verification can be processed.")
            return redirect("finance:loan_list")

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
        if loan.status != CapitalLoan.Status.PENDING_SETTLEMENT:
            messages.error(request, "Only loans pending settlement verification can be processed.")
            return redirect("finance:loan_list")

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

    from operations.services.pricing import get_invoice_suggestion_data
    cluster_suggestions_map = {}
    for c in TransactionCluster.objects.filter(is_archived=False).select_related("purchase_order", "logistics", "client").prefetch_related("invoices"):
        cluster_suggestions_map[str(c.id)] = get_invoice_suggestion_data(c)
    cluster_suggestions_json = json.dumps(cluster_suggestions_map)

    return render(
        request,
        "finance/invoice_list.html",
        {
            "invoice_form": form,
            "invoices": invoice_rows,
            "sales_invoices": sales_invoices,
            "supplier_invoices": supplier_invoices,
            "cluster_suggestions_json": cluster_suggestions_json,
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


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def download_voucher_pdf(request, pk):
    voucher = get_object_or_404(
        CashVoucher.objects.select_related("cluster", "cluster__client", "loan"),
        pk=pk,
    )
    template_path = "finance/voucher_pdf.html"
    context = {"voucher": voucher}

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Voucher_{voucher.voucher_number}.pdf"'

    template = get_template(template_path)
    html = template.render(context)

    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse("We had some errors <pre>" + html + "</pre>")
    return response
