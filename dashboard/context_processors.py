from accounts.permissions import (
    ADMIN_OPERATIONAL_NAV,
    ADMIN_PRIMARY_NAV,
    get_nav_items,
    get_user_permissions,
    nav_is_active,
)


def nav_context(request):
    if not request.user.is_authenticated:
        return {}
    view_name = ""
    if request.resolver_match:
        view_name = request.resolver_match.view_name or ""

    is_in_operational_views = any(
        nav_is_active(view_name, url_name, prefixes)
        for url_name, _, _, prefixes in ADMIN_OPERATIONAL_NAV
    )

    return {
        "user_role": request.user.get_role_display(),
        "user_role_code": request.user.role,
        "nav_items": get_nav_items(request.user),
        "admin_primary_nav": ADMIN_PRIMARY_NAV,
        "admin_operational_nav": ADMIN_OPERATIONAL_NAV,
        "is_in_operational_views": is_in_operational_views,
        "user_perms": get_user_permissions(request.user),
        "current_view_name": view_name,
        "nav_is_active": nav_is_active,
    }
