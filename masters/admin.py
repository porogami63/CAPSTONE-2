from django.contrib import admin

from .models import Client, LogisticsPartner, SugarMill


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "tin", "contact_person", "is_active")
    search_fields = ("name", "tin")


@admin.register(SugarMill)
class SugarMillAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "is_active")
    search_fields = ("name", "location")


@admin.register(LogisticsPartner)
class LogisticsPartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "default_freight_rate", "is_active")
    search_fields = ("name",)
