from io import BytesIO

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from operations.models import TransactionCluster


def build_workbook_bytes():
    from openpyxl import Workbook

    buffer = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["HEINDRICH TRADING CORPORATION 2026"])
    sheet.append(["SI", "Invoice Date", "Barge", "Source", "Purchase Price", "Trucking", "Barging", "Customer", "Delivered", "Received", "", "Selling", "Amount"])
    sheet.append([101, "2026-07-01", "MV Aurora", "BUSCO", 42000, 500, 250, "GSMI", 100, 99.2, "", 43500, 4350000])
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


class ExcelImportViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="testpass123",
            role=User.Role.MANAGEMENT,
            is_staff=True,
            is_superuser=True,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_management_user_can_upload_workbook(self):
        self.client.login(username="admin", password="testpass123")

        workbook = SimpleUploadedFile(
            "htc-summary.xlsx",
            build_workbook_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # 1. Post the workbook to trigger the staged preview
        response = self.client.post(
            reverse("operations:import_excel"),
            {"workbook": workbook, "replace_existing": True},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["preview_mode"])
        self.assertEqual(response.context["summary"]["total_rows"], 1)

        # 2. Confirm and commit the staged import
        response = self.client.post(
            reverse("operations:import_excel"),
            {"confirm_commit": "1"},
            follow=True,
        )

        self.assertRedirects(response, reverse("operations:cluster_list"))
        self.assertEqual(TransactionCluster.objects.count(), 1)
        self.assertTrue(TransactionCluster.objects.filter(reference_code="SI-101").exists())

        message_texts = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("Import completed successfully" in message for message in message_texts))


class OperationsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ops",
            password="testpass123",
            role=User.Role.OPERATIONS,
            is_staff=True,
        )

    def test_cluster_list_renders(self):
        from masters.models import Client, SugarMill
        from operations.models import PurchaseOrder, TransactionCluster

        client = Client.objects.create(name="Acme Foods")
        mill = SugarMill.objects.create(name="North Mill")
        cluster = TransactionCluster.objects.create(reference_code="PO-001", client=client, sugar_mill=mill)
        PurchaseOrder.objects.create(cluster=cluster, volume_mt=120, unit_price=41000, terms="Net 30")

        self.client.login(username="ops", password="testpass123")
        response = self.client.get(reverse("operations:cluster_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transactions")
        self.assertContains(response, "PO-001")

    def test_logistics_list_renders(self):
        from django.utils import timezone

        from masters.models import Client, LogisticsPartner, SugarMill
        from operations.models import LogisticsLedger, TransactionCluster

        client = Client.objects.create(name="Acme Foods")
        mill = SugarMill.objects.create(name="North Mill")
        partner = LogisticsPartner.objects.create(name="Harbor Logistics")
        cluster = TransactionCluster.objects.create(reference_code="PO-002", client=client, sugar_mill=mill)
        LogisticsLedger.objects.create(
            cluster=cluster,
            partner=partner,
            loaded_volume_mt=100,
            received_volume_mt=98,
            loaded_at=timezone.now(),
        )

        self.client.login(username="ops", password="testpass123")
        response = self.client.get(reverse("operations:logistics_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Logistics")
        self.assertContains(response, "PO-002")


class LogisticsLedgerVarianceTests(TestCase):
    def test_synchronous_variance_computation_and_tolerance(self):
        from masters.models import Client, LogisticsPartner, SugarMill
        from operations.models import LogisticsLedger, TransactionCluster

        client = Client.objects.create(name="Beta Foods")
        mill = SugarMill.objects.create(name="South Mill")
        partner = LogisticsPartner.objects.create(name="Oceanic Freight")
        cluster = TransactionCluster.objects.create(reference_code="PO-VAR-01", client=client, sugar_mill=mill)

        # 1. Under tolerance (0.5% variance <= 1.0% default tolerance)
        ledger = LogisticsLedger.objects.create(
            cluster=cluster,
            partner=partner,
            loaded_volume_mt=100,
            received_volume_mt=99.5,
        )
        self.assertAlmostEqual(float(ledger.variance_percent), 0.5, places=2)
        self.assertFalse(ledger.variance_exceeds_tolerance)

        # 2. Exceeds tolerance (2.0% variance > 1.0% tolerance)
        ledger.received_volume_mt = 98.0
        ledger.save()
        self.assertAlmostEqual(float(ledger.variance_percent), 2.0, places=2)
        self.assertTrue(ledger.variance_exceeds_tolerance)


class InvoiceStatusUpdateTests(TestCase):
    def test_update_invoice_status_inline(self):
        from datetime import date
        from finance.models import Invoice
        from masters.models import Client, SugarMill
        from operations.models import TransactionCluster

        user = User.objects.create_user(
            username="inv_user",
            password="password123",
            role=User.Role.INVOICING,
            is_staff=True,
        )
        client = Client.objects.create(name="Gamma Foods")
        mill = SugarMill.objects.create(name="Central Mill")
        cluster = TransactionCluster.objects.create(reference_code="PO-INV-01", client=client, sugar_mill=mill)
        invoice = Invoice.objects.create(
            cluster=cluster,
            invoice_number="INV-999",
            amount=500000,
            issued_at=date.today(),
            status=Invoice.Status.DRAFT,
        )

        self.client.login(username="inv_user", password="password123")
        url = reverse("operations:update_invoice_status", kwargs={"invoice_pk": invoice.pk})
        
        # 1. Update from draft to issued
        response = self.client.post(url, {"status": "issued"}, follow=True)
        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)

        # 2. Update from issued to paid
        response = self.client.post(url, {"status": "paid"}, follow=True)
        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)


class DisputeResolutionTests(TestCase):
    def test_concede_and_proceed_dispute(self):
        from masters.models import Client, LogisticsPartner, SugarMill
        from operations.models import LogisticsLedger, TransactionCluster

        user = User.objects.create_user(
            username="mgmt_user",
            password="password123",
            role=User.Role.MANAGEMENT,
            is_staff=True,
        )
        client = Client.objects.create(name="Delta Foods")
        mill = SugarMill.objects.create(name="North Mill")
        partner = LogisticsPartner.objects.create(name="Sea Transport")
        cluster = TransactionCluster.objects.create(reference_code="PO-DISP-01", client=client, sugar_mill=mill)
        ledger = LogisticsLedger.objects.create(
            cluster=cluster,
            partner=partner,
            loaded_volume_mt=500,
            received_volume_mt=490, # 2.0% variance > 1.0% tolerance -> Disputed
        )

        self.assertTrue(ledger.variance_exceeds_tolerance)
        self.assertEqual(ledger.dispute_status, LogisticsLedger.DisputeStatus.DISPUTED)

        self.client.login(username="mgmt_user", password="password123")
        url = reverse("operations:resolve_dispute", kwargs={"pk": cluster.pk})

        response = self.client.post(
            url,
            {
                "resolution_type": "CONCEDED",
                "resolution_notes": "Conceded 10 MT variance loss due to customer request.",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        ledger.refresh_from_db()
        self.assertFalse(ledger.variance_exceeds_tolerance)
        self.assertEqual(ledger.dispute_status, LogisticsLedger.DisputeStatus.RESOLVED)
        self.assertEqual(ledger.resolution_type, "CONCEDED")


class MROSummaryTests(TestCase):
    def setUp(self):
        from masters.models import Planter
        from operations.models import MolassesReleaseOrder
        self.user = User.objects.create_user(
            username="ops_mro",
            password="password123",
            role=User.Role.OPERATIONS,
            is_staff=True,
        )
        self.planter = Planter.objects.create(name="ABSFI", code="ABSFI")
        self.mro = MolassesReleaseOrder.objects.create(
            mro_number="000731",
            planter=self.planter,
            tons=913.11889,
            trader="HEINDRICH",
            crop_year="2024 - 25",
        )

    def test_mro_summary_view_renders(self):
        self.client.login(username="ops_mro", password="password123")
        response = self.client.get(reverse("operations:mro_summary"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Molasses Release Order Summary")
        self.assertContains(response, "000731")
        self.assertContains(response, "ABSFI")

    def test_mro_create_and_delete(self):
        self.client.login(username="ops_mro", password="password123")
        url = reverse("operations:mro_create")
        post_data = {
            "mro_number": "000800",
            "planter_name": "SGABI",
            "tons": "500.25",
            "crop_year": "2025 - 2026",
            "trader": "HEINDRICH",
        }
        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        from operations.models import MolassesReleaseOrder
        self.assertTrue(MolassesReleaseOrder.objects.filter(mro_number="000800").exists())

        # Test deletion
        new_mro = MolassesReleaseOrder.objects.get(mro_number="000800")
        del_url = reverse("operations:mro_delete", kwargs={"pk": new_mro.pk})
        del_response = self.client.post(del_url, follow=True)
        self.assertEqual(del_response.status_code, 200)
        self.assertFalse(MolassesReleaseOrder.objects.filter(mro_number="000800").exists())

    def test_mro_export_csv(self):
        self.client.login(username="ops_mro", password="password123")
        response = self.client.get(reverse("operations:mro_export_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertContains(response, "PLANTERS,TONS,DATE,TRADER,MRO #,CROP YEAR")
        self.assertContains(response, "ABSFI")




