"""
Frozen MVP scope for HTC Core (Phase 1).
Phase 2 items are documented but not implemented in this release.
"""

MVP_MODULES = (
    "auth_rbac",
    "master_data",
    "transaction_cluster",
    "variance_alerts",
    "finance_matching",
    "audit_trail",
    "management_dashboard",
)

MVP_ROLES = (
    "management",
    "finance",
    "operations",
    "invoicing",
)

PHASE_2_DEFERRED = (
    "celery_background_workers",
    "redis_message_broker",
    "docker_multi_container",
    "excel_import",
    "sra_regulatory_automation",
    "full_general_ledger",
    "multi_currency",
    "public_ecommerce_portal",
    "rfid_gps_hardware",
)

VARIANCE_TOLERANCE_PERCENT = 1.0
