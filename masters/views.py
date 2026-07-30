import json
from decimal import Decimal
from collections import defaultdict

from django.contrib import messages
from django.db.models import Avg, Count, Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from accounts.models import User
from dashboard.services.analytics import _avg_lead_days, _avg_shrinkage_percent, partner_stats
from finance.models import Invoice
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster

from .models import Client, LogisticsPartner, PartnerNote, SugarMill


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


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
)
def client_portfolio(request, pk):
    client = get_object_or_404(Client, pk=pk)

    if request.method == "POST" and "update_profile" in request.POST:
        client.contact_person = request.POST.get("contact_person", "").strip()
        client.contact_phone = request.POST.get("contact_phone", "").strip()
        client.email = request.POST.get("email", "").strip()
        client.tin = request.POST.get("tin", "").strip()
        client.address = request.POST.get("address", "").strip()
        client.notes = request.POST.get("notes", "").strip()
        client.save()
        messages.success(request, f"Updated relationship portfolio details for {client.name}.")
        return redirect("masters:client_portfolio", pk=pk)

    clusters = list(
        TransactionCluster.objects.filter(client=client)
        .select_related("sugar_mill", "logistics", "purchase_order")
        .prefetch_related("invoices")
        .order_by("-created_at")
    )
    invoices = list(
        Invoice.objects.filter(cluster__client=client).select_related("cluster").order_by("-issued_at")
    )

    total_volume = sum(c.purchase_order.volume_mt for c in clusters if hasattr(c, "purchase_order") and c.purchase_order) or Decimal("0")
    total_invoiced = sum(inv.amount for inv in invoices) or Decimal("0")
    paid_invoiced = sum(inv.amount for inv in invoices if inv.status == Invoice.Status.PAID) or Decimal("0")
    pending_invoiced = total_invoiced - paid_invoiced
    paid_ratio = round((paid_invoiced / total_invoiced * 100), 1) if total_invoiced > 0 else 100.0

    # Sales by month for Chart.js
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_sales = [0.0] * 12
    for inv in invoices:
        idx = inv.issued_at.month - 1
        monthly_sales[idx] += float(inv.amount) / 1_000_000.0

    notes_list = PartnerNote.objects.filter(client=client).select_related("author").order_by("-created_at")

    context = {
        "client": client,
        "clusters": clusters,
        "invoices": invoices,
        "total_volume": total_volume,
        "total_invoiced": total_invoiced,
        "paid_invoiced": paid_invoiced,
        "pending_invoiced": pending_invoiced,
        "paid_ratio": paid_ratio,
        "monthly_sales_json": json.dumps(monthly_sales),
        "month_labels_json": json.dumps(month_labels),
        "notes_list": notes_list,
    }
    return render(request, "masters/client_portfolio.html", context)


@role_required(
    User.Role.MANAGEMENT,
    User.Role.OPERATIONS,
    User.Role.FINANCE,
)
def supplier_portfolio(request, pk):
    mill = get_object_or_404(SugarMill, pk=pk)

    if request.method == "POST" and "update_profile" in request.POST:
        mill.contact_person = request.POST.get("contact_person", "").strip()
        mill.contact_phone = request.POST.get("contact_phone", "").strip()
        mill.email = request.POST.get("email", "").strip()
        mill.location = request.POST.get("location", "").strip()
        mill.notes = request.POST.get("notes", "").strip()
        mill.save()
        messages.success(request, f"Updated supplier portfolio details for {mill.name}.")
        return redirect("masters:supplier_portfolio", pk=pk)

    clusters = list(
        TransactionCluster.objects.filter(sugar_mill=mill)
        .select_related("client", "logistics", "purchase_order")
        .order_by("-created_at")
    )
    logistics_records = list(
        LogisticsLedger.objects.filter(cluster__sugar_mill=mill).select_related("cluster", "cluster__client", "partner")
    )

    total_sourced_volume = sum(c.purchase_order.volume_mt for c in clusters if hasattr(c, "purchase_order") and c.purchase_order) or Decimal("0")
    total_spend = sum(c.purchase_order.volume_mt * c.purchase_order.unit_price for c in clusters if hasattr(c, "purchase_order") and c.purchase_order) or Decimal("0")

    shrinkage_pct = _avg_shrinkage_percent(mill.id)
    lead_days = _avg_lead_days(mill.id)
    reliability = min(95, round(60 + float(len(clusters)) * 4))

    disputed_shipments = [l for l in logistics_records if l.variance_exceeds_tolerance]

    notes_list = PartnerNote.objects.filter(sugar_mill=mill).select_related("author").order_by("-created_at")

    context = {
        "mill": mill,
        "clusters": clusters,
        "logistics_records": logistics_records,
        "disputed_shipments": disputed_shipments,
        "total_sourced_volume": total_sourced_volume,
        "total_spend": total_spend,
        "shrinkage_pct": shrinkage_pct,
        "lead_days": lead_days,
        "reliability": reliability,
        "notes_list": notes_list,
    }
    return render(request, "masters/supplier_portfolio.html", context)


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS, User.Role.FINANCE)
def update_partner_avatar(request, partner_type, pk):
    if request.method == "POST" and request.FILES.get("avatar"):
        if partner_type == "client":
            partner = get_object_or_404(Client, pk=pk)
            partner.avatar = request.FILES["avatar"]
            partner.save()
            messages.success(request, f"Profile picture updated for {partner.name}.")
            return redirect("masters:client_portfolio", pk=pk)
        elif partner_type == "supplier":
            partner = get_object_or_404(SugarMill, pk=pk)
            partner.avatar = request.FILES["avatar"]
            partner.save()
            messages.success(request, f"Profile picture updated for {partner.name}.")
            return redirect("masters:supplier_portfolio", pk=pk)
    return redirect("masters:partners")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS, User.Role.FINANCE)
def add_partner_note(request, partner_type, pk):
    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if content:
            if partner_type == "client":
                client = get_object_or_404(Client, pk=pk)
                PartnerNote.objects.create(client=client, author=request.user, content=content)
                messages.success(request, "Interaction note added.")
                return redirect("masters:client_portfolio", pk=pk)
            elif partner_type == "supplier":
                mill = get_object_or_404(SugarMill, pk=pk)
                PartnerNote.objects.create(sugar_mill=mill, author=request.user, content=content)
                messages.success(request, "Interaction note added.")
                return redirect("masters:supplier_portfolio", pk=pk)
    return redirect("masters:partners")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS, User.Role.FINANCE)
def create_client(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Customer name is required.")
            return redirect("masters:partners")

        client = Client.objects.create(
            name=name,
            tin=request.POST.get("tin", "").strip(),
            address=request.POST.get("address", "").strip(),
            contact_person=request.POST.get("contact_person", "").strip(),
            contact_phone=request.POST.get("contact_phone", "").strip(),
            email=request.POST.get("email", "").strip(),
            notes=request.POST.get("notes", "").strip(),
            avatar=request.FILES.get("avatar"),
        )
        messages.success(request, f"Customer '{client.name}' registered successfully.")
        return redirect("masters:client_portfolio", pk=client.pk)
    return redirect("masters:partners")


@role_required(User.Role.MANAGEMENT, User.Role.OPERATIONS, User.Role.FINANCE)
def create_supplier(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Supplier name is required.")
            return redirect("masters:partners")

        mill = SugarMill.objects.create(
            name=name,
            location=request.POST.get("location", "").strip(),
            contact_person=request.POST.get("contact_person", "").strip(),
            contact_phone=request.POST.get("contact_phone", "").strip(),
            email=request.POST.get("email", "").strip(),
            notes=request.POST.get("notes", "").strip(),
            avatar=request.FILES.get("avatar"),
        )
        messages.success(request, f"Supplier '{mill.name}' registered successfully.")
        return redirect("masters:supplier_portfolio", pk=mill.pk)
    return redirect("masters:partners")

