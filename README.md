# HTC Core

Integrated Procurement & Financial Tracking System for Heindrich Trading Corporation.

## MVP (Phase 1)

- Auth + RBAC (Management, Finance, Operations, Invoicing)
- Master data: clients, sugar mills, logistics partners
- Transaction clusters with purchase orders and logistics ledger
- Transit volume variance alerts (1% tolerance)
- Invoices, cash vouchers, capital loans with interest accrual
- Payment-to-expense matching
- Append-only audit trail for financial records
- Management dashboard

Phase 2 (deferred): Celery, Redis, Docker multi-container hardening, SRA automation.

Phase 2 architecture roadmap: [docs/PHASE_2_ARCHITECTURE_PLAN.md](docs/PHASE_2_ARCHITECTURE_PLAN.md)

Excel import is available from the management UI under Transactions → Import Excel, and the CLI import command remains available for local resets.

## Quick start (local)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py import_htc_excel
.\.venv\Scripts\python manage.py runserver
```

Open http://127.0.0.1:8000 — login: `admin` / `htc2026`

## Pilot deploy (Docker — matches capstone architecture)

Requires Docker Desktop running.

```powershell
docker compose up --build
```

Open **http://localhost** (Nginx on port 80).

Stack: **Nginx → Gunicorn → Django → PostgreSQL**. See [docs/DOCKER_ARCHITECTURE.md](docs/DOCKER_ARCHITECTURE.md).

Phase 2 (Celery + Redis): `docker compose -f docker-compose.yml -f docker-compose.phase2.yml up --build`

## Figma wireframes

UI is aligned to the [Figma Make login + dashboard wireframe](https://www.figma.com/make/fpZJzZgpJGhACxGcVbfxNC/Create-Login-Screen?p=f&t=YCWsgQLWOGf7UQwa-0&preview-route=%2Fdashboard).  
Theme tokens: `static/css/htc-theme.css`. Guide: [docs/FIGMA_TO_DJANGO.md](docs/FIGMA_TO_DJANGO.md).

## Pilot users

| Username    | Role        | Password |
|-------------|-------------|----------|
| admin       | Management  | htc2026  |
| operations  | Operations  | htc2026  |
| finance     | Finance     | htc2026  |
| invoicing   | Invoicing   | htc2026  |

## End-to-end workflow

1. Create transaction cluster (contract + PO)
2. Update logistics with loaded/received volumes → variance alert if > 1%
3. Add sales invoice and cash voucher
4. Link capital loan → view accrued interest
5. Match payments to expenses on reconciliation screen
6. Review audit trail and dashboard alerts
