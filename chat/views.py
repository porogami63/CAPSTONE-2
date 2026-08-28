from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from operations.models import TransactionCluster
from .models import ChatMessage

User = get_user_model()


@login_required
def chat_room_view(request):
    users = User.objects.exclude(id=request.user.id).order_by("first_name", "username")
    clusters = TransactionCluster.objects.all().order_by("-id")[:20]
    
    # Target recipient or cluster thread
    recipient_id = request.GET.get("user")
    cluster_id = request.GET.get("cluster")
    
    active_recipient = get_object_or_404(User, id=recipient_id) if recipient_id else None
    active_cluster = get_object_or_404(TransactionCluster, id=cluster_id) if cluster_id else None

    if active_recipient:
        messages_qs = ChatMessage.objects.filter(
            (Q(sender=request.user, recipient=active_recipient) | Q(sender=active_recipient, recipient=request.user))
        )
        # Mark unread incoming messages as read
        ChatMessage.objects.filter(sender=active_recipient, recipient=request.user, is_read=False).update(is_read=True)
    elif active_cluster:
        messages_qs = ChatMessage.objects.filter(cluster=active_cluster)
    else:
        messages_qs = ChatMessage.objects.filter(recipient__isnull=True, cluster__isnull=True)

    messages_qs = messages_qs.select_related("sender", "recipient", "cluster").order_by("created_at")[:100]

    return render(
        request,
        "chat/room.html",
        {
            "team_users": users,
            "clusters": clusters,
            "active_recipient": active_recipient,
            "active_cluster": active_cluster,
            "chat_messages": messages_qs,
        },
    )


@login_required
def api_fetch_messages(request):
    recipient_id = request.GET.get("user_id")
    cluster_id = request.GET.get("cluster_id")

    if recipient_id:
        qs = ChatMessage.objects.filter(
            (Q(sender=request.user, recipient_id=recipient_id) | Q(sender_id=recipient_id, recipient=request.user))
        )
        # Mark incoming direct messages as read
        ChatMessage.objects.filter(sender_id=recipient_id, recipient=request.user, is_read=False).update(is_read=True)
    elif cluster_id:
        qs = ChatMessage.objects.filter(cluster_id=cluster_id)
    else:
        qs = ChatMessage.objects.filter(recipient__isnull=True, cluster__isnull=True)

    qs = qs.select_related("sender").order_by("created_at")[:50]

    data = []
    for msg in qs:
        data.append({
            "id": msg.id,
            "sender_id": msg.sender.id,
            "sender_name": msg.sender.get_full_name() or msg.sender.username,
            "sender_avatar": msg.sender.avatar_url if msg.sender.avatar else None,
            "sender_initial": msg.sender.username[:1].upper(),
            "message": msg.message,
            "is_system": msg.is_system,
            "created_at": msg.created_at.strftime("%I:%M %p"),
            "is_me": msg.sender.id == request.user.id,
        })

    return JsonResponse({"status": "success", "messages": data})


@login_required
def api_send_message(request):
    if request.method == "POST":
        text = request.POST.get("message", "").strip()
        recipient_id = request.POST.get("recipient_id")
        cluster_id = request.POST.get("cluster_id")

        if not text:
            return JsonResponse({"status": "error", "error": "Message body cannot be empty."}, status=400)

        recipient = User.objects.filter(id=recipient_id).first() if recipient_id else None
        cluster = TransactionCluster.objects.filter(id=cluster_id).first() if cluster_id else None

        msg = ChatMessage.objects.create(
            sender=request.user,
            recipient=recipient,
            cluster=cluster,
            message=text,
        )

        # Trigger Topbar System Notifications for chat messages
        from audit.services import notify_user, notify_roles
        sender_name = request.user.get_full_name() or request.user.username

        if recipient:
            notify_user(
                recipient,
                title=f"Message from {sender_name}",
                message=text[:100],
                level="info",
                link=f"/chat/?user={request.user.id}",
            )
        elif cluster:
            notify_roles(
                [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.FINANCE, User.Role.MANAGEMENT],
                title=f"Discussion on {cluster.reference_code}",
                message=f"{sender_name}: {text[:100]}",
                level="info",
                link=f"/chat/?cluster={cluster.id}",
                exclude_user=request.user,
            )
        else:
            notify_roles(
                [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.FINANCE, User.Role.INVOICING, User.Role.MANAGEMENT],
                title=f"General Team Chat from {sender_name}",
                message=text[:100],
                level="info",
                link="/chat/",
                exclude_user=request.user,
            )

        return JsonResponse({
            "status": "success",
            "message": {
                "id": msg.id,
                "sender_name": sender_name,
                "sender_avatar": request.user.avatar_url if request.user.avatar else None,
                "sender_initial": request.user.username[:1].upper(),
                "message": msg.message,
                "is_system": msg.is_system,
                "created_at": msg.created_at.strftime("%I:%M %p"),
                "is_me": True,
            }
        })

    return JsonResponse({"status": "error", "error": "Invalid HTTP method"}, status=405)


@login_required
def api_unread_count(request):
    """Return JSON count of unread messages sent directly to request.user."""
    unread_count = ChatMessage.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({"status": "success", "unread_count": unread_count})


def send_system_notification(cluster, message_text, sender_user=None):
    """Helper to post automated system notifications into transaction cluster chat threads."""
    if not sender_user:
        sender_user = User.objects.filter(is_superuser=True).first() or User.objects.filter(role=User.Role.ADMINISTRATOR).first()
    if not sender_user or not cluster:
        return None

    msg = ChatMessage.objects.create(
        sender=sender_user,
        cluster=cluster,
        message=message_text,
        is_system=True,
    )

    from audit.services import notify_roles
    notify_roles(
        [User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT, User.Role.FINANCE, User.Role.MANAGEMENT],
        title=f"Operational Event — {cluster.reference_code}",
        message=message_text,
        level="warning",
        link=f"/operations/{cluster.pk}/",
        exclude_user=sender_user,
    )

    return msg

