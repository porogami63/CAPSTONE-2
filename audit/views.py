from django.db.models import Q
from django.shortcuts import render

from accounts.decorators import role_required
from accounts.models import User
from .models import SystemAuditTrail


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def audit_list(request):
    """
    Deprecated Activity History route. Redirects seamlessly to the unified Blockchain Ledger.
    Access restricted exclusively to Administrator and Operations Management roles.
    """
    from django.shortcuts import redirect
    return redirect("operations:blockchain_ledger")


from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .models import Notification


@login_required
def api_notifications(request):
    category_filter = request.GET.get("category", "").strip().lower()
    unread_qs = Notification.objects.filter(recipient=request.user, is_read=False).order_by("-created_at")
    unread_count = unread_qs.count()

    data = []
    category_counts = {
        "all": unread_count,
        "approval": 0,
        "variance": 0,
        "logistics": 0,
        "loan": 0,
        "system": 0,
    }

    for n in unread_qs:
        cat = str(n.get_classified_category()).lower()
        if cat in category_counts:
            category_counts[cat] += 1
        else:
            category_counts["system"] += 1

        if (not category_filter or category_filter == "all" or cat == category_filter) and len(data) < 50:
            data.append({
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "level": n.level,
                "category": cat,
                "category_label": cat.upper(),
                "link": n.link or "#",
                "created_at": n.created_at.strftime("%b %d, %H:%M"),
            })

    return JsonResponse({
        "status": "success",
        "unread_count": unread_count,
        "category_counts": category_counts,
        "notifications": data,
    })


@login_required
@require_POST
def api_mark_single_notification_read(request, notif_id):
    Notification.objects.filter(recipient=request.user, id=notif_id).update(is_read=True)
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({"status": "success", "unread_count": unread_count})


@login_required
@require_POST
def api_mark_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"status": "success", "unread_count": 0})
