"""Role-based access control for HTC Core."""

from accounts.models import User

Role = User.Role

CORE_NAV_ITEMS = [
    ("dashboard:home", "Dashboard", "bi-grid-1x2-fill"),
    ("operations:cluster_list", "Transactions", "bi-receipt"),
    ("finance:invoice_list", "Invoicing", "bi-file-earmark-spreadsheet"),
    ("operations:logistics_list", "Logistics", "bi-truck"),
    ("finance:loan_list", "Finance", "bi-bank"),
]

# Navigation items each role can see
NAV_ITEMS = {
    Role.MANAGEMENT: CORE_NAV_ITEMS,
    Role.FINANCE: CORE_NAV_ITEMS,
    Role.OPERATIONS: CORE_NAV_ITEMS,
    Role.INVOICING: CORE_NAV_ITEMS,
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
    "import_excel": {Role.MANAGEMENT},
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
