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
		self.assertEqual(response.status_code, 403)

