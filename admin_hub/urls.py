from django.urls import path
from . import views

app_name = "admin_hub"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("backup/trigger/", views.trigger_backup_view, name="trigger_backup"),
    path("backup/download/<str:filename>/", views.download_backup_view, name="download_backup"),
    path("user/<int:pk>/approve/", views.user_approve_view, name="user_approve"),
    path("user/<int:pk>/toggle-active/", views.user_toggle_active_view, name="user_toggle_active"),
    path("user/<int:pk>/update-role/", views.user_update_role_view, name="user_update_role"),
    path("archive/<uuid:pk>/restore/", views.archive_restore_view, name="archive_restore"),
    path("audit/export/", views.export_audit_csv_view, name="export_audit_csv"),
    path("dataflow/export/", views.export_dataflow_csv_view, name="export_dataflow_csv"),
    path("security/scan/", views.trigger_security_scan_view, name="trigger_security_scan"),
    path("security/export/", views.export_security_audit_csv_view, name="export_security_audit_csv"),
    path("testing/run/", views.trigger_test_run_view, name="trigger_test_run"),
    path("testing/export/", views.export_test_results_csv_view, name="export_test_results_csv"),
]
