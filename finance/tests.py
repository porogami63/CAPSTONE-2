from datetime import date, timedelta

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

	def test_ops_manager_approves_loan_creation(self):
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
			{"action": "approve", "verification_notes": "Contract verified, approval granted."},
		)
		self.assertRedirects(response, reverse("finance:loan_list"))
		loan.refresh_from_db()
		self.assertEqual(loan.status, CapitalLoan.Status.ACTIVE)
		self.assertEqual(loan.verified_by, self.ops_manager)
		self.assertEqual(loan.verification_notes, "Contract verified, approval granted.")

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

	def test_loan_creation_hard_blocks_insufficient_principal(self):
		# Required = 1,150,000. Try submitting 1,000,000
		res = self.client.post(
			reverse("finance:loan_list"),
			{
				"cluster": self.cluster.pk,
				"bank_name": "BDO",
				"principal": "1000000.00",
				"interest_rate_annual": "10.00",
				"start_date": str(date.today()),
				"due_date": str(date.today() + timedelta(days=60)),
			},
		)
		self.assertEqual(res.status_code, 200) # Re-renders page with errors
		self.assertContains(res, "short of the required")
		self.assertFalse(CapitalLoan.objects.filter(cluster=self.cluster, bank_name="BDO").exists())

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



