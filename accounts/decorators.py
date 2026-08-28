from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_role = getattr(request.user, "role", "")
            # Alias mapping
            if user_role == "operations":
                user_role = "operations_management"
            elif user_role == "management":
                user_role = "administrator"

            allowed_roles = set()
            for r in roles:
                allowed_roles.add(r)
                if r == "operations_management":
                    allowed_roles.add("operations")
                elif r == "administrator":
                    allowed_roles.add("management")

            if user_role not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

