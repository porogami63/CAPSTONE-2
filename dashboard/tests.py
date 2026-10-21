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

        # Create second cluster with an issued Invoice (date field) alongside cluster created_at (datetime field)
        from finance.models import Invoice
        cluster2 = TransactionCluster.objects.create(
            reference_code="PO-CADENCE-02",
            client=client,
            sugar_mill=mill,
            status=TransactionCluster.Status.ACTIVE,
        )
        PurchaseOrder.objects.create(
            cluster=cluster2,
            po_reference_number="PO-CADENCE-02",
            volume_mt=Decimal("50.000"),
            unit_price=Decimal("42000.00"),
            customer=client,
        )
        Invoice.objects.create(
            cluster=cluster2,
            invoice_number="INV-CAD-02",
            amount=Decimal("2100000.00"),
            issued_at=date.today(),
            status=Invoice.Status.ISSUED,
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

    def test_documents_page_view_switcher_and_table_view(self):
        """Tests that the View Switcher toggles (Grid vs. Table View) and Master Table are rendered."""
        self.client.login(username="doc_manager", password="password123")
        url = reverse("dashboard:documents")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # View Switcher buttons
        self.assertContains(res, 'id="btnViewGrid"')
        self.assertContains(res, 'id="btnViewTable"')

        # Master Table container and table elements
        self.assertContains(res, 'id="documentsTableViewContainer"')
        self.assertContains(res, 'id="documentsMasterTable"')
        self.assertContains(res, 'id="documentsMasterTableBody"')

        # Table columns
        self.assertContains(res, "Document Name &amp; Ref")
        self.assertContains(res, "Linked Entities")
        self.assertContains(res, "File Size")

    def test_documents_batch_operations_and_action_bar(self):
        """Tests that Batch Operations controls, checkboxes, and floating batch action bar are present."""
        self.client.login(username="doc_manager", password="password123")
        url = reverse("dashboard:documents")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Selection checkboxes
        self.assertContains(res, 'id="globalSelectAllToggle"')
        self.assertContains(res, 'cat-select-all')
        self.assertContains(res, 'doc-row-check')

        # Floating batch action bar and primary actions
        self.assertContains(res, 'id="floatingBatchActionBar"')
        self.assertContains(res, 'id="batchSelectedCounter"')
        self.assertContains(res, 'id="btnBatchDownloadZip"')
        self.assertContains(res, "Download Selected (ZIP)")
        self.assertContains(res, 'id="btnBatchExportCsv"')
        self.assertContains(res, "Export Manifest (CSV)")
        self.assertContains(res, 'id="btnBatchMarkReviewed"')
        self.assertContains(res, "Mark as Reviewed")

    def test_sub_entry_badge_collapsing_when_exceeding_three(self):
        """Tests that cards with >3 sub-entry badges collapse extra tags and render +N more entries."""
        # Create 2 more MROs to bring total to 4 (exceeding max limit of 3)
        MolassesReleaseOrder.objects.create(
            mro_number="MRO-703",
            cluster=self.cluster,
            planter=self.planter1,
            sugar_mill=self.mill,
            tons=Decimal("500.000"),
            release_date=date(2026, 10, 11),
            crop_year="2024 - 2025",
        )
        MolassesReleaseOrder.objects.create(
            mro_number="MRO-704",
            cluster=self.cluster,
            planter=self.planter2,
            sugar_mill=self.mill,
            tons=Decimal("250.000"),
            release_date=date(2026, 10, 11),
            crop_year="2024 - 2025",
        )

        self.client.login(username="doc_manager", password="password123")
        url = reverse("dashboard:documents")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Collapsible component is rendered
        self.assertContains(res, "collapsible-entry-badges")
        # Counter badge for remaining entries (4 - 3 = 1 more entry)
        self.assertContains(res, "+1 more entries")
        # Collapsible drawer target
        self.assertContains(res, "mroCollapse-release_orders-")

    def test_standardized_actions_and_grid_equalization(self):
        """Tests that cards use equalized height and rows feature standardized action buttons."""
        self.client.login(username="doc_manager", password="password123")
        url = reverse("dashboard:documents")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Grid card equalization class
        self.assertContains(res, "doc-equalized-card")
        self.assertContains(res, "doc-category-scroll")

        # Standardized action buttons
        self.assertContains(res, "Preview")
        self.assertContains(res, "Download PDF")
        self.assertContains(res, "Request Scan")

