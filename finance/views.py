from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from accounts.models import User
from operations.models import TransactionCluster

from .forms import PaymentExpenseMatchForm
from .models import CapitalLoan, FinancialReconciliation, PaymentExpenseMatch


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
    loans = CapitalLoan.objects.select_related("cluster", "cluster__client")
    for loan in loans:
        loan.refresh_status()
        loan.save(update_fields=["status"])
    return render(request, "finance/loan_list.html", {"loans": loans})
