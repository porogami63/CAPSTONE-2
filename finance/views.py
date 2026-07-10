from decimal import Decimal
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from accounts.models import User
from operations.models import TransactionCluster

from .forms import PaymentExpenseMatchForm
from .models import CapitalLoan, FinancialReconciliation, Invoice, PaymentExpenseMatch


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def reconciliation_detail(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    reconciliation, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
    form = PaymentExpenseMatchForm()
    total_matched = reconciliation.matches.aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "finance/reconciliation.html",
        {
            "cluster": cluster,
            "reconciliation": reconciliation,
            "form": form,
            "total_matched": total_matched,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def add_match(request, pk):
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    reconciliation, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
    if request.method == "POST":
        form = PaymentExpenseMatchForm(request.POST)
        if form.is_valid():
            match = form.save(commit=False)
            match.reconciliation = reconciliation
            match._audit_user = request.user
            match.save()
            reconciliation.matched_payment_amount = (
                reconciliation.matches.aggregate(total=Sum("amount"))["total"] or 0
            )
            reconciliation._audit_user = request.user
            reconciliation.save()
            messages.success(request, "Payment matched to expense.")
    return redirect("finance:reconciliation", pk=pk)


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE)
def loan_list(request):
    loans = list(CapitalLoan.objects.select_related("cluster", "cluster__client"))
    for loan in loans:
        loan.refresh_status()
        loan.save(update_fields=["status"])

    active_exposure = 0
    accrued_interest = 0
    overdue_facilities = 0

    for loan in loans:
        if loan.status == loan.Status.ACTIVE:
            active_exposure += loan.principal
        accrued_interest += loan.accrued_interest
        if loan.is_overdue or loan.status == loan.Status.OVERDUE:
            overdue_facilities += 1

        total_days = max((loan.due_date - loan.start_date).days, 1)
        elapsed_days = max((timezone.localdate() - loan.start_date).days, 0)
        loan.timeline_percent = min(max((elapsed_days / total_days) * 100, 8), 100)
        loan.days_remaining = max((loan.due_date - timezone.localdate()).days, 0)
        loan.logistics_deposit = float(loan.principal) * 0.2916

        # Map timeline classes
        loan.timeline_color_class = "blue"
        if loan.status == loan.Status.CLOSED:
            loan.timeline_color_class = "green"
        elif loan.status == loan.Status.OVERDUE or loan.is_overdue:
            loan.timeline_color_class = "red"

    logistics_deposits = (
        PaymentExpenseMatch.objects.filter(
            expense_type=PaymentExpenseMatch.ExpenseType.LOGISTICS_DEPOSIT,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    active_exposure_m = float(active_exposure) / 1000000.0
    logistics_deposits_m = float(logistics_deposits) / 1000000.0

    # No mock data — template will handle empty state

    return render(
        request,
        "finance/loan_list.html",
        {
            "loans": loans,
            "active_exposure_m": active_exposure_m,
            "accrued_interest": accrued_interest,
            "logistics_deposits_m": logistics_deposits_m,
            "overdue_facilities": overdue_facilities,
        },
    )


@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING)
def invoice_list(request):
    invoice_rows = list(
        Invoice.objects.select_related("cluster", "cluster__client", "cluster__sugar_mill").order_by("-issued_at", "-created_at")
    )

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
            primary_inv = c.invoices.first()
            status = "Paid" if primary_inv and primary_inv.status == Invoice.Status.PAID else ("Overdue" if c.status == TransactionCluster.Status.DELIVERED else "Pending")
            badge = "delivered" if status == "Paid" else ("overdue" if status == "Overdue" else "active")
            supplier_invoices.append({
                "invoice_number": f"SUP-{c.reference_code}",
                "cluster": c,
                "amount": payable_amount,
                "payable_state": status,
                "status_badge": badge,
            })

    # No mock data — template will handle empty state

    return render(
        request,
        "finance/invoice_list.html",
        {
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
        },
    )

from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

@role_required(User.Role.MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING)
def download_invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("cluster", "cluster__client", "cluster__sugar_mill", "cluster__purchase_order"), pk=pk)
    template_path = 'finance/invoice_pdf.html'
    context = {'invoice': invoice}
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{invoice.invoice_number}.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
       
    if pisa_status.err:
       return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response
