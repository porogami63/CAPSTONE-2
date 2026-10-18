"""
Seed script for PO20261011-003 demonstration:
Creates a transaction cluster PO20261011-003 with:
- 1 consolidated scanned MRO document in storage (MRO_Scan_PO20261011-003.pdf)
- Multiple MRO entries (MRO-2026-701, MRO-2026-702, MRO-2026-703) totaling 5,000 MT
- Multiple batches of deliveries (4 delivery batches totaling 4,000 MT) drawing against these MRO entries
- Verifies that all MRO entries and delivery batches share that 1 single document in storage.
"""

import os
import sys
from decimal import Decimal
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ["DEBUG"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.core.files.base import ContentFile
from django.utils import timezone
from masters.models import Client, Planter, SugarMill, LogisticsPartner
from operations.models import TransactionCluster, PurchaseOrder, MolassesReleaseOrder, DeliveryLedger
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io


def generate_consolidated_mro_pdf():
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Header
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "SUGAR REGULATORY ADMINISTRATION (SRA)")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 68, "Official Molasses Release Order (MRO) Consolidation Certificate")
    p.drawString(50, height - 82, "Transaction PO Reference: PO20261011-003")

    p.setLineWidth(1)
    p.line(50, height - 90, width - 50, height - 90)

    # Overview box
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, height - 110, "CONSOLIDATED BATCH RELEASE ALLOCATION")
    p.setFont("Helvetica", 9)
    p.drawString(50, height - 126, "Sugar Mill / Source: BUSCO Sugar Milling Co., Inc. (Bukidnon)")
    p.drawString(50, height - 140, "Trader / Buyer: HEINDRICH TRADING CORP. (HTC Core)")
    p.drawString(50, height - 154, "Client Destination: Emperador Distillers Inc. (Batangas Main Silo)")
    p.drawString(50, height - 168, "Total Release Allocation: 5,000.000 MT Cane Molasses")
    p.drawString(50, height - 182, "Crop Year: 2024 - 2025")

    # Table Header
    y = height - 215
    p.setFillColorRGB(0.9, 0.95, 1.0)
    p.rect(50, y - 5, width - 100, 20, fill=True, stroke=True)
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(55, y, "MRO Permit #")
    p.drawString(160, y, "Planter / Association")
    p.drawString(330, y, "Volume (MT)")
    p.drawString(420, y, "Brix Level")
    p.drawString(490, y, "Release Date")

    # Entries
    entries = [
        ("MRO-2026-701", "ABSFI Planters Association Inc.", "1,500.000 MT", "85.20°", "2026-10-11"),
        ("MRO-2026-702", "SGABI Planters Cooperative", "2,000.000 MT", "85.40°", "2026-10-11"),
        ("MRO-2026-703", "BEACO Planters Federation", "1,500.000 MT", "84.90°", "2026-10-11"),
    ]

    y -= 22
    p.setFont("Helvetica", 9)
    for num, planter, vol, brix, rdate in entries:
        p.drawString(55, y, num)
        p.drawString(160, y, planter)
        p.drawString(330, y, vol)
        p.drawString(420, y, brix)
        p.drawString(490, y, rdate)
        p.setStrokeColorRGB(0.8, 0.8, 0.8)
        p.line(50, y - 4, width - 50, y - 4)
        y -= 20

    # Summary notes
    y -= 20
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "DOCUMENT STORAGE NOTICE:")
    p.setFont("Helvetica", 8.5)
    y -= 14
    p.drawString(50, y, "This official scanned document contains all three (3) MRO release permits listed above.")
    y -= 12
    p.drawString(50, y, "It applies across all multiple fulfillment delivery batches under PO20261011-003.")
    y -= 12
    p.drawString(50, y, "HTC Core deduplicates this document in system storage so one single file serves all entries.")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.getvalue()


def seed_po20261011_003():
    print("--- Setting up PO20261011-003 with Consolidated MRO Logic ---")

    # 1. Master Records
    client, _ = Client.objects.get_or_create(
        name="Emperador Distillers Inc.",
        defaults={"code": "EMP", "tin": "123-456-789-000", "is_active": True}
    )
    mill, _ = SugarMill.objects.get_or_create(
        name="BUSCO Sugar Milling Co.",
        defaults={"location": "Bukidnon", "is_active": True}
    )
    carrier, _ = LogisticsPartner.objects.get_or_create(
        name="Solid Shipping Lines / FastCargo",
        defaults={"is_active": True}
    )

    p1, _ = Planter.objects.get_or_create(name="ABSFI Planters Association Inc.", defaults={"code": "ABSFI", "is_active": True})
    p2, _ = Planter.objects.get_or_create(name="SGABI Planters Cooperative", defaults={"code": "SGABI", "is_active": True})
    p3, _ = Planter.objects.get_or_create(name="BEACO Planters Federation", defaults={"code": "BEACO", "is_active": True})

    # 2. TransactionCluster PO20261011-003
    cluster, created = TransactionCluster.objects.get_or_create(
        reference_code="PO20261011-003",
        defaults={
            "client": client,
            "sugar_mill": mill,
            "status": TransactionCluster.Status.ACTIVE,
            "contract_notes": "Consolidated supply agreement for 5,000 MT molasses across 3 MRO releases and 4 deliveries.",
        }
    )

    # 3. Generate and save the 1 single consolidated scanned MRO document
    pdf_content = generate_consolidated_mro_pdf()
    file_name = "MRO_Scan_PO20261011-003.pdf"
    cluster.mro_file.save(file_name, ContentFile(pdf_content), save=True)
    print(f"  [SAVED] 1 Physical Scanned Document: {cluster.mro_file.name}")

    # 4. Purchase Order Header
    po, _ = PurchaseOrder.objects.update_or_create(
        cluster=cluster,
        defaults={
            "po_reference_number": "PO20261011-003",
            "volume_mt": Decimal("5000.000"),
            "total_contracted_mt": Decimal("5000.000"),
            "unit_price": Decimal("32000.00"),
            "selling_price": Decimal("38500.00"),
            "po_status": PurchaseOrder.POStatus.PARTIALLY_FULFILLED,
            "customer": client,
            "terms": "30 days net",
        }
    )
    print(f"  [SAVED] Purchase Order: 5,000 MT (Remaining: {po.remaining_mt:,.3f} MT)")

    # 5. Multiple MRO entries (All sharing the 1 document on cluster)
    mro_data = [
        ("MRO-2026-701", p1, Decimal("1500.000"), date(2026, 10, 11), Decimal("85.20")),
        ("MRO-2026-702", p2, Decimal("2000.000"), date(2026, 10, 11), Decimal("85.40")),
        ("MRO-2026-703", p3, Decimal("1500.000"), date(2026, 10, 11), Decimal("84.90")),
    ]

    created_mros = {}
    for mro_num, planter, tons, rdate, brix in mro_data:
        mro_obj, _ = MolassesReleaseOrder.objects.update_or_create(
            mro_number=mro_num,
            cluster=cluster,
            defaults={
                "planter": planter,
                "sugar_mill": mill,
                "sugar_mill_name": mill.name,
                "tons": tons,
                "release_date": rdate,
                "crop_year": "2024 - 2025",
                "brix_level": brix,
                "notes": f"Part of consolidated SRA permit certificate ({file_name})",
            }
        )
        created_mros[mro_num] = mro_obj
        # Verify it uses the shared document
        assert mro_obj.scanned_document.name == cluster.mro_file.name
        assert mro_obj.is_shared_document is True
        print(f"  [MRO ENTRY] #{mro_num} ({tons} MT) -> Sharing doc: {mro_obj.scanned_document.name}")

    # 6. Multiple Batches of Deliveries (Fulfilling this PO against the MRO entries)
    # Clear existing deliveries for this PO if any to ensure clean state
    po.deliveries.all().delete()

    deliveries_data = [
        (date(2026, 10, 12), Decimal("1000.000"), "DR-003-BATCH-01", "WB-7710", created_mros["MRO-2026-701"]),
        (date(2026, 10, 14), Decimal("1200.000"), "DR-003-BATCH-02", "WB-7712", created_mros["MRO-2026-702"]),
        (date(2026, 10, 16), Decimal("800.000"),  "DR-003-BATCH-03", "WB-7715", created_mros["MRO-2026-702"]),
        (date(2026, 10, 17), Decimal("1000.000"), "DR-003-BATCH-04", "WB-7719", created_mros["MRO-2026-703"]),
    ]

    for d_date, d_mt, dr_num, wb_num, linked_mro in deliveries_data:
        deliv = DeliveryLedger.objects.create(
            purchase_order=po,
            supplier=mill,
            mro_permit=linked_mro,
            delivered_mt=d_mt,
            receiving_location="Emperador Balayan Silo A",
            delivery_date=d_date,
            carrier=carrier,
            dr_number=dr_num,
            waybill_number=wb_num,
            vessel_or_truck="Plate NBD-8841 / Barge Fast-03",
            trucking_rate_per_mt=Decimal("450.00"),
            barge_rate_per_mt=Decimal("1100.00"),
        )
        # Verify delivery batch accesses the shared document
        assert deliv.scanned_mro_document.name == cluster.mro_file.name
        print(f"  [DELIVERY BATCH] {dr_num} ({d_mt} MT) linked to MRO #{linked_mro.mro_number} -> Scanned Doc: {deliv.scanned_mro_document.name}")

    po.refresh_from_db()
    print(f"\nPO20261011-003 summary:")
    print(f"  Total Contracted: {po.total_contracted_mt} MT")
    print(f"  Delivered to Date: {po.total_delivered_mt} MT across {po.deliveries.count()} batches")
    print(f"  Remaining: {po.remaining_mt} MT")
    print(f"  Status: {po.po_status}")
    print(f"  MRO Entries: {cluster.mro_releases.count()} entries sharing 1 file: {cluster.mro_file.name}")
    print("--- PO20261011-003 SEEDING COMPLETE ---")

if __name__ == "__main__":
    seed_po20261011_003()
