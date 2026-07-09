from accounts.permissions import get_nav_items, get_user_permissions


def nav_context(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "user_role": request.user.get_role_display(),
        "user_role_code": request.user.role,
        "nav_items": get_nav_items(request.user),
        "user_perms": get_user_permissions(request.user),
    }
