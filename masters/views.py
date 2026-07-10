from django.shortcuts import render

from accounts.decorators import role_required
from accounts.models import User
from dashboard.services.analytics import partner_stats

from .models import Client, LogisticsPartner, SugarMill


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS)
def master_list(request):
    return render(
        request,
        "masters/list.html",
        {
            "clients": Client.objects.filter(is_active=True),
            "mills": SugarMill.objects.filter(is_active=True),
            "partners": LogisticsPartner.objects.filter(is_active=True),
        },
    )


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
)
def partners(request):
    stats = partner_stats()
    return render(request, "masters/partners.html", stats)
