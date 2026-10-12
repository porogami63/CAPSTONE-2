import csv
import os
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from audit.models import SystemAuditTrail
from operations.models import TransactionCluster

from .services import (
    create_database_backup,
    get_archive_metrics,
    get_audit_summary,
    get_backups_directory,
    get_dataflow_metrics,
    get_system_telemetry,
    get_user_analytics,
    get_website_latency_and_activity,
    list_database_backups,
)


def admin_required(view_func):
    """
    Decorator enforcing strict access control:
    Only authenticated users with the Administrator role are permitted.
    Operations managers and any other non-admin users are strictly denied with HTTP 403 Forbidden.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        
        is_admin_role = (getattr(request.user, "role", None) == User.Role.ADMINISTRATOR)
        if not is_admin_role or not request.user.is_active:
            raise PermissionDenied("Access restricted strictly to System Administrators (NFR-07 / NFR-08).")
        
        return view_func(request, *args, **kwargs)
    return _wrapped


@admin_required
def dashboard_view(request):
    """
    Website Administration Hub: monitors website latency, website activity,
    user accounts, user audits (NFR-07), data archives, and database backups (NFR-08).
    """
    active_tab = request.GET.get("tab", "overview")
    audit_action = request.GET.get("audit_action", "").strip()
    audit_table = request.GET.get("audit_table", "").strip()
    audit_q = request.GET.get("audit_q", "").strip()

    website_metrics = get_website_latency_and_activity()
    telemetry = get_system_telemetry()
    dataflow = get_dataflow_metrics()
    user_analytics = get_user_analytics()
    audit_summary = get_audit_summary(
        action_filter=audit_action,
        table_filter=audit_table,
        query=audit_q,
    )
    archive_metrics = get_archive_metrics()
    backups = list_database_backups()

    context = {
        "active_tab": active_tab,
        "website_metrics": website_metrics,
        "telemetry": telemetry,
        "dataflow": dataflow,
        "user_analytics": user_analytics,
        "audit_summary": audit_summary,
        "archive_metrics": archive_metrics,
        "backups": backups,
        "audit_action": audit_action,
        "audit_table": audit_table,
        "audit_q": audit_q,
    }

    return render(request, "admin_hub/dashboard.html", context)


@admin_required
@require_POST
def trigger_backup_view(request):
    """
    Triggers an instant, compressed database snapshot (NFR-08).
    """
    try:
        backup_info = create_database_backup(user=request.user)
        size_display = (
            f"{round(backup_info['size_bytes'] / (1024 * 1024), 2)} MB"
            if backup_info["size_bytes"] >= 1024 * 1024
            else f"{round(backup_info['size_bytes'] / 1024, 1)} KB"
        )
        messages.success(
            request,
            f"Instant database backup '{backup_info['filename']}' ({size_display}) created successfully."
        )
    except Exception as e:
        messages.error(request, f"Error generating database snapshot: {e}")

    return redirect("/admin/?tab=backups#tab-backups")


@admin_required
def download_backup_view(request, filename):
    """
    Securely streams a database backup file for administrative download.
    """
    clean_filename = os.path.basename(filename)
    b_dir = get_backups_directory()
    filepath = b_dir / clean_filename

    # Also check /home/ubuntu/backups if running on EC2
    if not filepath.exists():
        ec2_path = os.path.join("/home/ubuntu/backups", clean_filename)
        if os.path.exists(ec2_path):
            filepath = ec2_path

    if not os.path.exists(filepath):
        raise Http404(f"Backup archive '{clean_filename}' was not found on this server.")

    SystemAuditTrail.objects.create_entry(
        user=request.user,
        action="update",
        table_name="DatabaseBackup",
        record_id=clean_filename,
        new_values={"downloaded_by": request.user.username, "timestamp": timezone.now().isoformat()},
    )

    return FileResponse(open(filepath, "rb"), as_attachment=True, filename=clean_filename)


@admin_required
@require_POST
def user_approve_view(request, pk):
    """Approves a pending registration and assigns an operational role."""
    target_user = get_object_or_404(User, pk=pk)
    role = request.POST.get("role")
    
    if role and role in dict(User.Role.choices):
        target_user.role = role
    target_user.is_active = True
    target_user.save()

    SystemAuditTrail.objects.create_entry(
        user=request.user,
        action="update",
        table_name="User",
        record_id=str(target_user.pk),
        new_values={"is_active": True, "role": target_user.role, "action": "Admin Approval"},
    )

    messages.success(request, f"Account @{target_user.username} approved and activated as {target_user.get_role_display()}.")
    return redirect("/admin/?tab=users#tab-users")


@admin_required
@require_POST
def user_toggle_active_view(request, pk):
    """Toggles active/inactive status for a user account."""
    target_user = get_object_or_404(User, pk=pk)
    
    if target_user == request.user:
        messages.error(request, "Security Guard: You cannot deactivate your own administrative account.")
        return redirect("/admin/?tab=users#tab-users")

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])

    status_str = "activated" if target_user.is_active else "deactivated"
    SystemAuditTrail.objects.create_entry(
        user=request.user,
        action="update",
        table_name="User",
        record_id=str(target_user.pk),
        new_values={"is_active": target_user.is_active, "status": status_str},
    )

    messages.success(request, f"User account @{target_user.username} has been {status_str}.")
    return redirect("/admin/?tab=users#tab-users")


@admin_required
@require_POST
def user_update_role_view(request, pk):
    """Updates the RBAC role of a user."""
    target_user = get_object_or_404(User, pk=pk)
    new_role = request.POST.get("role")

    if new_role and new_role in dict(User.Role.choices):
        old_role = target_user.role
        target_user.role = new_role
        target_user.save(update_fields=["role"])

        SystemAuditTrail.objects.create_entry(
            user=request.user,
            action="update",
            table_name="User",
            record_id=str(target_user.pk),
            old_values={"role": old_role},
            new_values={"role": new_role},
        )
        messages.success(request, f"Updated role for @{target_user.username} to {target_user.get_role_display()}.")
    else:
        messages.error(request, "Invalid role specified.")

    return redirect("/admin/?tab=users#tab-users")


@admin_required
@require_POST
def archive_restore_view(request, pk):
    """Restores an archived transaction cluster back to active status."""
    cluster = get_object_or_404(TransactionCluster, pk=pk)
    cluster.is_archived = False
    cluster.archived_at = None
    cluster._audit_user = request.user
    cluster.save(update_fields=["is_archived", "archived_at"])

    SystemAuditTrail.objects.create_entry(
        user=request.user,
        action="update",
        table_name="TransactionCluster",
        record_id=str(cluster.pk),
        new_values={"is_archived": False, "action": "Restored from Archive Vault"},
    )

    messages.success(request, f"Transaction {cluster.reference_code} restored to active operations.")
    return redirect("/admin/?tab=archives#tab-archives")


@admin_required
def export_audit_csv_view(request):
    """Exports the System Audit Trail as a CSV spreadsheet (NFR-07)."""
    response = HttpResponse(content_type="text/csv")
    filename = f"htc_audit_trail_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["Timestamp (UTC)", "User", "Action", "Entity / Table", "Record ID", "Old Values", "New Values"])

    for entry in SystemAuditTrail.objects.select_related("user").all().order_by("-timestamp")[:1000]:
        writer.writerow([
            entry.timestamp.isoformat(),
            entry.user.username if entry.user else "System",
            entry.action.upper(),
            entry.table_name,
            entry.record_id,
            str(entry.old_values),
            str(entry.new_values),
        ])

    return response


@admin_required
def export_dataflow_csv_view(request):
    """Exports the operational data flow metrics as a CSV spreadsheet."""
    response = HttpResponse(content_type="text/csv")
    filename = f"htc_dataflow_metrics_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        "Transaction Reference", "Customer", "Sugar Mill", "Contracted MT",
        "Loaded MT", "Received MT", "Variance %", "Dispute Status", "Invoiced Amount", "Status"
    ])

    for c in TransactionCluster.objects.select_related("client", "sugar_mill", "logistics", "purchase_order").all():
        logistics = getattr(c, "logistics", None)
        loaded = logistics.loaded_volume_mt if logistics and logistics.loaded_volume_mt else 0
        received = logistics.received_volume_mt if logistics and logistics.received_volume_mt else 0
        var_pct = logistics.variance_percent if logistics and logistics.variance_percent else 0
        dispute = logistics.dispute_status if logistics else "NONE"
        inv_total = sum(inv.amount for inv in c.invoices.all())

        writer.writerow([
            c.reference_code,
            c.client.name if c.client else "—",
            c.sugar_mill.name if c.sugar_mill else "—",
            c.purchase_order.volume_mt if hasattr(c, "purchase_order") and c.purchase_order else 0,
            loaded,
            received,
            f"{var_pct:.2f}%" if var_pct else "0.00%",
            dispute,
            inv_total,
            c.get_status_display(),
        ])

    return response
