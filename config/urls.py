from django.contrib import admin
from django.urls import include, path

handler403 = "accounts.views.permission_denied"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("masters/", include("masters.urls")),
    path("operations/", include("operations.urls")),
    path("finance/", include("finance.urls")),
    path("audit/", include("audit.urls")),
]
