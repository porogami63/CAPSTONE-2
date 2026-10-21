"""Role-based access control for HTC Core."""

from accounts.models import User

Role = User.Role

ADMIN_PRIMARY_NAV = [
    ("admin_hub:dashboard", "Dashboard", "bi-grid-1x2-fill", ("admin_hub:",)),
    ("accounts:user_list", "User Management", "bi-people-fill", ("accounts:user",)),
    ("audit:list", "Activity History", "bi-journal-text", ("audit:",)),
    ("chat:room", "Team Chat", "bi-chat-dots-fill", ("chat:",)),
]

ADMIN_OPERATIONAL_NAV = [
    ("operations:pending_tasks", "Pending Tasks", "bi-check2-square", ("operations:pending_tasks",)),
    ("operations:cluster_list", "Orders & Deals", "bi-receipt", ("operations:cluster", "operations:import_excel", "operations:clear_database")),
    ("operations:mro_summary", "Loading Permits (MRO)", "bi-file-earmark-ruled", ("operations:mro",)),
    ("finance:invoice_list", "Customer Invoices", "bi-file-earmark-spreadsheet", ("finance:invoice", "finance:reconciliation")),
    ("operations:deliveries_list", "Deliveries & Trucking", "bi-truck", ("operations:deliveries", "operations:logistics")),
    ("finance:loan_list", "Bank Loans", "bi-bank", ("finance:loan",)),
    ("dashboard:analytics", "Analytics", "bi-graph-up-arrow", ("dashboard:analytics",)),
    ("masters:partners", "Partners & Directory", "bi-building", ("masters:",)),
    ("dashboard:documents", "Documents", "bi-folder2-open", ("dashboard:documents",)),
]

CORE_NAV_ITEMS = [
    ("dashboard:home", "Dashboard", "bi-grid-1x2-fill", ("dashboard:home",)),
    ("operations:pending_tasks", "Pending Tasks", "bi-check2-square", ("operations:pending_tasks",)),
    ("operations:cluster_list", "Orders & Deals", "bi-receipt", ("operations:cluster", "operations:import_excel", "operations:clear_database")),
    ("operations:mro_summary", "Loading Permits (MRO)", "bi-file-earmark-ruled", ("operations:mro",)),
    ("finance:invoice_list", "Customer Invoices", "bi-file-earmark-spreadsheet", ("finance:invoice", "finance:reconciliation")),
    ("operations:deliveries_list", "Deliveries & Trucking", "bi-truck", ("operations:deliveries", "operations:logistics")),
    ("finance:loan_list", "Bank Loans", "bi-bank", ("finance:loan",)),
    ("dashboard:analytics", "Analytics", "bi-graph-up-arrow", ("dashboard:analytics",)),
    ("masters:partners", "Partners & Directory", "bi-building", ("masters:",)),
    ("dashboard:documents", "Documents", "bi-folder2-open", ("dashboard:documents",)),
    ("chat:room", "Team Chat", "bi-chat-dots-fill", ("chat:",)),
    ("audit:list", "Activity History", "bi-journal-text", ("audit:",)),
    ("accounts:user_list", "User Management", "bi-people-fill", ("accounts:user",)),
    ("admin_hub:dashboard", "Admin Control Hub", "bi-shield-shaded", ("admin_hub:",)),
]

# Navigation items each role can see
NAV_ITEMS = {
    Role.ADMINISTRATOR: ADMIN_PRIMARY_NAV + ADMIN_OPERATIONAL_NAV,
    Role.OPERATIONS: [
        i for i in CORE_NAV_ITEMS 
        if i[0] not in ("accounts:user_list", "finance:loan_list", "finance:invoice_list", "admin_hub:dashboard")
    ],
    Role.OPERATIONS_MANAGEMENT: [
        i for i in CORE_NAV_ITEMS 
        if i[0] not in ("admin_hub:dashboard",)
    ],
    Role.FINANCE: [i for i in CORE_NAV_ITEMS if i[0] in ("dashboard:home", "operations:pending_tasks", "operations:cluster_list", "operations:mro_summary", "finance:invoice_list", "finance:loan_list", "dashboard:analytics", "dashboard:documents", "chat:room")],
    Role.INVOICING: [i for i in CORE_NAV_ITEMS if i[0] in ("dashboard:home", "operations:pending_tasks", "operations:cluster_list", "operations:mro_summary", "finance:invoice_list", "dashboard:documents", "chat:room")],
}

ALL_ROLES = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.OPERATIONS, Role.FINANCE, Role.INVOICING}
OPS_ROLES = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.OPERATIONS}
EXEC_ROLES = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT}
MGMT_FINANCE = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.FINANCE}
FINANCE_ADMIN = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.FINANCE}
MGMT_INVOICING = {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.INVOICING, Role.FINANCE}

# Fine-grained permissions
PERMISSIONS = {
    "manage_users": {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT},
    "create_transaction": ALL_ROLES,
    "edit_transaction": ALL_ROLES,
    "approve_transaction": {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.OPERATIONS},
    "archive_transaction": EXEC_ROLES,
    "edit_logistics": OPS_ROLES,
    "upload_mro": OPS_ROLES,
    "view_mro": ALL_ROLES,
    "view_chai": ALL_ROLES,
    "manage_chai": {Role.ADMINISTRATOR, Role.OPERATIONS_MANAGEMENT, Role.OPERATIONS, Role.FINANCE},
    "add_invoice": MGMT_INVOICING,
    "add_voucher": FINANCE_ADMIN,
    "add_loan": FINANCE_ADMIN,
    "view_loans": FINANCE_ADMIN,
    "verify_loan": {Role.ADMINISTRATOR},
    "reconcile_payments": FINANCE_ADMIN,
    "add_match": FINANCE_ADMIN,
    "view_reconciliation": FINANCE_ADMIN,
    "view_audit": OPS_ROLES,
    "view_masters": ALL_ROLES,
    "view_financial_summary": FINANCE_ADMIN,
    "view_operational_alerts": ALL_ROLES,
    "import_excel": OPS_ROLES,
    "clear_database": {Role.ADMINISTRATOR},
}


def _normalize_role(role_str: str) -> str:
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
    if role == Role.OPERATIONS_MANAGEMENT:
        # Operations Manager encompasses operations, finance, and invoicing
        if role in allowed or user.role in allowed:
            return True
        if any(r in allowed for r in (Role.OPERATIONS, Role.FINANCE, Role.INVOICING)):
            return True
    return role in allowed or user.role in allowed


def get_user_permissions(user) -> set[str]:
    if user.is_superuser:
        return set(PERMISSIONS.keys())
    role = _normalize_role(user.role)
    perms = {p for p, roles in PERMISSIONS.items() if role in roles or user.role in roles}
    if role == Role.OPERATIONS_MANAGEMENT:
        for p, roles in PERMISSIONS.items():
            if any(r in roles for r in (Role.OPERATIONS, Role.FINANCE, Role.INVOICING)):
                perms.add(p)
    return perms


def get_nav_items(user):
    role = _normalize_role(getattr(user, "role", ""))
    if role == Role.ADMINISTRATOR:
        return NAV_ITEMS[Role.ADMINISTRATOR]
    return NAV_ITEMS.get(role, NAV_ITEMS.get(Role.OPERATIONS, CORE_NAV_ITEMS))


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
