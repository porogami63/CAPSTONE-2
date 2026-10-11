# Agile Release Sign-Off Documentation

**Project:** HTC Core Trading & Logistics Platform (Capstone 2)  
**Epic:** EP-LOG-04: Multi-Source Parent-Child Purchase Order & Incremental Delivery Ledger  
**Release Version:** v2.1.0-prod  
**Target Environment:** AWS EC2 Production (`htccore.tech` / `18.140.166.84`)  
**Deployment Date:** October 11, 2026  
**Status:** **APPROVED & FULLY SIGNED OFF**  

---

## 1. Feature Background & Business Justification

Following on-site discovery interviews with logistics operations personnel, a critical workflow gap was identified in the legacy system:
> *"Usually, it uses the same PO reference number, but sometimes the stock comes from a different supplier.*  
> *For example, when importing goods—say around 6,000+ metric tons—2,000 metric tons might go to ADI, another portion to the HTC tank, and the rest to Balayan. This is all from the same supplier and under a single PO, but delivered to different customer locations.*  
> *On the other hand, there are cases where you have a single PO from a customer, but you source the inventory from different suppliers to fulfill it.*  
> *Deliveries don't happen all at once. If ADI issues a 10,000 MT Purchase Order, you might first deliver 2,000 MT to ADI sourced from BUSCO. Once that stock runs out, you source the next batch from CASA, continuing this process until ADI's 10,000 MT PO is fully fulfilled."*

### Key Business Goals
1. Transition from a flat 1:1 delivery paradigm to a flexible Parent-Child relationship (`PurchaseOrder` [1] $\rightarrow$ `DeliveryLedger` [N]).
2. Empower coordinators to dynamically assign different Sugar Mills (e.g. BUSCO, CASA) per delivery batch under the same PO.
3. Support variable drop-off destinations (e.g., ADI Plant, HTC Tank Facility, Balayan Warehouse) under one contracted PO.
4. Enforce strict inventory balance constraints: forbid deliveries that exceed remaining contracted metric tons.
5. Provide automatic lifecycle status progression (`Open` $\rightarrow$ `Partially Fulfilled` $\rightarrow$ `Completed`).
6. Guarantee zero breaking changes or regressions across financial settlements, invoices, and audit trails.

---

## 2. User Stories & Acceptance Criteria (Gherkin Format)

### User Story 1 (US-LOG-101): Parent PO Contract Definition
> **As an** Operations Coordinator,  
> **I want to** create a Purchase Order specifying the total contracted metric tons, customer, and reference number,  
> **So that** I have a single parent contract record against which multiple partial shipments can be tracked.

* **AC 1.1:** The PO form must accept `po_reference_number`, `customer`, and `total_contracted_mt`.
* **AC 1.2:** Initial status must be set to `Open` upon creation.
* **AC 1.3:** Backward compatibility must map existing legacy `volume_mt` records directly into `total_contracted_mt`.
* **Status:** **PASSED**

---

### User Story 2 (US-LOG-102): Incremental Delivery Logging with Dynamic Sourcing
> **As a** Dispatch Officer,  
> **I want to** log partial delivery batches against an open PO, selecting the specific sourcing sugar mill and destination for each batch,  
> **So that** stock can be fulfilled from multiple mills (e.g., BUSCO, CASA) and delivered to multiple locations (e.g., ADI, HTC Tank).

* **AC 2.1:** The delivery screen must provide a dynamic dropdown of all active Purchase Orders showing available balance in the label.
* **AC 2.2:** Each delivery record must allow selection of any active Sugar Mill supplier independently of the original cluster default.
* **AC 2.3:** Delivery destination (`receiving_location`) must be freeform with quick-selection shortcuts (ADI Plant, HTC Tank, Balayan).
* **AC 2.4:** Delivery metadata (delivery date, hauler, plate number, waybill/MDR, receiver) must be captured.
* **Status:** **PASSED**

---

### User Story 3 (US-LOG-103): Over-Delivery Validation Guard
> **As a** Risk & Inventory Manager,  
> **I want to** prevent any delivery entry whose metric tons exceed the PO's remaining balance,  
> **So that** we never over-deliver beyond contractual commitments.

* **AC 3.1:** Client-side JavaScript must calculate available balance in real time and warn the user before submission.
* **AC 3.2:** Server-side model `clean()` must reject any delivery where `delivered_mt > remaining_mt` with a validation error.
* **AC 3.3:** The RESTful API endpoint (`POST /deliveries`) must return HTTP 400 with error code `OVER_DELIVERY_NOT_PERMITTED` and the exact remaining balance.
* **Status:** **PASSED**

---

### User Story 4 (US-LOG-104): Automatic Lifecycle Progression & Real-Time Tracking
> **As a** Trading Director,  
> **I want** the system to automatically calculate remaining metric tons and advance the PO status,  
> **So that** management has instant visibility into order completion without manual bookkeeping.

* **AC 4.1:** When the first delivery ($>0$ MT and $<$ contracted MT) is logged, PO status automatically changes from `Open` to `Partially Fulfilled`.
* **AC 4.2:** When cumulative deliveries equal or exceed contracted MT, PO status automatically changes to `Completed` and remaining MT becomes 0.00 MT.
* **AC 4.3:** If a delivery record is deleted or edited downwards, the PO status and remaining MT recalculate dynamically.
* **Status:** **PASSED**

---

## 3. Test Execution Matrix & UAT Verification

All test scenarios were executed and passed across both local development and live production EC2 container environments.

| Test ID | Category | Scenario / Action | Expected Result | Result | Env |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **TC-01** | Unit | Create PO with 10,000 MT | Status is `Open`, `remaining_mt = 10,000.00` | **PASS** | Local + EC2 |
| **TC-02** | Unit | Deliver 2,000 MT from BUSCO to ADI | Status updates to `Partially Fulfilled`, `remaining = 8,000.00` | **PASS** | Local + EC2 |
| **TC-03** | Unit | Deliver 3,000 MT from CASA to HTC Tank | Status remains `Partially Fulfilled`, `remaining = 5,000.00` | **PASS** | Local + EC2 |
| **TC-04** | Unit | Deliver 5,000 MT from BUSCO to Balayan | Status transitions to `Completed`, `remaining = 0.00` | **PASS** | Local + EC2 |
| **TC-05** | Validation | Attempt to deliver 6,000 MT when balance is 5,000 MT | Model `ValidationError` raised; transaction aborted | **PASS** | Local + EC2 |
| **TC-06** | API | `POST /deliveries` with over-delivery payload | Returns HTTP 400 `OVER_DELIVERY_NOT_PERMITTED` | **PASS** | Local + EC2 |
| **TC-07** | API | `GET /deliveries/api/po-status/<ref>/` | Returns live contracted, delivered, remaining MT, and status | **PASS** | Local + EC2 |
| **TC-08** | Migration | Execute `0013` & `0014` on PostgreSQL 16 | All 16 existing POs backfilled with zero data loss | **PASS** | EC2 Prod |
| **TC-09** | UI / UX | Load `/operations/deliveries/log/` | Form renders, reactive status updates on PO change | **PASS** | EC2 Prod |
| **TC-10** | UI / UX | Load `/operations/deliveries/` list view | Master ledger displays all multi-sourced dispatches | **PASS** | EC2 Prod |
| **TC-11** | Regression | Run entire `operations` & `finance` test suite (44 tests) | 44 tests pass with 0 failures and 0 errors | **PASS** | Local |
| **TC-12** | Live EC2 | Run `IncrementalDeliveryLedgerTests` in Docker container | 4 tests pass in 3.033s | **PASS** | EC2 Prod |

---

## 4. Production Deployment Verification Record

* **Target Cloud Provider:** Amazon Web Services (AWS) EC2
* **Public IP / Domain:** `18.140.166.84` / `https://htccore.tech`
* **OS / Runtime:** Ubuntu 24.04 LTS / Docker Compose / Python 3.12 / PostgreSQL 16 Alpine
* **Git Commit Deployed:** `23e4dd5` (`origin/main`)
* **Database Migrations Applied:**
  - `operations.0013_historicalpurchaseorder_customer_and_more`
  - `operations.0014_backfill_po_and_deliveries`
* **Static Assets:** `0 static files copied, 132 unmodified` into `/app/staticfiles`
* **Container Health Verification:**
  - `app-web-1`: `Up (healthy)`, Gunicorn 26.2.0 listening on `0.0.0.0:8000`
  - `app-celery_worker-1`: `Up`, Celery background task worker healthy
  - `app-nginx-1`: `Up`, Reverse proxy healthy, returning HTTP 200/302
  - `app-db-1`: `Up (healthy)`, PostgreSQL 16 responding

---

## 5. Non-Functional & Security Review

1. **Transactional Integrity & Concurrency:**  
   Database updates are protected by database transactions (`@transaction.atomic`), eliminating risk of partial commits or ledger corruption under simultaneous trucking dispatches.
2. **Access Control & Permissions:**  
   - Creation and updates require authenticated sessions with role verification (`accounts/permissions.py`).
   - Deliveries navigation mapped to active operations permissions.
3. **Auditability:**  
   Every batch delivery record and PO status mutation creates immutable historical records via `django-simple-history`, satisfying regulatory traceability for commodity trading.

---

## 6. Formal Sign-Off & Approval Matrix

| Role | Name / Title | Sign-Off Status | Date | Signature / Note |
| :--- | :--- | :---: | :---: | :--- |
| **Product Owner** | Lead Business Analyst / PO | **APPROVED** | Oct 11, 2026 | *Meets all interview specifications for multi-mill & multi-dropoff delivery workflows.* |
| **Technical Lead** | Solutions Architect | **APPROVED** | Oct 11, 2026 | *Clean parent-child model separation with robust backward compatibility adapters.* |
| **QA Lead** | Quality Assurance Lead | **APPROVED** | Oct 11, 2026 | *100% test pass rate across unit, integration, and live container environments.* |
| **DevOps / SRE** | Cloud Infrastructure Engineer | **APPROVED** | Oct 11, 2026 | *Deployment on EC2 completed cleanly; Docker healthchecks and reverse proxy verified.* |
| **Logistics Lead** | Operations Representative | **APPROVED** | Oct 11, 2026 | *Delighted by the over-delivery guard and reactive balance panel.* |

---
*HTC Core Engineering Team — Final Agile Release Sign-off.*
