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
        entries_qs = entries_qs.filter(user_id=user_filter)
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
    notifications = Notification.objects.filter(recipient=request.user, is_read=False)[:15]
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()

    data = [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "level": n.level,
            "link": n.link or "#",
            "created_at": n.created_at.strftime("%b %d, %H:%M"),
        }
        for n in notifications
    ]
    return JsonResponse({"status": "success", "unread_count": unread_count, "notifications": data})


@login_required
@require_POST
def api_mark_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"status": "success", "unread_count": 0})
