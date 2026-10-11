from django.contrib import admin

from .models import DeliveryLedger, LogisticsLedger, PurchaseOrder, TransactionCluster


class DeliveryLedgerInline(admin.TabularInline):
    model = DeliveryLedger
    extra = 0
    fields = ("delivery_date", "supplier", "receiving_location", "delivered_mt", "carrier", "vessel_or_truck", "dr_number")


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


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("po_reference_number", "customer", "total_contracted_mt", "total_delivered_mt", "remaining_mt", "po_status")
    list_filter = ("po_status",)
    search_fields = ("po_reference_number", "customer__name")
    inlines = [DeliveryLedgerInline]


@admin.register(DeliveryLedger)
class DeliveryLedgerAdmin(admin.ModelAdmin):
    list_display = ("delivery_id", "purchase_order", "supplier", "receiving_location", "delivered_mt", "delivery_date")
    list_filter = ("supplier", "receiving_location", "delivery_date")
    search_fields = ("purchase_order__po_reference_number", "receiving_location", "dr_number")


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
