from accounts.permissions import get_nav_items, get_user_permissions, nav_is_active


def nav_context(request):
    if not request.user.is_authenticated:
        return {}
    view_name = ""
    if request.resolver_match:
        view_name = request.resolver_match.view_name or ""
    return {
        "user_role": request.user.get_role_display(),
        "user_role_code": request.user.role,
        "nav_items": get_nav_items(request.user),
        "user_perms": get_user_permissions(request.user),
        "current_view_name": view_name,
        "nav_is_active": nav_is_active,
    }
