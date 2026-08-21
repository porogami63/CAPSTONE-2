from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.audit_list, name="list"),
    path("api/notifications/", views.api_notifications, name="api_notifications"),
    path("api/notifications/read/", views.api_mark_notifications_read, name="api_mark_notifications_read"),
]
