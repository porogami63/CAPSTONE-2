import statistics
from decimal import Decimal
from django.db.models import Avg, Max, Min


def compute_series_stats(values_list, default_threshold_mult=1.5):
    """
    Computes mean, median, mode, min, max, std_dev and upper high threshold
    for a list of numerical values (float or Decimal).
    """
    clean_vals = []
    for v in values_list:
        if v is not None:
            try:
                clean_vals.append(float(v))
            except (ValueError, TypeError):
                pass

    if not clean_vals:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "mode": 0.0,
            "min": 0.0,
            "max": 0.0,
            "std_dev": 0.0,
            "high_threshold": 0.0,
        }

    n = len(clean_vals)
    mean_val = round(statistics.mean(clean_vals), 2)
    median_val = round(statistics.median(clean_vals), 2)

    # Compute mode safely
    try:
        mode_val = round(statistics.mode(clean_vals), 2)
    except statistics.StatisticsError:
        # Fallback if multiple modes or all unique values
        modes = statistics.multimode(clean_vals)
        mode_val = round(modes[0], 2) if modes else median_val

    min_val = round(min(clean_vals), 2)
    max_val = round(max(clean_vals), 2)
    std_dev = round(statistics.stdev(clean_vals), 2) if n > 1 else 0.0

    # Upper high threshold calculation:
    # 2 stddev above mean or threshold multiplier above max(mean, median)
    std_threshold = mean_val + (2.0 * std_dev) if std_dev > 0 else mean_val * default_threshold_mult
    mult_threshold = max(mean_val, median_val) * default_threshold_mult
    high_threshold = round(max(std_threshold, mult_threshold), 2)

    return {
        "count": n,
        "mean": mean_val,
        "median": median_val,
        "mode": mode_val,
        "min": min_val,
        "max": max_val,
        "std_dev": std_dev,
        "high_threshold": high_threshold,
    }


def get_operational_stats():
    """
    Returns summarized mean, median, mode statistics across operational domain models.
    """
    from operations.models import PurchaseOrder, CHAIRecord, MolassesReleaseOrder, LogisticsLedger
    from finance.models import Invoice

    stats = {}

    # 1. Purchase Orders
    po_qs = list(PurchaseOrder.objects.all())
    stats["po_volume"] = {
        "label": "Purchase Order Volume (MT)",
        **compute_series_stats([po.volume_mt for po in po_qs], default_threshold_mult=1.5)
    }
    stats["po_unit_price"] = {
        "label": "Supplier Sourcing Price (₱/MT)",
        **compute_series_stats([po.unit_price for po in po_qs], default_threshold_mult=1.4)
    }
    stats["po_selling_price"] = {
        "label": "Customer Selling Price (₱/MT)",
        **compute_series_stats([po.selling_price for po in po_qs if po.selling_price], default_threshold_mult=1.4)
    }
    stats["po_brix"] = {
        "label": "Brix Level (%)",
        **compute_series_stats([po.brix_level for po in po_qs if po.brix_level], default_threshold_mult=1.15)
    }

    # 2. CHAI Quality Records
    chai_qs = list(CHAIRecord.objects.all())
    stats["chai_grade"] = {
        "label": "Numerical CHAI Rating",
        **compute_series_stats([c.chai_value for c in chai_qs], default_threshold_mult=1.3)
    }
    stats["chai_brix"] = {
        "label": "CHAI Brix Level (%)",
        **compute_series_stats([c.brix_level for c in chai_qs if c.brix_level], default_threshold_mult=1.15)
    }
    stats["chai_purity"] = {
        "label": "Apparent Purity (%)",
        **compute_series_stats([c.purity_percent for c in chai_qs if c.purity_percent], default_threshold_mult=1.2)
    }

    # 3. Molasses Release Orders
    mro_qs = list(MolassesReleaseOrder.objects.all())
    stats["mro_tons"] = {
        "label": "Release Volume (Tons/MT)",
        **compute_series_stats([m.tons for m in mro_qs], default_threshold_mult=1.5)
    }

    # 4. Logistics
    log_qs = list(LogisticsLedger.objects.all())
    stats["logistics_loaded"] = {
        "label": "Loaded Volume (MT)",
        **compute_series_stats([l.loaded_volume_mt for l in log_qs if l.loaded_volume_mt], default_threshold_mult=1.5)
    }

    # 5. Financial Invoices
    try:
        inv_qs = list(Invoice.objects.all())
        stats["invoice_amount"] = {
            "label": "Invoice Amount (₱)",
            **compute_series_stats([inv.amount for inv in inv_qs if inv.amount], default_threshold_mult=1.5)
        }
    except Exception:
        pass

    return stats


def check_input_outliers(field_values_dict):
    """
    Checks user inputs against operational historical mean/median/mode statistics.
    Returns a dict with flag status and list of outlier details.
    
    field_values_dict example:
    {
        "volume_mt": 5000.0,
        "unit_price": 18000.0,
        "selling_price": 22000.0,
        "brix_level": 92.5,
        "chai_value": 4.5,
        "tons": 4500.0
    }
    """
    operational_stats = get_operational_stats()
    field_mapping = {
        "volume_mt": "po_volume",
        "unit_price": "po_unit_price",
        "selling_price": "po_selling_price",
        "brix_level": "po_brix",
        "chai_value": "chai_grade",
        "chai_brix": "chai_brix",
        "tons": "mro_tons",
        "loaded_volume_mt": "logistics_loaded",
        "amount": "invoice_amount",
    }

    outliers = []

    for field_key, input_raw in field_values_dict.items():
        if input_raw is None or input_raw == "":
            continue
        try:
            val = float(input_raw)
        except (ValueError, TypeError):
            continue

        stat_key = field_mapping.get(field_key)
        if not stat_key or stat_key not in operational_stats:
            continue

        stat_info = operational_stats[stat_key]
        count = stat_info["count"]
        high_threshold = stat_info["high_threshold"]

        # Only evaluate if we have prior records and value exceeds high threshold
        if count >= 2 and high_threshold > 0 and val > high_threshold:
            outliers.append({
                "field_key": field_key,
                "label": stat_info["label"],
                "value": val,
                "mean": stat_info["mean"],
                "median": stat_info["median"],
                "mode": stat_info["mode"],
                "threshold": high_threshold,
                "diff_pct": round(((val - stat_info["mean"]) / stat_info["mean"]) * 100.0, 1) if stat_info["mean"] > 0 else 0,
            })

    return {
        "is_flagged": len(outliers) > 0,
        "outliers": outliers,
    }
