import os
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from audit.models import SystemAuditTrail
from admin_hub.services import get_backups_directory

User = get_user_model()


class AdminHubSecurityAndFunctionalityTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Admin user
        self.admin_user = User.objects.create_user(
            username="admin_test",
            password="testpassword123",
            role=User.Role.ADMINISTRATOR,
            is_active=True,
        )

        # Non-admin user (Operations Management)
        self.ops_user = User.objects.create_user(
            username="ops_test",
            password="testpassword123",
            role=User.Role.OPERATIONS_MANAGEMENT,
        )

        # Non-admin user (Finance)
        self.finance_user = User.objects.create_user(
            username="finance_test",
            password="testpassword123",
            role=User.Role.FINANCE,
        )

        # Superuser
        self.superuser = User.objects.create_superuser(
            username="super_test",
            password="testpassword123",
            email="super@test.com",
            role=User.Role.ADMINISTRATOR,
        )

    def test_anonymous_redirected_to_login(self):
        """Anonymous user trying to access /admin/ must be redirected to login."""
        response = self.client.get(reverse("admin_hub:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_non_admin_forbidden_operations(self):
        """Non-admin user (Operations Management) must receive HTTP 403 Forbidden."""
        self.client.force_login(self.ops_user)
        response = self.client.get(reverse("admin_hub:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_non_admin_forbidden_finance(self):
        """Non-admin user (Finance) must receive HTTP 403 Forbidden."""
        self.client.force_login(self.finance_user)
        response = self.client.get(reverse("admin_hub:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_admin_access_allowed(self):
        """Admin user must receive HTTP 200 and access all hub tabs."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin_hub:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Website Administration Hub")
        self.assertContains(response, "Website Latency")
        self.assertContains(response, "Website Activity")
        self.assertContains(response, "System Telemetry")
        self.assertContains(response, "User Audits (NFR-07)")
        self.assertContains(response, "User Accounts")
        self.assertContains(response, "Data Backups (NFR-08)")
        self.assertContains(response, "Data Archives")

    def test_admin_default_dashboard_redirect(self):
        """Admin accessing '/' must be redirected to the Admin Hub dashboard."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/", response.url)

    def test_operations_manager_with_superuser_flag_still_denied(self):
        """Operations Manager even with is_superuser=True is strictly denied access."""
        self.ops_user.is_superuser = True
        self.ops_user.save()
        self.client.force_login(self.ops_user)
        response = self.client.get(reverse("admin_hub:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_trigger_backup_generates_file_and_audit(self):
        """NFR-08: Admin can trigger an instant backup snapshot with audit logging."""
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("admin_hub:trigger_backup"))
        self.assertEqual(response.status_code, 302)

        # Check backup file exists
        backup_dir = get_backups_directory()
        files = [f for f in os.listdir(backup_dir) if f.startswith("htc_core_snapshot_") and f.endswith(".json.gz")]
        self.assertTrue(len(files) > 0, "Expected at least one backup snapshot file")

        # Verify audit trail record was created
        audit_entry = SystemAuditTrail.objects.filter(
            table_name="DatabaseBackup",
            action="create",
        ).first()
        self.assertIsNotNone(audit_entry, "Expected audit trail entry for backup creation")
        self.assertEqual(audit_entry.user, self.admin_user)

    def test_audit_csv_export(self):
        """NFR-07: Admin can export audit trail logs as CSV."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin_hub:export_audit_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Timestamp (UTC)", response.content.decode("utf-8"))

    def test_dataflow_csv_export(self):
        """Admin can export operational data flow report as CSV."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin_hub:export_dataflow_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Transaction Reference", response.content.decode("utf-8"))

    def test_user_toggle_active_prevents_self_deactivation(self):
        """Admin cannot deactivate their own account."""
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("admin_hub:user_toggle_active", kwargs={"pk": self.admin_user.pk}))
        self.assertEqual(response.status_code, 302)
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active, "Admin should remain active after attempting self-deactivation")

    def test_user_toggle_active_for_other_user(self):
        """Admin can activate/deactivate other users."""
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("admin_hub:user_toggle_active", kwargs={"pk": self.ops_user.pk}))
        self.assertEqual(response.status_code, 302)
        self.ops_user.refresh_from_db()
        self.assertFalse(self.ops_user.is_active, "Ops user should have been deactivated")
