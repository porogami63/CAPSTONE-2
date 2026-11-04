from datetime import date, datetime, time, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from audit.models import Notification
from finance.models import (
    CapitalLoan,
    CashVoucher,
    FinancialReconciliation,
    Invoice,
    PaymentExpenseMatch,
)
from masters.models import (
    Client,
    LogisticsPartner,
    Planter,
    SugarMill,
    ensure_default_trucking_partners,
)
from operations.models import (
    CHAIRecord,
    DeliveryLedger,
    LogisticsLedger,
    MolassesReleaseOrder,
    PurchaseOrder,
    TransactionCluster,
)


class Command(BaseCommand):
    help = "Clear existing PO data and seed realistic dummy POs for Capstone Defense (Dashboard, Analytics & Suggestive Data)."

    def handle(self, *args, **options):
        self.stdout.write("Preparing database for Capstone Defense...")

        with transaction.atomic():
            # 1. Remove all PO & operational transaction records cleanly
            PaymentExpenseMatch.objects.all().delete()
            FinancialReconciliation.objects.all().delete()
            Invoice.objects.all().delete()
            CashVoucher.objects.all().delete()
            CapitalLoan.objects.all().delete()
            DeliveryLedger.objects.all().delete()
            LogisticsLedger.objects.all().delete()
            CHAIRecord.objects.filter(cluster__isnull=False).delete()
            MolassesReleaseOrder.objects.filter(cluster__isnull=False).update(cluster=None)
            PurchaseOrder.objects.all().delete()
            TransactionCluster.objects.all().delete()
            Notification.objects.all().delete()

            # Remove test/junk master records
            Client.objects.filter(name__in=["testt", "test", "Unassigned Customer"]).delete()
            SugarMill.objects.filter(name__in=["test", "Unknown Mill"]).delete()

            self.stdout.write("  Cleared all old PO, Delivery, Loan, Voucher, Invoice & Reconciliation data.")

            # 2. Ensure core users exist
            admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

            # 3. Ensure core Clients exist with proper Origin Indicators
            clients_spec = {
                "ADI": ("Absolute Distillers Inc.", "Luzon Hub / Lian Batangas Zone", "000-555-666", "Lian, Batangas", "Engr. Marco Villanueva", "+63 917 550 1120"),
                "GSMI": ("Ginebra San Miguel Inc.", "GSMI Sta. Rosa / Cabuyao Zone", "000-111-222", "Cabuyao, Laguna", "Ms. Clarisse Reyes", "+63 917 882 3401"),
                "PROGREEN": ("Progreen", "Progreen Balayan / Nasugbu Zone", "000-444-888", "Balayan, Batangas", "Mr. Raymond Lim", "+63 917 309 7742"),
                "EMPERADOR": ("Emperador Distillers Inc.", "Emperador Biñan / Laguna Zone", "000-333-444", "Biñan, Laguna", "Mr. Victor Tan", "+63 918 412 9005"),
                "BDI": ("BDI", "BDI Batangas Terminal Zone", "000-777-999", "Bauan, Batangas", "Ms. Patricia Cruz", "+63 917 624 8810"),
            }
            clients = {}
            for key, (name, origin, tin, addr, person, phone) in clients_spec.items():
                obj, _ = Client.objects.get_or_create(name=name)
                obj.tin = tin
                obj.address = addr
                obj.contact_person = person
                obj.contact_phone = phone
                obj.is_active = True
                obj.save()
                clients[key] = obj

            # 4. Ensure core Sugar Mills exist
            mills_spec = {
                "BUSCO": ("BUSCO Sugar Milling Co.", "Quezon, Bukidnon", "Engr. Roberto Santos", "+63 917 701 2211"),
                "BISCOM": ("Binalbagan-Isabela Sugar Co. (BISCOM)", "Binalbagan, Negros Occidental", "Mr. Eduardo Gomez", "+63 917 802 3312"),
                "LOPEZ": ("Lopez Sugar Mill", "Fabrica, Sagay, Negros Occidental", "Engr. Antonio Lopez", "+63 917 903 4413"),
                "AABC": ("AABC Mill", "Bacolod, Negros Occidental", "Ms. Elena Navarro", "+63 918 504 5514"),
                "PASSI": ("URC Passi", "Passi City, Iloilo", "Mr. Dennis Morales", "+63 917 605 6615"),
                "SONEDCO": ("URC SONEDCO", "Kabankalan, Negros Occidental", "Engr. Francis Chua", "+63 917 406 7716"),
                "HAWAIIAN": ("Hawaiian-Philippine Company", "Silay City, Negros Occidental", "Mr.Arthur Mendoza", "+63 917 307 8817"),
                "CASA": ("Casa Molasses Source", "Iloilo Port Terminal", "Ms. Grace Sy", "+63 917 208 9918"),
            }
            mills = {}
            for key, (name, loc, person, phone) in mills_spec.items():
                obj, _ = SugarMill.objects.get_or_create(name=name)
                obj.location = loc
                obj.contact_person = person
                obj.contact_phone = phone
                obj.is_active = True
                obj.save()
                mills[key] = obj

            # 5. Ensure Trucking & Barging Logistics Partners exist
            ensure_default_trucking_partners()
            trk_fast = LogisticsPartner.objects.filter(category=LogisticsPartner.Category.TRUCKING, name__icontains="Fast").first() or LogisticsPartner.objects.filter(category=LogisticsPartner.Category.TRUCKING).first()
            trk_royal = LogisticsPartner.objects.filter(category=LogisticsPartner.Category.TRUCKING, name__icontains="Royal").first() or trk_fast
            trk_f2 = LogisticsPartner.objects.filter(category=LogisticsPartner.Category.TRUCKING, name__icontains="F2").first() or trk_fast
            trk_2go = LogisticsPartner.objects.filter(category=LogisticsPartner.Category.TRUCKING, name__icontains="2GO").first() or trk_fast

            brg_1st, _ = LogisticsPartner.objects.get_or_create(
                name="1ST KIRSTINE MARIE",
                defaults={
                    "category": LogisticsPartner.Category.BARGING,
                    "region": "Visayas · Batangas Marine Route",
                    "default_freight_rate": Decimal("1150.00"),
                    "fleet_count": 6,
                    "is_active": True,
                },
            )
            brg_manila, _ = LogisticsPartner.objects.get_or_create(
                name="Manila Barge Logistics",
                defaults={
                    "category": LogisticsPartner.Category.BARGING,
                    "region": "Iloilo · Negros · Batangas Route",
                    "default_freight_rate": Decimal("1200.00"),
                    "fleet_count": 8,
                    "is_active": True,
                },
            )
            brg_solid, _ = LogisticsPartner.objects.get_or_create(
                name="Solid Shipping Lines / FastCargo",
                defaults={
                    "category": LogisticsPartner.Category.BARGING,
                    "region": "Mindanao · Visayas · Luzon Marine Corridor",
                    "default_freight_rate": Decimal("1350.00"),
                    "fleet_count": 10,
                    "is_active": True,
                },
            )

            today = timezone.localdate()

            # Helper to convert date to aware datetime
            def dt_on(d: date, hr=10, mn=0):
                return timezone.make_aware(datetime.combine(d, time(hr, mn)))

            # 6. Define 12 Dummy POs spanning May 2026 to Nov 2026
            # Covers all Client x Mill pairs for Smart Suggestive Pricing + Weekly/Monthly/Yearly Dashboard Charts
            po_specs = [
                # --- HISTORICAL COMPLETED / DELIVERED POs (May - Oct 2026) ---
                {
                    "ref": "PO-20260518-001",
                    "date": date(2026, 5, 18),
                    "client": clients["ADI"],
                    "mill": mills["BUSCO"],
                    "volume": Decimal("2500.000"),
                    "buy": Decimal("12200.00"),
                    "sell": Decimal("16200.00"),
                    "brix": Decimal("85.50"),
                    "chai": "CHAI 1.8",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal,
                    "trk_rate": Decimal("450.00"),
                    "brg_partner": brg_solid,
                    "brg_rate": Decimal("1250.00"),
                    "batches": [(Decimal("2500.000"), True, "ADI Lian Main Site", "DR-2605-01", "WB-2605-01")],
                    "invoice_status": Invoice.Status.PAID,
                    "loan_bank": "BDO Unibank",
                    "loan_status": CapitalLoan.Status.CLOSED,
                    "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260622-001",
                    "date": date(2026, 6, 22),
                    "client": clients["GSMI"],
                    "mill": mills["BISCOM"],
                    "volume": Decimal("3000.000"),
                    "buy": Decimal("12400.00"),
                    "sell": Decimal("16500.00"),
                    "brix": Decimal("85.20"),
                    "chai": "CHAI 2.0",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast,
                    "trk_rate": Decimal("420.00"),
                    "brg_partner": brg_1st,
                    "brg_rate": Decimal("1150.00"),
                    "batches": [(Decimal("3000.000"), True, "Ginebra San Miguel Inc. Main Site", "DR-2606-01", "WB-2606-01")],
                    "invoice_status": Invoice.Status.PAID,
                    "loan_bank": "Metropolitan Bank & Trust (Metrobank)",
                    "loan_status": CapitalLoan.Status.CLOSED,
                    "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260715-001",
                    "date": date(2026, 7, 15),
                    "client": clients["PROGREEN"],
                    "mill": mills["LOPEZ"],
                    "volume": Decimal("2000.000"),
                    "buy": Decimal("12100.00"),
                    "sell": Decimal("16000.00"),
                    "brix": Decimal("84.80"),
                    "chai": "CHAI 2.1",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2,
                    "trk_rate": Decimal("440.00"),
                    "brg_partner": brg_manila,
                    "brg_rate": Decimal("1180.00"),
                    "batches": [(Decimal("2000.000"), True, "Progreen Main Site", "DR-2607-01", "WB-2607-01")],
                    "invoice_status": Invoice.Status.PAID,
                    "loan_bank": "Bank of the Philippine Islands (BPI)",
                    "loan_status": CapitalLoan.Status.CLOSED,
                    "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260819-001",
                    "date": date(2026, 8, 19),
                    "client": clients["EMPERADOR"],
                    "mill": mills["AABC"],
                    "volume": Decimal("3500.000"),
                    "buy": Decimal("12500.00"),
                    "sell": Decimal("16800.00"),
                    "brix": Decimal("85.60"),
                    "chai": "CHAI 1.9",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go,
                    "trk_rate": Decimal("460.00"),
                    "brg_partner": brg_1st,
                    "brg_rate": Decimal("1200.00"),
                    "batches": [(Decimal("3500.000"), True, "Emperador Distillers Inc. Main Site", "DR-2608-01", "WB-2608-01")],
                    "invoice_status": Invoice.Status.PAID,
                    "loan_bank": "Security Bank Corporation",
                    "loan_status": CapitalLoan.Status.CLOSED,
                    "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260914-001",
                    "date": date(2026, 9, 14),
                    "client": clients["BDI"],
                    "mill": mills["PASSI"],
                    "volume": Decimal("2800.000"),
                    "buy": Decimal("12300.00"),
                    "sell": Decimal("16400.00"),
                    "brix": Decimal("85.00"),
                    "chai": "CHAI 2.0",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.DELIVERED,
                    "trk_partner": trk_royal,
                    "trk_rate": Decimal("430.00"),
                    "brg_partner": brg_manila,
                    "brg_rate": Decimal("1150.00"),
                    "batches": [(Decimal("2800.000"), True, "BDI Main Site", "DR-2609-01", "WB-2609-01")],
                    "invoice_status": Invoice.Status.PAID,
                    "loan_bank": "BDO Unibank",
                    "loan_status": CapitalLoan.Status.CLOSED,
                    "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20261012-001",
                    "date": date(2026, 10, 12),
                    "client": clients["ADI"],
                    "mill": mills["BISCOM"],
                    "volume": Decimal("4000.000"),
                    "buy": Decimal("12500.00"),
                    "sell": Decimal("16900.00"),
                    "brix": Decimal("85.40"),
                    "chai": "CHAI 1.8",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.DELIVERED,
                    "trk_partner": trk_fast,
                    "trk_rate": Decimal("450.00"),
                    "brg_partner": brg_1st,
                    "brg_rate": Decimal("1200.00"),
                    "batches": [
                        (Decimal("2000.000"), True, "Absolute Distillers Inc. Main Site", "DR-2610-01A", "WB-2610-01A"),
                        (Decimal("2000.000"), True, "Absolute Distillers Inc. Main Site", "DR-2610-01B", "WB-2610-01B"),
                    ],
                    "invoice_status": Invoice.Status.PAID,
                    "loan_bank": "Metrobank",
                    "loan_status": CapitalLoan.Status.ACTIVE,
                    "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20261026-002",
                    "date": date(2026, 10, 26),
                    "client": clients["GSMI"],
                    "mill": mills["HAWAIIAN"],
                    "volume": Decimal("3200.000"),
                    "buy": Decimal("12450.00"),
                    "sell": Decimal("16700.00"),
                    "brix": Decimal("85.30"),
                    "chai": "CHAI 1.9",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.DELIVERED,
                    "trk_partner": trk_f2,
                    "trk_rate": Decimal("440.00"),
                    "brg_partner": brg_solid,
                    "brg_rate": Decimal("1220.00"),
                    "batches": [
                        (Decimal("1600.000"), True, "Ginebra San Miguel Inc. Main Site", "DR-2610-02A", "WB-2610-02A"),
                        (Decimal("1600.000"), True, "Ginebra San Miguel Inc. Main Site", "DR-2610-02B", "WB-2610-02B"),
                    ],
                    "invoice_status": Invoice.Status.ISSUED,
                    "loan_bank": "BPI Corporate Facility",
                    "loan_status": CapitalLoan.Status.ACTIVE,
                    "reconcile_mode": "dp_and_b1",
                },
                # --- ACTIVE / CURRENT MONTH SHOWCASE POs FOR LIVE DEFENSE DEMO (Nov 2026) ---
                {
                    "ref": "PO-20261101-001",
                    "date": date(2026, 11, 1),
                    "client": clients["PROGREEN"],
                    "mill": mills["SONEDCO"],
                    "volume": Decimal("5000.000"),
                    "buy": Decimal("12500.00"),
                    "sell": Decimal("16800.00"),
                    "brix": Decimal("85.50"),
                    "chai": "CHAI 1.8",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.ACTIVE,
                    "trk_partner": trk_royal,
                    "trk_rate": Decimal("450.00"),
                    "brg_partner": brg_1st,
                    "brg_rate": Decimal("1250.00"),
                    # Partially delivered: 3,000 MT delivered in 2 batches, 2,000 MT remaining for live demo!
                    # 50% DP reconciled, ready to demonstrate dynamic 50% post-delivery balance match!
                    "batches": [
                        (Decimal("1500.000"), True, "Progreen Main Site", "DR-2611-01A", "WB-2611-01A"),
                        (Decimal("1500.000"), True, "Progreen Main Site", "DR-2611-01B", "WB-2611-01B"),
                    ],
                    "invoice_status": None,  # Unbilled so user can demo suggestive invoice pricing!
                    "loan_bank": "BDO Unibank",
                    "loan_status": CapitalLoan.Status.ACTIVE,
                    "reconcile_mode": "dp_only",
                },
                {
                    "ref": "PO-20261103-002",
                    "date": date(2026, 11, 3),
                    "client": clients["BDI"],
                    "mill": mills["BUSCO"],
                    "volume": Decimal("4000.000"),
                    "buy": Decimal("12350.00"),
                    "sell": Decimal("16500.00"),
                    "brix": Decimal("85.20"),
                    "chai": "CHAI 2.0",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.ACTIVE,
                    "trk_partner": trk_fast,
                    "trk_rate": Decimal("450.00"),
                    "brg_partner": brg_solid,
                    "brg_rate": Decimal("1300.00"),
                    # Partially delivered: 2,000 MT delivered, 2,000 MT remaining!
                    "batches": [
                        (Decimal("2000.000"), True, "BDI Main Site", "DR-2611-02A", "WB-2611-02A"),
                    ],
                    "invoice_status": None,
                    "loan_bank": "Security Bank",
                    "loan_status": CapitalLoan.Status.ACTIVE,
                    "reconcile_mode": "dp_only",
                },
                {
                    "ref": "PO-20261104-003",
                    "date": date(2026, 11, 4),
                    "client": clients["EMPERADOR"],
                    "mill": mills["CASA"],
                    "volume": Decimal("3000.000"),
                    "buy": Decimal("12400.00"),
                    "sell": Decimal("16600.00"),
                    "brix": Decimal("85.00"),
                    "chai": "CHAI 2.1",
                    "terms": "Net 30 days",
                    "status": TransactionCluster.Status.APPROVED,
                    "trk_partner": trk_2go,
                    "trk_rate": Decimal("440.00"),
                    "brg_partner": brg_manila,
                    "brg_rate": Decimal("1180.00"),
                    # Fresh approved PO with 0 deliveries so user can demo logging initial delivery & adding initial loan!
                    "batches": [],
                    "invoice_status": None,
                    "loan_bank": None,
                    "loan_status": None,
                    "reconcile_mode": "none",
                },
            ]

            for spec in po_specs:
                c_date = spec["date"]
                c_dt = dt_on(c_date, 9, 30)

                cluster = TransactionCluster.objects.create(
                    reference_code=spec["ref"],
                    client=spec["client"],
                    sugar_mill=spec["mill"],
                    status=spec["status"],
                    contract_notes=f"Contracted molasses supply for {spec['client'].name} sourced from {spec['mill'].name}.",
                )
                TransactionCluster.objects.filter(pk=cluster.pk).update(created_at=c_dt, updated_at=c_dt)

                po = PurchaseOrder.objects.create(
                    cluster=cluster,
                    po_reference_number=spec["ref"],
                    customer=spec["client"],
                    total_contracted_mt=spec["volume"],
                    volume_mt=spec["volume"],
                    unit_price=spec["buy"],
                    selling_price=spec["sell"],
                    terms=spec["terms"],
                    brix_level=spec["brix"],
                    chai_specs=spec["chai"],
                    approved_at=c_dt,
                    approved_by=admin_user,
                )

                # Create CHAI record
                chai_num_val = Decimal(spec["chai"].replace("CHAI", "").strip())
                CHAIRecord.objects.create(
                    cluster=cluster,
                    chai_number=f"CHAI-{spec['ref']}",
                    chai_value=chai_num_val,
                    title=f"Verified Quality Grade {spec['chai']}",
                    sugar_mill=spec["mill"],
                    brix_level=spec["brix"],
                    purity_percent=Decimal("46.50"),
                    status="approved",
                )

                # Create base LogisticsLedger
                total_deliv_mt = sum(b[0] for b in spec["batches"])
                est_trk_total = spec["volume"] * spec["trk_rate"]
                est_brg_total = spec["volume"] * spec["brg_rate"]
                log_ledger = LogisticsLedger.objects.create(
                    cluster=cluster,
                    partner=spec["brg_partner"],
                    trucking_partner=spec["trk_partner"],
                    barge_partner=spec["brg_partner"],
                    vessel_id=spec["brg_partner"].name,
                    loaded_volume_mt=total_deliv_mt,
                    received_volume_mt=total_deliv_mt if total_deliv_mt > 0 else None,
                    loaded_at=dt_on(c_date + timedelta(days=1), 8, 0) if total_deliv_mt > 0 else None,
                    received_at=dt_on(c_date + timedelta(days=4), 15, 0) if total_deliv_mt > 0 else None,
                    tracking_fees=est_trk_total if not spec["batches"] else Decimal("0.00"),
                    barge_fees=est_brg_total if not spec["batches"] else Decimal("0.00"),
                )

                recon = FinancialReconciliation.objects.create(cluster=cluster)

                # Create Delivery Batches
                created_batches = []
                for b_idx, (b_mt, is_arrived, b_loc, b_dr, b_wb) in enumerate(spec["batches"], start=1):
                    b_date = min(c_date + timedelta(days=b_idx * 2), today)
                    disp_dt = dt_on(b_date, 8, 0)
                    arr_dt = dt_on(min(b_date + timedelta(days=2), today), 16, 30) if is_arrived else None
                    d_obj = DeliveryLedger.objects.create(
                        purchase_order=po,
                        supplier=spec["mill"],
                        delivered_mt=b_mt,
                        receiving_location=b_loc,
                        delivery_date=b_date,
                        dispatched_at=disp_dt,
                        received_at=arr_dt,
                        carrier=spec["brg_partner"],
                        trucking_partner=spec["trk_partner"],
                        trucking_rate_per_mt=spec["trk_rate"],
                        barge_partner=spec["brg_partner"],
                        vessel_or_barge_name=spec["brg_partner"].name,
                        barge_rate_per_mt=spec["brg_rate"],
                        vessel_or_truck=f"NBD-{2400 + b_idx}",
                        dr_number=b_dr,
                        waybill_number=b_wb,
                        notes=f"Batch {b_idx} shipment to {b_loc}",
                    )
                    created_batches.append(d_obj)

                # Preserve intended cluster status
                if cluster.status != spec["status"]:
                    cluster.status = spec["status"]
                    cluster.save(update_fields=["status"])

                # Calculate 100% Sourcing + 100% Logistics for Loan
                sourcing_100 = (spec["volume"] * spec["buy"]).quantize(Decimal("0.01"))
                trk_100 = (spec["volume"] * spec["trk_rate"]).quantize(Decimal("0.01"))
                brg_100 = (spec["volume"] * spec["brg_rate"]).quantize(Decimal("0.01"))
                logistics_100 = trk_100 + brg_100
                suggested_loan_100 = sourcing_100 + logistics_100

                loan_obj = None
                if spec["loan_bank"]:
                    loan_obj = CapitalLoan.objects.create(
                        cluster=cluster,
                        bank_name=spec["loan_bank"],
                        principal=suggested_loan_100,
                        interest_rate_annual=Decimal("10.5000"),
                        start_date=c_date,
                        due_date=c_date + timedelta(days=60),
                        status=spec["loan_status"],
                        created_by=admin_user,
                        verified_by=admin_user,
                        verification_notes="Approved 100% PO Financing (100% Sourcing + 100% Logistics).",
                    )

                # Sync delivery vouchers
                for d_obj in created_batches:
                    d_obj.sync_delivery_expense_vouchers()

                # Create PaymentExpenseMatches according to reconcile_mode
                rmode = spec["reconcile_mode"]
                if rmode in ("full", "dp_and_b1", "dp_only"):
                    # 1. Sourcing match
                    src_amt = sourcing_100 if rmode == "full" else (created_batches[0].delivered_mt * spec["buy"] if created_batches else Decimal("0"))
                    if src_amt > 0:
                        m_src = PaymentExpenseMatch.objects.create(
                            reconciliation=recon,
                            payment_reference=f"SRC-{spec['ref']}",
                            expense_type=PaymentExpenseMatch.ExpenseType.SOURCING,
                            amount=src_amt,
                            notes=f"Supplier sourcing payment to {spec['mill'].name}",
                        )
                        PaymentExpenseMatch.objects.filter(pk=m_src.pk).update(matched_at=dt_on(c_date + timedelta(days=1), 11, 0))
                        CashVoucher.objects.get_or_create(
                            voucher_number=f"CV-M{m_src.pk}",
                            defaults={
                                "cluster": cluster,
                                "loan": loan_obj,
                                "amount": src_amt,
                                "purpose": f"Supplier Purchase Cost ({spec['mill'].name})",
                                "issued_at": c_date + timedelta(days=1),
                                "status": CashVoucher.Status.ISSUED,
                            },
                        )

                    # 2. 50% Upfront Down Payment (Trucking & Barge)
                    trk_dp = (trk_100 * Decimal("0.50")).quantize(Decimal("0.01"))
                    brg_dp = (brg_100 * Decimal("0.50")).quantize(Decimal("0.01"))
                    m_tdp = PaymentExpenseMatch.objects.create(
                        reconciliation=recon,
                        payment_reference=f"DEP-TRK-{spec['ref']}",
                        expense_type=PaymentExpenseMatch.ExpenseType.TRUCKING,
                        amount=trk_dp,
                        notes="50% Upfront Trucking Down Payment",
                    )
                    PaymentExpenseMatch.objects.filter(pk=m_tdp.pk).update(matched_at=dt_on(c_date + timedelta(days=1), 14, 0))
                    m_bdp = PaymentExpenseMatch.objects.create(
                        reconciliation=recon,
                        payment_reference=f"DEP-BRG-{spec['ref']}",
                        expense_type=PaymentExpenseMatch.ExpenseType.BARGE,
                        amount=brg_dp,
                        notes="50% Upfront Barge Down Payment",
                    )
                    PaymentExpenseMatch.objects.filter(pk=m_bdp.pk).update(matched_at=dt_on(c_date + timedelta(days=1), 14, 30))

                    # 3. Post-delivery 50% balance
                    if rmode == "full":
                        for d_obj in created_batches:
                            sid = str(d_obj.delivery_id)[:8].upper()
                            b_trk_bal = (d_obj.trucking_cost * Decimal("0.50")).quantize(Decimal("0.01"))
                            b_brg_bal = (d_obj.barge_cost * Decimal("0.50")).quantize(Decimal("0.01"))
                            m_tb = PaymentExpenseMatch.objects.create(
                                reconciliation=recon,
                                payment_reference=f"CV-DEL-{sid}-TRK",
                                expense_type=PaymentExpenseMatch.ExpenseType.TRUCKING,
                                amount=b_trk_bal,
                                notes=f"50% Post-Delivery Trucking Balance for Batch #{sid}",
                            )
                            PaymentExpenseMatch.objects.filter(pk=m_tb.pk).update(matched_at=dt_on(d_obj.delivery_date + timedelta(days=2), 16, 0))
                            m_bb = PaymentExpenseMatch.objects.create(
                                reconciliation=recon,
                                payment_reference=f"CV-DEL-{sid}-BRG",
                                expense_type=PaymentExpenseMatch.ExpenseType.BARGE,
                                amount=b_brg_bal,
                                notes=f"50% Post-Delivery Barge Balance for Batch #{sid}",
                            )
                            PaymentExpenseMatch.objects.filter(pk=m_bb.pk).update(matched_at=dt_on(d_obj.delivery_date + timedelta(days=2), 16, 15))
                    elif rmode == "dp_and_b1" and created_batches:
                        d0 = created_batches[0]
                        sid = str(d0.delivery_id)[:8].upper()
                        b_trk_bal = (d0.trucking_cost * Decimal("0.50")).quantize(Decimal("0.01"))
                        b_brg_bal = (d0.barge_cost * Decimal("0.50")).quantize(Decimal("0.01"))
                        PaymentExpenseMatch.objects.create(
                            reconciliation=recon,
                            payment_reference=f"CV-DEL-{sid}-TRK",
                            expense_type=PaymentExpenseMatch.ExpenseType.TRUCKING,
                            amount=b_trk_bal,
                            notes=f"50% Post-Delivery Trucking Balance for Batch #{sid}",
                        )
                        PaymentExpenseMatch.objects.create(
                            reconciliation=recon,
                            payment_reference=f"CV-DEL-{sid}-BRG",
                            expense_type=PaymentExpenseMatch.ExpenseType.BARGE,
                            amount=b_brg_bal,
                            notes=f"50% Post-Delivery Barge Balance for Batch #{sid}",
                        )

                # Create Sales Invoice if specified
                if spec["invoice_status"]:
                    inv_amt = (total_deliv_mt * spec["sell"]).quantize(Decimal("0.01"))
                    inv_date = min(c_date + timedelta(days=5), today)
                    Invoice.objects.create(
                        cluster=cluster,
                        invoice_number=f"SI-{spec['ref'][3:]}",
                        amount=inv_amt,
                        issued_at=inv_date,
                        status=spec["invoice_status"],
                        notes=f"Sales billing for {total_deliv_mt:,.3f} MT delivered to {spec['client'].name}.",
                    )

                self.stdout.write(f"  Created {spec['ref']} ({spec['client'].name} <- {spec['mill'].name}, {spec['volume']:,.0f} MT, {spec['status']})")

            # 7. Link a few MRO permits to the active November POs if MROs exist
            unlinked_mros = list(MolassesReleaseOrder.objects.filter(cluster__isnull=True)[:4])
            nov_clusters = list(TransactionCluster.objects.filter(reference_code__startswith="PO-202611"))
            if unlinked_mros and nov_clusters:
                for idx, mro in enumerate(unlinked_mros):
                    target_c = nov_clusters[idx % len(nov_clusters)]
                    mro.cluster = target_c
                    mro.save(update_fields=["cluster"])

        self.stdout.write(self.style.SUCCESS("Defense dummy PO dataset seeded successfully!"))
