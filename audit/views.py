from django.shortcuts import render

from accounts.decorators import role_required
from accounts.models import User

from .models import SystemAuditTrail


@role_required(User.Role.MANAGEMENT)
def audit_list(request):
    entries = SystemAuditTrail.objects.select_related("user")[:200]
    return render(request, "audit/list.html", {"entries": entries})
