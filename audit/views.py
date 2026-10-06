from django.db.models import Q
from django.shortcuts import render

from accounts.decorators import role_required
from accounts.models import User
from .models import SystemAuditTrail


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def audit_list(request):
    action_filter = request.GET.get("action", "").strip()
    table_filter = request.GET.get("table", "").strip()
    user_filter = request.GET.get("user", "").strip()
    q = request.GET.get("q", "").strip()

    entries_qs = SystemAuditTrail.objects.select_related("user").all()

    if action_filter:
        entries_qs = entries_qs.filter(action=action_filter)
    if table_filter:
        entries_qs = entries_qs.filter(table_name__icontains=table_filter)
    if user_filter:
        try:
            entries_qs = entries_qs.filter(user_id=user_filter)
        except Exception:
            pass
    if q:
        entries_qs = entries_qs.filter(
            Q(table_name__icontains=q) |
            Q(record_id__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)
        )

    users_list = User.objects.filter(audit_entries__isnull=False).distinct()
    available_actions = SystemAuditTrail.Action.choices

    entries = entries_qs.order_by("-timestamp")[:300]

    return render(
        request,
        "audit/list.html",
        {
            "entries": entries,
            "users_list": users_list,
            "available_actions": available_actions,
            "action_filter": action_filter,
            "table_filter": table_filter,
            "user_filter": user_filter,
            "q": q,
            "total_audit_count": SystemAuditTrail.objects.count(),
        },
    )


from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .models import Notification


@login_required
def api_notifications(request):
    category_filter = request.GET.get("category", "").strip().lower()
    notifications = Notification.objects.filter(recipient=request.user, is_read=False)[:50]
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()

    data = []
    category_counts = {
        "all": unread_count,
        "approval": 0,
        "variance": 0,
        "logistics": 0,
        "loan": 0,
        "system": 0,
    }

    for n in notifications:
        cat = str(n.get_classified_category()).lower()
        if cat in category_counts:
            category_counts[cat] += 1
        else:
            category_counts["system"] += 1

        if not category_filter or category_filter == "all" or cat == category_filter:
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
