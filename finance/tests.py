from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from masters.models import Client, LogisticsPartner, SugarMill
from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster

from .models import CapitalLoan, FinancialReconciliation, Invoice, PaymentExpenseMatch


class FinanceNavigationTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="finance",
			password="testpass123",
			role=User.Role.FINANCE,
			is_staff=True,
		)

	def test_invoice_list_renders(self):
		client = Client.objects.create(name="Acme Foods")
		mill = SugarMill.objects.create(name="North Mill")
		cluster = TransactionCluster.objects.create(reference_code="PO-001", client=client, sugar_mill=mill)
		Invoice.objects.create(
			cluster=cluster,
			invoice_number="INV-001",
			amount=150000,
			issued_at=date.today(),
			status=Invoice.Status.ISSUED,
		)

		self.client.login(username="finance", password="testpass123")
		response = self.client.get(reverse("finance:invoice_list"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Invoicing")
		self.assertContains(response, "INV-001")

	def test_loan_list_renders_with_aggregates(self):
		client = Client.objects.create(name="Acme Foods")
		mill = SugarMill.objects.create(name="North Mill")
		partner = LogisticsPartner.objects.create(name="Harbor Logistics")
		cluster = TransactionCluster.objects.create(reference_code="PO-002", client=client, sugar_mill=mill)
		PurchaseOrder.objects.create(cluster=cluster, volume_mt=100, unit_price=42000, terms="Net 30")
		LogisticsLedger.objects.create(cluster=cluster, partner=partner, loaded_volume_mt=100, received_volume_mt=99.5)
		CapitalLoan.objects.create(
			cluster=cluster,
			bank_name="BDO",
			principal=500000,
			interest_rate_annual=12,
			start_date=date.today() - timedelta(days=30),
			due_date=date.today() + timedelta(days=30),
		)
		PaymentExpenseMatch.objects.create(
			reconciliation=FinancialReconciliation.objects.create(cluster=cluster),
			payment_reference="PAY-001",
			expense_type=PaymentExpenseMatch.ExpenseType.LOGISTICS_DEPOSIT,
			amount=25000,
		)

		self.client.login(username="finance", password="testpass123")
		response = self.client.get(reverse("finance:loan_list"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "BDO")


class LoanVerificationTests(TestCase):
	def setUp(self):
		self.finance_user = User.objects.create_user(
			username="finance_user",
			password="password123",
			role=User.Role.FINANCE,
		)
		self.ops_manager = User.objects.create_user(
			username="ops_manager",
			password="password123",
			role=User.Role.OPERATIONS_MANAGEMENT,
		)
		self.admin_user = User.objects.create_user(
			username="admin_user",
			password="password123",
			role=User.Role.ADMINISTRATOR,
		)
		self.client_entity = Client.objects.create(name="Metro Supermarkets")
		self.mill = SugarMill.objects.create(name="Central Mill")
		self.cluster = TransactionCluster.objects.create(
			reference_code="HTC-LOAN-001",
			client=self.client_entity,
			sugar_mill=self.mill,
		)

	def test_loan_creation_starts_as_pending_creation(self):
		loan = CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="Security Bank",
			principal=1000000,
			interest_rate_annual=10,
			start_date=date.today(),
			due_date=date.today() + timedelta(days=60),
		)
		self.assertEqual(loan.status, CapitalLoan.Status.PENDING_CREATION)

	def test_admin_approves_loan_creation(self):
		loan = CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="Security Bank",
			principal=1000000,
			interest_rate_annual=10,
			start_date=date.today(),
			due_date=date.today() + timedelta(days=60),
		)
		self.client.login(username="admin_user", password="password123")
		response = self.client.post(
			reverse("finance:verify_loan_creation", kwargs={"pk": loan.pk}),
			{"action": "approve", "verification_notes": "Contract verified, approval granted."},
		)
		self.assertRedirects(response, reverse("finance:loan_list"))
		loan.refresh_from_db()
		self.assertEqual(loan.status, CapitalLoan.Status.ACTIVE)
		self.assertEqual(loan.verified_by, self.admin_user)
		self.assertEqual(loan.verification_notes, "Contract verified, approval granted.")

	def test_ops_manager_cannot_verify_loan_creation(self):
		loan = CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="Security Bank",
			principal=1000000,
			interest_rate_annual=10,
			start_date=date.today(),
			due_date=date.today() + timedelta(days=60),
		)
		self.client.login(username="ops_manager", password="password123")
		response = self.client.post(
			reverse("finance:verify_loan_creation", kwargs={"pk": loan.pk}),
			{"action": "approve"},
		)
		self.assertEqual(response.status_code, 403)
		loan.refresh_from_db()
		self.assertEqual(loan.status, CapitalLoan.Status.PENDING_CREATION)

	def test_ops_manager_cannot_access_finance_loan_list(self):
		self.client.login(username="ops_manager", password="password123")
		response = self.client.get(reverse("finance:loan_list"))
		self.assertEqual(response.status_code, 403)

	def test_ops_manager_cannot_access_reconciliation(self):
		self.client.login(username="ops_manager", password="password123")
		response = self.client.get(reverse("finance:reconciliation", kwargs={"pk": self.cluster.pk}))
		self.assertEqual(response.status_code, 403)

	def test_finance_submits_loan_settlement(self):
		loan = CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="BPI",
			principal=500000,
			interest_rate_annual=8,
			start_date=date.today() - timedelta(days=30),
			due_date=date.today() + timedelta(days=30),
			status=CapitalLoan.Status.ACTIVE,
		)
		self.client.login(username="finance_user", password="password123")
		response = self.client.post(
			reverse("finance:settle_loan", kwargs={"pk": loan.pk}),
			{"settlement_receipt_number": "BRA-99120", "settlement_date": str(date.today())},
		)
		self.assertRedirects(response, reverse("finance:loan_list"))
		loan.refresh_from_db()
		self.assertEqual(loan.status, CapitalLoan.Status.PENDING_SETTLEMENT)
		self.assertEqual(loan.settlement_receipt_number, "BRA-99120")

	def test_admin_approves_loan_settlement(self):
		loan = CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="BPI",
			principal=500000,
			interest_rate_annual=8,
			start_date=date.today() - timedelta(days=30),
			due_date=date.today() + timedelta(days=30),
			status=CapitalLoan.Status.PENDING_SETTLEMENT,
			settlement_receipt_number="BRA-99120",
		)
		self.client.login(username="admin_user", password="password123")
		response = self.client.post(
			reverse("finance:verify_loan_settlement", kwargs={"pk": loan.pk}),
			{"action": "approve", "verification_notes": "Official release advice verified."},
		)
		self.assertRedirects(response, reverse("finance:loan_list"))
		loan.refresh_from_db()
		self.assertEqual(loan.status, CapitalLoan.Status.CLOSED)
		self.assertEqual(loan.verified_by, self.admin_user)

	def test_finance_user_cannot_verify_loan(self):
		loan = CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="Metrobank",
			principal=750000,
			interest_rate_annual=9,
			start_date=date.today(),
			due_date=date.today() + timedelta(days=45),
			status=CapitalLoan.Status.PENDING_CREATION,
		)
		self.client.login(username="finance_user", password="password123")
		response = self.client.post(
			reverse("finance:verify_loan_creation", kwargs={"pk": loan.pk}),
			{"action": "approve"},
		)
	def test_finance_creates_standalone_loan_linked_to_transaction(self):
		self.client.login(username="finance_user", password="password123")
		response = self.client.post(
			reverse("finance:loan_list"),
			{
				"cluster": self.cluster.pk,
				"bank_name": "Metrobank",
				"principal": "2500000.00",
				"interest_rate_annual": "11.5000",
				"start_date": str(date.today()),
				"due_date": str(date.today() + timedelta(days=60)),
			},
		)
		self.assertRedirects(response, reverse("finance:loan_list"))
		loan = CapitalLoan.objects.filter(cluster=self.cluster, bank_name="Metrobank").first()
		self.assertIsNotNone(loan)
		self.assertEqual(loan.principal, 2500000)
		self.assertEqual(loan.status, CapitalLoan.Status.PENDING_CREATION)


class SuggestiveInvoicePricingTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="finance_user",
			password="password123",
			role=User.Role.FINANCE,
		)
		self.client.login(username="finance_user", password="password123")
		self.client_obj = Client.objects.create(name="San Miguel Foods")
		self.mill = SugarMill.objects.create(name="Central Azucarera de Tarlac")
		self.cluster = TransactionCluster.objects.create(reference_code="PO-TEST-100", client=self.client_obj, sugar_mill=self.mill)
		self.po = PurchaseOrder.objects.create(
			cluster=self.cluster,
			volume_mt=100.0,
			unit_price=35000.0,
			selling_price=40000.0,
		)
		self.logistics = LogisticsLedger.objects.create(
			cluster=self.cluster,
			loaded_volume_mt=100.0,
			received_volume_mt=98.0,
		)

	def test_get_invoice_suggestion_data_without_previous_invoices(self):
		from operations.services.pricing import get_invoice_suggestion_data
		data = get_invoice_suggestion_data(self.cluster)
		self.assertEqual(data["selling_price"], 40000.0)
		self.assertEqual(data["contract_volume"], 100.0)
		self.assertEqual(data["contract_total"], 4000000.0)
		self.assertEqual(data["already_invoiced"], 0.0)
		self.assertEqual(data["remaining_balance"], 4000000.0)
		self.assertEqual(data["suggested_full"], 4000000.0)
		self.assertEqual(data["suggested_50_pct"], 2000000.0)
		self.assertEqual(data["received_total"], 3920000.0)

	def test_get_invoice_suggestion_data_with_partial_invoice(self):
		from operations.services.pricing import get_invoice_suggestion_data
		Invoice.objects.create(
			cluster=self.cluster,
			invoice_number="SI-PARTIAL-001",
			amount=1500000.0,
			issued_at=date.today(),
			status=Invoice.Status.ISSUED,
		)
		data = get_invoice_suggestion_data(self.cluster)
		self.assertEqual(data["already_invoiced"], 1500000.0)
		self.assertEqual(data["invoices_count"], 1)
		self.assertEqual(data["remaining_balance"], 2500000.0)
		self.assertEqual(data["suggested_full"], 2500000.0)
		self.assertEqual(data["suggested_50_pct"], 1250000.0)

	def test_invoice_list_view_renders_suggestive_tooltip(self):
		res = self.client.get(reverse("finance:invoice_list"))
		self.assertEqual(res.status_code, 200)
		self.assertIn("cluster_suggestions_json", res.context)
		self.assertContains(res, "standaloneAmountWrap")

	def test_cluster_detail_view_renders_suggestive_tooltip(self):
		res = self.client.get(reverse("operations:cluster_detail", kwargs={"pk": self.cluster.pk}))
		self.assertEqual(res.status_code, 200)
		self.assertIn("invoice_suggestion_data", res.context)
		self.assertContains(res, "Suggested Contract Balance")


class LoanValidationTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="finance_officer",
			password="password123",
			role=User.Role.FINANCE,
		)
		self.client.login(username="finance_officer", password="password123")
		self.client_obj = Client.objects.create(name="Universal Robina")
		self.mill = SugarMill.objects.create(name="First Sugar Mill")
		self.cluster = TransactionCluster.objects.create(reference_code="PO-VAL-001", client=self.client_obj, sugar_mill=self.mill)
		self.po = PurchaseOrder.objects.create(
			cluster=self.cluster,
			volume_mt=100.0,
			unit_price=10000.0, # Sourcing = 1,000,000
		)
		self.logistics = LogisticsLedger.objects.create(
			cluster=self.cluster,
			loaded_volume_mt=100.0,
			tracking_fees=100000.0, # Trucking = 100,000 (50% = 50,000)
			barge_fees=200000.0, # Freight/Barging = 200,000 (50% = 100,000)
		)

	def test_loan_requirement_data(self):
		from operations.services.pricing import loan_requirement_data
		req = loan_requirement_data(self.cluster)
		self.assertEqual(req["sourcing"], 1000000.0)
		self.assertEqual(req["trucking_down_payment"], 50000.0)
		self.assertEqual(req["freight_down_payment"], 100000.0)
		# Required = 1,000,000 + 50,000 + 100,000 = 1,150,000
		self.assertEqual(req["required"], 1150000.0)

	def test_loan_creation_blocks_when_already_fully_funded(self):
		# First create a fully funding loan
		CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="BDO",
			principal=Decimal("1150000.00"),
			interest_rate_annual=Decimal("10.00"),
			start_date=date.today(),
			due_date=date.today() + timedelta(days=60),
			status=CapitalLoan.Status.ACTIVE,
		)
		# Now try submitting another loan for the same cluster
		res = self.client.post(
			reverse("finance:loan_list"),
			{
				"cluster": self.cluster.pk,
				"bank_name": "BDO Extra",
				"principal": "500000.00",
				"interest_rate_annual": "10.00",
				"start_date": str(date.today()),
				"due_date": str(date.today() + timedelta(days=60)),
			},
		)
		self.assertEqual(res.status_code, 200) # Re-renders page with errors because cluster is excluded from dropdown choices
		self.assertContains(res, "Select a valid choice. That choice is not one of the available choices.")
		self.assertFalse(CapitalLoan.objects.filter(cluster=self.cluster, bank_name="BDO Extra").exists())

	def test_loan_creation_accepts_valid_principal(self):
		res = self.client.post(
			reverse("finance:loan_list"),
			{
				"cluster": self.cluster.pk,
				"bank_name": "BPI",
				"principal": "1200000.00",
				"interest_rate_annual": "10.00",
				"start_date": str(date.today()),
				"due_date": str(date.today() + timedelta(days=60)),
			},
		)
		self.assertRedirects(res, reverse("finance:loan_list"))
		self.assertTrue(CapitalLoan.objects.filter(cluster=self.cluster, bank_name="BPI").exists())

	def test_due_date_must_be_after_start_date(self):
		res = self.client.post(
			reverse("finance:loan_list"),
			{
				"cluster": self.cluster.pk,
				"bank_name": "Metrobank",
				"principal": "1500000.00",
				"interest_rate_annual": "10.00",
				"start_date": str(date.today()),
				"due_date": str(date.today() - timedelta(days=5)), # Invalid
			},
		)
		self.assertEqual(res.status_code, 200)
		self.assertContains(res, "Facility due date must be later than the loan start date")


class POFocusedFinanceWorkspaceTests(TestCase):
	def setUp(self):
		self.finance_user = User.objects.create_user(
			username="finance_pro",
			password="password123",
			role=User.Role.FINANCE,
		)
		self.client_entity = Client.objects.create(name="San Miguel Foods")
		self.mill = SugarMill.objects.create(name="URC Sugar Mill")
		self.cluster = TransactionCluster.objects.create(
			reference_code="PO-SMF-2026",
			client=self.client_entity,
			sugar_mill=self.mill,
		)
		self.po = PurchaseOrder.objects.create(
			cluster=self.cluster,
			po_reference_number="PO-SMF-2026",
			volume_mt=200,
			unit_price=42000,
			selling_price=46000,
		)
		self.client.login(username="finance_pro", password="password123")

	def test_loan_list_focus_by_po_param(self):
		res = self.client.get(reverse("finance:loan_list") + f"?po={self.cluster.reference_code}")
		self.assertEqual(res.status_code, 302)
		self.assertRedirects(res, reverse("finance:po_workspace", args=[self.cluster.pk]))

	def test_po_workspace_dedicated_view(self):
		res = self.client.get(reverse("finance:po_workspace", args=[self.cluster.pk]))
		self.assertEqual(res.status_code, 200)
		self.assertEqual(res.context["focused_cluster"], self.cluster)
		self.assertContains(res, "Focused PO Workspace")
		self.assertContains(res, "Capital Financing Requirements")
		self.assertContains(res, "Expense Outlays &amp; Matchmaking")
		self.assertContains(res, "PO-SMF-2026")
		self.assertContains(res, "Return to Loans Portfolio")
		self.assertContains(res, "View Operations PO")

	def test_po_portfolio_rendered(self):
		res = self.client.get(reverse("finance:loan_list"))
		self.assertEqual(res.status_code, 200)
		self.assertIn("po_portfolio", res.context)
		portfolio_refs = [p["po_ref"] for p in res.context["po_portfolio"]]
		self.assertIn("PO-SMF-2026", portfolio_refs)
		self.assertContains(res, "PO Financial &amp; Expense Matchmaking Portfolio")
		self.assertContains(res, "PO-SMF-2026")
		self.assertContains(res, "Focus Workspace")
		self.assertContains(res, "Operations PO")

	def test_direct_match_and_redirect_next(self):
		target_next = reverse("finance:po_workspace", args=[self.cluster.pk])
		res = self.client.post(
			reverse("finance:add_match", args=[self.cluster.pk]),
			{
				"payment_reference": "OR-SMF-001",
				"expense_type": "sourcing",
				"amount": "250000.00",
				"notes": "Advance payment for sugar mill",
				"next": target_next,
			},
		)
		self.assertRedirects(res, target_next)
		self.assertTrue(PaymentExpenseMatch.objects.filter(payment_reference="OR-SMF-001").exists())

	def test_over_target_warning_and_glow_red(self):
		target_next = reverse("finance:po_workspace", args=[self.cluster.pk])
		# Total required is 200 * 42000 = 8,400,000. Add match of 9,000,000
		res = self.client.post(
			reverse("finance:add_match", args=[self.cluster.pk]),
			{
				"payment_reference": "OR-OVER-001",
				"expense_type": "sourcing",
				"amount": "9000000.00",
				"notes": "Over budget outlay test",
				"next": target_next,
			},
			follow=True,
		)
		self.assertEqual(res.status_code, 200)
		self.assertTrue(res.context["is_over_target"])
		self.assertContains(res, "glow-danger-box")
		self.assertContains(res, "Reconciliation Target Exceeded!")

	def test_cluster_detail_has_link_and_no_inline_loan_form(self):
		res = self.client.get(reverse("operations:cluster_detail", args=[self.cluster.pk]))
		self.assertEqual(res.status_code, 200)
		self.assertContains(res, reverse("finance:po_workspace", args=[self.cluster.pk]))
		self.assertNotContains(res, 'id="clusterDetailLoanForm"')
		self.assertContains(res, "Open Bank Loans &amp; Matching Panel")


class DeliveryExpenseMatchingLinkTests(TestCase):
	def setUp(self):
		self.finance_user = User.objects.create_user(
			username="finance_auditor",
			password="password123",
			role=User.Role.FINANCE,
		)
		self.client_entity = Client.objects.create(name="Universal Robina Corp")
		self.mill = SugarMill.objects.create(name="Balayan Sugar Central")
		self.trucking = LogisticsPartner.objects.create(name="Solid Ground Hauling")
		self.barge = LogisticsPartner.objects.create(name="Pacific Barge Lines")
		self.cluster = TransactionCluster.objects.create(
			reference_code="PO-URC-8801",
			client=self.client_entity,
			sugar_mill=self.mill,
		)
		self.po = PurchaseOrder.objects.create(
			cluster=self.cluster,
			po_reference_number="PO-URC-8801",
			total_contracted_mt=Decimal("1000.000"),
			volume_mt=Decimal("1000.000"),
			unit_price=Decimal("45000.00"),
			selling_price=Decimal("49000.00"),
		)
		self.client.login(username="finance_auditor", password="password123")

	def test_delivery_fulfillment_auto_generates_pending_cash_vouchers_and_matches(self):
		from operations.models import DeliveryLedger
		from finance.models import CashVoucher, PaymentExpenseMatch, FinancialReconciliation

		delivery = DeliveryLedger.objects.create(
			purchase_order=self.po,
			supplier=self.mill,
			delivered_mt=Decimal("250.000"),
			receiving_location="URC Batangas Plant",
			trucking_partner=self.trucking,
			trucking_rate_per_mt=Decimal("600.00"),
			barge_partner=self.barge,
			barge_rate_per_mt=Decimal("400.00"),
		)

		short_id = str(delivery.delivery_id)[:8].upper()
		trk_ref = f"CV-DEL-{short_id}-TRK"
		brg_ref = f"CV-DEL-{short_id}-BRG"
		src_ref = f"CV-DEL-{short_id}-SRC"

		trk_cv = CashVoucher.objects.get(voucher_number=trk_ref)
		self.assertEqual(trk_cv.amount, Decimal("150000.00"))
		self.assertEqual(trk_cv.status, CashVoucher.Status.PENDING)
		self.assertIn("Truck Delivery", trk_cv.purpose)

		brg_cv = CashVoucher.objects.get(voucher_number=brg_ref)
		self.assertEqual(brg_cv.amount, Decimal("100000.00"))
		self.assertEqual(brg_cv.status, CashVoucher.Status.PENDING)
		self.assertIn("Marine Barging", brg_cv.purpose)

		src_cv = CashVoucher.objects.get(voucher_number=src_ref)
		self.assertEqual(src_cv.amount, Decimal("11250000.00"))
		self.assertEqual(src_cv.status, CashVoucher.Status.PENDING)
		self.assertIn("Sugar Sourcing Outlay", src_cv.purpose)

		# Vouchers are created as PENDING without force-matching to prevent automatic inflation
		recon = FinancialReconciliation.objects.get(cluster=self.cluster)
		self.assertFalse(recon.matches.filter(payment_reference=trk_ref).exists())

		# Performing matching adds the match
		self.client.post(
			reverse("finance:add_match", args=[self.cluster.pk]),
			{
				"payment_reference": trk_ref,
				"expense_type": "trucking",
				"amount": "150000.00",
				"voucher_number": trk_ref,
			},
		)
		recon.refresh_from_db()
		self.assertTrue(recon.matches.filter(payment_reference=trk_ref).exists())
		self.assertEqual(recon.matched_payment_amount, Decimal("150000.00"))

	def test_bank_loan_tab_picks_up_delivery_vouchers(self):
		from operations.models import DeliveryLedger
		delivery = DeliveryLedger.objects.create(
			purchase_order=self.po,
			supplier=self.mill,
			delivered_mt=Decimal("100.000"),
			receiving_location="URC Balayan Terminal",
			trucking_partner=self.trucking,
			trucking_rate_per_mt=Decimal("500.00"),
		)

		res = self.client.get(reverse("finance:po_workspace", args=[self.cluster.pk]))
		self.assertEqual(res.status_code, 200)

		short_id = str(delivery.delivery_id)[:8].upper()
		self.assertContains(res, f"CV-DEL-{short_id}-SRC")
		self.assertContains(res, f"CV-DEL-{short_id}-TRK")
		self.assertContains(res, "Quick Match Suggestions")

	def test_cluster_detail_ui_decluttered(self):
		res = self.client.get(reverse("operations:cluster_detail", args=[self.cluster.pk]))
		self.assertEqual(res.status_code, 200)
		self.assertNotContains(res, "Core Finance Workflow")
		self.assertNotContains(res, "Payment &amp; Expense Matching Workspace")
		self.assertNotContains(res, "Min Capital Required")
		self.assertNotContains(res, "Funded Loan Principal")
		self.assertContains(res, "Finance is currently pending for this PO.")
		self.assertContains(res, "Open Bank Loans &amp; Matching Panel")
		self.assertContains(res, 'id="auditLogCollapse"')
		self.assertContains(res, 'data-bs-target="#auditLogCollapse"')
		self.assertContains(res, "Comprehensive Audit Log (Simple History)")


class DeferredLogisticsAndBatchAccountingTests(TestCase):
	def setUp(self):
		self.admin_user = User.objects.create_superuser(
			username="admin_ops",
			password="password123",
			email="admin@htc.corp",
			role=User.Role.ADMINISTRATOR,
		)
		self.client.login(username="admin_ops", password="password123")
		self.client_entity = Client.objects.create(name="Universal Robina")
		self.mill = SugarMill.objects.create(name="First Sugar Mill")
		self.logistics_partner = LogisticsPartner.objects.create(name="TransLogistics Corp")

		# Create cluster via form / view without logistics upfront
		res = self.client.post(
			reverse("operations:cluster_create"),
			{
				"reference_code": "PO-TEST-DEF-01",
				"client": self.client_entity.pk,
				"sugar_mill": self.mill.pk,
				"volume_mt": "500.000",
				"unit_price": "30000.00",
				"selling_price": "34000.00",
				"confirmed_outlier": "true",
			},
			follow=True,
		)
		self.assertEqual(res.status_code, 200)
		self.cluster = TransactionCluster.objects.get(reference_code="PO-TEST-DEF-01")
		self.po = self.cluster.purchase_order

	def test_initial_creation_defers_logistics(self):
		# Logistics ledger is created with 0.00 fees and partner=None
		self.assertTrue(hasattr(self.cluster, "logistics"))
		log = self.cluster.logistics
		self.assertEqual(log.tracking_fees, Decimal("0.00"))
		self.assertEqual(log.barge_fees, Decimal("0.00"))
		self.assertIsNone(log.partner)

	def test_batch_based_logistics_calculation_with_flat_fees(self):
		from operations.models import DeliveryLedger
		from operations.services.pricing import get_po_logistics_summary

		# Log batch 1: 200 MT @ 300/MT trucking + 1,000 flat trucking fee, 400/MT barge + 2,000 flat barge fee
		d1 = DeliveryLedger.objects.create(
			purchase_order=self.po,
			supplier=self.mill,
			delivered_mt=Decimal("200.000"),
			receiving_location="Warehouse A",
			trucking_partner=self.logistics_partner,
			trucking_rate_per_mt=Decimal("300.00"),
			flat_trucking_fee=Decimal("1000.00"),
			barge_partner=self.logistics_partner,
			barge_rate_per_mt=Decimal("400.00"),
			flat_barge_fee=Decimal("2000.00"),
		)
		# Trucking cost = (200 * 300) + 1,000 = 61,000
		self.assertEqual(d1.trucking_cost, Decimal("61000.00"))
		# Barge cost = (200 * 400) + 2,000 = 82,000
		self.assertEqual(d1.barge_cost, Decimal("82000.00"))
		# Total freight = 61,000 + 82,000 = 143,000
		self.assertEqual(d1.total_freight_cost, Decimal("143000.00"))

		# Sync vouchers
		d1.sync_delivery_expense_vouchers()
		vouchers = self.cluster.cash_vouchers.all()
		short_id = str(d1.delivery_id)[:8].upper()
		self.assertTrue(vouchers.filter(voucher_number=f"CV-DEL-{short_id}-TRK", amount=Decimal("61000.00")).exists())
		self.assertTrue(vouchers.filter(voucher_number=f"CV-DEL-{short_id}-BRG", amount=Decimal("82000.00")).exists())

		# PO Logistics Summary check
		summary = get_po_logistics_summary(self.cluster)
		self.assertEqual(summary["total_incurred"], Decimal("143000.00"))
		self.assertEqual(summary["status_indicator"], "In Progress / Ongoing")
		self.assertEqual(summary["total_delivered_mt"], Decimal("200.000"))
		self.assertEqual(summary["remaining_undelivered_mt"], Decimal("300.000"))
		# Avg rate = 143,000 / 200 = 715.00/MT
		self.assertEqual(summary["avg_rate_per_mt"], Decimal("715.00"))
		# Projected = 143,000 + (300 * 715) = 143,000 + 214,500 = 357,500
		self.assertEqual(summary["projected_total"], Decimal("357500.00"))

		# Check cluster_detail rendering
		res = self.client.get(reverse("operations:cluster_detail", args=[self.cluster.pk]))
		self.assertEqual(res.status_code, 200)
		self.assertContains(res, "Logistics Summary")
		self.assertContains(res, "Total Incurred Logistics Expense")
		self.assertContains(res, "143,000.00")
		self.assertContains(res, "Projected Total Logistics Expense")
		self.assertContains(res, "357,500.00")
		self.assertContains(res, "In Progress / Ongoing")


class LoanValidationCap100PercentTests(TestCase):
	def setUp(self):
		self.admin_user = User.objects.create_superuser(
			username="admin_loan",
			password="password123",
			email="admin_loan@htc.corp",
			role=User.Role.ADMINISTRATOR,
		)
		self.client.login(username="admin_loan", password="password123")
		self.client_entity = Client.objects.create(name="Monde Nissin")
		self.mill = SugarMill.objects.create(name="Central Azucarera")
		self.cluster = TransactionCluster.objects.create(
			reference_code="PO-CAP-100",
			client=self.client_entity,
			sugar_mill=self.mill,
		)
		self.po = PurchaseOrder.objects.create(
			cluster=self.cluster,
			volume_mt=100.0,
			unit_price=10000.0, # Sourcing = 1,000,000
		)
		self.logistics = LogisticsLedger.objects.create(
			cluster=self.cluster,
			loaded_volume_mt=100.0,
			tracking_fees=100000.0, # Trucking DP = 50,000
			barge_fees=100000.0, # Freight DP = 50,000
		)
		# Capital requirement = 1,000,000 + 50,000 + 50,000 = 1,100,000.00

	def test_100_percent_cap_blocks_creation_with_exact_message(self):
		from finance.services import check_loan_capital_cap

		# Initially, allowed
		allowed, _ = check_loan_capital_cap(self.cluster)
		self.assertTrue(allowed)

		# Create an active loan that funds 100% of the requirement
		CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="BDO Unibank",
			principal=Decimal("1100000.00"),
			interest_rate_annual=Decimal("10.00"),
			start_date=date.today(),
			due_date=date.today() + timedelta(days=90),
			status=CapitalLoan.Status.ACTIVE,
		)

		# Now check_loan_capital_cap must block
		allowed, msg = check_loan_capital_cap(self.cluster)
		self.assertFalse(allowed)
		self.assertEqual(
			msg,
			"Capital requirement for this order has already been 100% funded. Additional loans cannot be created.",
		)

		# Submitting via operations:add_loan is blocked
		res = self.client.post(
			reverse("operations:add_loan", args=[self.cluster.pk]),
			{
				"bank_name": "BPI",
				"principal": "500000.00",
				"interest_rate_annual": "10.00",
				"start_date": str(date.today()),
				"due_date": str(date.today() + timedelta(days=90)),
			},
			follow=True,
		)
		self.assertContains(res, "Capital requirement for this order has already been 100% funded. Additional loans cannot be created.")

	def test_100_percent_cap_blocks_approval_when_already_funded(self):
		# Create an approved active loan funding 100%
		CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="BDO Unibank",
			principal=Decimal("1100000.00"),
			interest_rate_annual=Decimal("10.00"),
			start_date=date.today(),
			due_date=date.today() + timedelta(days=90),
			status=CapitalLoan.Status.ACTIVE,
		)

		# Create a pending loan
		pending_loan = CapitalLoan.objects.create(
			cluster=self.cluster,
			bank_name="Metrobank",
			principal=Decimal("300000.00"),
			interest_rate_annual=Decimal("9.50"),
			start_date=date.today(),
			due_date=date.today() + timedelta(days=90),
			status=CapitalLoan.Status.PENDING_CREATION,
		)

		# Attempt to verify/approve pending loan
		res = self.client.post(
			reverse("finance:verify_loan_creation", args=[pending_loan.pk]),
			{"action": "approve", "verification_notes": "Trying to approve"},
			follow=True,
		)
		pending_loan.refresh_from_db()
		self.assertEqual(pending_loan.status, CapitalLoan.Status.PENDING_CREATION)
		self.assertContains(res, "Capital requirement for this order has already been 100% funded. Additional loans cannot be created.")






