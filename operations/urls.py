from django.urls import path

from . import views

app_name = "operations"

urlpatterns = [
    path("", views.cluster_list, name="cluster_list"),
    path("logistics/", views.logistics_list, name="logistics_list"),
    path("logistics/export/", views.export_logistics_csv, name="export_logistics_csv"),
    path("import/", views.import_excel, name="import_excel"),
    path("clear-database/", views.clear_database_view, name="clear_database"),
    path("new/", views.cluster_create, name="cluster_create"),
    path("<uuid:pk>/", views.cluster_detail, name="cluster_detail"),
    path("<uuid:pk>/edit/", views.cluster_edit, name="cluster_edit"),
    path("<uuid:pk>/logistics/", views.update_logistics, name="update_logistics"),
    path("<uuid:pk>/invoice/", views.add_invoice, name="add_invoice"),
    path("<uuid:pk>/voucher/", views.add_voucher, name="add_voucher"),
    path("<uuid:pk>/loan/", views.add_loan, name="add_loan"),
    path("invoice/<int:invoice_pk>/status/", views.update_invoice_status, name="update_invoice_status"),
    path("<uuid:pk>/resolve-dispute/", views.resolve_dispute, name="resolve_dispute"),
    path("archive/", views.archive_list, name="archive_list"),
    path("bulk-archive/", views.bulk_archive_completed, name="bulk_archive_completed"),
    path("<uuid:pk>/archive/", views.archive_cluster, name="archive_cluster"),
    path("<uuid:pk>/unarchive/", views.unarchive_cluster, name="unarchive_cluster"),
    path("<uuid:pk>/upload-mro/", views.upload_mro, name="upload_mro"),
    path("mro-summary/", views.mro_summary_view, name="mro_summary"),
    path("mro-summary/create/", views.mro_create_view, name="mro_create"),
    path("mro-summary/<int:pk>/edit/", views.mro_edit_view, name="mro_edit"),
    path("mro-summary/<int:pk>/delete/", views.mro_delete_view, name="mro_delete"),
    path("mro-summary/import/", views.mro_import_excel_view, name="mro_import_excel"),
    path("mro-summary/export/", views.mro_export_csv_view, name="mro_export_csv"),
]

