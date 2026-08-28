from django.test import TestCase

from accounts.models import User
from accounts.permissions import get_nav_items, get_user_permissions, user_has_perm


class AccountsPermissionTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_user",
            password="password123",
            role=User.Role.ADMINISTRATOR,
        )
        self.ops_mgmt_user = User.objects.create_user(
            username="ops_mgmt_user",
            password="password123",
            role=User.Role.OPERATIONS_MANAGEMENT,
        )
        self.finance_user = User.objects.create_user(
            username="fin_user",
            password="password123",
            role=User.Role.FINANCE,
        )
        self.invoicing_user = User.objects.create_user(
            username="inv_user",
            password="password123",
            role=User.Role.INVOICING,
        )
        self.superuser = User.objects.create_superuser(
            username="super_user",
            password="password123",
            email="admin@example.com",
        )

    def test_administrator_user_permissions(self):
        self.assertTrue(user_has_perm(self.admin_user, "manage_users"))
        self.assertTrue(user_has_perm(self.admin_user, "create_transaction"))
        self.assertTrue(user_has_perm(self.admin_user, "clear_database"))

    def test_operations_management_user_permissions(self):
        self.assertTrue(user_has_perm(self.ops_mgmt_user, "manage_users"))
        self.assertTrue(user_has_perm(self.ops_mgmt_user, "create_transaction"))
        self.assertTrue(user_has_perm(self.ops_mgmt_user, "edit_logistics"))
        self.assertTrue(user_has_perm(self.ops_mgmt_user, "import_excel"))
        self.assertFalse(user_has_perm(self.ops_mgmt_user, "clear_database"))

    def test_finance_user_permissions(self):
        self.assertFalse(user_has_perm(self.finance_user, "create_transaction"))
        self.assertTrue(user_has_perm(self.finance_user, "add_invoice"))
        self.assertTrue(user_has_perm(self.finance_user, "add_loan"))
        self.assertTrue(user_has_perm(self.finance_user, "reconcile_payments"))

    def test_invoicing_user_permissions(self):
        self.assertFalse(user_has_perm(self.invoicing_user, "create_transaction"))
        self.assertTrue(user_has_perm(self.invoicing_user, "add_invoice"))
        self.assertFalse(user_has_perm(self.invoicing_user, "add_loan"))

    def test_superuser_has_all_permissions(self):
        perms = get_user_permissions(self.superuser)
        self.assertTrue(user_has_perm(self.superuser, "import_excel"))
        self.assertTrue(user_has_perm(self.superuser, "create_transaction"))
        self.assertGreaterEqual(len(perms), 10)

    def test_nav_items_for_roles(self):
        admin_nav = get_nav_items(self.admin_user)
        fin_nav = get_nav_items(self.finance_user)
        self.assertGreater(len(admin_nav), len(fin_nav))


class AccountsViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="password123", role=User.Role.ADMINISTRATOR)
        self.finance = User.objects.create_user(username="fin", password="password123", role=User.Role.FINANCE)

    def test_user_list_view_access(self):
        self.client.login(username="admin", password="password123")
        res = self.client.get("/accounts/users/")
        self.assertEqual(res.status_code, 200)

        # Finance user should be denied access (403)
        self.client.login(username="fin", password="password123")
        res_fin = self.client.get("/accounts/users/")
        self.assertEqual(res_fin.status_code, 403)

    def test_user_edit_view(self):
        self.client.login(username="admin", password="password123")
        res = self.client.get(f"/accounts/users/{self.finance.id}/edit/")
        self.assertEqual(res.status_code, 200)

        post_data = {
            "first_name": "Finance",
            "last_name": "Manager",
            "email": "fin@htc.ph",
            "role": User.Role.FINANCE,
            "is_active": True,
            "is_staff": False,
        }
        res_post = self.client.post(f"/accounts/users/{self.finance.id}/edit/", post_data)
        self.assertEqual(res_post.status_code, 302)
        self.finance.refresh_from_db()
        self.assertEqual(self.finance.first_name, "Finance")
        self.assertEqual(self.finance.email, "fin@htc.ph")

    def test_profile_view_update(self):
        self.client.login(username="fin", password="password123")
        res = self.client.get("/accounts/profile/")
        self.assertEqual(res.status_code, 200)

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "johndoe@htc.ph",
        }
        res_post = self.client.post("/accounts/profile/", post_data)
        self.assertEqual(res_post.status_code, 302)
        self.finance.refresh_from_db()
        self.assertEqual(self.finance.first_name, "John")
        self.assertEqual(self.finance.last_name, "Doe")


