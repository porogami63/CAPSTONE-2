from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.urls import include, path, re_path, reverse

from config.media_views import protected_media

handler403 = "accounts.views.permission_denied"


def _admin_login_via_portal(request, extra_context=None):
    """Send the Django admin login through the portal login.

    The stock admin login form has no throttling and no 2FA, so it would bypass the controls on
    the custom sign-in flow. After signing in through the portal (with 2FA if enabled) staff users
    are returned to the admin.
    """
    target = request.GET.get("next") or reverse("admin:index")
    return redirect_to_login(target, settings.LOGIN_URL)


admin.site.login = _admin_login_via_portal

urlpatterns = [
    path("admin-portal/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("masters/", include("masters.urls")),
    path("operations/", include("operations.urls")),
    path("finance/", include("finance.urls")),
    path("audit/", include("audit.urls")),
    path("chat/", include("chat.urls")),
    # Uploaded documents are served through an authenticated view (never straight from disk/Nginx).
    re_path(r"^media/(?P<path>.+)$", protected_media, name="protected_media"),
]
