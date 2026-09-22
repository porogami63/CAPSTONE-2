# HTC Core — MVP Implementation vs Capstone Paper

This document aligns the built system with Chapters 1–3 of the capstone proposal and maps current capabilities to the Phase 2 production roadmap.

## Implemented Baseline (Matches Codebase)

| Proposal feature | Implementation Status |
|------------------|----------------|
| Multi-role permissions | `accounts.User` with Management, Finance, Operations, Invoicing roles + Admin Approval workflow |
| Master registries | `masters` app: Client, SugarMill, LogisticsPartner |
| Transaction cluster hub | `operations.TransactionCluster` + PurchaseOrder + LogisticsLedger |
| Transit variance (1% tolerance) | Computed on save in `LogisticsLedger._compute_variance()` |
| Sales invoice & cash voucher | `finance.Invoice`, `finance.CashVoucher` |
| Capital loan + interest accrual | `finance.CapitalLoan.accrued_interest` property + Celery nightly refresh |
| Payment-to-expense matching | `finance.PaymentExpenseMatch` + reconciliation UI |
| Immutable audit trail | `audit.SystemAuditTrail` (append-only, signals on finance models) |
| Containerized stack | Docker Compose (`web`, `db`, `redis`, `nginx`, `celery_worker`) |
| Excel import pipeline | Management upload (`operations:import_excel`) & `import_htc_excel` command |
| Management dashboard | `dashboard.home` with status cards, metric alerts, and summaries |

## Phase 2 Production Roadmap (Amazon EC2 Deployment)

| Proposal / System Item | Current Baseline | Phase 2 Production Target |
|------------------|------------------|---------------------------|
| **Host Environment** | Local Docker Compose | **Amazon EC2 (Ubuntu 24.04 LTS instance)** |
| **Domain & Encryption** | HTTP on port 80 / localhost | **HTTPS (Let's Encrypt / Certbot SSL certificate on Nginx)** |
| **Production Secrets** | `.env` pilot credentials | **`.env.production` (Hardened SECRET_KEY, DEBUG=False)** |
| **Deployment Automation** | Manual `docker compose up` | **`scripts/deploy_ec2.sh` automated single-command deployment** |
| **Data Backups & Storage** | Local Docker volume | **Automated `pg_dump` database backup cron jobs to Amazon S3** |

See [docs/PHASE_2_ARCHITECTURE_PLAN.md](PHASE_2_ARCHITECTURE_PLAN.md) for the complete Amazon EC2 host deployment plan.

## Chapter 3 Methodology Alignment

- **Agile Sprints:** MVP maps to original Sprints 1–4 (auth, procurement, dashboard, finance).
- **Architecture Diagram:** Multi-container topology (Nginx proxy -> Gunicorn WSGI -> Django -> Postgres + Redis + Celery Worker) is fully integrated.
- **Constraints:** Internet, browser, and confidentiality constraints unchanged; pilot uses sanitized `seed_demo` data.

## UAT Test Script for HTC Staff

1. Self-register a new account via `/accounts/signup/`.
2. Log in as an Administrator (`admin`), navigate to `/accounts/users/`, select employee role, and click **Approve & Activate**.
3. Log in as `operations` — create a transaction, update delivered vs received volumes.
4. Log in as `invoicing` — add a sales invoice to the same transaction.
5. Log in as `finance` — add cash voucher, capital loan, and payment match.
6. Log in as `admin` — review dashboard alerts and audit trail.

## Demo Seed Data

Run `python manage.py seed_demo` for three sanitized transactions (GSMI, Emperador, ADI) with variance alerts and overdue loan scenarios.
