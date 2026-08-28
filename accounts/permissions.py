"""Role-based access control for HTC Core."""

from accounts.models import User

Role = User.Role

CORE_NAV_ITEMS = [
    ("dashboard:home", "Dashboard", "bi-grid-1x2-fill", ("dashboard:home",)),
    ("operations:cluster_list", "Transactions", "bi-receipt", ("operations:cluster", "operations:import_excel", "operations:clear_database")),
    ("operations:mro_summary", "MRO Summary", "bi-file-earmark-ruled", ("operations:mro",)),
    ("finance:invoice_list", "Invoicing", "bi-file-earmark-spreadsheet", ("finance:invoice", "finance:reconciliation")),
    ("operations:logistics_list", "Logistics", "bi-truck", ("operations:logistics",)),
    ("finance:loan_list", "Finance", "bi-bank", ("finance:loan",)),
    ("dashboard:analytics", "Analytics", "bi-graph-up-arrow", ("dashboard:analytics",)),
    ("masters:partners", "Suppliers & Customers", "bi-building", ("masters:",)),
    ("dashboard:documents", "Documents", "bi-folder2-open", ("dashboard:documents",)),
    ("chat:room", "Team Chat", "bi-chat-dots-fill", ("chat:",)),
    ("audit:list", "Audit Logs", "bi-journal-text", ("audit:",)),
    ("accounts:user_list", "User Management", "bi-people-fill", ("accounts:user",)),
]

# Navigation items each role can see
NAV_ITEMS = {
    Role.ADMINISTRATOR: CORE_NAV_ITEMS,
    Role.OPERATIONS_MANAGEMENT: [i for i in CORE_NAV_ITEMS if i[0] != "accounts:user_list"],
    Role.FINANCE: [i for i in CORE_NAV_ITEMS if i[0] in ("dashboard:home", "operations:cluster_list", "operations:mro_summary", "finance:invoice_list", "finance:loan_list", "dashboard:analytics", "dashboard:documents", "chat:room")],
    Role.INVOICING: [i for i in CORE_NAV_ITEMS if i[0] in ("dashboard:home", "operations:cluster_list", "operations:mro_summary", "finance:invoice_list", "dashboard:documents", "chat:room")],
}

ALL_ROLES = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.FINANCE, Role.INVOICING}
EXEC_ROLES = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT}
MGMT_FINANCE = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.FINANCE}
MGMT_INVOICING = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.INVOICING, Role.FINANCE}

# Fine-grained permissions
PERMISSIONS = {
    "manage_users": {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT},
    "create_transaction": EXEC_ROLES,
    "edit_transaction": EXEC_ROLES,
    "archive_transaction": EXEC_ROLES,
    "edit_logistics": EXEC_ROLES,
    "upload_mro": EXEC_ROLES,
    "view_mro": ALL_ROLES,
    "add_invoice": MGMT_INVOICING,
    "add_voucher": MGMT_FINANCE,
    "add_loan": MGMT_FINANCE,
    "view_loans": MGMT_FINANCE,
    "verify_loan": EXEC_ROLES,
    "reconcile_payments": MGMT_FINANCE,
    "view_audit": EXEC_ROLES,
    "view_masters": ALL_ROLES,
    "view_financial_summary": MGMT_FINANCE,
    "view_operational_alerts": ALL_ROLES,
    "import_excel": EXEC_ROLES,
    "clear_database": {Role.ADMINISTRATOR},
}


def _normalize_role(role_str: str) -> str:
    if role_str == "operations":
        return Role.OPERATIONS_MANAGEMENT
    if role_str == "management":
        return Role.ADMINISTRATOR
    return role_str


def user_has_perm(user, perm: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = _normalize_role(user.role)
    allowed = PERMISSIONS.get(perm, set())
    return role in allowed or user.role in allowed


def get_user_permissions(user) -> set[str]:
    if user.is_superuser:
        return set(PERMISSIONS.keys())
    role = _normalize_role(user.role)
    return {p for p, roles in PERMISSIONS.items() if role in roles or user.role in roles}


def get_nav_items(user):
    if user.is_superuser:
        items = NAV_ITEMS[Role.ADMINISTRATOR]
    else:
        role = _normalize_role(user.role)
        items = NAV_ITEMS.get(role, NAV_ITEMS.get(Role.OPERATIONS_MANAGEMENT, CORE_NAV_ITEMS))
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
