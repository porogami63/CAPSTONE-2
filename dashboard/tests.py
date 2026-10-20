from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from masters.models import Client, Planter, SugarMill, LogisticsPartner
from operations.models import TransactionCluster, PurchaseOrder, MolassesReleaseOrder, DeliveryLedger
from dashboard.services.documents import build_document_registry

User = get_user_model()


class DashboardRoleInterfaceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_user", password="password123", role=User.Role.ADMINISTRATOR)
        self.ops = User.objects.create_user(username="ops_user", password="password123", role=User.Role.OPERATIONS_MANAGEMENT)
        self.ops_role = User.objects.create_user(username="ops_role_user", password="password123", role=User.Role.OPERATIONS)
        self.fin = User.objects.create_user(username="fin_user", password="password123", role=User.Role.FINANCE)
        self.inv = User.objects.create_user(username="inv_user", password="password123", role=User.Role.INVOICING)

    def test_admin_dashboard_home(self):
        self.client.login(username="admin_user", password="password123")
        res = self.client.get("/", follow=True)
        self.assertEqual(res.status_code, 200)

    def test_operations_manager_dashboard_home(self):
        self.client.login(username="ops_user", password="password123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["user_role"], User.Role.OPERATIONS_MANAGEMENT)
        self.assertIn("active_shipments_count", res.context)

    def test_operations_role_dashboard_home(self):
        self.client.login(username="ops_role_user", password="password123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["user_role"], User.Role.OPERATIONS)
        self.assertIn("active_shipments_count", res.context)

    def test_financial_table_cadence_and_copilot_context(self):
        client = Client.objects.create(name="San Miguel Corp")
        mill = SugarMill.objects.create(name="Central Azucarera")
        cluster = TransactionCluster.objects.create(
            reference_code="PO-CADENCE-01",
            client=client,
            sugar_mill=mill,
            status=TransactionCluster.Status.ACTIVE,
        )
        PurchaseOrder.objects.create(
            cluster=cluster,
            po_reference_number="PO-CADENCE-01",
            volume_mt=Decimal("100.000"),
            unit_price=Decimal("41000.00"),
            customer=client,
        )

        self.client.login(username="ops_user", password="password123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("financial_intervals", res.context)
        intervals = res.context["financial_intervals"]
        self.assertIn("weekly", intervals)
        self.assertIn("monthly", intervals)
        self.assertIn("yearly", intervals)
        for cadence in ["weekly", "monthly", "yearly"]:
            self.assertIn("title", intervals[cadence])
            self.assertIn("labels", intervals[cadence])
            self.assertIn("table", intervals[cadence])
            self.assertIn("copilot_text", intervals[cadence])
        self.assertContains(res, 'id="financialTableContainer"')
        self.assertContains(res, 'id="financialCopilotFootnote"')

    def test_finance_dashboard_home(self):
        self.client.login(username="fin_user", password="password123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["user_role"], User.Role.FINANCE)
        self.assertIn("vouchers_count", res.context)

    def test_invoicing_dashboard_home(self):
        self.client.login(username="inv_user", password="password123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["user_role"], User.Role.INVOICING)
        self.assertIn("pending_invoices_list", res.context)


class DocumentStorageAndDistinctionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="doc_manager",
            password="password123",
            role=User.Role.ADMINISTRATOR,
            is_staff=True,
        )
        self.client_obj = Client.objects.create(name="Emperador Distillers Inc.")
        self.mill = SugarMill.objects.create(name="BUSCO Sugar Milling Co.")
        self.carrier = LogisticsPartner.objects.create(name="Solid Shipping Lines")
        self.planter1 = Planter.objects.create(name="ABSFI Planters Assoc", code="ABSFI")
        self.planter2 = Planter.objects.create(name="SGABI Planters Coop", code="SGABI")

        # Create PO cluster with 1 single uploaded scanned MRO PDF
        dummy_pdf = SimpleUploadedFile("MRO_Scan_PO20261011-003.pdf", b"%PDF-1.4 dummy consolidated mro file content", content_type="application/pdf")
        self.cluster = TransactionCluster.objects.create(
            reference_code="PO20261011-003",
            client=self.client_obj,
            sugar_mill=self.mill,
            mro_file=dummy_pdf,
            status=TransactionCluster.Status.ACTIVE,
        )

        self.po = PurchaseOrder.objects.create(
            cluster=self.cluster,
            po_reference_number="PO20261011-003",
            volume_mt=Decimal("5000.000"),
            total_contracted_mt=Decimal("5000.000"),
            unit_price=Decimal("32000.00"),
            selling_price=Decimal("38500.00"),
            po_status=PurchaseOrder.POStatus.PARTIALLY_FULFILLED,
            customer=self.client_obj,
        )

        # Create multiple MRO entries under this cluster (all sharing the 1 uploaded file)
        self.mro1 = MolassesReleaseOrder.objects.create(
            mro_number="MRO-701",
            cluster=self.cluster,
            planter=self.planter1,
            sugar_mill=self.mill,
            tons=Decimal("2000.000"),
            release_date=date(2026, 10, 11),
            crop_year="2024 - 2025",
        )
        self.mro2 = MolassesReleaseOrder.objects.create(
            mro_number="MRO-702",
            cluster=self.cluster,
            planter=self.planter2,
            sugar_mill=self.mill,
            tons=Decimal("3000.000"),
            release_date=date(2026, 10, 11),
            crop_year="2024 - 2025",
        )

        # Create multiple batches of deliveries fulfilling against these MRO entries
        self.deliv1 = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill,
            mro_permit=self.mro1,
            delivered_mt=Decimal("1500.000"),
            receiving_location="Main Silo",
            delivery_date=date(2026, 10, 12),
            dr_number="DR-001",
        )
        self.deliv2 = DeliveryLedger.objects.create(
            purchase_order=self.po,
            supplier=self.mill,
            mro_permit=self.mro2,
            delivered_mt=Decimal("2000.000"),
            receiving_location="Main Silo",
            delivery_date=date(2026, 10, 14),
            dr_number="DR-002",
        )

    def test_multiple_mros_share_single_scanned_document(self):
        """Verifies that multiple MRO entries share 1 single document without storage duplication."""
        self.assertTrue(self.mro1.has_scanned_document)
        self.assertTrue(self.mro2.has_scanned_document)
        self.assertTrue(self.mro1.is_shared_document)
        self.assertTrue(self.mro2.is_shared_document)

        # Both entries point to the EXACT same physical file
        self.assertEqual(self.mro1.scanned_document.name, self.cluster.mro_file.name)
        self.assertEqual(self.mro2.scanned_document.name, self.cluster.mro_file.name)

        # Delivery batches access the shared scanned MRO document
        self.assertEqual(self.deliv1.scanned_mro_document.name, self.cluster.mro_file.name)
        self.assertEqual(self.deliv2.scanned_mro_document.name, self.cluster.mro_file.name)

    def test_document_registry_distinguishes_generated_vs_uploaded(self):
        """Tests that document registry separates official generated PDFs from user-uploaded scans."""
        reg = build_document_registry()

        # Check category origins
        self.assertEqual(reg["categories"]["contracts"]["origin"], "generated")
        self.assertEqual(reg["categories"]["purchase_orders"]["origin"], "generated")
        self.assertEqual(reg["categories"]["sales_invoices"]["origin"], "generated")
        self.assertEqual(reg["categories"]["cash_vouchers"]["origin"], "generated")

        self.assertEqual(reg["categories"]["release_orders"]["origin"], "uploaded")
        self.assertEqual(reg["categories"]["delivery_receipts"]["origin"], "uploaded")
        self.assertNotIn("loan_settlements", reg["categories"])

        # Counts
        self.assertGreaterEqual(reg["total_uploaded_count"], 1)
        self.assertGreaterEqual(reg["total_generated_count"], 2)

    def test_consolidated_mro_document_metadata_and_search(self):
        """Tests that 1 document covering multiple MRO entries produces consolidated metadata and can be searched by MRO #."""
        reg = build_document_registry("PO20261011-003")
        mro_items = reg["categories"]["release_orders"]["items"]
        self.assertEqual(len(mro_items), 1)

        doc = mro_items[0]
        self.assertEqual(doc["origin"], "uploaded")
        self.assertTrue(doc["is_consolidated"])
        self.assertEqual(doc["mro_count"], 2)
        self.assertIn("MRO-701", doc["mro_numbers"])
        self.assertIn("MRO-702", doc["mro_numbers"])
        self.assertEqual(doc["total_tons"], 5000.0)
        self.assertEqual(doc["deliveries_count"], 2)
        self.assertIn("Consolidated Document", doc["coverage_summary"])

        # Search specifically by individual MRO permit number
        reg_by_mro = build_document_registry("MRO-702")
        found_mros = reg_by_mro["categories"]["release_orders"]["items"]
        self.assertEqual(len(found_mros), 1)
        self.assertEqual(found_mros[0]["ref"], "PO20261011-003")

    def test_documents_page_renders_cleanly(self):
        """Tests that documents management view returns 200 and renders origin filters and consolidated details."""
        self.client.login(username="doc_manager", password="password123")
        url = reverse("dashboard:documents")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Filter by Origin:")
        self.assertContains(res, "Uploaded by User")
        self.assertContains(res, "System Generated")
        self.assertContains(res, "Consolidated Scan")

    def test_po_workspace_renders_documents_section(self):
        """Tests that PO Financial Workspace displays the supporting operational documents section."""
        self.client.login(username="doc_manager", password="password123")
        url = reverse("finance:po_workspace", args=[self.cluster.pk])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "PO Documents &amp; Supporting Scans")
        self.assertContains(res, "User-Uploaded Supporting Documents")
        self.assertContains(res, "Consolidated Document:")
        self.assertContains(res, "MRO-701")
        self.assertContains(res, "MRO-702")
