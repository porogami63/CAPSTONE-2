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
