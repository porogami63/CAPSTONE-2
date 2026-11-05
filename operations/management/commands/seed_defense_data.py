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
    help = "Clear existing PO data and seed multi-year realistic data (2024-2026) for Capstone Defense."

    def handle(self, *args, **options):
        self.stdout.write("Preparing database for Capstone Defense (2024-2026 multi-year data)...")

        with transaction.atomic():
            # 1. Clean operational & transaction records
            PaymentExpenseMatch.objects.all().delete()
            FinancialReconciliation.objects.all().delete()
            Invoice.objects.all().delete()
            CashVoucher.objects.all().delete()
            CapitalLoan.objects.all().delete()
            DeliveryLedger.objects.all().delete()
            LogisticsLedger.objects.all().delete()
            CHAIRecord.objects.filter(cluster__isnull=False).delete()
            MolassesReleaseOrder.objects.all().delete()
            PurchaseOrder.objects.all().delete()
            TransactionCluster.objects.all().delete()
            Notification.objects.all().delete()

            # Clean junk master records
            Client.objects.filter(name__in=["testt", "test", "Unassigned Customer"]).delete()
            SugarMill.objects.filter(name__in=["test", "Unknown Mill"]).delete()

            self.stdout.write("  Cleared all previous POs, deliveries, invoices, vouchers, loans, and reconciliations.")

            # 2. Ensure core users exist
            admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

            # 3. Ensure core Clients exist
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
                "HAWAIIAN": ("Hawaiian-Philippine Company", "Silay City, Negros Occidental", "Mr. Arthur Mendoza", "+63 917 307 8817"),
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

            default_planter, _ = Planter.objects.get_or_create(
                name="Central Sugar Planters Assoc.",
                defaults={"is_active": True}
            )

            def dt_on(d: date, hr=10, mn=0):
                return timezone.make_aware(datetime.combine(d, time(hr, mn)))

            # Seed realistic Molasses Release Orders (MROs) for 2024-2026
            mro_specs = [
                ("MRO-BUSCO-24-01", mills["BUSCO"], Decimal("15000.00"), date(2024, 1, 10), "2023-2024"),
                ("MRO-BISCOM-24-01", mills["BISCOM"], Decimal("18000.00"), date(2024, 2, 5), "2023-2024"),
                ("MRO-LOPEZ-24-01", mills["LOPEZ"], Decimal("12000.00"), date(2024, 3, 1), "2023-2024"),
                ("MRO-BUSCO-25-01", mills["BUSCO"], Decimal("22000.00"), date(2025, 1, 15), "2024-2025"),
                ("MRO-BISCOM-25-01", mills["BISCOM"], Decimal("20000.00"), date(2025, 2, 10), "2024-2025"),
                ("MRO-HAWAIIAN-25-01", mills["HAWAIIAN"], Decimal("16000.00"), date(2025, 3, 5), "2024-2025"),
                ("MRO-CASA-25-01", mills["CASA"], Decimal("14000.00"), date(2025, 4, 1), "2024-2025"),
                ("MRO-BUSCO-26-01", mills["BUSCO"], Decimal("25000.00"), date(2026, 1, 12), "2025-2026"),
                ("MRO-BISCOM-26-01", mills["BISCOM"], Decimal("24000.00"), date(2026, 1, 20), "2025-2026"),
                ("MRO-HAWAIIAN-26-01", mills["HAWAIIAN"], Decimal("18500.00"), date(2026, 2, 10), "2025-2026"),
                ("MRO-CASA-26-01", mills["CASA"], Decimal("15000.00"), date(2026, 2, 25), "2025-2026"),
                ("MRO-LOPEZ-26-01", mills["LOPEZ"], Decimal("14000.00"), date(2026, 3, 15), "2025-2026"),
                ("MRO-SONEDCO-26-01", mills["SONEDCO"], Decimal("19000.00"), date(2026, 4, 5), "2025-2026"),
                ("MRO-PASSI-26-01", mills["PASSI"], Decimal("13500.00"), date(2026, 4, 20), "2025-2026"),
            ]
            created_mros = []
            for num, mill, tons, r_date, cy in mro_specs:
                mro_obj = MolassesReleaseOrder.objects.create(
                    mro_number=num,
                    sugar_mill=mill,
                    sugar_mill_name=mill.name,
                    planter=default_planter,
                    tons=tons,
                    release_date=r_date,
                    crop_year=cy,
                    trader="Heindrich Trading Corporation",
                    brix_level=Decimal("85.00"),
                    chai_specs="CHAI 1.8 - 2.0",
                    notes=f"Official Sugar Regulatory Administration MRO Release for {mill.name}.",
                )
                created_mros.append(mro_obj)

            # 6. Define 2024, 2025, and 2026 PO Specifications
            po_specs = [
                # ===================== 2024 HISTORICAL POs =====================
                {
                    "ref": "PO-20240115-001", "date": date(2024, 1, 15), "client": clients["ADI"], "mill": mills["BUSCO"],
                    "volume": Decimal("2500.000"), "buy": Decimal("11800.00"), "sell": Decimal("15200.00"),
                    "brix": Decimal("85.20"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("420.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1180.00"),
                    "batches": [(Decimal("2500.000"), True, "ADI Lian Main Site", "DR-2401-01", "WB-2401-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20240220-001", "date": date(2024, 2, 20), "client": clients["GSMI"], "mill": mills["BISCOM"],
                    "volume": Decimal("3000.000"), "buy": Decimal("11900.00"), "sell": Decimal("15400.00"),
                    "brix": Decimal("85.00"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("400.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1100.00"),
                    "batches": [(Decimal("3000.000"), True, "GSMI Cabuyao Site", "DR-2402-01", "WB-2402-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20240318-001", "date": date(2024, 3, 18), "client": clients["PROGREEN"], "mill": mills["LOPEZ"],
                    "volume": Decimal("2200.000"), "buy": Decimal("11750.00"), "sell": Decimal("15100.00"),
                    "brix": Decimal("84.80"), "chai": "CHAI 2.1", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("410.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1120.00"),
                    "batches": [(Decimal("2200.000"), True, "Progreen Balayan Site", "DR-2403-01", "WB-2403-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BPI", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20240422-001", "date": date(2024, 4, 22), "client": clients["EMPERADOR"], "mill": mills["AABC"],
                    "volume": Decimal("3200.000"), "buy": Decimal("12000.00"), "sell": Decimal("15600.00"),
                    "brix": Decimal("85.50"), "chai": "CHAI 1.9", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("430.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1150.00"),
                    "batches": [(Decimal("3200.000"), True, "Emperador Biñan Site", "DR-2404-01", "WB-2404-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20240515-001", "date": date(2024, 5, 15), "client": clients["BDI"], "mill": mills["PASSI"],
                    "volume": Decimal("2400.000"), "buy": Decimal("11850.00"), "sell": Decimal("15300.00"),
                    "brix": Decimal("85.10"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("420.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1160.00"),
                    "batches": [(Decimal("2400.000"), True, "BDI Terminal Site", "DR-2405-01", "WB-2405-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20240618-001", "date": date(2024, 6, 18), "client": clients["ADI"], "mill": mills["SONEDCO"],
                    "volume": Decimal("2800.000"), "buy": Decimal("12100.00"), "sell": Decimal("15700.00"),
                    "brix": Decimal("85.40"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("430.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1170.00"),
                    "batches": [(Decimal("2800.000"), True, "ADI Lian Main Site", "DR-2406-01", "WB-2406-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20240725-001", "date": date(2024, 7, 25), "client": clients["GSMI"], "mill": mills["HAWAIIAN"],
                    "volume": Decimal("3500.000"), "buy": Decimal("12050.00"), "sell": Decimal("15800.00"),
                    "brix": Decimal("85.30"), "chai": "CHAI 1.9", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("420.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1140.00"),
                    "batches": [(Decimal("3500.000"), True, "GSMI Cabuyao Site", "DR-2407-01", "WB-2407-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BPI", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20240820-001", "date": date(2024, 8, 20), "client": clients["PROGREEN"], "mill": mills["CASA"],
                    "volume": Decimal("2000.000"), "buy": Decimal("11900.00"), "sell": Decimal("15250.00"),
                    "brix": Decimal("84.90"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("410.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1130.00"),
                    "batches": [(Decimal("2000.000"), True, "Progreen Balayan Site", "DR-2408-01", "WB-2408-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20241014-001", "date": date(2024, 10, 14), "client": clients["EMPERADOR"], "mill": mills["BUSCO"],
                    "volume": Decimal("3600.000"), "buy": Decimal("12200.00"), "sell": Decimal("16000.00"),
                    "brix": Decimal("85.60"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("440.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1190.00"),
                    "batches": [(Decimal("3600.000"), True, "Emperador Biñan Site", "DR-2410-01", "WB-2410-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20241118-001", "date": date(2024, 11, 18), "client": clients["BDI"], "mill": mills["BISCOM"],
                    "volume": Decimal("2600.000"), "buy": Decimal("12150.00"), "sell": Decimal("15900.00"),
                    "brix": Decimal("85.20"), "chai": "CHAI 1.9", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("430.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1160.00"),
                    "batches": [(Decimal("2600.000"), True, "BDI Terminal Site", "DR-2411-01", "WB-2411-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },

                # ===================== 2025 HISTORICAL POs =====================
                {
                    "ref": "PO-20250120-001", "date": date(2025, 1, 20), "client": clients["ADI"], "mill": mills["BISCOM"],
                    "volume": Decimal("3000.000"), "buy": Decimal("12100.00"), "sell": Decimal("15800.00"),
                    "brix": Decimal("85.30"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("430.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1170.00"),
                    "batches": [(Decimal("3000.000"), True, "ADI Lian Main Site", "DR-2501-01", "WB-2501-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250218-001", "date": date(2025, 2, 18), "client": clients["GSMI"], "mill": mills["LOPEZ"],
                    "volume": Decimal("3500.000"), "buy": Decimal("12250.00"), "sell": Decimal("16000.00"),
                    "brix": Decimal("85.10"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("440.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1190.00"),
                    "batches": [(Decimal("3500.000"), True, "GSMI Cabuyao Site", "DR-2502-01", "WB-2502-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250324-001", "date": date(2025, 3, 24), "client": clients["PROGREEN"], "mill": mills["AABC"],
                    "volume": Decimal("2800.000"), "buy": Decimal("12150.00"), "sell": Decimal("15900.00"),
                    "brix": Decimal("84.90"), "chai": "CHAI 2.1", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("420.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1150.00"),
                    "batches": [(Decimal("2800.000"), True, "Progreen Balayan Site", "DR-2503-01", "WB-2503-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BPI", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250415-001", "date": date(2025, 4, 15), "client": clients["EMPERADOR"], "mill": mills["BUSCO"],
                    "volume": Decimal("4000.000"), "buy": Decimal("12300.00"), "sell": Decimal("16200.00"),
                    "brix": Decimal("85.50"), "chai": "CHAI 1.9", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("450.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1200.00"),
                    "batches": [(Decimal("4000.000"), True, "Emperador Biñan Site", "DR-2504-01", "WB-2504-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250520-001", "date": date(2025, 5, 20), "client": clients["BDI"], "mill": mills["SONEDCO"],
                    "volume": Decimal("3200.000"), "buy": Decimal("12200.00"), "sell": Decimal("16000.00"),
                    "brix": Decimal("85.20"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("430.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1180.00"),
                    "batches": [(Decimal("3200.000"), True, "BDI Terminal Site", "DR-2505-01", "WB-2505-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250625-001", "date": date(2025, 6, 25), "client": clients["ADI"], "mill": mills["HAWAIIAN"],
                    "volume": Decimal("3800.000"), "buy": Decimal("12400.00"), "sell": Decimal("16400.00"),
                    "brix": Decimal("85.40"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("440.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1210.00"),
                    "batches": [(Decimal("3800.000"), True, "ADI Lian Main Site", "DR-2506-01", "WB-2506-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250721-001", "date": date(2025, 7, 21), "client": clients["GSMI"], "mill": mills["CASA"],
                    "volume": Decimal("3400.000"), "buy": Decimal("12350.00"), "sell": Decimal("16250.00"),
                    "brix": Decimal("85.00"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("430.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1180.00"),
                    "batches": [(Decimal("3400.000"), True, "GSMI Cabuyao Site", "DR-2507-01", "WB-2507-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BPI", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250818-001", "date": date(2025, 8, 18), "client": clients["PROGREEN"], "mill": mills["PASSI"],
                    "volume": Decimal("2600.000"), "buy": Decimal("12200.00"), "sell": Decimal("16100.00"),
                    "brix": Decimal("84.80"), "chai": "CHAI 2.1", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("420.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1160.00"),
                    "batches": [(Decimal("2600.000"), True, "Progreen Balayan Site", "DR-2508-01", "WB-2508-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20250915-001", "date": date(2025, 9, 15), "client": clients["EMPERADOR"], "mill": mills["BISCOM"],
                    "volume": Decimal("4200.000"), "buy": Decimal("12450.00"), "sell": Decimal("16500.00"),
                    "brix": Decimal("85.60"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("450.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1220.00"),
                    "batches": [(Decimal("4200.000"), True, "Emperador Biñan Site", "DR-2509-01", "WB-2509-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20251020-001", "date": date(2025, 10, 20), "client": clients["BDI"], "mill": mills["LOPEZ"],
                    "volume": Decimal("3000.000"), "buy": Decimal("12300.00"), "sell": Decimal("16200.00"),
                    "brix": Decimal("85.10"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("430.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1170.00"),
                    "batches": [(Decimal("3000.000"), True, "BDI Terminal Site", "DR-2510-01", "WB-2510-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20251117-001", "date": date(2025, 11, 17), "client": clients["ADI"], "mill": mills["BUSCO"],
                    "volume": Decimal("4500.000"), "buy": Decimal("12500.00"), "sell": Decimal("16600.00"),
                    "brix": Decimal("85.50"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("450.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1250.00"),
                    "batches": [(Decimal("4500.000"), True, "ADI Lian Main Site", "DR-2511-01", "WB-2511-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BPI", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20251215-001", "date": date(2025, 12, 15), "client": clients["GSMI"], "mill": mills["SONEDCO"],
                    "volume": Decimal("3600.000"), "buy": Decimal("12400.00"), "sell": Decimal("16450.00"),
                    "brix": Decimal("85.20"), "chai": "CHAI 1.9", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("440.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1200.00"),
                    "batches": [(Decimal("3600.000"), True, "GSMI Cabuyao Site", "DR-2512-01", "WB-2512-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },

                # ===================== 2026 CURRENT YTD POs =====================
                {
                    "ref": "PO-20260119-001", "date": date(2026, 1, 19), "client": clients["EMPERADOR"], "mill": mills["AABC"],
                    "volume": Decimal("3500.000"), "buy": Decimal("12300.00"), "sell": Decimal("16300.00"),
                    "brix": Decimal("85.30"), "chai": "CHAI 1.9", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("430.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1180.00"),
                    "batches": [(Decimal("3500.000"), True, "Emperador Biñan Site", "DR-2601-01", "WB-2601-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260223-001", "date": date(2026, 2, 23), "client": clients["PROGREEN"], "mill": mills["PASSI"],
                    "volume": Decimal("2800.000"), "buy": Decimal("12250.00"), "sell": Decimal("16200.00"),
                    "brix": Decimal("85.00"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("420.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1160.00"),
                    "batches": [(Decimal("2800.000"), True, "Progreen Balayan Site", "DR-2602-01", "WB-2602-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260316-001", "date": date(2026, 3, 16), "client": clients["BDI"], "mill": mills["HAWAIIAN"],
                    "volume": Decimal("3200.000"), "buy": Decimal("12350.00"), "sell": Decimal("16350.00"),
                    "brix": Decimal("85.10"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("430.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1200.00"),
                    "batches": [(Decimal("3200.000"), True, "BDI Terminal Site", "DR-2603-01", "WB-2603-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BPI", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260420-001", "date": date(2026, 4, 20), "client": clients["ADI"], "mill": mills["CASA"],
                    "volume": Decimal("3000.000"), "buy": Decimal("12300.00"), "sell": Decimal("16250.00"),
                    "brix": Decimal("85.20"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("420.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1170.00"),
                    "batches": [(Decimal("3000.000"), True, "ADI Lian Main Site", "DR-2604-01", "WB-2604-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260518-001", "date": date(2026, 5, 18), "client": clients["GSMI"], "mill": mills["BUSCO"],
                    "volume": Decimal("3800.000"), "buy": Decimal("12400.00"), "sell": Decimal("16500.00"),
                    "brix": Decimal("85.50"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("450.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1250.00"),
                    "batches": [(Decimal("3800.000"), True, "GSMI Cabuyao Site", "DR-2605-01", "WB-2605-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260622-001", "date": date(2026, 6, 22), "client": clients["PROGREEN"], "mill": mills["BISCOM"],
                    "volume": Decimal("3000.000"), "buy": Decimal("12350.00"), "sell": Decimal("16400.00"),
                    "brix": Decimal("85.20"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("420.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1150.00"),
                    "batches": [(Decimal("3000.000"), True, "Progreen Balayan Site", "DR-2606-01", "WB-2606-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260715-001", "date": date(2026, 7, 15), "client": clients["EMPERADOR"], "mill": mills["LOPEZ"],
                    "volume": Decimal("3600.000"), "buy": Decimal("12450.00"), "sell": Decimal("16600.00"),
                    "brix": Decimal("85.40"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("440.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1200.00"),
                    "batches": [(Decimal("3600.000"), True, "Emperador Biñan Site", "DR-2607-01", "WB-2607-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "BPI", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260819-001", "date": date(2026, 8, 19), "client": clients["BDI"], "mill": mills["SONEDCO"],
                    "volume": Decimal("3400.000"), "buy": Decimal("12400.00"), "sell": Decimal("16500.00"),
                    "brix": Decimal("85.10"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.CLOSED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("430.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1190.00"),
                    "batches": [(Decimal("3400.000"), True, "BDI Terminal Site", "DR-2608-01", "WB-2608-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.PAID, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.CLOSED, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20260914-001", "date": date(2026, 9, 14), "client": clients["ADI"], "mill": mills["HAWAIIAN"],
                    "volume": Decimal("3500.000"), "buy": Decimal("12450.00"), "sell": Decimal("16650.00"),
                    "brix": Decimal("85.50"), "chai": "CHAI 1.9", "terms": "Net 30 days", "status": TransactionCluster.Status.DELIVERED,
                    "trk_partner": trk_royal, "trk_rate": Decimal("440.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1210.00"),
                    "batches": [(Decimal("3500.000"), True, "ADI Lian Main Site", "DR-2609-01", "WB-2609-01", Decimal("0"))],
                    "invoice_status": Invoice.Status.ISSUED, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.ACTIVE, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20261012-001", "date": date(2026, 10, 12), "client": clients["GSMI"], "mill": mills["BISCOM"],
                    "volume": Decimal("4000.000"), "buy": Decimal("12500.00"), "sell": Decimal("16800.00"),
                    "brix": Decimal("85.30"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.DELIVERED,
                    "trk_partner": trk_fast, "trk_rate": Decimal("450.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1240.00"),
                    "batches": [
                        (Decimal("2000.000"), True, "GSMI Cabuyao Site", "DR-2610-01A", "WB-2610-01A", Decimal("0")),
                        (Decimal("2000.000"), True, "GSMI Cabuyao Site", "DR-2610-01B", "WB-2610-01B", Decimal("0")),
                    ],
                    "invoice_status": Invoice.Status.ISSUED, "loan_bank": "Metrobank", "loan_status": CapitalLoan.Status.ACTIVE, "reconcile_mode": "full",
                },
                {
                    "ref": "PO-20261026-002", "date": date(2026, 10, 26), "client": clients["EMPERADOR"], "mill": mills["BUSCO"],
                    "volume": Decimal("3800.000"), "buy": Decimal("12550.00"), "sell": Decimal("16850.00"),
                    "brix": Decimal("85.40"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.DELIVERED,
                    "trk_partner": trk_f2, "trk_rate": Decimal("450.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1230.00"),
                    # Weight discrepancy: 3,740 MT received vs 3,800 MT dispatched (60 MT shortage = 1.58% variance > 1% tolerance)
                    "batches": [
                        (Decimal("1900.000"), True, "Emperador Biñan Site", "DR-2610-02A", "WB-2610-02A", Decimal("30.000")),
                        (Decimal("1840.000"), True, "Emperador Biñan Site", "DR-2610-02B", "WB-2610-02B", Decimal("30.000")),
                    ],
                    "invoice_status": Invoice.Status.ISSUED, "loan_bank": "BPI Corporate Facility", "loan_status": CapitalLoan.Status.ACTIVE, "reconcile_mode": "dp_and_b1",
                },
                {
                    "ref": "PO-20261101-001", "date": date(2026, 11, 1), "client": clients["PROGREEN"], "mill": mills["SONEDCO"],
                    "volume": Decimal("5000.000"), "buy": Decimal("12500.00"), "sell": Decimal("16800.00"),
                    "brix": Decimal("85.50"), "chai": "CHAI 1.8", "terms": "Net 30 days", "status": TransactionCluster.Status.ACTIVE,
                    "trk_partner": trk_royal, "trk_rate": Decimal("450.00"), "brg_partner": brg_1st, "brg_rate": Decimal("1250.00"),
                    # 3,000 MT delivered, 2,000 MT in transit!
                    "batches": [
                        (Decimal("1500.000"), True, "Progreen Balayan Site", "DR-2611-01A", "WB-2611-01A", Decimal("0")),
                        (Decimal("1500.000"), True, "Progreen Balayan Site", "DR-2611-01B", "WB-2611-01B", Decimal("0")),
                        (Decimal("2000.000"), False, "Progreen Balayan Site", "DR-2611-01C", "WB-2611-01C", Decimal("0")),
                    ],
                    "invoice_status": None, "loan_bank": "BDO Unibank", "loan_status": CapitalLoan.Status.ACTIVE, "reconcile_mode": "dp_only",
                },
                {
                    "ref": "PO-20261103-002", "date": date(2026, 11, 3), "client": clients["BDI"], "mill": mills["BUSCO"],
                    "volume": Decimal("4000.000"), "buy": Decimal("12350.00"), "sell": Decimal("16500.00"),
                    "brix": Decimal("85.20"), "chai": "CHAI 2.0", "terms": "Net 30 days", "status": TransactionCluster.Status.ACTIVE,
                    "trk_partner": trk_fast, "trk_rate": Decimal("450.00"), "brg_partner": brg_solid, "brg_rate": Decimal("1300.00"),
                    # 2,000 MT delivered, 2,000 MT in transit
                    "batches": [
                        (Decimal("2000.000"), True, "BDI Terminal Site", "DR-2611-02A", "WB-2611-02A", Decimal("0")),
                        (Decimal("2000.000"), False, "BDI Terminal Site", "DR-2611-02B", "WB-2611-02B", Decimal("0")),
                    ],
                    "invoice_status": None, "loan_bank": "Security Bank", "loan_status": CapitalLoan.Status.ACTIVE, "reconcile_mode": "dp_only",
                },
                {
                    "ref": "PO-20261104-003", "date": date(2026, 11, 4), "client": clients["ADI"], "mill": mills["CASA"],
                    "volume": Decimal("3000.000"), "buy": Decimal("12450.00"), "sell": Decimal("16700.00"),
                    "brix": Decimal("85.10"), "chai": "CHAI 2.1", "terms": "Net 30 days", "status": TransactionCluster.Status.APPROVED,
                    "trk_partner": trk_2go, "trk_rate": Decimal("440.00"), "brg_partner": brg_manila, "brg_rate": Decimal("1180.00"),
                    "batches": [], "invoice_status": None, "loan_bank": None, "loan_status": None, "reconcile_mode": "none",
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

                # CHAI record
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

                # Base LogisticsLedger
                total_loaded_mt = sum(b[0] + (b[5] if len(b) > 5 else Decimal("0")) for b in spec["batches"])
                total_deliv_mt = sum(b[0] for b in spec["batches"] if b[1])
                est_trk_total = spec["volume"] * spec["trk_rate"]
                est_brg_total = spec["volume"] * spec["brg_rate"]
                has_variance = any(len(b) > 5 and b[5] > Decimal("0") for b in spec["batches"])

                log_ledger = LogisticsLedger.objects.create(
                    cluster=cluster,
                    partner=spec["brg_partner"],
                    trucking_partner=spec["trk_partner"],
                    barge_partner=spec["brg_partner"],
                    vessel_id=spec["brg_partner"].name,
                    loaded_volume_mt=total_loaded_mt,
                    received_volume_mt=total_deliv_mt if total_deliv_mt > 0 else None,
                    loaded_at=dt_on(c_date + timedelta(days=1), 8, 0) if total_loaded_mt > 0 else None,
                    received_at=dt_on(c_date + timedelta(days=4), 15, 0) if (total_deliv_mt > 0 and spec["status"] != TransactionCluster.Status.ACTIVE) else None,
                    tracking_fees=est_trk_total if not spec["batches"] else Decimal("0.00"),
                    barge_fees=est_brg_total if not spec["batches"] else Decimal("0.00"),
                    variance_exceeds_tolerance=has_variance,
                    dispute_status="DISPUTED" if has_variance else "NONE",
                )

                recon = FinancialReconciliation.objects.create(cluster=cluster)

                # Delivery Batches
                created_batches = []
                for b_idx, b_info in enumerate(spec["batches"], start=1):
                    b_mt = b_info[0]
                    is_arrived = b_info[1]
                    b_loc = b_info[2]
                    b_dr = b_info[3]
                    b_wb = b_info[4]
                    shortage = b_info[5] if len(b_info) > 5 else Decimal("0")
                    disp_mt = b_mt + shortage

                    b_date = min(c_date + timedelta(days=b_idx * 2), today)
                    disp_dt = dt_on(b_date, 8, 0)
                    arr_dt = dt_on(min(b_date + timedelta(days=2), today), 16, 30) if is_arrived else None

                    d_obj = DeliveryLedger.objects.create(
                        purchase_order=po,
                        supplier=spec["mill"],
                        dispatched_mt=disp_mt,
                        delivered_mt=b_mt if is_arrived else Decimal("0"),
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
                        notes=f"Batch {b_idx} shipment to {b_loc}" + (f" (shortage of {shortage} MT)" if shortage > 0 else ""),
                    )
                    created_batches.append(d_obj)

                # Cluster Status
                if cluster.status != spec["status"]:
                    cluster.status = spec["status"]
                    cluster.save(update_fields=["status"])

                # Loan setup
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

                for d_obj in created_batches:
                    d_obj.sync_delivery_expense_vouchers()

                # Reconciliations and Cash Vouchers
                rmode = spec["reconcile_mode"]
                if rmode in ("full", "dp_and_b1", "dp_only"):
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

                # Sales Invoice
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

            # Link MRO permits to some active 2026 POs
            unlinked_mros = list(MolassesReleaseOrder.objects.filter(cluster__isnull=True)[:6])
            active_2026_clusters = list(TransactionCluster.objects.filter(reference_code__startswith="PO-2026"))
            if unlinked_mros and active_2026_clusters:
                for idx, mro in enumerate(unlinked_mros):
                    target_c = active_2026_clusters[idx % len(active_2026_clusters)]
                    mro.cluster = target_c
                    mro.save(update_fields=["cluster"])

        self.stdout.write(self.style.SUCCESS("2024-2026 multi-year dataset seeded successfully!"))
