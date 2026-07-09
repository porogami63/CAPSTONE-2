# HTC Core — MVP Implementation vs Capstone Paper

This document aligns the built system with Chapters 1–3 of the capstone proposal and marks Phase 2 deferrals.

## Implemented in MVP (matches defense demo)

| Proposal feature | Implementation |
|------------------|----------------|
| Multi-role permissions | `accounts.User` with Management, Finance, Operations, Invoicing roles |
| Master registries | `masters` app: Client, SugarMill, LogisticsPartner |
| Transaction cluster hub | `operations.TransactionCluster` + PurchaseOrder + LogisticsLedger |
| Transit variance (1% tolerance) | Computed on save in `LogisticsLedger._compute_variance()` |
| Sales invoice & cash voucher | `finance.Invoice`, `finance.CashVoucher` |
| Capital loan + interest accrual | `finance.CapitalLoan.accrued_interest` property |
| Payment-to-expense matching | `finance.PaymentExpenseMatch` + reconciliation UI |
| Immutable audit trail | `audit.SystemAuditTrail` (append-only, signals on finance models) |
| Management dashboard | `dashboard.home` with alerts and summaries |
| Bootstrap 5 UI | CDN Bootstrap 5, high-contrast status cards |

## Deferred to Phase 2 (document in Chapter 3/4)

| Proposal item | MVP status | Phase 2 plan |
|---------------|------------|--------------|
| Celery background workers | Not included | Move variance/interest recalc to scheduled tasks |
| Redis message broker | Not included | Add when async jobs are enabled |
| Docker multi-container (app + worker + redis) | Single-service pilot only | Extend compose file |
| AWS EC2 production | Local + Docker pilot | Deploy after UAT sign-off |
| Excel import from legacy sheets | Manual seed command | `import_excel` management command |
| SRA regulatory automation | Out of scope per proposal | Remains external workflow |
| Full GL / tax modules | Out of scope per proposal | Not planned |

## Chapter 3 methodology alignment

- **Agile sprints:** MVP maps to original Sprints 1–4 (auth, procurement, dashboard, finance).
- **Architecture diagram:** Phase 1 uses Django + PostgreSQL + Gunicorn (pilot). Celery/Redis shown as Phase 2 extension in revised diagrams.
- **Constraints:** Internet, browser, and confidentiality constraints unchanged; pilot uses sanitized `seed_demo` data.

## UAT test script for HTC staff

1. Log in as `operations` — create a transaction, update delivered vs received volumes.
2. Log in as `invoicing` — add a sales invoice to the same transaction.
3. Log in as `finance` — add cash voucher, capital loan, and payment match.
4. Log in as `admin` — review dashboard alerts and audit trail.

## Demo seed data

Run `python manage.py seed_demo` for three sanitized transactions (GSMI, Emperador, ADI) with one variance alert and overdue loan scenarios.
