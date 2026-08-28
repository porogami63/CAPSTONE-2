from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class DashboardRoleInterfaceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_user", password="password123", role=User.Role.ADMINISTRATOR)
        self.ops = User.objects.create_user(username="ops_user", password="password123", role=User.Role.OPERATIONS_MANAGEMENT)
        self.fin = User.objects.create_user(username="fin_user", password="password123", role=User.Role.FINANCE)
        self.inv = User.objects.create_user(username="inv_user", password="password123", role=User.Role.INVOICING)

    def test_admin_dashboard_home(self):
        self.client.login(username="admin_user", password="password123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["user_role"], User.Role.ADMINISTRATOR)
        self.assertIn("mro_mill_balances", res.context)

    def test_operations_dashboard_home(self):
        self.client.login(username="ops_user", password="password123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["user_role"], User.Role.OPERATIONS_MANAGEMENT)
        self.assertIn("active_shipments_count", res.context)

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
