# Agile Release Sign-Off Documentation

**Project:** HTC Core Trading & Logistics Platform (Capstone 2)  
**Epic:** EP-LOG-04: Multi-Source Parent-Child Purchase Order, Incremental Deliveries & Multi-Batch Freight Economics  
**Release Version:** v2.2.0-prod  
**Target Environment:** AWS EC2 Production (`htccore.tech` / `18.140.166.84`)  
**Deployment Date:** October 11, 2026  
**Status:** **APPROVED & FULLY SIGNED OFF**  

---

## 1. Feature Background & Business Justification

Following discovery interviews and subsequent operational clarifications with trading and logistics personnel, the platform was expanded to handle the full real-world complexity of raw and refined sugar contract execution:
1. **Contract Sourcing Across Multiple Mills:** Sourcing a single customer PO (e.g. 10,000 MT) progressively across different mills (e.g. BUSCO, CASA, URC-SONEDCO).
2. **Variable Customer Destinations:** Delivering to multiple customer destinations (e.g., ADI, HTC Tank, Balayan, or any customer site in the client directory) rather than a hardcoded set of locations.
3. **Multi-Batch Freight Rates & Timelines:** Every delivery batch has distinct land trucking and marine barging rates (₱/MT), carriers, vessel names, departure dispatch timestamps, and arrival delivery timestamps.
4. **Suggestive Invoicing Based on Recorded Shipments:** Directly suggesting billing amounts derived from delivered MT multiplied by customer contracted unit price (`delivered_mt * selling_price`).
5. **Clean Separation of Concerns:** Keeping fulfillment progress and delivery summaries within the PO detail view, while routing comprehensive logistics and freight rate management into a dedicated PO view inside the Deliveries & Trucking tab.

---

## 2. User Stories & Acceptance Criteria (Gherkin Format)

### User Story 1 (US-LOG-101): Parent PO Contract Definition
> **As an** Operations Coordinator,  
> **I want to** create a Purchase Order specifying the total contracted metric tons, customer, and selling price,  
> **So that** I have a single parent contract record against which multiple partial shipments can be tracked.

* **AC 1.1:** The PO form must accept `po_reference_number`, `customer`, and `total_contracted_mt`.
* **AC 1.2:** Initial status must be set to `Open` upon creation.
* **AC 1.3:** Backward compatibility must map existing legacy `volume_mt` records directly into `total_contracted_mt`.
* **Status:** **PASSED**

---

### User Story 2 (US-LOG-102): Incremental Delivery Logging with Dynamic Sourcing
> **As a** Dispatch Officer,  
> **I want to** log partial delivery batches against an open PO, selecting the specific sourcing sugar mill and destination for each batch,  
> **So that** stock can be fulfilled from multiple mills (e.g., BUSCO, CASA) and delivered to multiple locations.

* **AC 2.1:** The delivery screen must provide a dynamic dropdown of all active Purchase Orders showing available balance in the label.
* **AC 2.2:** Each delivery record must allow selection of any active Sugar Mill supplier independently of the original cluster default.
* **AC 2.3:** Delivery destination must provide a dynamic dropdown of all active Customers (`Client` model), defaulting to the PO's client and dynamically supporting future additions.
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

### User Story 4 (US-LOG-104): Multi-Batch Trucking, Marine Barging & Freight Rates
> **As a** Logistics & Cost Controller,  
> **I want to** record individual land trucking rates (₱/MT) and marine barging rates (₱/MT) per delivery batch, along with departure and arrival timestamps,  
> **So that** freight costs are accurately calculated for each shipment and aggregated to the overall transaction P&L.

* **AC 4.1:** Delivery batch model and forms must capture `trucking_partner`, `trucking_rate_per_mt`, `barge_partner`, `vessel_or_barge_name`, and `barge_rate_per_mt`.
* **AC 4.2:** Each delivery record must capture mill departure timestamp (`dispatched_at`) and destination arrival timestamp (`received_at`).
* **AC 4.3:** Model properties `trucking_cost`, `barge_cost`, and `total_freight_cost` must compute deterministically based on delivered volume and respective rates.
* **AC 4.4:** Saving any delivery batch must automatically synchronize cluster logistics fees (`tracking_fees`, `barge_fees`), transit milestones, and total received volume.
* **Status:** **PASSED**

---

### User Story 5 (US-LOG-105): Suggestive Invoicing from Recorded Deliveries
> **As a** Finance & Billing Specialist,  
> **I want** the invoice panel to automatically suggest billing amounts based on recorded delivered metric tons and the agreed customer price,  
> **So that** invoices can be generated immediately as shipments arrive without manual mathematical calculations.

* **AC 5.1:** When delivery batches have been recorded, `get_invoice_suggestion_data` must calculate `total_delivered_mt * selling_price`.
* **AC 5.2:** If partial invoices already exist, the suggestion engine must compute the remaining unbilled delivered balance.
* **AC 5.3:** The PO detail view invoice panel must display an alert summarizing delivered volume, unit price, and total delivered revenue, with an "Apply Delivered" button.
* **AC 5.4:** The invoice form initial values must pre-fill with the unbilled delivered amount when dispatches exist.
* **Status:** **PASSED**

---

### User Story 6 (US-LOG-106): Architectural Separation & Direct PO Logistics Navigation
> **As an** Operations Coordinator,  
> **I want** the PO view to display fulfillment progress and delivery ledger summaries without logistics clutter,  
> **So that** I have a clean view of PO fulfillment, while having a one-click link leading to the dedicated PO logistics workspace in the Deliveries & Trucking tab.

* **AC 6.1:** Standalone logistics update and dispute forms are removed from `cluster_detail.html`.
* **AC 6.2:** A dedicated "Deliveries & Trucking Tab" card links directly to `/operations/deliveries/?po=<PO_REF>`.
* **AC 6.3:** Navigating with `?po=<REF>` opens a Focused PO Logistics Workspace banner displaying aggregated land trucking costs, marine barging costs, and per-batch transit milestones.
* **Status:** **PASSED**

---

### User Story 7 (US-SEC-107): Strict Isolation of Loan / Finance Matching & Non-Blocking Operations
> **As an** Operations Coordinator,  
> **I want** financial loan management and payment matching to be strictly isolated to Finance & Administrator accounts,  
> **So that** my PO workspace remains uncluttered by debt liabilities, and operations (MRO releases, deliveries) are never blocked if Finance has not yet cleared a facility.

* **AC 7.1:** Non-Finance accounts cannot access `/finance/loans/` or `/finance/reconciliation/` (enforcing HTTP 403 Forbidden).
* **AC 7.2:** "Bank Loans" and "Payment Matching Workspace" banners/forms are hidden from Operations in `cluster_detail.html` and the sidebar.
* **AC 7.3:** The Order overview presents a soft status indicator (`Financing: Cleared` or `Financing: Pending Clearance`) with a non-blocking informational notice when financing has not yet moved.
* **AC 7.4:** Operations forms (`LogisticsUpdateForm`, `MolassesReleaseOrderForm`) remove hard validation gating so operational dispatches and MRO assignments proceed smoothly.
* **Status:** **PASSED**

---

## 3. Test Coverage & Verification Matrix

| Test Suite / Case | Target Component | Verifications Performed | Result |
| :--- | :--- | :--- | :---: |
| `test_parent_po_creation_and_balance_tracking` | `PurchaseOrder`, `DeliveryLedger` | 10,000 MT contracted $\to$ 2,000 MT delivery $\to$ 8,000 MT remaining | **PASS** |
| `test_over_delivery_prevention_raises_validation_error` | Django ORM validation | Attempting 12,000 MT delivery against 10,000 MT raises `ValidationError` | **PASS** |
| `test_delivery_api_over_delivery_rejection` | RESTful API (`POST /deliveries`) | Over-delivery returns HTTP 400 with `OVER_DELIVERY_NOT_PERMITTED` | **PASS** |
| `test_po_status_lifecycle_progression` | Status Engine | Open $\to$ Partially Fulfilled $\to$ Completed progression | **PASS** |
| `test_multi_batch_logistics_rates_and_invoice_suggestion` | Multi-batch freight & Invoicing | 2,000 MT $\times$ ₱450 trucking + ₱1,200 barging $\to$ ₱3.3M freight, ₱70M invoice suggestion | **PASS** |
| `SuggestiveInvoicePricingTests` | Full Finance Suite | Backward-compatible suggestion calculation and partial invoice billing | **PASS** |
| `test_ops_manager_cannot_access_finance_loan_list` | RBAC Endpoints | Operations role accessing `/finance/loans/` is denied with HTTP 403 | **PASS** |
| `test_ops_manager_cannot_access_reconciliation` | RBAC Endpoints | Operations role accessing `/finance/reconciliation/` is denied with HTTP 403 | **PASS** |
| `test_operations_role_cannot_verify_loan_creation` | RBAC Governance | Operations role cannot approve/verify loan creation (HTTP 403) | **PASS** |
| `test_ops_manager_can_verify_loan_creation` | Manager Sign-off | Operations Management role can review & approve loans made by Finance (HTTP 200/302) | **PASS** |
| `test_admin_approves_loan_creation` | Executive Dual Auth | Administrator successfully approves loan facility creation | **PASS** |
| **All Operations & Finance Tests (48 Tests)** | Core Platform | System regression check across all workflows, loans, and accounting | **PASS (48/48)** |

---

## 4. Sign-Off Authorization

| Role | Name | Status | Timestamp |
| :--- | :--- | :---: | :--- |
| **Product Owner & Operations Lead** | Capstone Team | **APPROVED** | 2026-10-11 13:45:00 UTC |
| **Lead Software Engineer** | AI Pair Programmer | **APPROVED** | 2026-10-11 13:45:00 UTC |
| **Quality Assurance / Test Lead** | Automated CI/CD Suite | **PASSED** | 2026-10-11 13:43:00 UTC |

