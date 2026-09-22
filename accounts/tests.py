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

    def test_signup_creates_inactive_user(self):
        signup_data = {
            "username": "newemployee",
            "email": "employee@heindrich.net",
            "first_name": "New",
            "last_name": "Employee",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        res = self.client.post("/accounts/signup/", signup_data)
        self.assertEqual(res.status_code, 302)
        new_user = User.objects.get(username="newemployee")
        self.assertFalse(new_user.is_active)
        self.assertEqual(new_user.email, "employee@heindrich.net")

    def test_login_blocked_for_pending_user(self):
        pending_user = User.objects.create_user(username="pending", password="password123", is_active=False)
        res = self.client.post("/accounts/login/", {"username": "pending", "password": "password123"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("pending Administrator approval", res.context["login_error"])

    def test_admin_approve_user(self):
        pending_user = User.objects.create_user(username="pending2", password="password123", is_active=False)
        self.client.login(username="admin", password="password123")
        res = self.client.post(f"/accounts/users/{pending_user.id}/approve/", {"role": User.Role.FINANCE})
        self.assertEqual(res.status_code, 302)
        pending_user.refresh_from_db()
        self.assertTrue(pending_user.is_active)
        self.assertEqual(pending_user.role, User.Role.FINANCE)

    def test_admin_reset_password(self):
        user = User.objects.create_user(username="staff1", password="oldpassword123")
        self.client.login(username="admin", password="password123")
        res = self.client.post(f"/accounts/users/{user.id}/reset-password/", {
            "new_password": "NewSecretPassword123!",
            "confirm_password": "NewSecretPassword123!",
        })
        self.assertEqual(res.status_code, 302)
        self.client.logout()
        auth_res = self.client.login(username="staff1", password="NewSecretPassword123!")
        self.assertTrue(auth_res)

    def test_2fa_login_verification_flow(self):
        import pyotp
        secret = pyotp.random_base32()
        user_2fa = User.objects.create_user(
            username="user2fa",
            password="password123",
            otp_secret=secret,
            is_2fa_enabled=True,
            backup_codes=["BACKUP123"],
        )

        # Login step 1: valid password redirects to 2FA verification page
        res = self.client.post("/accounts/login/", {"username": "user2fa", "password": "password123"})
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/two-factor-verify/", res.url)

        # Verification step 2: invalid TOTP token returns error
        res_verify_fail = self.client.post("/accounts/two-factor-verify/", {"otp_token": "000000"})
        self.assertEqual(res_verify_fail.status_code, 200)
        self.assertIn("Invalid 2FA code", res_verify_fail.context["error_message"])

        # Verification step 2: valid TOTP token succeeds
        totp = pyotp.TOTP(secret)
        valid_token = totp.now()
        res_verify_success = self.client.post("/accounts/two-factor-verify/", {"otp_token": valid_token})
        self.assertEqual(res_verify_success.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user_2fa.id)

    def test_2fa_backup_code_login(self):
        user_2fa = User.objects.create_user(
            username="backupuser",
            password="password123",
            otp_secret="BASE32SECRET3232",
            is_2fa_enabled=True,
            backup_codes=["BACKUP999"],
        )
        self.client.post("/accounts/login/", {"username": "backupuser", "password": "password123"})
        res = self.client.post("/accounts/two-factor-verify/", {"otp_token": "BACKUP999"})
        self.assertEqual(res.status_code, 302)
        user_2fa.refresh_from_db()
        self.assertNotIn("BACKUP999", user_2fa.backup_codes)


