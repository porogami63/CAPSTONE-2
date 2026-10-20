from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_role = getattr(request.user, "role", "")
            if user_role == "management":
                user_role = "administrator"

            allowed_roles = set()
            for r in roles:
                allowed_roles.add(r)
                if r == "administrator":
                    allowed_roles.add("management")

            # Operations Manager encompasses: finance, invoicing, and operations
            if user_role == "operations_management":
                if "operations_management" in allowed_roles:
                    return view_func(request, *args, **kwargs)
                if any(r in allowed_roles for r in ("operations", "finance", "invoicing")):
                    return view_func(request, *args, **kwargs)

            # Operations role access:
            if user_role == "operations":
                if "operations" in allowed_roles or "operations_management" in allowed_roles:
                    return view_func(request, *args, **kwargs)

            if user_role not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

