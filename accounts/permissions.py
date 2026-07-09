"""Role-based access control for HTC Core."""

from accounts.models import User

Role = User.Role

# Navigation items each role can see
NAV_ITEMS = {
    Role.MANAGEMENT: [
        ("dashboard:home", "Dashboard", "bi-grid-1x2-fill"),
        ("operations:cluster_list", "Transactions", "bi-box-seam"),
        ("finance:loan_list", "Loans", "bi-bank"),
        ("masters:list", "Master Data", "bi-database"),
        ("audit:list", "Audit Trail", "bi-shield-check"),
    ],
    Role.FINANCE: [
        ("dashboard:home", "Dashboard", "bi-grid-1x2-fill"),
        ("operations:cluster_list", "Transactions", "bi-box-seam"),
        ("finance:loan_list", "Loans & Interest", "bi-bank"),
    ],
    Role.OPERATIONS: [
        ("dashboard:home", "Dashboard", "bi-grid-1x2-fill"),
        ("operations:cluster_list", "Transactions", "bi-box-seam"),
        ("masters:list", "Master Data", "bi-database"),
    ],
    Role.INVOICING: [
        ("dashboard:home", "Dashboard", "bi-grid-1x2-fill"),
        ("operations:cluster_list", "Transactions", "bi-box-seam"),
    ],
}

# Fine-grained permissions
PERMISSIONS = {
    "create_transaction": {Role.MANAGEMENT, Role.OPERATIONS},
    "edit_logistics": {Role.MANAGEMENT, Role.OPERATIONS},
    "add_invoice": {Role.MANAGEMENT, Role.INVOICING, Role.FINANCE},
    "add_voucher": {Role.MANAGEMENT, Role.FINANCE},
    "add_loan": {Role.MANAGEMENT, Role.FINANCE},
    "view_loans": {Role.MANAGEMENT, Role.FINANCE},
    "reconcile_payments": {Role.MANAGEMENT, Role.FINANCE},
    "view_audit": {Role.MANAGEMENT},
    "view_masters": {Role.MANAGEMENT, Role.OPERATIONS},
    "view_financial_summary": {Role.MANAGEMENT, Role.FINANCE},
    "view_operational_alerts": {Role.MANAGEMENT, Role.OPERATIONS, Role.INVOICING},
}


def user_has_perm(user, perm: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    allowed = PERMISSIONS.get(perm, set())
    return user.role in allowed


def get_user_permissions(user) -> set[str]:
    if user.is_superuser:
        return set(PERMISSIONS.keys())
    return {p for p, roles in PERMISSIONS.items() if user.role in roles}


def get_nav_items(user):
    if user.is_superuser:
        return NAV_ITEMS[Role.MANAGEMENT]
    return NAV_ITEMS.get(user.role, NAV_ITEMS[Role.OPERATIONS])
