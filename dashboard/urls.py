from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("analytics/", views.analytics, name="analytics"),
    path("analytics/export/pdf/", views.export_analytics_pdf, name="analytics_export_pdf"),
    path("analytics/export/xlsx/", views.export_analytics_xlsx, name="analytics_export_xlsx"),
    path("analytics/export/csv/", views.export_analytics_csv, name="analytics_export_csv"),
    path("documents/", views.documents, name="documents"),
    path("report/<str:period>/pdf/", views.download_consolidated_report, name="download_report"),
]
