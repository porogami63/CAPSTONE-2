"""Financial services and capital loan validations."""

from decimal import Decimal
from django.db.models import Sum


def check_loan_capital_cap(cluster, exclude_loan_id=None) -> tuple[bool, str]:
    """
    Validates whether new loan creation or loan approval is permitted for the given PO/cluster.
    Logic: Checks Sum(Active/Approved Loans for PO) against Total Capital Requirement.
    If Total Funded Capital >= 100% of Capital Requirement, blocks creation or approval.
    Returns:
        (is_allowed: bool, error_message: str)
    """
    if not cluster:
        return True, ""

    from operations.services.pricing import loan_requirement_data
    from finance.models import CapitalLoan

    req = loan_requirement_data(cluster)
    capital_requirement = req.get("required", Decimal("0.00"))
    projected_sales = req.get("projected_sales", Decimal("0.00"))
    # Loan amount reflects cash capital plus profit (projected sales)
    loan_cap = max(capital_requirement, projected_sales)

    # Active / Approved loans for PO
    active_approved_statuses = [
        CapitalLoan.Status.ACTIVE,
        CapitalLoan.Status.OVERDUE,
        CapitalLoan.Status.PENDING_SETTLEMENT,
        CapitalLoan.Status.CLOSED,
    ]
    loans_qs = cluster.loans.filter(status__in=active_approved_statuses)
    if exclude_loan_id:
        loans_qs = loans_qs.exclude(pk=exclude_loan_id)

    total_funded_capital = loans_qs.aggregate(total=Sum("principal"))["total"] or Decimal("0.00")
    two = Decimal("0.01")

    if loan_cap > Decimal("0.00") and total_funded_capital >= (loan_cap - two):
        return False, "Capital requirement for this order has already been 100% funded. Additional loans cannot be created."

    return True, ""
