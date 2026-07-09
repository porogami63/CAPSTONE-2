from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from finance.models import FinancialReconciliation, Invoice
from masters.models import Client, LogisticsPartner, SugarMill
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster

CLIENT_NAMES = {
    "ADI": "Absolute Distillers Inc.",
    "PROGREEN": "Progreen",
    "GSMI": "Ginebra San Miguel Inc.",
    "BDI": "BDI",
    "EMPERADOR": "Emperador Distillers Inc.",
    "HTC": "Heindrich Trading Corp.",
}

SOURCE_MILL_NAMES = {
    "BUSCO": "BUSCO Sugar Milling Co.",
    "LOPEZ": "Lopez Sugar Mill",
    "CASA": "Casa Molasses Source",
    "CAB": "CAB Source",
    "AABC": "AABC Mill",
    "URC-PASSI": "URC Passi",
    "URC - PASSI": "URC Passi",
    "URC-PASSI": "URC Passi",
    "URC - SONEDCO": "URC SONEDCO",
    "URC-SONEDCO": "URC SONEDCO",
    "URC-SONEDCO ": "URC SONEDCO",
    "HTC TANK": "HTC Tank Storage",
    "HTC": "HTC Internal Tank",
    "SBTI PHILIPA": "SBTI Philippa",
    "ZKYARC": "ZKYARC Source",
    "CASA X CAB": "Casa x CAB Blend",
}


def _clean_str(val):
    if val is None:
        return ""
    return str(val).strip()


def _to_decimal(val):
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _parse_si(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    text = str(val).strip()
    if not text or text.upper() in {"ON GOING", "SI"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _client_display(code):
    code = _clean_str(code)
    if not code:
        return "Unassigned Customer"
    return CLIENT_NAMES.get(code.upper(), code)


def _mill_display(source):
    source = _clean_str(source)
    if not source:
        return "Unknown Mill"
    key = source.upper()
    for k, v in SOURCE_MILL_NAMES.items():
        if k.upper() == key:
            return v
    return source


def clear_operational_data():
    from audit.models import SystemAuditTrail
    from finance.models import CashVoucher, CapitalLoan, PaymentExpenseMatch

    PaymentExpenseMatch.objects.all().delete()
    FinancialReconciliation.objects.all().delete()
    Invoice.objects.all().delete()
    CashVoucher.objects.all().delete()
    CapitalLoan.objects.all().delete()
    LogisticsLedger.objects.all().delete()
    PurchaseOrder.objects.all().delete()
    TransactionCluster.objects.all().delete()
    Client.objects.all().delete()
    SugarMill.objects.all().delete()
    LogisticsPartner.objects.all().delete()
    SystemAuditTrail.objects.all().delete()


def load_workbook_rows(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    return list(ws.iter_rows(values_only=True))


def import_htc_summary(path):
    rows = load_workbook_rows(path)
    ongoing_section = False
    ongoing_counter = 0
    imported = 0
    skipped = 0
    notes_buffer = []

    with transaction.atomic():
        for row in rows:
            if not row:
                continue

            first_cell = _clean_str(row[0]).upper()
            if first_cell == "ON GOING":
                ongoing_section = True
                continue
            if first_cell == "SI" or first_cell == "HEINDRICH TRADING CORPORATION 2026":
                continue

            si = _parse_si(row[0])
            barge = _clean_str(row[2])
            source = _clean_str(row[3])
            customer = _clean_str(row[7])

            # Continuation row (split source line under same invoice block)
            if si is None and not barge and not source:
                skipped += 1
                continue

            if si is None:
                if not barge and not source:
                    skipped += 1
                    continue
                ongoing_counter += 1
                ref = f"ONGOING-{ongoing_counter:03d}"
                status = TransactionCluster.Status.DRAFT
            else:
                ref = f"SI-{si}"
                status = (
                    TransactionCluster.Status.DRAFT
                    if ongoing_section
                    else TransactionCluster.Status.ACTIVE
                )

            if TransactionCluster.objects.filter(reference_code=ref).exists():
                skipped += 1
                continue

            purchase_price = _to_decimal(row[4]) or Decimal("0")
            trucking = _to_decimal(row[5]) or Decimal("0")
            barging = _to_decimal(row[6]) or Decimal("0")
            delivered = _to_decimal(row[8])
            received = _to_decimal(row[9])
            selling = _to_decimal(row[11]) or purchase_price
            amount = _to_decimal(row[12]) or Decimal("0")
            inv_date = row[1]

            if isinstance(inv_date, datetime):
                issued_at = inv_date.date()
                loaded_at = timezone.make_aware(inv_date) if timezone.is_naive(inv_date) else inv_date
            else:
                issued_at = timezone.now().date()
                loaded_at = timezone.now()

            client, _ = Client.objects.get_or_create(name=_client_display(customer))
            mill, _ = SugarMill.objects.get_or_create(name=_mill_display(source))
            partner_name = barge or "TRUCKING"
            partner, _ = LogisticsPartner.objects.get_or_create(
                name=partner_name,
                defaults={"default_freight_rate": barging or trucking},
            )

            extra_notes = "; ".join(notes_buffer)
            notes_buffer = []

            cluster = TransactionCluster.objects.create(
                reference_code=ref,
                client=client,
                sugar_mill=mill,
                contract_notes=extra_notes,
                status=status,
            )

            volume = delivered or received or Decimal("0")
            PurchaseOrder.objects.create(
                cluster=cluster,
                volume_mt=volume,
                unit_price=purchase_price,
                terms=f"Selling ₱{selling}" if selling else "",
                approved_at=loaded_at,
            )

            LogisticsLedger.objects.create(
                cluster=cluster,
                partner=partner,
                vessel_id=barge[:100] if barge else "",
                loaded_volume_mt=delivered or received or Decimal("0"),
                received_volume_mt=received,
                loaded_at=loaded_at,
                received_at=loaded_at if received else None,
                tracking_fees=trucking,
                barge_fees=barging,
            )

            if si is not None:
                Invoice.objects.create(
                    cluster=cluster,
                    invoice_number=f"SI-{si}",
                    amount=amount,
                    issued_at=issued_at,
                    status=Invoice.Status.ISSUED if amount > 0 else Invoice.Status.DRAFT,
                )

            FinancialReconciliation.objects.create(cluster=cluster)
            imported += 1

    return imported, skipped
