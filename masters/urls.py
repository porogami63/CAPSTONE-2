from django.urls import path

from . import views

app_name = "masters"

urlpatterns = [
    path("", views.master_list, name="list"),
    path("partners/", views.partners, name="partners"),
    path("clients/new/", views.create_client, name="create_client"),
    path("suppliers/new/", views.create_supplier, name="create_supplier"),
    path("clients/<int:pk>/", views.client_portfolio, name="client_portfolio"),
    path("suppliers/<int:pk>/", views.supplier_portfolio, name="supplier_portfolio"),
    path("partners/<str:partner_type>/<int:pk>/avatar/", views.update_partner_avatar, name="update_partner_avatar"),
    path("partners/<str:partner_type>/<int:pk>/note/", views.add_partner_note, name="add_partner_note"),
]
