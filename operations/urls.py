from django.urls import path

from . import views

app_name = "operations"

urlpatterns = [
    path("", views.cluster_list, name="cluster_list"),
    path("new/", views.cluster_create, name="cluster_create"),
    path("<uuid:pk>/", views.cluster_detail, name="cluster_detail"),
    path("<uuid:pk>/logistics/", views.update_logistics, name="update_logistics"),
    path("<uuid:pk>/invoice/", views.add_invoice, name="add_invoice"),
    path("<uuid:pk>/voucher/", views.add_voucher, name="add_voucher"),
    path("<uuid:pk>/loan/", views.add_loan, name="add_loan"),
]
