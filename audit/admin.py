from django.contrib import admin

from .models import SystemAuditTrail


@admin.register(SystemAuditTrail)
class SystemAuditTrailAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "table_name", "record_id")
    list_filter = ("action", "table_name")
    search_fields = ("table_name", "record_id", "user__username")
    readonly_fields = (
        "user",
        "action",
        "table_name",
        "record_id",
        "old_values",
        "new_values",
        "timestamp",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
