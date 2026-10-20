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
        self.assertContains(res, "Pending Tasks")


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


class IncrementalDeliveryLedgerTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from masters.models import Client, SugarMill, LogisticsPartner
        from operations.models import TransactionCluster, PurchaseOrder

        self.client_adi = Client.objects.create(name="Absolute Distillers Inc. (ADI)")
        self.mill_busco = SugarMill.objects.create(name="BUSCO Sugar Milling Co.")
        self.mill_casa = SugarMill.objects.create(name="CASA Sugar Mill")
        self.mill_balayan = SugarMill.objects.create(name="Balayan Sugar Mill")
        self.logistics_partner = LogisticsPartner.objects.create(name="Manila Barge Logistics")

        self.cluster = TransactionCluster.objects.create(
            reference_code="PO-ADI-10000",
            client=self.client_adi,
            sugar_mill=self.mill_busco,
            status=TransactionCluster.Status.APPROVED,
        )

        self.po = PurchaseOrder.objects.create(
            cluster=self.cluster,
            po_reference_number="PO-ADI-10000",
            total_contracted_mt=Decimal("10000.000"),
            volume_mt=Decimal("10000.000"),
            customer=self.client_adi,
            unit_price=Decimal("32000.00"),
            selling_price=Decimal("41000.00"),
        )

        self.admin = User.objects.create_user(
            username="ops_mgr",
            password="testpass123",
            role=User.Role.OPERATIONS_MANAGEMENT,
        )

    def test_dynamic_remaining_mt_and_status_progression(self):
        from decimal import Decimal
        from operations.models import DeliveryLedger

        # 1. Initial State: 10,000 MT Contracted, 0 Delivered, Status: Open
        self.assertEqual(self.po.total_delivered_mt, Decimal("0"))
        self.assertEqual(self.po.remaining_mt, Decimal("10000.000"))
        self.assertEqual(self.po.po_status, "Open")

        # 2. First Shipment: 2,000 MT from BUSCO -> ADI Site
        d1 = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill_busco,
            delivered_mt=Decimal("2000.000"),
            receiving_location="ADI Nasugbu Site",
            carrier=self.logistics_partner,
        )
        self.po.refresh_from_db()
        self.assertEqual(self.po.total_delivered_mt, Decimal("2000.000"))
        self.assertEqual(self.po.remaining_mt, Decimal("8000.000"))
        self.assertEqual(self.po.po_status, "Partially Fulfilled")

        # 3. Second Shipment: 5,000 MT from CASA -> HTC Tank
        d2 = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill_casa,
            delivered_mt=Decimal("5000.000"),
            receiving_location="HTC Storage Tank",
            carrier=self.logistics_partner,
        )
        self.po.refresh_from_db()
        self.assertEqual(self.po.total_delivered_mt, Decimal("7000.000"))
        self.assertEqual(self.po.remaining_mt, Decimal("3000.000"))
        self.assertEqual(self.po.po_status, "Partially Fulfilled")

        # 4. Third Shipment: 3,000 MT from Balayan -> Balayan
        d3 = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill_balayan,
            delivered_mt=Decimal("3000.000"),
            receiving_location="Balayan Distillery",
            carrier=self.logistics_partner,
        )
        self.po.refresh_from_db()
        self.assertEqual(self.po.total_delivered_mt, Decimal("10000.000"))
        self.assertEqual(self.po.remaining_mt, Decimal("0.000"))
        self.assertEqual(self.po.po_status, "Completed")
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.status, TransactionCluster.Status.DELIVERED)

    def test_over_delivery_validation_prevented_in_model(self):
        from decimal import Decimal
        from django.core.exceptions import ValidationError
        from operations.models import DeliveryLedger

        # Attempt to deliver 12,000 MT when contracted is 10,000 MT
        with self.assertRaises(ValidationError):
            d = DeliveryLedger(
                purchase_order=self.po,
                supplier=self.mill_busco,
                delivered_mt=Decimal("12000.000"),
                receiving_location="ADI Nasugbu Site",
            )
            d.save()

    def test_delivery_api_post_success_and_over_delivery_prevention(self):
        import json

        # 1. Valid API Delivery via POST /deliveries
        payload1 = {
            "po_reference_number": "PO-ADI-10000",
            "supplier_id": self.mill_busco.id,
            "delivered_mt": "4000.000",
            "receiving_location": "ADI Nasugbu Site",
            "delivery_date": "2026-10-11",
            "notes": "First batch of 4000 MT",
        }
        res1 = self.client.post(
            "/deliveries",
            data=json.dumps(payload1),
            content_type="application/json",
        )
        self.assertEqual(res1.status_code, 201)
        res1_data = res1.json()
        self.assertTrue(res1_data["success"])
        self.assertEqual(res1_data["remaining_mt"], "6000.000")
        self.assertEqual(res1_data["po_status"], "Partially Fulfilled")

        # 2. Over-delivery attempt via POST /deliveries (7000 MT > 6000 MT remaining)
        payload2 = {
            "po_reference_number": "PO-ADI-10000",
            "supplier_id": self.mill_casa.id,
            "delivered_mt": "7000.000",
            "receiving_location": "HTC Storage Tank",
        }
        res2 = self.client.post(
            "/deliveries",
            data=json.dumps(payload2),
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 400)
        res2_data = res2.json()
        self.assertEqual(res2_data["error"], "OVER_DELIVERY_NOT_PERMITTED")
        self.assertEqual(res2_data["remaining_mt"], "6000.000")

    def test_po_status_api_endpoint(self):
        res = self.client.get(f"/deliveries/api/po-status/{self.po.po_reference_number}/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["po_reference_number"], "PO-ADI-10000")
        self.assertEqual(data["customer_name"], "Absolute Distillers Inc. (ADI)")
        self.assertEqual(data["total_contracted_mt"], "10000.000")
        self.assertEqual(data["remaining_mt"], "10000.000")
        self.assertEqual(data["po_status"], "Open")

    def test_multi_batch_logistics_rates_and_invoice_suggestion(self):
        from decimal import Decimal
        from operations.models import DeliveryLedger
        from operations.services.pricing import get_invoice_suggestion_data

        # Set cluster PO selling price
        self.po.selling_price = Decimal("35000.00")
        self.po.save()

        # Log batch 1: 2,000 MT with ₱450/MT trucking and ₱1,200/MT barging
        d1 = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill_busco,
            delivered_mt=Decimal("2000.000"),
            receiving_location="ADI Nasugbu Site",
            trucking_partner=self.logistics_partner,
            trucking_rate_per_mt=Decimal("450.00"),
            barge_partner=self.logistics_partner,
            barge_rate_per_mt=Decimal("1200.00"),
            vessel_or_barge_name="LCT LBC-1",
        )

        self.assertEqual(d1.trucking_cost, Decimal("900000.00"))   # 2,000 MT * ₱450
        self.assertEqual(d1.barge_cost, Decimal("2400000.00"))    # 2,000 MT * ₱1,200
        self.assertEqual(d1.total_freight_cost, Decimal("3300000.00"))

        # Check cluster logistics synchronization
        self.cluster.logistics.refresh_from_db()
        self.assertEqual(self.cluster.logistics.tracking_fees, Decimal("900000.00"))
        self.assertEqual(self.cluster.logistics.barge_fees, Decimal("2400000.00"))

        # Verify Invoice suggestion is based on delivered MT * selling price (2,000 MT * ₱35,000 = ₱70,000,000)
        sugg = get_invoice_suggestion_data(self.cluster)
        self.assertEqual(sugg["total_delivered_mt"], 2000.0)
        self.assertEqual(sugg["delivered_total"], 70000000.0)
        self.assertEqual(sugg["suggested_full"], 70000000.0)
        self.assertTrue(sugg["has_deliveries_to_bill"])

    def test_mro_ocr_workflow(self):
        import json
        from django.urls import reverse
        from django.core.files.uploadedfile import SimpleUploadedFile
        from masters.models import Planter
        from operations.models import MROExtractionJob, MolassesReleaseOrder

        planter = Planter.objects.create(name="ABSFI Planters Assoc.")
        self.client.force_login(self.admin)

        dummy_file = SimpleUploadedFile("MRO_Permit_88123.pdf", b"%PDF-1.4 dummy content", content_type="application/pdf")
        upload_url = reverse("operations:mro_upload_ocr", kwargs={"pk": self.cluster.pk})

        response = self.client.post(upload_url, {"file": dummy_file})
        self.assertEqual(response.status_code, 202)
        res_data = response.json()
        self.assertIn("job_id", res_data)
        job_id = res_data["job_id"]

        poll_url = reverse("operations:mro_ocr_job_status", kwargs={"job_id": job_id})
        poll_resp = self.client.get(poll_url)
        self.assertEqual(poll_resp.status_code, 200)
        poll_data = poll_resp.json()
        self.assertEqual(poll_data["status"], "completed")
        self.assertIn("data", poll_data)
        extracted = poll_data["data"]
        self.assertIn("fields", extracted)
        self.assertIn("mro_number", extracted["fields"])

        commit_url = reverse("operations:mro_commit_ocr", kwargs={"pk": self.cluster.pk})
        commit_payload = {
            "job_id": job_id,
            "mro_number": "MRO-88123",
            "sugar_mill_id": self.mill_busco.id,
            "planter_id": planter.id,
            "tons": 750.50,
            "release_date": "2026-09-28",
            "crop_year": "2024 - 2025",
            "brix_level": 85.00,
            "chai_specs": "CHAI 1.0",
            "notes": "Verified through OCR preview",
        }
        commit_resp = self.client.post(commit_url, data=json.dumps(commit_payload), content_type="application/json")
        self.assertEqual(commit_resp.status_code, 200)
        commit_data = commit_resp.json()
        self.assertTrue(commit_data["success"])

        mro = MolassesReleaseOrder.objects.get(mro_number="MRO-88123")
        self.assertEqual(mro.cluster, self.cluster)
        self.assertEqual(float(mro.tons), 750.50)
        self.assertEqual(mro.sugar_mill, self.mill_busco)

    def test_create_and_link_mro_manual_with_scanned_supporting_document(self):
        from operations.models import MolassesReleaseOrder
        from masters.models import Planter

        self.client.force_login(self.admin)
        manual_url = reverse("operations:create_and_link_mro_manual", kwargs={"pk": self.cluster.pk})

        dummy_scan = SimpleUploadedFile(
            "Permit_Scan_Manual_77201.pdf",
            b"%PDF-1.4 scanned supporting document content",
            content_type="application/pdf",
        )

        payload = {
            "sugar_mill": self.mill_busco.id,
            "sugar_mill_name": self.mill_busco.name,
            "mro_number": "MRO-77201",
            "crop_year": "2024 - 25",
            "planter_name": "Hacienda Test Planters",
            "tons": "620.45000",
            "release_date": "2026-10-12",
            "trader": "HEINDRICH",
            "cluster": str(self.cluster.pk),
            "notes": "Direct manual entry from PO view with scanned supporting doc",
            "mro_file": dummy_scan,
        }

        response = self.client.post(manual_url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verify MRO record created and linked to cluster
        mro = MolassesReleaseOrder.objects.get(mro_number="MRO-77201")
        self.assertEqual(mro.cluster, self.cluster)
        self.assertEqual(float(mro.tons), 620.45)
        self.assertEqual(mro.planter.name, "Hacienda Test Planters")
        self.assertEqual(mro.sugar_mill, self.mill_busco)

        # Verify cluster.mro_file was saved with supporting document
        self.cluster.refresh_from_db()
        self.assertTrue(bool(self.cluster.mro_file))
        self.assertIn("Permit_Scan_Manual_77201", self.cluster.mro_file.name)

        # Verify PO view displays the newly linked MRO and View Scan badge
        detail_url = reverse("operations:cluster_detail", kwargs={"pk": self.cluster.pk})
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "MRO-77201")
        self.assertContains(detail_resp, "View Scan")
        self.assertIn("mro_create_form", detail_resp.context)

    def test_multi_page_mro_batch_filing_workflow(self):
        import json
        import io
        import pypdf
        from django.urls import reverse
        from django.core.files.uploadedfile import SimpleUploadedFile
        from operations.models import MolassesReleaseOrder

        self.client.force_login(self.admin)

        # Build a valid 19-page PDF dummy in memory using pypdf
        writer = pypdf.PdfWriter()
        for _ in range(19):
            writer.add_blank_page(width=612, height=792)
        buf = io.BytesIO()
        writer.write(buf)
        multi_page_bytes = buf.getvalue()

        multi_file = SimpleUploadedFile(
            "MRO 27,000 MT ..pdf",
            multi_page_bytes,
            content_type="application/pdf",
        )

        upload_url = reverse("operations:mro_upload_ocr", kwargs={"pk": self.cluster.pk})
        upload_resp = self.client.post(upload_url, {"file": multi_file})
        self.assertEqual(upload_resp.status_code, 202)
        job_id = upload_resp.json()["job_id"]

        poll_url = reverse("operations:mro_ocr_job_status", kwargs={"job_id": job_id})
        poll_resp = self.client.get(poll_url)
        self.assertEqual(poll_resp.status_code, 200)
        data = poll_resp.json()["data"]

        self.assertTrue(data["is_multi_page"])
        self.assertEqual(data["total_pages"], 19)
        self.assertAlmostEqual(data["total_tons"], 27000.0, places=2)
        self.assertEqual(len(data["pages"]), 19)
        self.assertEqual(data["pages"][0]["mro_number"], "000713")
        self.assertEqual(data["pages"][18]["mro_number"], "000804")

        # Now test batch commit of all 19 permits
        commit_url = reverse("operations:mro_commit_ocr", kwargs={"pk": self.cluster.pk})
        commit_payload = {
            "job_id": job_id,
            "permits": data["pages"],
        }
        commit_resp = self.client.post(commit_url, data=json.dumps(commit_payload), content_type="application/json")
        self.assertEqual(commit_resp.status_code, 200)
        commit_data = commit_resp.json()
        self.assertTrue(commit_data["success"])
        self.assertTrue(commit_data["batch"])
        self.assertEqual(commit_data["count"], 19)
        self.assertAlmostEqual(commit_data["total_tons"], 27000.0, places=2)

        # Verify database state
        cluster_mros = MolassesReleaseOrder.objects.filter(cluster=self.cluster)
        self.assertEqual(cluster_mros.count(), 19)
        self.assertTrue(cluster_mros.filter(mro_number="000713").exists())
        self.assertTrue(cluster_mros.filter(mro_number="000804").exists())


class DeliveryLoggingValidationTests(TestCase):
    def setUp(self):
        from operations.models import PurchaseOrder

        self.user = User.objects.create_user(
            username="ops_tester",
            password="password123",
            role=User.Role.OPERATIONS,
            is_staff=True,
        )
        self.client_entity = Client.objects.create(name="San Miguel Foods")
        self.mill = SugarMill.objects.create(name="First Farmers Mill")
        self.cluster = TransactionCluster.objects.create(
            reference_code="HTC-DLV-TEST",
            client=self.client_entity,
            sugar_mill=self.mill,
        )
        self.po = PurchaseOrder.objects.create(
            cluster=self.cluster,
            po_reference_number="PO-TEST-DLV",
            volume_mt=100.0,
            unit_price=41000.0,
            customer=self.client_entity,
        )

    def test_future_arrival_date_is_valid_and_flagged(self):
        from datetime import timedelta
        from django.utils import timezone
        from operations.forms import DeliveryLedgerForm

        now = timezone.now()
        future_arrival = now + timedelta(days=7)

        form = DeliveryLedgerForm(
            data={
                "purchase_order": self.po.pk,
                "supplier": self.mill.pk,
                "delivery_date": now.date().isoformat(),
                "delivered_mt": 25.5,
                "dispatched_at": now.strftime("%Y-%m-%dT%H:%M"),
                "received_at": future_arrival.strftime("%Y-%m-%dT%H:%M"),
                "receiving_location": "Bacolod Terminal Pier 2",
                "trucking_rate_per_mt": 450.0,
                "barge_rate_per_mt": 200.0,
                "trucking_cost": 11475.0,
                "barge_cost": 5100.0,
                "delivery_status": "in_transit",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        delivery = form.save(commit=False)
        delivery._audit_user = self.user
        delivery.save()
        self.assertTrue(delivery.is_future_arrival)

    def test_received_before_dispatched_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        from operations.forms import DeliveryLedgerForm

        now = timezone.now()
        past_arrival = now - timedelta(hours=4)

        form = DeliveryLedgerForm(
            data={
                "purchase_order": self.po.pk,
                "supplier": self.mill.pk,
                "delivery_date": now.date().isoformat(),
                "delivered_mt": 20.0,
                "dispatched_at": now.strftime("%Y-%m-%dT%H:%M"),
                "received_at": past_arrival.strftime("%Y-%m-%dT%H:%M"),
                "receiving_location": "Bacolod Terminal",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("received_at", form.errors)
        self.assertIn("cannot be earlier than", form.errors["received_at"][0])

    def test_negative_rates_rejected(self):
        from django.utils import timezone
        from operations.forms import DeliveryLedgerForm

        now = timezone.now()
        form = DeliveryLedgerForm(
            data={
                "purchase_order": self.po.pk,
                "supplier": self.mill.pk,
                "delivery_date": now.date().isoformat(),
                "delivered_mt": 20.0,
                "dispatched_at": now.strftime("%Y-%m-%dT%H:%M"),
                "receiving_location": "Bacolod Terminal",
                "trucking_rate_per_mt": -100.0,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("trucking_rate_per_mt", form.errors)

    def test_exceeding_po_balance_rejected(self):
        from django.utils import timezone
        from operations.forms import DeliveryLedgerForm

        now = timezone.now()
        form = DeliveryLedgerForm(
            data={
                "purchase_order": self.po.pk,
                "supplier": self.mill.pk,
                "delivery_date": now.date().isoformat(),
                "delivered_mt": 999.0,  # PO is only 100 MT
                "dispatched_at": now.strftime("%Y-%m-%dT%H:%M"),
                "receiving_location": "Bacolod Terminal",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("delivered_mt", form.errors)

    def test_update_delivery_arrival_view_success(self):
        from django.utils import timezone
        from datetime import timedelta
        from django.urls import reverse
        from operations.models import DeliveryLedger

        now = timezone.localtime()
        delivery = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill,
            delivered_mt=30.0,
            receiving_location="Bacolod Terminal",
            delivery_date=now.date(),
            dispatched_at=now,
        )
        self.assertIsNone(delivery.received_at)

        self.client.force_login(self.user)
        arrival_time = now + timedelta(hours=5)
        url = reverse("operations:update_delivery_arrival", args=[delivery.delivery_id])
        resp = self.client.post(
            url,
            {"received_at": arrival_time.strftime("%Y-%m-%dT%H:%M")},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        delivery.refresh_from_db()
        self.assertIsNotNone(delivery.received_at)

    def test_update_delivery_arrival_view_earlier_than_dispatch_rejected(self):
        from django.utils import timezone
        from datetime import timedelta
        from django.urls import reverse
        from operations.models import DeliveryLedger

        now = timezone.localtime()
        delivery = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill,
            delivered_mt=30.0,
            receiving_location="Bacolod Terminal",
            delivery_date=now.date(),
            dispatched_at=now,
        )

        self.client.force_login(self.user)
        invalid_arrival = now - timedelta(hours=2)
        url = reverse("operations:update_delivery_arrival", args=[delivery.delivery_id])
        resp = self.client.post(
            url,
            {"received_at": invalid_arrival.strftime("%Y-%m-%dT%H:%M")},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data["error"], "INVALID_ARRIVAL_DATE")


class CopilotFinancialLocalORMTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="copilot_admin",
            password="password123",
            role=User.Role.ADMINISTRATOR,
            is_staff=True,
        )

    def test_evaluate_financial_query_offline_orm(self):
        from operations.services.copilot_services import evaluate_copilot_query

        res = evaluate_copilot_query(self.admin, "explain weekly profit and revenue breakdown")
        self.assertIn("answer_html", res)
        self.assertIn("Financial Performance &amp; Profit Breakdown", res["answer_html"])
        self.assertIn("Weekly Cadence", res["answer_html"])
        self.assertIn("Local ORM Explanation", res["answer_html"])
        self.assertTrue(len(res.get("suggestions", [])) > 0)











