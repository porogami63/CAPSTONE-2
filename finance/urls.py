from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("invoice/", views.invoice_list, name="invoice_list"),
    path("loans/", views.loan_list, name="loan_list"),
    path("reconciliation/<uuid:pk>/", views.reconciliation_detail, name="reconciliation"),
    path("reconciliation/<uuid:pk>/match/", views.add_match, name="add_match"),
]
