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
		self.assertContains(response, "Capital Loan Tracker")
		self.assertContains(response, "BDO")
