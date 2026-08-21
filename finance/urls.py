from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("loans/", views.loan_list, name="loan_list"),
    path("loans/<int:pk>/settle/", views.settle_loan, name="settle_loan"),
    path("loans/<int:pk>/verify-creation/", views.verify_loan_creation, name="verify_loan_creation"),
    path("loans/<int:pk>/verify-settlement/", views.verify_loan_settlement, name="verify_loan_settlement"),
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("reconciliation/<uuid:pk>/", views.reconciliation_detail, name="reconciliation"),
    path("reconciliation/<uuid:pk>/match/", views.add_match, name="add_match"),
    path("invoice/<int:pk>/pdf/", views.download_invoice_pdf, name="download_invoice_pdf"),
]
