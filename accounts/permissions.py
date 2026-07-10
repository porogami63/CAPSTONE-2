"""Role-based access control for HTC Core."""

from accounts.models import User

Role = User.Role

CORE_NAV_ITEMS = [
    ("dashboard:home", "Dashboard", "bi-grid-1x2-fill", ("dashboard:home",)),
    ("operations:cluster_list", "Transactions", "bi-receipt", ("operations:cluster", "operations:import_excel", "operations:clear_database")),
    ("finance:invoice_list", "Invoicing", "bi-file-earmark-spreadsheet", ("finance:invoice", "finance:reconciliation")),
    ("operations:logistics_list", "Logistics", "bi-truck", ("operations:logistics",)),
    ("finance:loan_list", "Finance", "bi-bank", ("finance:loan",)),
    ("dashboard:analytics", "Analytics", "bi-graph-up-arrow", ("dashboard:analytics",)),
    ("masters:partners", "Suppliers & Customers", "bi-building", ("masters:",)),
    ("dashboard:documents", "Documents", "bi-folder2-open", ("dashboard:documents",)),
]

# Navigation items each role can see
NAV_ITEMS = {
    Role.MANAGEMENT: CORE_NAV_ITEMS,
    Role.OPERATIONS_MANAGER: CORE_NAV_ITEMS,
    Role.FINANCE: [i for i in CORE_NAV_ITEMS if i[0] in ("dashboard:home", "finance:invoice_list", "finance:loan_list", "dashboard:documents")],
    Role.OPERATIONS: [i for i in CORE_NAV_ITEMS if i[0] in ("dashboard:home", "operations:cluster_list", "operations:logistics_list", "masters:partners", "dashboard:documents")],
    Role.INVOICING: [i for i in CORE_NAV_ITEMS if i[0] in ("dashboard:home", "operations:cluster_list", "finance:invoice_list", "dashboard:documents")],
}

# Fine-grained permissions
PERMISSIONS = {
    "create_transaction": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.OPERATIONS},
    "edit_logistics": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.OPERATIONS},
    "add_invoice": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.INVOICING, Role.FINANCE},
    "add_voucher": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.FINANCE},
    "add_loan": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.FINANCE},
    "view_loans": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.FINANCE},
    "reconcile_payments": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.FINANCE},
    "view_audit": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER},
    "view_masters": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.OPERATIONS},
    "view_financial_summary": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.FINANCE},
    "view_operational_alerts": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER, Role.OPERATIONS, Role.INVOICING},
    "import_excel": {Role.MANAGEMENT, Role.OPERATIONS_MANAGER},
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
        items = NAV_ITEMS[Role.MANAGEMENT]
    else:
        items = NAV_ITEMS.get(user.role, NAV_ITEMS[Role.OPERATIONS])
    return items


def nav_is_active(view_name: str, url_name: str, prefixes: tuple[str, ...]) -> bool:
    if view_name == url_name:
        return True
    if not view_name:
        return False
    for prefix in prefixes:
        if prefix.endswith(":"):
            if view_name.startswith(prefix):
                return True
        elif view_name.startswith(prefix):
            return True
    return False
