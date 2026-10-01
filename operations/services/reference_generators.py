"""Reference number generators for Purchase Orders (POs), Contracts, Sales Invoices (SI), and Check Vouchers (CV).

Auto-generates sensible date-based reference codes consistent with company processes.
"""

import re
from datetime import date
from django.utils import timezone


def generate_po_reference(date_val=None, prefix="PO"):
    """Auto-generates sensible date-based PO / Contract reference code.

    Format: PO-YYYYMMDD-XXX (e.g. PO-20260925-001)
    """
    from operations.models import TransactionCluster

    if date_val is None:
        date_val = timezone.localdate()
    elif isinstance(date_val, str):
        try:
            date_val = date.fromisoformat(date_val)
        except ValueError:
            date_val = timezone.localdate()

    date_str = date_val.strftime("%Y%m%d")
    pattern_prefix = f"{prefix}-{date_str}-"

    existing = TransactionCluster.objects.filter(
        reference_code__startswith=pattern_prefix
    ).values_list("reference_code", flat=True)

    max_seq = 0
    for ref in existing:
        seq_part = ref[len(pattern_prefix):]
        match = re.match(r"^(\d+)", seq_part)
        if match:
            num = int(match.group(1))
            if num > max_seq:
                max_seq = num

    new_seq = max_seq + 1
    return f"{pattern_prefix}{new_seq:03d}"


def generate_si_reference(cluster_or_po_ref=None, date_val=None):
    """Auto-generates sensible date-based Sales Invoice (SI) reference number linked to PO.

    If PO is PO-20260925-001, SI will be SI-20260925-001.
    If SI-20260925-001 already exists, generates SI-20260925-001-2 etc.
    """
    from finance.models import Invoice

    if date_val is None:
        date_val = timezone.localdate()
    date_str = date_val.strftime("%Y%m%d")

    po_ref_clean = ""
    if cluster_or_po_ref:
        po_ref_clean = str(cluster_or_po_ref).strip()

    if po_ref_clean.startswith(("PO-", "HTC-", "CT-")):
        parts = po_ref_clean.split("-", 1)
        base_si = f"SI-{parts[1]}"
    elif po_ref_clean:
        clean_code = re.sub(r"[^A-Za-z0-9]", "", po_ref_clean)
        base_si = f"SI-{date_str}-{clean_code}"
    else:
        base_si = f"SI-{date_str}-001"

    if not Invoice.objects.filter(invoice_number=base_si).exists():
        return base_si

    seq = 2
    while Invoice.objects.filter(invoice_number=f"{base_si}-{seq}").exists():
        seq += 1
    return f"{base_si}-{seq}"


def generate_cv_reference(cluster_or_po_ref=None, date_val=None):
    """Auto-generates sensible date-based Check Voucher (CV) reference number linked to PO.

    If PO is PO-20260925-001, CV will be CV-20260925-001.
    If CV-20260925-001 already exists, generates CV-20260925-001-A etc.
    """
    from finance.models import CashVoucher

    if date_val is None:
        date_val = timezone.localdate()
    date_str = date_val.strftime("%Y%m%d")

    po_ref_clean = ""
    if cluster_or_po_ref:
        po_ref_clean = str(cluster_or_po_ref).strip()

    if po_ref_clean.startswith(("PO-", "HTC-", "CT-", "SI-")):
        parts = po_ref_clean.split("-", 1)
        base_cv = f"CV-{parts[1]}"
    elif po_ref_clean:
        clean_code = re.sub(r"[^A-Za-z0-9]", "", po_ref_clean)
        base_cv = f"CV-{date_str}-{clean_code}"
    else:
        base_cv = f"CV-{date_str}-001"

    if not CashVoucher.objects.filter(voucher_number=base_cv).exists():
        return base_cv

    suffixes = [chr(i) for i in range(ord("A"), ord("Z") + 1)]
    for suffix in suffixes:
        candidate = f"{base_cv}-{suffix}"
        if not CashVoucher.objects.filter(voucher_number=candidate).exists():
            return candidate

    seq = 1
    while CashVoucher.objects.filter(voucher_number=f"{base_cv}-{seq}").exists():
        seq += 1
    return f"{base_cv}-{seq}"


def generate_chai_number(date_val=None):
    """Auto-generates sensible date-based CHAI record number (e.g. CHAI-20260925-001)."""
    from operations.models import CHAIRecord

    if date_val is None:
        date_val = timezone.localdate()
    elif isinstance(date_val, str):
        try:
            date_val = date.fromisoformat(date_val)
        except ValueError:
            date_val = timezone.localdate()

    date_str = date_val.strftime("%Y%m%d")
    pattern_prefix = f"CHAI-{date_str}-"

    existing = CHAIRecord.objects.filter(
        chai_number__startswith=pattern_prefix
    ).values_list("chai_number", flat=True)

    max_seq = 0
    for ref in existing:
        seq_part = ref[len(pattern_prefix):]
        match = re.match(r"^(\d+)", seq_part)
        if match:
            num = int(match.group(1))
            if num > max_seq:
                max_seq = num

    new_seq = max_seq + 1
    return f"{pattern_prefix}{new_seq:03d}"
