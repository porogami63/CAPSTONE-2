from io import BytesIO

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from masters.models import Client, SugarMill
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
        self.assertContains(response, "Orders &amp; Deals")
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


class MROLinkingAndCopilotTests(TestCase):
    def setUp(self):
        from masters.models import Client, Planter, SugarMill
        from operations.models import MolassesReleaseOrder, TransactionCluster

        self.user = User.objects.create_user(
            username="ops_copilot",
            password="password123",
            role=User.Role.OPERATIONS,
            is_staff=True,
        )
        self.client_obj = Client.objects.create(name="San Miguel Corp")
        self.mill = SugarMill.objects.create(name="BUSCO Sugar Mill")
        self.planter = Planter.objects.create(name="Planter Alpha")
        self.cluster = TransactionCluster.objects.create(
            reference_code="GSMI-2026-TEST",
            client=self.client_obj,
            sugar_mill=self.mill,
        )
        self.mro = MolassesReleaseOrder.objects.create(
            mro_number="MRO-9999",
            planter=self.planter,
            sugar_mill=self.mill,
            tons=150.50,
            trader="HEINDRICH",
            crop_year="2024 - 25",
        )

    def test_link_and_unlink_mro_to_cluster(self):
        self.client.login(username="ops_copilot", password="password123")

        # 1. Link MRO
        link_url = reverse("operations:link_mro", kwargs={"pk": self.cluster.pk})
        response = self.client.post(link_url, {"mro_id": self.mro.pk}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.mro.refresh_from_db()
        self.assertEqual(self.mro.cluster, self.cluster)

        # 2. Unlink MRO
        unlink_url = reverse("operations:unlink_mro", kwargs={"pk": self.cluster.pk, "mro_pk": self.mro.pk})
        response = self.client.post(unlink_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.mro.refresh_from_db()
        self.assertIsNone(self.mro.cluster)

    def test_copilot_api_endpoint(self):
        self.client.login(username="ops_copilot", password="password123")
        url = reverse("operations:copilot_query_api")

        # Query high variance
        res = self.client.post(url, data='{"query": "high variance"}', content_type="application/json")
        self.assertEqual(res.status_code, 200)
        json_data = res.json()
        self.assertIn("answer_html", json_data)

        res = self.client.post(url, data='{"query": "unassigned mro"}', content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Molasses Release Order", res.json()["answer_html"])


class AutoGenerationAndDocumentTests(TestCase):
    def setUp(self):
        from masters.models import Client, SugarMill
        self.user = User.objects.create_user(
            username="ops_autogen",
            password="password123",
            role=User.Role.MANAGEMENT,
            is_staff=True,
        )
        self.client_obj = Client.objects.create(name="Emperador Distillers")
        self.mill = SugarMill.objects.create(name="HAWAIIAN Sugar Mill")

    def test_auto_reference_generators(self):
        from operations.services.reference_generators import (
            generate_po_reference,
            generate_si_reference,
            generate_cv_reference,
        )
        po_ref = generate_po_reference()
        self.assertTrue(po_ref.startswith("PO-"))

        si_ref = generate_si_reference(po_ref)
        self.assertTrue(si_ref.startswith("SI-"))

        cv_ref = generate_cv_reference(po_ref)
        self.assertTrue(cv_ref.startswith("CV-"))

    def test_cluster_creation_with_auto_generated_reference(self):
        self.client.login(username="ops_autogen", password="password123")
        url = reverse("operations:cluster_create")
        response = self.client.post(url, {
            "reference_code": "",  # Blank to trigger auto-generation
            "client": self.client_obj.pk,
            "sugar_mill": self.mill.pk,
            "status": "draft",
            "volume_mt": "500.000",
            "unit_price": "32000.00",
            "selling_price": "41000.00",
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        cluster = TransactionCluster.objects.first()
        self.assertIsNotNone(cluster)
        self.assertTrue(cluster.reference_code.startswith("PO-"))

    def test_contract_and_po_pdf_download(self):
        self.client.login(username="ops_autogen", password="password123")
        cluster = TransactionCluster.objects.create(
            reference_code="PO-20260925-001",
            client=self.client_obj,
            sugar_mill=self.mill,
        )
        from operations.models import PurchaseOrder
        PurchaseOrder.objects.create(
            cluster=cluster,
            volume_mt=100.0,
            unit_price=30000.00,
            selling_price=40000.00,
        )

        contract_pdf_url = reverse("operations:download_contract_pdf", kwargs={"pk": cluster.pk})
        res = self.client.get(contract_pdf_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")

        po_pdf_url = reverse("operations:download_po_pdf", kwargs={"pk": cluster.pk})
        res = self.client.get(po_pdf_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")

    def test_generate_reference_api(self):
        self.client.login(username="ops_autogen", password="password123")
        url = reverse("operations:generate_reference_api")
        res = self.client.get(url, {"cluster_ref": "PO-20260925-001"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("po_ref", data)
        self.assertIn("si_ref", data)
        self.assertIn("cv_ref", data)
        self.assertTrue(data["si_ref"].startswith("SI-"))
        self.assertTrue(data["cv_ref"].startswith("CV-"))


class CHAICrudTests(TestCase):
    def setUp(self):
        from masters.models import SugarMill
        self.user = User.objects.create_user(
            username="chai_admin",
            password="password123",
            role=User.Role.MANAGEMENT,
            is_staff=True,
        )
        self.mill = SugarMill.objects.create(name="BUSCO Sugar Mill")

    def test_chai_crud_flow(self):
        self.client.login(username="chai_admin", password="password123")

        # 1. Create CHAI Record
        create_url = reverse("operations:chai_create")
        res = self.client.post(create_url, {
            "chai_number": "CHAI-TEST-001",
            "chai_value": "1.0",
            "title": "Verified High Grade Test",
            "sugar_mill": self.mill.pk,
            "brix_level": "85.50",
            "purity_percent": "79.00",
            "total_sugars_percent": "56.00",
            "tested_at": "2026-09-25",
            "inspector": "Chief Inspector",
            "status": "approved",
            "remarks": "Excellent quality molasses batch.",
        }, follow=True)
        self.assertEqual(res.status_code, 200)

        from operations.models import CHAIRecord
        record = CHAIRecord.objects.get(chai_number="CHAI-TEST-001")
        self.assertEqual(float(record.chai_value), 1.0)

        # 2. View CHAI List & Detail
        list_url = reverse("operations:chai_list")
        res = self.client.get(list_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "CHAI-TEST-001")

        detail_url = reverse("operations:chai_detail", kwargs={"pk": record.pk})
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Verified High Grade Test")

        # 3. Edit CHAI Record
        edit_url = reverse("operations:chai_edit", kwargs={"pk": record.pk})
        res = self.client.post(edit_url, {
            "chai_number": "CHAI-TEST-001",
            "chai_value": "2.0",
            "title": "Updated Quality Spec",
            "sugar_mill": self.mill.pk,
            "brix_level": "82.00",
            "tested_at": "2026-09-25",
            "status": "approved",
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(float(record.chai_value), 2.0)
        self.assertEqual(record.title, "Updated Quality Spec")

        # 4. Export CSV
        export_url = reverse("operations:export_chai_csv")
        res = self.client.get(export_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv")
        self.assertContains(res, "CHAI-TEST-001")

        # 5. Delete CHAI Record
        delete_url = reverse("operations:chai_delete", kwargs={"pk": record.pk})
        res = self.client.post(delete_url, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(CHAIRecord.objects.filter(chai_number="CHAI-TEST-001").exists())


class StatisticalComputationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="statuser",
            password="password123",
            role=User.Role.MANAGEMENT,
        )
        self.client.login(username="statuser", password="password123")

    def test_compute_series_stats(self):
        from operations.services.stats_services import compute_series_stats
        data = [100.0, 200.0, 200.0, 300.0]
        stats = compute_series_stats(data)
        self.assertEqual(stats["mean"], 200.0)
        self.assertEqual(stats["median"], 200.0)
        self.assertEqual(stats["mode"], 200.0)
        self.assertEqual(stats["min"], 100.0)
        self.assertEqual(stats["max"], 300.0)
        self.assertEqual(stats["count"], 4)

    def test_outlier_detection_and_api(self):
        from operations.services.stats_services import check_input_outliers
        # Test API endpoint
        url = reverse("operations:stats_check_api")
        res = self.client.post(url, {"volume_mt": "50000"})
        self.assertEqual(res.status_code, 200)
        json_resp = res.json()
        self.assertIn("is_flagged", json_resp)

    def test_stats_monitoring_view(self):
        url = reverse("operations:stats_monitoring")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Operational Statistical Benchmarks")


class RoleProcessNotificationTests(TestCase):
    def setUp(self):
        self.op_mgr = User.objects.create_user(
            username="op_mgr",
            password="password123",
            role=User.Role.OPERATIONS_MANAGEMENT,
        )
        self.admin_user = User.objects.create_user(
            username="admin_mgr",
            password="password123",
            role=User.Role.ADMINISTRATOR,
        )
        self.finance_user = User.objects.create_user(
            username="fin_user",
            password="password123",
            role=User.Role.FINANCE,
        )
        self.invoice_user = User.objects.create_user(
            username="inv_user",
            password="password123",
            role=User.Role.INVOICING,
        )
        self.client_obj = Client.objects.create(name="Notification Test Client")
        self.mill = SugarMill.objects.create(name="Notification Sugar Mill")

    def test_po_creation_triggers_notifications(self):
        from audit.models import Notification
        self.client.login(username="op_mgr", password="password123")
        url = reverse("operations:cluster_create")
        res = self.client.post(url, {
            "reference_code": "PO-NOTIF-999",
            "client": self.client_obj.pk,
            "sugar_mill": self.mill.pk,
            "volume_mt": "1500.00",
            "unit_price": "14000.00",
            "status": "draft",
            "confirmed_outlier": "true",
        }, follow=True)
        self.assertEqual(res.status_code, 200)

        # Check Finance and Invoicing users received notifications
        fin_notifs = Notification.objects.filter(recipient=self.finance_user)
        self.assertTrue(fin_notifs.exists())
        self.assertIn("New Purchase Order Created", fin_notifs.first().title)

        inv_notifs = Notification.objects.filter(recipient=self.invoice_user)
        self.assertTrue(inv_notifs.exists())

    def test_offspec_chai_triggers_alert(self):
        from audit.models import Notification
        self.client.login(username="op_mgr", password="password123")
        url = reverse("operations:chai_create")
        res = self.client.post(url, {
            "chai_number": "CHAI-OFFSPEC-101",
            "chai_value": "4.0",
            "title": "Low Quality Off-Spec Batch",
            "sugar_mill": self.mill.pk,
            "brix_level": "68.50",
            "tested_at": "2026-09-25",
            "status": "rejected",
            "confirmed_outlier": "true",
        }, follow=True)
        self.assertEqual(res.status_code, 200)

        # Check notification level is danger / alert
        alert = Notification.objects.filter(title__contains="CHAI Quality Alert").first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.level, "danger")

    def test_pending_tasks_view(self):
        self.client.login(username="op_mgr", password="password123")
        url = reverse("operations:pending_tasks")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Operational Process Handoffs")


class ApprovalWorkflowAndReminderTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_approval",
            password="password123",
            role=User.Role.ADMINISTRATOR,
        )
        self.client_obj = Client.objects.create(name="Approval Test Client")
        self.mill = SugarMill.objects.create(name="Approval Test Mill")
        self.cluster = TransactionCluster.objects.create(
            reference_code="PO-APPROVE-100",
            client=self.client_obj,
            sugar_mill=self.mill,
            status=TransactionCluster.Status.DRAFT,
        )
        self.client.login(username="admin_approval", password="password123")

    def test_submit_approve_reject_workflow(self):
        # 1. Submit for approval
        sub_url = reverse("operations:submit_cluster", kwargs={"pk": self.cluster.pk})
        res = self.client.post(sub_url, follow=True)
        self.assertEqual(res.status_code, 200)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, TransactionCluster.Status.PENDING_APPROVAL)
        self.assertIsNotNone(self.cluster.submitted_at)

        # 2. Approve
        app_url = reverse("operations:approve_cluster", kwargs={"pk": self.cluster.pk})
        res = self.client.post(app_url, follow=True)
        self.assertEqual(res.status_code, 200)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, TransactionCluster.Status.APPROVED)
        self.assertIsNotNone(self.cluster.approved_at)
        self.assertEqual(self.cluster.approved_by, self.admin)

        # 3. Reject without comments (Fails validation)
        rej_url = reverse("operations:reject_cluster", kwargs={"pk": self.cluster.pk})
        res = self.client.post(rej_url, {"rejection_comments": ""}, follow=True)
        self.assertContains(res, "Rejection comments are required")

        # 4. Reject with mandatory rejection comments
        res = self.client.post(rej_url, {"rejection_comments": "Brix specs do not match lab cert."}, follow=True)
        self.assertEqual(res.status_code, 200)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, TransactionCluster.Status.RETURNED)
        self.assertEqual(self.cluster.rejection_comments, "Brix specs do not match lab cert.")
        self.assertIsNotNone(self.cluster.rejected_at)

    def test_timeline_reminders_pre_and_post(self):
        from datetime import date, timedelta
        from finance.models import Invoice
        from operations.services.reminder_services import process_timeline_reminders

        due_soon = date.today() + timedelta(days=3)
        Invoice.objects.create(
            cluster=self.cluster,
            invoice_number="INV-TIMELINE-001",
            amount=500000.00,
            issued_at=date.today(),
            due_date=due_soon,
            status=Invoice.Status.ISSUED,
        )

        count = process_timeline_reminders()
        self.assertGreaterEqual(count, 1)








