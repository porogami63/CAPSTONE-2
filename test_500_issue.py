import os
import sys
import traceback
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client as TestClient
from django.utils import timezone
from decimal import Decimal

from accounts.models import User
from masters.models import Client as MasterClient, SugarMill, Planter, LogisticsPartner
from operations.models import TransactionCluster, PurchaseOrder, LogisticsLedger, CHAIRecord, MolassesReleaseOrder
from finance.models import CapitalLoan, Invoice, CashVoucher, FinancialReconciliation

def run():
    print("==================================================")
    print("       COMPREHENSIVE WORKFLOW & 500 TEST         ")
    print("==================================================")

    # Clean previous test clusters and their orphaned CHAIRecords/etc
    TransactionCluster.objects.filter(reference_code__icontains="OPSMGR").delete()
    CHAIRecord.objects.filter(chai_number__icontains="OPSMGR").delete()
    # 1. Create or get test users for all roles
    ops_mgr, _ = User.objects.get_or_create(username="ops_mgr_user", defaults={"email": "ops_mgr@test.com", "role": User.Role.OPERATIONS_MANAGEMENT, "is_active": True})
    ops_mgr.set_password("password123")
    ops_mgr.role = User.Role.OPERATIONS_MANAGEMENT
    ops_mgr.is_active = True
    ops_mgr.save()

    admin_user, _ = User.objects.get_or_create(username="admin_test_user", defaults={"email": "admin@test.com", "role": User.Role.ADMINISTRATOR, "is_active": True})
    admin_user.set_password("password123")
    admin_user.role = User.Role.ADMINISTRATOR
    admin_user.is_active = True
    admin_user.save()

    fin_user, _ = User.objects.get_or_create(username="fin_test_user", defaults={"email": "fin@test.com", "role": User.Role.FINANCE, "is_active": True})
    fin_user.set_password("password123")
    fin_user.role = User.Role.FINANCE
    fin_user.is_active = True
    fin_user.save()

    inv_user, _ = User.objects.get_or_create(username="inv_test_user", defaults={"email": "inv@test.com", "role": User.Role.INVOICING, "is_active": True})
    inv_user.set_password("password123")
    inv_user.role = User.Role.INVOICING
    inv_user.is_active = True
    inv_user.save()

    # 2. Setup master data
    m_client, _ = MasterClient.objects.get_or_create(name="San Miguel Corp", defaults={"is_active": True})
    m_client.is_active = True
    m_client.save()

    m_mill, _ = SugarMill.objects.get_or_create(name="BUSCO Sugar Mill", defaults={"is_active": True})
    m_mill.is_active = True
    m_mill.save()

    m_partner, _ = LogisticsPartner.objects.get_or_create(name="RL Cargo Services", defaults={"is_active": True})
    m_partner.is_active = True
    m_partner.save()

    m_planter, _ = Planter.objects.get_or_create(name="Planter Bukidnon", defaults={"is_active": True})

    # Test Client harness
    client = TestClient()

    # STEP A: Operations Manager creates a cluster
    client.login(username="ops_mgr_user", password="password123")
    resp = client.post("/operations/new/", {
        "reference_code": "PO-OPSMGR-999",
        "client": m_client.pk,
        "sugar_mill": m_mill.pk,
        "volume_mt": "500.000",
        "unit_price": "24500.00",
        "selling_price": "27500.00",
        "terms": "Net 30 days. Sourcing ₱24,500/MT, Selling ₱27,500/MT",
        "brix_level": "85.50",
        "chai_specs": "1.5",
        "logistics_partner": m_partner.pk,
        "contract_notes": "Operations Manager created trade deal.",
        "status": "draft",
    }, follow=False)
    print("Create response status:", resp.status_code)
    if resp.status_code == 200 and hasattr(resp, "context") and resp.context and "form" in resp.context:
        print("FORM ERRORS:", resp.context["form"].errors)

    cluster = TransactionCluster.objects.filter(reference_code="PO-OPSMGR-999").first()
    if not cluster:
        print("ERROR: Cluster PO-OPSMGR-999 was not created!")
        return

    # STEP B: Operations Manager submits cluster for executive approval
    print("\n[STEP B] Operations Manager submitting cluster for approval...")
    resp = client.post(f"/operations/{cluster.pk}/submit/", follow=True)
    print("Submit response status:", resp.status_code)
    cluster.refresh_from_db()
    print(f"Cluster status after submit: {cluster.status}")

    # STEP C: User logs in (e.g. Admin or Ops Manager) and APPROVES the transaction
    print("\n[STEP C] Executive approving the transaction made by Operations Manager...")
    client.login(username="admin_test_user", password="password123")
    app_resp = client.post(f"/operations/{cluster.pk}/approve/", follow=True)
    print("Approve response status:", app_resp.status_code)
    cluster.refresh_from_db()
    print(f"Cluster status after approval: {cluster.status}, Approved By: {cluster.approved_by}")

    users = [
        ("Admin", admin_user),
        ("Ops Manager", ops_mgr),
        ("Finance", fin_user),
        ("Invoicing", inv_user),
    ]

    # STEP D: Test all GET routes for ALL user roles!
    urls_to_test = [
        ("/", "Dashboard Home"),
        ("/operations/", "Transactions List"),
        (f"/operations/{cluster.pk}/", "Transaction Detail"),
        ("/operations/logistics/", "Logistics Master Ledger"),
        ("/operations/pending-tasks/", "Pending Tasks"),
        ("/operations/stats-monitoring/", "System Stats & Health Monitoring"),
        ("/operations/mro-summary/", "MRO Summary"),
        ("/operations/chai/", "CHAI Quality Management"),
        ("/finance/invoices/", "Invoicing Overview"),
        ("/finance/loans/", "Capital Loan Facilities"),
        (f"/finance/reconciliation/{cluster.pk}/", "Financial Reconciliation"),
        ("/audit/", "System Audit Trail"),
    ]

    errors_found = 0

    for role_name, user_obj in users:
        print(f"\n==================================================")
        print(f"   TESTING ALL VIEWS AS: {role_name} ({user_obj.username} / {user_obj.role})")
        print(f"==================================================")
        client.login(username=user_obj.username, password="password123")

        for url, name in urls_to_test:
            resp = client.get(url)
            status = resp.status_code
            if status == 500:
                errors_found += 1
                print(f"❌ [500 SERVER ERROR] {name} ({url})")
                if hasattr(resp, "exc_info") and resp.exc_info:
                    traceback.print_exception(*resp.exc_info)
                elif hasattr(resp, "content"):
                    print("Response content snippet:", resp.content[:500].decode("utf-8", errors="ignore"))
            else:
                print(f"  OK [{status}] {name} ({url})")

    # STEP E: Add MRO, CHAI, Loans, Invoices to fully test transaction graph
    mro = MolassesReleaseOrder.objects.create(
        mro_number="MRO-9999",
        planter=m_planter,
        sugar_mill=m_mill,
        release_date=timezone.localdate(),
        tons=Decimal("500.000"),
        cluster=cluster
    )

    errors_found = 0

    for role_name, user_obj in users:
        print(f"\n==================================================")
        print(f"   TESTING ALL VIEWS AS: {role_name} ({user_obj.username} / {user_obj.role})")
        print(f"==================================================")
        client.login(username=user_obj.username, password="password123")

        for url, name in urls_to_test:
            resp = client.get(url)
            status = resp.status_code
            if status == 500:
                errors_found += 1
                print(f"❌ [500 SERVER ERROR] {name} ({url})")
                if hasattr(resp, "exc_info") and resp.exc_info:
                    traceback.print_exception(*resp.exc_info)
                elif hasattr(resp, "content"):
                    print("Response content snippet:", resp.content[:500].decode("utf-8", errors="ignore"))
            else:
                print(f"  OK [{status}] {name} ({url})")

    # STEP F: Test Edge Case Cluster (Missing Optional Fields)
    print("\n==================================================")
    print("   TESTING EDGE CASE CLUSTER (Missing Optional Fields)")
    print("==================================================")
    
    client.login(username="ops_mgr_user", password="password123")
    resp2 = client.post("/operations/new/", {
        "reference_code": "PO-OPSMGR-888",
        "client": m_client.pk,
        "sugar_mill": m_mill.pk,
        "volume_mt": "100.000",
        "unit_price": "24500.00",
        "selling_price": "",
        "terms": "Net 30 days.",
        "brix_level": "",
        "chai_specs": "",
        "logistics_partner": "",
        "contract_notes": "",
        "status": "draft",
    }, follow=False)
    print("Create Edge Cluster status:", resp2.status_code)
    
    cluster2 = TransactionCluster.objects.filter(reference_code="PO-OPSMGR-888").first()
    if cluster2:
        client.post(f"/operations/{cluster2.pk}/submit/", follow=True)
        
        client.login(username="admin_test_user", password="password123")
        app_resp2 = client.post(f"/operations/{cluster2.pk}/approve/", follow=True)
        print("Approve Edge Cluster status:", app_resp2.status_code)
        
        for url, name in urls_to_test:
            if cluster.pk in str(url):
                url = str(url).replace(str(cluster.pk), str(cluster2.pk))
            if hasattr(locals(), 'chai') and chai.pk in str(url):
                continue # Skip chai detail
                
            resp = client.get(url)
            status = resp.status_code
            if status == 500:
                errors_found += 1
                print(f"❌ [500 SERVER ERROR] {name} ({url})")
                if hasattr(resp, "exc_info") and resp.exc_info:
                    traceback.print_exception(*resp.exc_info)
            else:
                print(f"  OK [{status}] {name} ({url})")
    
    print("\n==================================================")
    print(f"TEST RUN COMPLETED. Total 500 Errors Found: {errors_found}")
    print("==================================================")

if __name__ == "__main__":
    run()
