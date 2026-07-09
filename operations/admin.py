from django.contrib import admin

from .models import LogisticsLedger, PurchaseOrder, TransactionCluster


class PurchaseOrderInline(admin.StackedInline):
    model = PurchaseOrder
    extra = 0


class LogisticsLedgerInline(admin.StackedInline):
    model = LogisticsLedger
    extra = 0


@admin.register(TransactionCluster)
class TransactionClusterAdmin(admin.ModelAdmin):
    list_display = ("reference_code", "client", "sugar_mill", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reference_code", "client__name")
    inlines = [PurchaseOrderInline, LogisticsLedgerInline]


@admin.register(LogisticsLedger)
class LogisticsLedgerAdmin(admin.ModelAdmin):
    list_display = (
        "cluster",
        "loaded_volume_mt",
        "received_volume_mt",
        "variance_percent",
        "variance_exceeds_tolerance",
    )
    list_filter = ("variance_exceeds_tolerance",)
