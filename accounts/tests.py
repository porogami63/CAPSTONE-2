from django.test import TestCase

from accounts.models import User
from accounts.permissions import get_nav_items, get_user_permissions, user_has_perm


class AccountsPermissionTests(TestCase):
    def setUp(self):
        self.mgmt_user = User.objects.create_user(
            username="mgmt_user",
            password="password123",
            role=User.Role.MANAGEMENT,
        )
        self.ops_user = User.objects.create_user(
            username="ops_user",
            password="password123",
            role=User.Role.OPERATIONS,
        )
        self.finance_user = User.objects.create_user(
            username="fin_user",
            password="password123",
            role=User.Role.FINANCE,
        )
        self.superuser = User.objects.create_superuser(
            username="super_user",
            password="password123",
            email="admin@example.com",
        )

    def test_management_user_permissions(self):
        self.assertTrue(user_has_perm(self.mgmt_user, "create_transaction"))
        self.assertTrue(user_has_perm(self.mgmt_user, "import_excel"))
        self.assertTrue(user_has_perm(self.mgmt_user, "view_audit"))

    def test_operations_user_permissions(self):
        self.assertTrue(user_has_perm(self.ops_user, "create_transaction"))
        self.assertTrue(user_has_perm(self.ops_user, "edit_logistics"))
        self.assertFalse(user_has_perm(self.ops_user, "import_excel"))
        self.assertFalse(user_has_perm(self.ops_user, "reconcile_payments"))

    def test_finance_user_permissions(self):
        self.assertFalse(user_has_perm(self.finance_user, "create_transaction"))
        self.assertTrue(user_has_perm(self.finance_user, "add_invoice"))
        self.assertTrue(user_has_perm(self.finance_user, "add_loan"))
        self.assertTrue(user_has_perm(self.finance_user, "reconcile_payments"))

    def test_superuser_has_all_permissions(self):
        perms = get_user_permissions(self.superuser)
        self.assertTrue(user_has_perm(self.superuser, "import_excel"))
        self.assertTrue(user_has_perm(self.superuser, "create_transaction"))
        self.assertGreaterEqual(len(perms), 10)

    def test_nav_items_for_roles(self):
        mgmt_nav = get_nav_items(self.mgmt_user)
        fin_nav = get_nav_items(self.finance_user)
        self.assertGreater(len(mgmt_nav), len(fin_nav))
