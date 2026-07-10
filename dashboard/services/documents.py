"""Document registry grouped by operational category."""

from django.utils import timezone

from finance.models import CashVoucher, Invoice
from operations.models import LogisticsLedger, TransactionCluster


def _fmt_size(amount) -> str:
    """Approximate display size from monetary amount."""
    kb = max(int(float(amount) / 1000), 48)
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"


def build_document_registry(query: str = "") -> dict:
    query = query.strip().lower()
    categories = {
        "release_orders": {"title": "Molasses Release Orders", "icon": "bi-file-earmark-ruled", "items": []},
        "sales_invoices": {"title": "Sales Invoices", "icon": "bi-receipt", "items": []},
        "delivery_receipts": {"title": "Delivery Receipts", "icon": "bi-truck", "items": []},
        "cash_vouchers": {"title": "Cash Vouchers", "icon": "bi-cash-stack", "items": []},
    }

    clusters = TransactionCluster.objects.select_related("client", "sugar_mill").order_by("-created_at")
    for cluster in clusters:
        label = f"MRO-{cluster.reference_code}-{cluster.client.name[:12]}.pdf"
        if query and query not in label.lower() and query not in cluster.reference_code.lower():
            continue
        categories["release_orders"]["items"].append(
            {
                "name": label,
                "date": cluster.created_at,
                "size": _fmt_size(getattr(cluster, "purchase_order", None) and cluster.purchase_order.total_value or 50000),
                "ref": cluster.reference_code,
            }
        )

    invoices = Invoice.objects.select_related("cluster", "cluster__client").order_by("-issued_at")
    for invoice in invoices:
        label = f"{invoice.invoice_number}.pdf"
        if query and query not in label.lower() and query not in invoice.invoice_number.lower():
            continue
        categories["sales_invoices"]["items"].append(
            {
                "name": label,
                "date": invoice.issued_at,
                "size": _fmt_size(invoice.amount),
                "ref": invoice.invoice_number,
            }
        )

    logistics = LogisticsLedger.objects.select_related("cluster", "cluster__client").order_by("-updated_at")
    for record in logistics:
        label = f"DR-{record.cluster.reference_code}.pdf"
        if query and query not in label.lower():
            continue
        categories["delivery_receipts"]["items"].append(
            {
                "name": label,
                "date": record.received_at or record.loaded_at or record.updated_at,
                "size": _fmt_size(record.loaded_volume_mt or 100),
                "ref": record.cluster.reference_code,
            }
        )

    vouchers = CashVoucher.objects.select_related("cluster").order_by("-issued_at")
    for voucher in vouchers:
        label = f"CV-{voucher.voucher_number}.pdf"
        if query and query not in label.lower() and query not in voucher.voucher_number.lower():
            continue
        categories["cash_vouchers"]["items"].append(
            {
                "name": label,
                "date": voucher.issued_at,
                "size": _fmt_size(voucher.amount),
                "ref": voucher.voucher_number,
            }
        )

    total_docs = sum(len(c["items"]) for c in categories.values())
    this_month = timezone.localdate().replace(day=1)
    uploaded_month = 0
    for cat in categories.values():
        for item in cat["items"]:
            item_date = item["date"]
            if hasattr(item_date, "date"):
                item_date = item_date.date()
            if item_date >= this_month:
                uploaded_month += 1

    return {
        "categories": categories,
        "total_documents": total_docs,
        "uploaded_this_month": uploaded_month,
        "storage_used_gb": round(total_docs * 0.0096, 1),
        "pending_review": sum(1 for c in clusters if c.status == TransactionCluster.Status.DRAFT),
        "query": query,
    }
