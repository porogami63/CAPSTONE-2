from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from finance.models import (
    CapitalLoan,
    CashVoucher,
    FinancialReconciliation,
    Invoice,
    PaymentExpenseMatch,
)
from masters.models import Client, LogisticsPartner, SugarMill
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster


class Command(BaseCommand):
    help = "Seed HTC Core with sanitized mock data for UAT and demos."

    def handle(self, *args, **options):
        self.stdout.write("Seeding HTC Core demo data...")

        users = [
            ("admin", User.Role.ADMINISTRATOR, True),
            ("ops_mgmt", User.Role.OPERATIONS_MANAGEMENT, True),
            ("operations", User.Role.OPERATIONS_MANAGEMENT, False),
            ("finance", User.Role.FINANCE, False),
            ("invoicing", User.Role.INVOICING, False),
        ]
        for username, role, is_super in users:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "is_staff": is_super, "is_superuser": is_super},
            )
            if created or not user.check_password("htc2026"):
                user.set_password("htc2026")
                user.role = role
                user.save()
            self.stdout.write(f"  User: {username} ({role})")

        clients = {
            "GSMI": Client.objects.get_or_create(
                name="Ginebra San Miguel Inc.",
                defaults={"tin": "000-111-222", "contact_person": "Accounts Payable"},
            )[0],
            "Emperador": Client.objects.get_or_create(
                name="Emperador Distillers Inc.",
                defaults={"tin": "000-333-444"},
            )[0],
            "ADI": Client.objects.get_or_create(
                name="Absolute Distillers Inc.",
                defaults={"tin": "000-555-666"},
            )[0],
        }
        busco = SugarMill.objects.get_or_create(
            name="BUSCO Sugar Milling Co.",
            defaults={"location": "Bukidnon"},
        )[0]
        partner = LogisticsPartner.objects.get_or_create(
            name="Manila Barge Logistics",
            defaults={"default_freight_rate": Decimal("85000.00")},
        )[0]

        demo_specs = [
            {
                "ref": "HTC-2026-001",
                "client": clients["GSMI"],
                "volume": Decimal("1500.000"),
                "price": Decimal("18500.00"),
                "loaded": Decimal("1500.000"),
                "received": Decimal("1485.000"),
                "invoice": ("SI-GSMI-2401", Decimal("27750000.00")),
                "voucher": ("CV-LOG-501", Decimal("42500.00"), "50% barge deposit"),
                "loan": ("BDO", Decimal("5000000.00"), Decimal("12.0000"), 45),
            },
            {
                "ref": "HTC-2026-002",
                "client": clients["Emperador"],
                "volume": Decimal("2200.000"),
                "price": Decimal("19200.00"),
                "loaded": Decimal("2200.000"),
                "received": Decimal("2156.000"),
                "invoice": ("SI-EMP-2402", Decimal("42240000.00")),
                "voucher": ("CV-LOG-502", Decimal("62000.00"), "Tracking service"),
                "loan": ("Metrobank", Decimal("8000000.00"), Decimal("11.5000"), 60),
            },
            {
                "ref": "HTC-2026-003",
                "client": clients["ADI"],
                "volume": Decimal("980.500"),
                "price": Decimal("17800.00"),
                "loaded": Decimal("980.500"),
                "received": Decimal("968.000"),
                "invoice": ("SI-ADI-2403", Decimal("17452900.00")),
                "voucher": ("CV-MILL-103", Decimal("150000.00"), "Mill downpayment"),
                "loan": ("Security Bank", Decimal("3500000.00"), Decimal("13.2500"), 30),
            },
        ]

        for spec in demo_specs:
            cluster, created = TransactionCluster.objects.get_or_create(
                reference_code=spec["ref"],
                defaults={
                    "client": spec["client"],
                    "sugar_mill": busco,
                    "status": TransactionCluster.Status.ACTIVE,
                    "contract_notes": "Sanitized demo transaction for UAT.",
                },
            )
            if not created:
                continue

            PurchaseOrder.objects.create(
                cluster=cluster,
                volume_mt=spec["volume"],
                unit_price=spec["price"],
                terms="Net 30",
                approved_at=timezone.now() - timedelta(days=20),
            )
            logistics = LogisticsLedger.objects.create(
                cluster=cluster,
                partner=partner,
                vessel_id=f"MB-{spec['ref'][-3:]}",
                loaded_volume_mt=spec["loaded"],
                received_volume_mt=spec["received"],
                loaded_at=timezone.now() - timedelta(days=15),
                received_at=timezone.now() - timedelta(days=5),
                tracking_fees=Decimal("12500.00"),
                barge_fees=Decimal("85000.00"),
            )
            inv_num, inv_amt = spec["invoice"]
            Invoice.objects.create(
                cluster=cluster,
                invoice_number=inv_num,
                amount=inv_amt,
                status=Invoice.Status.ISSUED,
            )
            cv_num, cv_amt, cv_purpose = spec["voucher"]
            CashVoucher.objects.create(
                cluster=cluster,
                voucher_number=cv_num,
                amount=cv_amt,
                purpose=cv_purpose,
            )
            bank, principal, rate, days_ago = spec["loan"]
            CapitalLoan.objects.create(
                cluster=cluster,
                bank_name=bank,
                principal=principal,
                interest_rate_annual=rate,
                start_date=date.today() - timedelta(days=days_ago),
                due_date=date.today() - timedelta(days=max(days_ago - 30, 0)),
                status=CapitalLoan.Status.OVERDUE if days_ago > 35 else CapitalLoan.Status.ACTIVE,
            )
            recon, _ = FinancialReconciliation.objects.get_or_create(cluster=cluster)
            PaymentExpenseMatch.objects.create(
                reconciliation=recon,
                payment_reference=f"PAY-{spec['ref'][-3:]}",
                expense_type=PaymentExpenseMatch.ExpenseType.LOGISTICS_DEPOSIT,
                amount=spec["voucher"][1],
                notes="Demo match for UAT",
            )
            recon.matched_payment_amount = spec["voucher"][1]
            recon.save()

            if logistics.variance_exceeds_tolerance:
                self.stdout.write(f"  {spec['ref']}: variance alert {logistics.variance_percent}%")

        self.stdout.write(self.style.SUCCESS("Seed complete. Login with any pilot user / htc2026"))
