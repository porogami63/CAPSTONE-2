import datetime
import json
import re
from django import template
from django.utils.dateparse import parse_datetime

register = template.Library()

FIELD_NAME_MAP = {
    "loaded_volume_mt": "Loaded Volume (MT)",
    "received_volume_mt": "Received Volume (MT)",
    "shrinkage_mt": "Shrinkage Loss (MT)",
    "shrinkage_pct": "Shrinkage (%)",
    "volume_mt": "Volume (MT)",
    "unit_price": "Unit Price (₱)",
    "amount": "Total Amount (₱)",
    "total_price": "Total Price (₱)",
    "principal": "Loan Principal (₱)",
    "interest_rate_annual": "Annual Interest Rate (%)",
    "accrued_interest": "Accrued Interest (₱)",
    "tracking_fees": "Logistics Tracking Fees (₱)",
    "trucking_fee": "Trucking Freight Fee (₱)",
    "barging_fee": "Barging Freight Fee (₱)",
    "sugar_mill": "Sugar Mill Supplier",
    "sugar_mill_id": "Sugar Mill ID",
    "client": "Buyer Client",
    "client_id": "Buyer Client ID",
    "cluster": "Transaction Contract",
    "cluster_id": "Transaction Contract ID",
    "reference_code": "Reference Code",
    "invoice_number": "Invoice Number",
    "voucher_number": "Voucher Number",
    "cheque_number": "Cheque Number",
    "bank_name": "Bank Name",
    "status": "Status",
    "created_at": "Date Created",
    "updated_at": "Date Updated",
    "issued_at": "Date Issued",
    "due_date": "Due Date",
    "is_active": "Account Active Status",
    "role": "User Role",
    "email": "Email Address",
    "first_name": "First Name",
    "last_name": "Last Name",
    "username": "Username",
    "notes": "Audit Notes",
    "remarks": "Remarks",
    "mro_file": "Scanned MRO Soft Copy",
    "driver_name": "Driver Name",
    "plate_number": "Vehicle Plate Number",
    "vessel_name": "Barge Vessel Name",
}


def _format_value(key, val):
    if val is None or val == "":
        return "None"
    if isinstance(val, bool):
        return "Yes" if val else "No"
    
    # Try parsing date string
    if isinstance(val, str) and len(val) >= 10:
        dt = parse_datetime(val)
        if dt:
            return dt.strftime("%b %d, %Y · %I:%M %p")

    # Numeric formatting
    if isinstance(val, (int, float)):
        k_lower = key.lower()
        if any(term in k_lower for term in ["price", "amount", "principal", "fee", "cost", "revenue", "interest"]) and not k_lower.endswith("_id"):
            return f"₱{val:,.2f}"
        if any(term in k_lower for term in ["volume", "shrinkage_mt"]) and not k_lower.endswith("_id"):
            return f"{val:,.3f} MT"
        if any(term in k_lower for term in ["pct", "percent", "rate"]):
            return f"{val:.2f}%"
        return f"{val:,}"

    # Default string / fallback
    return str(val)


@register.filter
def humanize_field_name(key):
    if not key:
        return ""
    if key in FIELD_NAME_MAP:
        return FIELD_NAME_MAP[key]
    # Fallback formatting: replace underscores and capitalize
    return key.replace("_", " ").title()


@register.filter
def parse_audit_diff(entry):
    """
    Parses SystemAuditTrail entry old_values and new_values into a list of field diff dictionaries.
    Each item contains:
    - field_key
    - field_label
    - old_val_formatted
    - new_val_formatted
    - is_changed
    """
    old_dict = entry.old_values or {}
    new_dict = entry.new_values or {}

    if isinstance(old_dict, str):
        try:
            old_dict = json.loads(old_dict)
        except Exception:
            old_dict = {}
    if isinstance(new_dict, str):
        try:
            new_dict = json.loads(new_dict)
        except Exception:
            new_dict = {}

    all_keys = list(dict.fromkeys(list(old_dict.keys()) + list(new_dict.keys())))
    diffs = []

    for key in all_keys:
        has_old = key in old_dict
        has_new = key in new_dict

        raw_old = old_dict.get(key)
        raw_new = new_dict.get(key)

        is_changed = (has_old and has_new and raw_old != raw_new) or (has_old != has_new)

        label = humanize_field_name(key)
        old_formatted = _format_value(key, raw_old) if has_old else "—"
        new_formatted = _format_value(key, raw_new) if has_new else "—"

        diffs.append({
            "key": key,
            "label": label,
            "old_val": old_formatted,
            "new_val": new_formatted,
            "raw_old": raw_old,
            "raw_new": raw_new,
            "is_changed": is_changed,
            "has_old": has_old,
            "has_new": has_new,
        })

    return diffs


@register.filter
def to_json_pretty(val):
    try:
        return json.dumps(val, indent=2, default=str)
    except Exception:
        return str(val)
