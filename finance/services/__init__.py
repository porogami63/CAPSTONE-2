"""Financial services and capital loan validations."""

from decimal import Decimal
from django.db.models import Sum

from .finance_hash_chain import (
    get_finance_lifecycle_chain,
    get_finance_block_info,
    verify_finance_integrity,
)


FUNDED_LOAN_STATUSES = ("active", "overdue", "pending_settlement", "closed")


def check_loan_capital_cap(cluster, new_principal=None, exclude_loan_id=None) -> tuple[bool, str]:
    """
    Validates whether new loan creation or loan approval is permitted for the given PO/cluster.

    Rule: Sum(Active/Approved Loans for PO) + proposed principal must not exceed the
    Initial Suggested Loan Amount (100% Sourcing + 100% Logistics).

    Args:
        cluster: TransactionCluster being financed.
        new_principal: Principal of the loan being created or approved (Decimal). Optional.
        exclude_loan_id: Loan PK to exclude from already-funded totals (e.g. the loan being edited/approved).

    Returns:
        (is_allowed: bool, error_message: str)
    """
    if not cluster:
        return True, ""

    from operations.services.pricing import loan_requirement_data

    req = loan_requirement_data(cluster)
    loan_cap = Decimal(str(req.get("required") or "0.00")).quantize(Decimal("0.01"))

    loans_qs = cluster.loans.filter(status__in=FUNDED_LOAN_STATUSES)
    if exclude_loan_id:
        loans_qs = loans_qs.exclude(pk=exclude_loan_id)

    total_funded_capital = loans_qs.aggregate(total=Sum("principal"))["total"] or Decimal("0.00")
    proposed = Decimal(str(new_principal or "0.00"))
    two = Decimal("0.01")

    if loan_cap <= Decimal("0.00"):
        return True, ""

    if total_funded_capital >= (loan_cap - two):
        return False, "Capital requirement for this order has already been 100% funded. Additional loans cannot be created."

    if proposed > Decimal("0.00") and (total_funded_capital + proposed) > (loan_cap + two):
        remaining = max(loan_cap - total_funded_capital, Decimal("0.00"))
        return False, (
            f"Loan principal (₱{proposed:,.2f}) exceeds the remaining capital requirement for this order "
            f"(₱{remaining:,.2f} of ₱{loan_cap:,.2f} = 100% Sourcing + 100% Logistics)."
        )

    return True, ""
