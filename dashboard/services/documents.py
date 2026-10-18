"""Document registry grouped by operational category with clear distinction between
System-Generated official documents and User-Uploaded supporting scans & receipts.
"""

import os
from django.urls import reverse
from django.utils import timezone

from finance.models import CashVoucher, Invoice
from operations.models import LogisticsLedger, MolassesReleaseOrder, TransactionCluster


def _format_bytes(size_bytes: int) -> str:
    """Format bytes into human-readable string (KB/MB)."""
    if not size_bytes or size_bytes <= 0:
        return "—"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def _fmt_size(amount) -> str:
    """Approximate display size for dynamically generated PDFs."""
    kb = max(int(float(amount) / 1000), 48)
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"


def build_document_registry(query: str = "") -> dict:
    query = query.strip().lower()
    categories = {
        # --- USER UPLOADED DOCUMENTS ---
        "release_orders": {
            "title": "Molasses Release Orders (MRO)",
            "icon": "bi-file-earmark-ruled",
            "origin": "uploaded",
            "origin_label": "User Uploaded Scans",
            "badge_class": "bg-success-subtle text-success border border-success-subtle",
            "items": [],
        },
        "delivery_receipts": {
            "title": "Delivery Receipts & Waybills",
            "icon": "bi-truck",
            "origin": "uploaded",
            "origin_label": "User Uploaded Receipts",
            "badge_class": "bg-success-subtle text-success border border-success-subtle",
            "items": [],
        },
        # --- SYSTEM GENERATED DOCUMENTS ---
        "contracts": {
            "title": "Supply Contracts",
            "icon": "bi-file-earmark-text-fill",
            "origin": "generated",
            "origin_label": "System Generated PDF",
            "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
            "items": [],
        },
        "purchase_orders": {
            "title": "Purchase Orders",
            "icon": "bi-file-earmark-check-fill",
            "origin": "generated",
            "origin_label": "System Generated PDF",
            "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
            "items": [],
        },
        "sales_invoices": {
            "title": "Sales Invoices",
            "icon": "bi-receipt",
            "origin": "generated",
            "origin_label": "System Generated PDF",
            "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
            "items": [],
        },
        "cash_vouchers": {
            "title": "Cash Vouchers",
            "icon": "bi-cash-stack",
            "origin": "generated",
            "origin_label": "System Generated PDF",
            "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
            "items": [],
        },
    }

    clusters = (
        TransactionCluster.objects.select_related("client", "sugar_mill", "purchase_order")
        .prefetch_related("mro_releases__planter", "mro_releases__sugar_mill", "purchase_order__deliveries")
        .order_by("-created_at")
    )

    total_uploaded_bytes = 0
    consolidated_mro_count = 0

    # 1. PROCESS CLUSTERS FOR CONTRACTS, POs, AND MROs
    seen_mro_files = set()

    for cluster in clusters:
        # A. Supply Contract (System Generated)
        c_label = f"Contract-{cluster.reference_code}.pdf"
        if not query or query in c_label.lower() or query in cluster.reference_code.lower() or query in cluster.client.name.lower():
            categories["contracts"]["items"].append(
                {
                    "id": str(cluster.pk),
                    "name": c_label,
                    "date": cluster.created_at,
                    "size": "Dynamic PDF (~115 KB)",
                    "ref": cluster.reference_code,
                    "client_name": cluster.client.name,
                    "mill_name": cluster.sugar_mill.name,
                    "url": reverse("operations:cluster_detail", args=[cluster.pk]),
                    "pdf_url": reverse("operations:download_contract_pdf", args=[cluster.pk]),
                    "origin": "generated",
                    "origin_label": "System Generated PDF",
                    "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
                }
            )

        # B. Purchase Order (System Generated)
        po_label = f"PO-{cluster.reference_code}.pdf"
        if not query or query in po_label.lower() or query in cluster.reference_code.lower() or query in cluster.client.name.lower():
            categories["purchase_orders"]["items"].append(
                {
                    "id": str(cluster.pk),
                    "name": po_label,
                    "date": cluster.created_at,
                    "size": "Dynamic PDF (~120 KB)",
                    "ref": cluster.reference_code,
                    "client_name": cluster.client.name,
                    "mill_name": cluster.sugar_mill.name,
                    "url": reverse("operations:cluster_detail", args=[cluster.pk]),
                    "pdf_url": reverse("operations:download_po_pdf", args=[cluster.pk]),
                    "origin": "generated",
                    "origin_label": "System Generated PDF",
                    "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
                }
            )

        # C. Molasses Release Orders (MRO - User Uploaded Scan / Soft Copy)
        mros = list(cluster.mro_releases.all())
        mro_numbers = [m.mro_number for m in mros]
        mro_search_match = (
            not query
            or query in cluster.reference_code.lower()
            or query in cluster.client.name.lower()
            or query in cluster.sugar_mill.name.lower()
            or any(query in num.lower() for num in mro_numbers)
        )

        has_scan = bool(cluster.mro_file)
        real_file_name = ""
        file_size_display = "—"
        file_size_bytes = 0

        if has_scan:
            try:
                real_file_name = os.path.basename(cluster.mro_file.name)
                file_size_bytes = cluster.mro_file.size
                file_size_display = _format_bytes(file_size_bytes)
                total_uploaded_bytes += file_size_bytes
                seen_mro_files.add(cluster.mro_file.name)
            except Exception:
                real_file_name = os.path.basename(cluster.mro_file.name)
                file_size_display = "Scanned File"

        if not real_file_name:
            real_file_name = f"MRO-PO-{cluster.reference_code}.pdf"

        if has_scan and real_file_name:
            mro_search_match = mro_search_match or (query in real_file_name.lower())

        if mro_search_match:
            total_tons = sum(float(m.tons) for m in mros)
            deliv_count = 0
            if hasattr(cluster, "purchase_order") and cluster.purchase_order:
                deliv_count = cluster.purchase_order.deliveries.count()

            is_consolidated = len(mros) > 1
            if is_consolidated and has_scan:
                consolidated_mro_count += 1

            if is_consolidated:
                coverage_summary = f"Consolidated Document: 1 uploaded scan covers {len(mros)} MRO entries ({total_tons:,.2f} MT) across {deliv_count} delivery batch(es)."
            elif len(mros) == 1:
                coverage_summary = f"Covers MRO #{mros[0].mro_number} ({total_tons:,.2f} MT) for {cluster.reference_code}."
            elif has_scan:
                coverage_summary = f"Uploaded supporting MRO permit document for PO {cluster.reference_code}."
            else:
                coverage_summary = f"Pending scan upload for PO {cluster.reference_code}."

            categories["release_orders"]["items"].append(
                {
                    "id": str(cluster.pk),
                    "name": real_file_name,
                    "date": cluster.updated_at if has_scan else cluster.created_at,
                    "size": file_size_display,
                    "size_bytes": file_size_bytes,
                    "ref": cluster.reference_code,
                    "client_name": cluster.client.name,
                    "mill_name": cluster.sugar_mill.name,
                    "url": reverse("operations:cluster_detail", args=[cluster.pk]),
                    "upload_url": reverse("operations:upload_mro", args=[cluster.pk]),
                    "has_scan": has_scan,
                    "scan_url": cluster.mro_file.url if has_scan else "",
                    "is_pdf": cluster.mro_file.name.lower().endswith(".pdf") if has_scan else True,
                    "origin": "uploaded",
                    "origin_label": "User Uploaded Scan",
                    "badge_class": "bg-success-subtle text-success border border-success-subtle",
                    # Consolidated Multi-MRO / Multi-Delivery metadata
                    "is_consolidated": is_consolidated,
                    "mro_count": len(mros),
                    "mro_numbers": mro_numbers,
                    "mro_entries": [
                        {
                            "mro_number": m.mro_number,
                            "tons": float(m.tons),
                            "planter_name": m.planter.name if m.planter else "",
                            "date": m.release_date,
                        }
                        for m in mros
                    ],
                    "total_tons": total_tons,
                    "deliveries_count": deliv_count,
                    "coverage_summary": coverage_summary,
                }
            )

    # Standalone MRO entries that have their own individual scanned_file (not covered above)
    standalone_mros = (
        MolassesReleaseOrder.objects.filter(scanned_file__isnull=False)
        .exclude(scanned_file="")
        .select_related("cluster", "planter", "sugar_mill")
    )
    for sm in standalone_mros:
        if sm.scanned_file.name in seen_mro_files:
            continue
        try:
            s_name = os.path.basename(sm.scanned_file.name)
            s_bytes = sm.scanned_file.size
            total_uploaded_bytes += s_bytes
        except Exception:
            s_name = f"MRO-{sm.mro_number}-Scan.pdf"
            s_bytes = 0

        if not query or query in s_name.lower() or query in sm.mro_number.lower():
            categories["release_orders"]["items"].append(
                {
                    "id": f"mro-{sm.id}",
                    "name": s_name,
                    "date": sm.created_at,
                    "size": _format_bytes(s_bytes),
                    "size_bytes": s_bytes,
                    "ref": sm.cluster.reference_code if sm.cluster else f"MRO #{sm.mro_number}",
                    "client_name": sm.cluster.client.name if sm.cluster else "Direct Planter",
                    "mill_name": sm.display_sugar_mill,
                    "url": reverse("operations:cluster_detail", args=[sm.cluster.pk]) if sm.cluster else reverse("operations:mro_summary"),
                    "upload_url": reverse("operations:cluster_detail", args=[sm.cluster.pk]) if sm.cluster else "",
                    "has_scan": True,
                    "scan_url": sm.scanned_file.url,
                    "is_pdf": sm.scanned_file.name.lower().endswith(".pdf"),
                    "origin": "uploaded",
                    "origin_label": "User Uploaded Scan",
                    "badge_class": "bg-success-subtle text-success border border-success-subtle",
                    "is_consolidated": False,
                    "mro_count": 1,
                    "mro_numbers": [sm.mro_number],
                    "mro_entries": [{"mro_number": sm.mro_number, "tons": float(sm.tons), "planter_name": sm.planter.name if sm.planter else ""}],
                    "total_tons": float(sm.tons),
                    "deliveries_count": 0,
                    "coverage_summary": f"Direct MRO permit scan for #{sm.mro_number} ({sm.tons} MT).",
                }
            )

    # 2. SALES INVOICES (System Generated)
    invoices = Invoice.objects.select_related("cluster", "cluster__client").order_by("-issued_at")
    for invoice in invoices:
        label = f"{invoice.invoice_number}.pdf"
        if query and query not in label.lower() and query not in invoice.invoice_number.lower():
            continue
        categories["sales_invoices"]["items"].append(
            {
                "id": str(invoice.pk),
                "name": label,
                "date": invoice.issued_at,
                "size": "Dynamic PDF (~110 KB)",
                "ref": invoice.invoice_number,
                "client_name": invoice.cluster.client.name,
                "mill_name": invoice.cluster.sugar_mill.name if invoice.cluster else "",
                "url": reverse("operations:cluster_detail", args=[invoice.cluster.pk]),
                "pdf_url": reverse("finance:download_invoice_pdf", args=[invoice.pk]),
                "origin": "generated",
                "origin_label": "System Generated PDF",
                "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
            }
        )

    # 3. DELIVERY RECEIPTS & WAYBILLS (User Uploaded Scans)
    logistics = LogisticsLedger.objects.select_related("cluster", "cluster__client").order_by("-updated_at")
    for record in logistics:
        # Check DR File
        if record.dr_file:
            try:
                dr_name = os.path.basename(record.dr_file.name)
                dr_bytes = record.dr_file.size
                total_uploaded_bytes += dr_bytes
            except Exception:
                dr_name = f"DR-{record.cluster.reference_code}.pdf"
                dr_bytes = 0

            if not query or query in dr_name.lower() or query in record.cluster.reference_code.lower():
                categories["delivery_receipts"]["items"].append(
                    {
                        "id": f"dr-{record.pk}",
                        "name": dr_name,
                        "date": record.received_at or record.loaded_at or record.updated_at,
                        "size": _format_bytes(dr_bytes),
                        "size_bytes": dr_bytes,
                        "ref": record.cluster.reference_code,
                        "client_name": record.cluster.client.name,
                        "url": reverse("operations:cluster_detail", args=[record.cluster.pk]),
                        "has_scan": True,
                        "scan_url": record.dr_file.url,
                        "is_pdf": record.dr_file.name.lower().endswith(".pdf"),
                        "origin": "uploaded",
                        "origin_label": "User Uploaded DR",
                        "badge_class": "bg-success-subtle text-success border border-success-subtle",
                        "doc_subtype": "Delivery Receipt",
                    }
                )

        # Check Waybill File
        if record.waybill_file:
            try:
                wb_name = os.path.basename(record.waybill_file.name)
                wb_bytes = record.waybill_file.size
                total_uploaded_bytes += wb_bytes
            except Exception:
                wb_name = f"Waybill-{record.cluster.reference_code}.pdf"
                wb_bytes = 0

            if not query or query in wb_name.lower() or query in record.cluster.reference_code.lower():
                categories["delivery_receipts"]["items"].append(
                    {
                        "id": f"wb-{record.pk}",
                        "name": wb_name,
                        "date": record.loaded_at or record.updated_at,
                        "size": _format_bytes(wb_bytes),
                        "size_bytes": wb_bytes,
                        "ref": record.cluster.reference_code,
                        "client_name": record.cluster.client.name,
                        "url": reverse("operations:cluster_detail", args=[record.cluster.pk]),
                        "has_scan": True,
                        "scan_url": record.waybill_file.url,
                        "is_pdf": record.waybill_file.name.lower().endswith(".pdf"),
                        "origin": "uploaded",
                        "origin_label": "User Uploaded Waybill",
                        "badge_class": "bg-success-subtle text-success border border-success-subtle",
                        "doc_subtype": "Waybill",
                    }
                )

        # If no DR or Waybill file uploaded yet, list as pending DR entry
        if not record.dr_file and not record.waybill_file:
            label = f"DR-{record.cluster.reference_code}.pdf"
            if not query or query in label.lower() or query in record.cluster.reference_code.lower():
                categories["delivery_receipts"]["items"].append(
                    {
                        "id": f"pending-{record.pk}",
                        "name": label,
                        "date": record.received_at or record.loaded_at or record.updated_at,
                        "size": "— (Awaiting Scan)",
                        "size_bytes": 0,
                        "ref": record.cluster.reference_code,
                        "client_name": record.cluster.client.name,
                        "url": reverse("operations:cluster_detail", args=[record.cluster.pk]),
                        "has_scan": False,
                        "scan_url": "",
                        "is_pdf": True,
                        "origin": "uploaded",
                        "origin_label": "User Uploaded DR",
                        "badge_class": "bg-warning-subtle text-warning border border-warning-subtle",
                        "doc_subtype": "Delivery Receipt",
                    }
                )

    # 4. CASH VOUCHERS (System Generated)
    vouchers = CashVoucher.objects.select_related("cluster").order_by("-issued_at")
    for voucher in vouchers:
        label = f"CV-{voucher.voucher_number}.pdf"
        if query and query not in label.lower() and query not in voucher.voucher_number.lower():
            continue
        categories["cash_vouchers"]["items"].append(
            {
                "id": str(voucher.pk),
                "name": label,
                "date": voucher.issued_at,
                "size": "Dynamic PDF (~95 KB)",
                "ref": voucher.voucher_number,
                "client_name": voucher.cluster.client.name if voucher.cluster else "",
                "url": reverse("operations:cluster_detail", args=[voucher.cluster.pk]),
                "pdf_url": reverse("finance:download_voucher_pdf", args=[voucher.pk]),
                "origin": "generated",
                "origin_label": "System Generated PDF",
                "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
            }
        )

    # Total counts and origin breakdown
    total_docs = sum(len(c["items"]) for c in categories.values())
    total_uploaded = sum(len(c["items"]) for c in categories.values() if c["origin"] == "uploaded")
    total_generated = sum(len(c["items"]) for c in categories.values() if c["origin"] == "generated")

    this_month = timezone.localdate().replace(day=1)
    uploaded_month = 0
    for cat in categories.values():
        for item in cat["items"]:
            item_date = item["date"]
            if hasattr(item_date, "date"):
                item_date = item_date.date()
            if item_date and item_date >= this_month:
                uploaded_month += 1

    storage_used_display = _format_bytes(total_uploaded_bytes)
    if total_uploaded_bytes == 0 and total_docs > 0:
        storage_used_display = f"{round(total_docs * 0.12, 1)} MB"

    return {
        "categories": categories,
        "total_documents": total_docs,
        "total_uploaded_count": total_uploaded,
        "total_generated_count": total_generated,
        "total_uploaded_bytes": total_uploaded_bytes,
        "storage_used_display": storage_used_display,
        "consolidated_mro_scans_count": consolidated_mro_count,
        "uploaded_this_month": uploaded_month,
        "pending_review": sum(1 for c in clusters if c.status == TransactionCluster.Status.DRAFT),
        "query": query,
    }
