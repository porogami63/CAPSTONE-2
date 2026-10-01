"""
HTC Core — Complete Database Wipe for UAT Preparation
Clears ALL transactional data, master data, chat, notifications, and audit trails.
Preserves: database structure (migrations), superuser accounts.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

def wipe_database():
    print("=" * 60)
    print("  HTC CORE — FULL DATABASE WIPE FOR UAT")
    print("=" * 60)
    
    # Import all models
    from finance.models import PaymentExpenseMatch, FinancialReconciliation, Invoice, CashVoucher, CapitalLoan
    from operations.models import LogisticsLedger, PurchaseOrder, TransactionCluster, MolassesReleaseOrder, CHAIRecord
    from masters.models import Client, SugarMill, LogisticsPartner, PartnerNote, Planter
    from audit.models import SystemAuditTrail, Notification
    from chat.models import ChatMessage
    from accounts.models import User
    
    # Delete in dependency order (children first)
    tables = [
        ("PaymentExpenseMatch", PaymentExpenseMatch),
        ("FinancialReconciliation", FinancialReconciliation),
        ("CashVoucher", CashVoucher),
        ("CapitalLoan", CapitalLoan),
        ("Invoice", Invoice),
        ("ChatMessage", ChatMessage),
        ("Notification", Notification),
        ("SystemAuditTrail", SystemAuditTrail),
        ("PartnerNote", PartnerNote),
        ("CHAIRecord", CHAIRecord),
        ("MolassesReleaseOrder", MolassesReleaseOrder),
        ("LogisticsLedger", LogisticsLedger),
        ("PurchaseOrder", PurchaseOrder),
        ("TransactionCluster", TransactionCluster),
        # Preserved master data:
        # ("Planter", Planter),
        # ("Client", Client),
        # ("SugarMill", SugarMill),
        # ("LogisticsPartner", LogisticsPartner),
    ]
    
    # Also clear historical records from django-simple-history
    history_tables = []
    for model_name, model in tables:
        if hasattr(model, 'history'):
            history_tables.append((f"{model_name} History", model.history.model))
    
    print("\n--- Clearing Historical Records ---")
    for name, model in history_tables:
        count = model.objects.count()
        model.objects.all().delete()
        print(f"  [DELETED] {name}: {count} records")
    
    print("\n--- Clearing Transactional & Master Data ---")
    for name, model in tables:
        count = model.objects.count()
        model.objects.all().delete()
        print(f"  [DELETED] {name}: {count} records")
    
    # Clear non-superuser accounts (keep superusers for admin access)
    # non_super_users = User.objects.filter(is_superuser=False)
    # user_count = non_super_users.count()
    # non_super_users.delete()
    # print(f"  [DELETED] Non-superuser accounts: {user_count} records")
    
    # Show remaining superusers
    superusers = User.objects.filter(is_superuser=True)
    print(f"\n--- Preserved Superuser Accounts ---")
    for u in superusers:
        print(f"  > {u.username} ({u.email}) — {u.get_role_display()}")
    
    print("\n" + "=" * 60)
    print("  DATABASE WIPE COMPLETE — READY FOR UAT")
    print("=" * 60)


wipe_database()
