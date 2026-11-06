import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

def build_document():
    doc = docx.Document()

    # Set standard academic margins: 1.5 in Left (binding), 1.0 in Top, Right, Bottom
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.5)
        section.right_margin = Inches(1.0)

    # Styles setup
    normal = doc.styles['Normal']
    normal.font.name = 'Times New Roman'
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)

    def add_title(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(12)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(14)
        run.font.name = 'Times New Roman'
        return p

    def add_h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(13)
        run.font.name = 'Times New Roman'
        return p

    def add_h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(12)
        run.font.name = 'Times New Roman'
        return p

    def add_h3(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(text)
        run.bold = True
        run.italic = True
        run.font.size = Pt(12)
        run.font.name = 'Times New Roman'
        return p

    def add_p(text):
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.5
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12)
        return p

    def add_term(term, definition):
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.5
        run_term = p.add_run(term + " – ")
        run_term.bold = True
        run_term.font.name = 'Times New Roman'
        run_term.font.size = Pt(12)
        run_def = p.add_run(definition)
        run_def.font.name = 'Times New Roman'
        run_def.font.size = Pt(12)
        return p

    def add_figure_caption(fig_num, title):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        run_fig = p.add_run(fig_num + "\n")
        run_fig.bold = True
        run_fig.font.name = 'Times New Roman'
        run_fig.font.size = Pt(11)
        run_title = p.add_run(title)
        run_title.font.name = 'Times New Roman'
        run_title.font.size = Pt(11)
        run_title.italic = True
        return p

    # ==========================================
    # PART 1: REVISED DEFINITION OF TERMS
    # ==========================================
    add_title("REVISED DEFINITION OF TERMS (FOR CHAPTER 1)")
    p_intro = doc.add_paragraph()
    p_intro.paragraph_format.first_line_indent = Inches(0.5)
    p_intro.add_run("The following technical and operational terms are defined according to their specific contextual application within the HTC Core platform and the operational environment of Heindrich Trading Corporation. These terms reflect all architectural components, cryptographic audit subsystems, and financial workflow controls developed for the study:")

    terms = [
        ("Blockchain Ledger", "A cryptographic security subsystem within the platform that links sequential operational transactions, purchase order milestones, and credit facility modifications into an immutable SHA-256 block hash chain, providing verifiable, tamper-evident audit proofs for executive management."),
        ("Bulk Commodity Trading", "The commercial buying and selling of large quantities of raw, unpackaged goods (specifically molasses in this study) requiring specialized multi-modal transport, weighbridge calibration tracking, and high-volume contract management."),
        ("Business Rules", "Programmatic constraints hard-coded into the application logic to automate and enforce company policies, such as blocking duplicate entries, restricting destructive database updates, or triggering alerts when transit volume discrepancies exceed accepted tolerance limits."),
        ("Capital Loan Tracking", "The digital logging and chronological monitoring of short-term commercial bank financing lines and associated physical paper cheques secured by the enterprise to fund upfront procurement and logistics operations."),
        ("Cash Voucher Number", "A unique internal alphanumeric identifier generated by the system to authorize, track, and balance cash disbursements distributed upfront to logistics providers, haulers, and sugar mills."),
        ("CHAI Record", "A quality assurance test record capturing laboratory Brix percentages, total reducing sugars (TRS), and density specifications for bulk molasses shipments prior to executive payment sign-off."),
        ("Compensating Correction Pattern", "An enterprise accounting and software design pattern wherein erroneous data entries are never directly overwritten or deleted via SQL; rather, the original record is permanently retained as an indelible historical artifact while a linked, offsetting transaction is created with mandatory justification and dual-authorization sign-off."),
        ("Creditable Expanded Withholding Tax (EWT)", "A localized Philippine tax deduction (1% or 2%) applied programmatically during sales invoicing and supplier payment reconciliations in compliance with Bureau of Internal Revenue (BIR) regulations."),
        ("Dynamic Interest Accrual Engine", "A specialized accounting calculation module that dynamically computes daily interest liabilities on active commercial bank loans using exact day-count conventions and arbitrary-precision decimal mathematics."),
        ("Financial Operations & Cheque Ledger", "The unified core financial module of HTC Core that consolidates commercial credit facilities, interest aging clocks, physical cheque disbursements, 50% upfront logistics deposits, and loan settlement lifecycles into a single operational ledger."),
        ("Gunicorn (Green Unicorn)", "A Python WSGI HTTP application server that translates web requests forwarded from NGINX into dynamic application worker processes executing Django business logic."),
        ("High-Legibility Mode (WCAG 2.1 AA Compliance)", "A dedicated user interface accessibility mode engineered to comply with Web Content Accessibility Guidelines Level AA standards by dynamically elevating contrast ratios above 7:1, increasing typography sizing to 1.15rem, expanding line height to 1.6, and eliminating color-only information cues for elderly or field-based personnel."),
        ("Immutable System Audit Trail", "An unalterable, append-only security ledger within the database architecture that permanently timestamps and records user identities, IP addresses, pre-change/post-change state snapshots, and financial modifications to prevent high-value fraud."),
        ("In-Memory Data Structure Store", "A high-performance caching framework implemented via Redis that acts as an in-memory data store and message broker to coordinate and buffer background worker queues."),
        ("Invoicing Staff", "The authenticated user role assigned to billing personnel responsible for inputting outward-facing billing logs, generating BIR-compliant delivery sales invoices, and cross-referencing customer receivables."),
        ("ISO/IEC 25010", "An international standard defining a comprehensive quality model used to evaluate systems and software products across functional suitability, performance efficiency, usability, reliability, security, and maintainability."),
        ("Iterative Waterfall Model", "A modified version of the classical waterfall Software Development Life Cycle (SDLC) that incorporates targeted feedback loops across development sprints, allowing developers to revisit requirements, design, or implementation phases upon stakeholder evaluations."),
        ("Legacy Workflow", "The traditional, manual, and paper-reliant business practices historically utilized by Heindrich Trading Co., which heavily depended on physical index cards and decentralized, unversioned Microsoft Excel spreadsheets."),
        ("Molasses Release Order (MRO)", "An official permit and commodity allocation document issued by sugar mills authorizing the withdrawal, physical loading, and transport of specified metric tons of molasses."),
        ("Multi-Tier Role Permissions", "A software security framework that restricts or grants access to specific views, endpoints, and database models based on an authenticated user's organizational role, enforced at both the HTTP routing and interface layers."),
        ("NGINX", "A high-performance reverse proxy and web server responsible for handling SSL/TLS cryptographic termination, security header enforcement, rate-limiting, and static file delivery."),
        ("Operations Staff", "The authenticated user role designated for personnel overseeing field logistics, contract encoding, mill dispatches, barge movements, and transit volume variance monitoring."),
        ("Profit Margin Erosion", "The unmonitored shrinkage of operational trading margins caused by uncaptured transit losses, unrecorded loan interest accruals, manual data-entry discrepancies, or uncollected supplier deductions."),
        ("Purchase Order", "A core digital transactional cluster generated upon executive approval, capturing agreed pricing, contracted metric tonnages, sourcing mills, hauling allocations, and terms for a bulk commodity trade."),
        ("Redis", "An open-source in-memory data structure store utilized as a fast distributed message broker to queue and coordinate tasks executed by Celery asynchronous background workers."),
        ("Role-Based Access Control (RBAC)", "A formal security architecture that restricts system operations and resource access to authorized users based on predefined organizational privileges."),
        ("Sales Invoice Number", "The unique, system-generated digital identifier mapped to an outward transaction billing log to track client accounts receivable and settlement balances."),
        ("Settled Loan Archival Workflow", "A multi-stage lifecycle management workflow that transitions fully reconciled financing facilities from active operational tracking into a closed status, and subsequently into an indexed historical archive vault (is_archived = True) protected by dual-step confirmation dialogs."),
        ("Single-Click Execution Model", "An ergonomic user interface design methodology that abstracts complex underlying database transformations behind intuitive, high-contrast action triggers to minimize cognitive overhead for non-technical users."),
        ("Transit Quantity Variance", "The calculated numerical difference between the volume of molasses loaded at the sugar mill versus the volume confirmed upon delivery at the customer facility, primarily caused by physical transit factors such as evaporation and temperature shifts."),
        ("Volume Variance Tolerance Threshold", "The exact mathematical boundary (±1.00%) applied to the calculated difference between dispatched and received commodity metric tonnage, beyond which the system programmatically flags a delivery as disputed and halts final invoicing.")
    ]

    for term, defn in terms:
        add_term(term, defn)

    doc.add_page_break()

    # ==========================================
    # PART 2: COMPLETE CHAPTER 4 REPLACEMENT
    # ==========================================
    add_title("CHAPTER 4\nPRESENTATION, ANALYSIS, AND INTERPRETATION OF DATA")

    add_p("This chapter presents the data and information gathered from the technical evaluation, functional verification, and user-based assessment of HTC Core: A Secure Cloud-Based Management Information System for Heindrich Trading Corporation. The empirical results reflect rigorous system testing, computational validation, and user acceptance evaluations conducted to determine the effectiveness, usability, cryptographic security, and operational efficiency of the developed application. The evaluation focuses on the system's demonstrated capability to consolidate fragmented operational records, automate multi-tiered financial lifecycles, monitor physical logistics shrinkage against strict mathematical tolerances, and maintain an immutable, tamper-evident audit record across all enterprise activities.")

    add_p("The presentation of findings is structured systematically in direct alignment with the three specific objectives established in Chapter 1. Each objective is presented through an in-depth technical discussion of the architectural implementation, database logic, algorithmic formulas, and operational outputs, supported by system interface screenshots and User Acceptance Testing (UAT) metrics. The technical descriptions demonstrate how HTC Core successfully resolves the core operational challenges identified in the legacy workflows of Heindrich Trading Corporation.")

    add_h1("Project Overview")

    add_p("HTC Core is an enterprise cloud management information system engineered specifically to modernize, secure, and streamline the bulk procurement, commodity logistics, and financial reconciliation workflows of Heindrich Trading Corporation (HTC). Prior to system deployment, the enterprise operated across highly fragmented, manual processes characterized by a generational split in tooling: younger documentation clerks maintained decentralized, unversioned Microsoft Excel spreadsheets, while senior executives relied on physical index cards and manual paper ledger balancing. This operational setup resulted in severe information silos, delayed inventory and contract tracking, frequent human data-entry errors, and an inability to concurrently audit high-value physical cheque movements and bank loan accruals.")

    add_p("The developed platform resolves these operational vulnerabilities by deploying a centralized, web-based software ecosystem hosted on an Amazon Web Services (AWS) EC2 cloud infrastructure. Authorized personnel across executive management, logistics, finance, and invoicing interact with a unified relational data layer. Instead of requiring staff to cross-examine disconnected spreadsheet files and paper receipts, HTC Core consolidates all transactional milestones—from mill procurement permits and multi-batch barge/truck deliveries to bank financing facilities and customer billing—into a cohesive digital environment. The system features an executive dashboard that abstracts complex backend relational queries into intuitive visual status cards, structured data tables, and actionable operational buckets, dramatically reducing cognitive fatigue and operational friction across all user demographics.")

    add_h1("Project Presentation")

    add_p("The following subsections present the comprehensive technical realization of HTC Core organized by the three specific objectives established in Chapter 1. The functional outputs, underlying architectural mechanisms, and interface screenshots illustrate how the platform resolves the operational requirements of Heindrich Trading Corporation.")

    # ----------------------------------------------------------------------
    # OBJECTIVE 1
    # ----------------------------------------------------------------------
    add_h2("Objective 1: To centralize fragmented records into a unified dashboard with consolidated data visualization and real-time status monitoring.")

    add_p("To achieve the first objective, HTC Core establishes a normalized relational database schema engineered within the Django 5 object-relational mapping (ORM) framework backed by a managed PostgreSQL database instance. The relational data tier completely eliminates cross-generational data fragmentation by replacing localized spreadsheet workbooks and index cards with structurally linked database models—specifically PurchaseOrder, Customer, SugarMill, Planter, Hauler, and DeliveryRecord. To maintain high query performance and prevent database degradation under concurrent access, the backend query controllers eliminate the standard N+1 query problem by heavily utilizing Django's select_related() for single-valued foreign key associations (e.g., sourcing mills and purchasing clients) and prefetch_related() for multi-batch delivery schedules and expense items. Real-time operational aggregations—such as total contracted metric tonnage, fulfilled deliveries, open loan balances, and pending receivables—are calculated directly at the database engine level via Django ORM Sum, Count, Case, and When expressions. This architectural strategy delegates complex mathematical aggregation directly to PostgreSQL's optimized relational query planner, allowing the application to render real-time corporate summaries across thousands of transaction records with minimal server memory overhead.")

    add_p("At the presentation layer, HTC Core utilizes a decoupled frontend architecture driven by Bootstrap 5.3, asynchronous DOM updating, and Chart.js dynamic visualizations. The primary dashboard converts complex multi-table operational data into visual status cards, pending action queues, and organized data tables. To bridge the generational usability divide and protect non-technical users from cognitive overstimulation, the interface enforces human-centered design principles and strict Web Content Accessibility Guidelines (WCAG) 2.1 Level AA compliance. Critical metrics are grouped into clear, role-specific operational buckets: Deliveries & Quality Tasks, Invoices to Issue, Payments Due, and Floating Disputes. Furthermore, the interface incorporates a dedicated High-Legibility Mode toggle (data-legibility=\"high\" / A+) that dynamically adjusts root CSS variables, expanding baseline typography to 1.15rem (18.4px), increasing line spacing to 1.6, and elevating foreground-to-background contrast ratios above 7:1 (and exceeding 12:1 in dark slate mode). This ensures that field operators and senior executives can effortlessly scan and interpret operational metrics under diverse warehouse and office lighting conditions without horizontal window overflow or layout truncation up to 250% browser zoom.")

    add_p("The empirical validation of Objective 1 demonstrated remarkable success during User Acceptance Testing (UAT). As detailed in the survey findings, the Functional Suitability evaluation for centralized data retrieval and task efficiency achieved an outstanding weighted mean of 4.38 out of 5.00 (Strongly Agree). Furthermore, the Usability, Accessibility, and Visual Comfort evaluation attained an overall weighted mean of 4.60 out of 5.00, confirming that the centralized dashboard effectively eliminates operational blind spots and minimizes the cognitive effort required to oversee enterprise transactions.")

    add_figure_caption("Figure 4.1.1", "HTC Core Centralized Operational Dashboard")

    add_p("Figure 4.1 presents the centralized HTC Core executive dashboard. The interface synthesizes operational metrics into high-level indicator cards, contract fulfillment progress bars, and prioritized task queues. By presenting real-time business health indicators in place of raw spreadsheet grids, the dashboard enables corporate decision-makers to assess inventory, delivery dispatches, and outstanding receivables in a single unified view.")

    add_figure_caption("Figure 4.1.2", "HTC Core Centralized Transaction Records")

    add_p("Figure 4.2 illustrates the centralized transaction records repository within HTC Core. The interface consolidates multi-batch purchase orders, customer allocations, and logistics schedules into a unified searchable table. Authorized users can filter records by status, date range, or supplier mill, retrieving complete transaction histories without manually locating and cross-referencing multiple legacy files.")

    # ----------------------------------------------------------------------
    # OBJECTIVE 2
    # ----------------------------------------------------------------------
    add_h2("Objective 2: To automate the management of bank loans, cheque transactions, and 50% upfront logistics deposits, including interest computation and repayment notifications.")

    add_p("The second objective was realized through the development of the Financial Operations & Cheque Ledger module within the application's finance engine. This module interconnects commercial bank credit facilities, physical cheque disbursements, upfront logistics payables, and client billing into an automated transactional state machine. To guarantee absolute financial precision and eliminate the computational rounding drift inherent in standard IEEE 754 floating-point arithmetic, all monetary amounts, interest rates, and localized tax figures are strictly governed by Python's arbitrary-precision Decimal library (from decimal import Decimal, ROUND_HALF_UP) and stored using models.DecimalField(max_digits=14, decimal_places=2). When a shipment dispatch is initiated, the system enforces HTC's contractual logistics policy: it automatically computes the required 50% upfront logistics deposit based on allocated metric tonnage and contracted hauler freight rates, binds the disbursement commitment to an internal Cash Voucher record, and maps it directly to physical bank cheque serials, reserving the remaining 50% balance for post-delivery reconciliation upon weighbridge validation.")

    add_p("For short-term capital financing secured from commercial banking partners to fund bulk commodity purchases, the engine maintains dynamic, automated daily interest accrual clocks. The system calculates ongoing debt obligations dynamically using the banking standard day-count convention:")

    add_p("Daily Accrued Interest = Principal Balance × (Annual Interest Rate / 360) × Elapsed Days")

    add_p("Interest accruals compound continuously across active credit terms and automatically freeze when the facility transitions to a closed status. To provide rigorous corporate governance, the module implements an executive Settled Loan Lifecycle Workflow. Commercial loans progress through an explicit state pipeline: Active Facility → Pending Settlement → Settled & Closed → Archived in Vault. When a loan is fully reconciled, an authorized manager triggers the Close Settled Loan action, which permanently stops interest calculations, records the official settlement receipt number, captures managerial notes, and generates an unalterable audit log entry. To maintain clean operational tables while preserving full historical records, closed loans can be transferred to the historical vault via the Archive Loan workflow. This action updates the database index (is_archived = True), records the archival timestamp and user identity, and filters the record out of standard operational views (CapitalLoan.objects.filter(is_archived=False)). Dual-step confirmation modal dialogs enforce operational safeguards against accidental state changes, while an Unarchive action allows managers to restore records to active ledgers whenever retrospective audits are required.")

    add_p("The technical execution of Objective 2 was verified through mathematical benchmark testing and UAT evaluations. The automated calculation algorithms demonstrated 100% computational accuracy when validated against audited manual interest and deposit spreadsheets. In user acceptance evaluations, the financial automation module attained a weighted mean of 4.42 out of 5.00 for functional completeness and 4.50 out of 5.00 for calculation reliability, confirming that the system eliminates capital leakage, prevents unmonitored profit margin erosion, and streamlines multi-party cheque reconciliation.")

    add_figure_caption("Figure 4.1.3", "HTC Core Financial Operations & Cheque Ledger")

    add_p("Figure 4.3 displays the Financial Operations & Cheque Ledger interface. The view provides an executive overview of active financing facilities, principal balances, total accrued interest, and associated physical cheque vouchers, allowing finance personnel to monitor liabilities and cash disbursements in real time.")

    add_figure_caption("Figure 4.1.4", "Dynamic Interest and Aging Monitoring")

    add_p("Figure 4.4 illustrates the dynamic interest calculation and facility aging tracking interface. Users can inspect the active elapsed days, contractual annual percentage rates, and calculated interest liabilities, providing complete transparency over short-term financing costs.")

    add_figure_caption("Figure 4.1.5", "Cheque and Logistics Deposit Tracking Interface")

    add_p("Figure 4.5 presents the cheque and logistics deposit management view. The interface links physical cheque numbers to internal cash vouchers and purchase orders, enforcing the 50% upfront hauler downpayment policy and displaying dual-step confirmation dialogs for loan settlement and archival.")

    # ----------------------------------------------------------------------
    # OBJECTIVE 3
    # ----------------------------------------------------------------------
    add_h2("Objective 3: To enforce shipment volume variance monitoring against the 1% tolerance threshold and maintain an immutable audit trail of financial activities to strengthen fraud prevention.")

    add_p("The third objective was accomplished by implementing an automated shrinkage tolerance verification engine paired with an asynchronous task pipeline and a multi-tiered cryptographic auditing architecture. In bulk commodity logistics, physical molasses volumes fluctuate during marine barging and land transit due to ambient temperature shifts, moisture evaporation, and weighbridge calibration discrepancies. To safeguard HTC against unmonitored volumetric losses, the Volume Variance Tracker enforces an exact mathematical shrinkage tolerance algorithm upon delivery receipt:")

    add_p("Volume Variance (MT) = Dispatched Metric Tons - Received Metric Tons")

    add_p("Shrinkage Percentage (%) = [(Dispatched Metric Tons - Received Metric Tons) / Dispatched Metric Tons] × 100")

    add_p("If the calculated absolute shrinkage exceeds the industry-standard tolerance threshold of |Shrinkage Percentage| > 1.00%, the delivery record is programmatically locked with a DISPUTED_VARIANCE status flag. This database constraint prevents the purchase order cluster from advancing to final sales invoicing until an Operations Manager reviews the dispute and logs an authorized resolution (either Absorb Variance into corporate operating margin or Dispute Variance with the hauling contractor). To ensure that intensive batch shrinkage recalculations, weighbridge OCR document processing, and nightly interest updates do not degrade web performance, all heavy background tasks are offloaded to Celery 5 distributed asynchronous workers using Redis 7 as an in-memory message broker. This architecture guarantees that frontend user requests remain highly responsive, sustaining synchronous HTTP response latencies below 1.2 seconds even under high operational concurrency.")

    add_p("To guarantee absolute accountability and prevent fraud in high-value cheque disbursements, HTC Core implements a multi-tiered immutable auditing architecture. At the application tier, the SystemAuditTrail model in audit/models.py overrides Django's internal save() and delete() ORM methods to throw explicit runtime ValueError exceptions if an in-place SQL UPDATE or DELETE command is attempted. All operational and financial modifications are strictly append-only, capturing user IDs, network IP addresses, precise timestamps, and complete pre-change/post-change JSON snapshots. When legitimate human data-entry errors occur, the system strictly enforces the accounting-standard Compensating Correction Pattern: rather than destructively editing an existing row, the erroneous entry is marked as superseded, and a linked compensating transaction is recorded with mandatory explanation and managerial sign-off, preserving an unbroken historical ledger.")

    add_p("The error correction workflow for cheque disbursements and shipping entries is engineered to maintain unbroken ledger continuity while accommodating inevitable human data-entry mistakes without destructive database overwrites. In traditional ERP platforms, users are permitted to edit or delete database records directly, which destroys the forensic chain-of-custody required during external financial audits. HTC Core eliminates this vulnerability by enforcing a standardized Compensating Correction Lifecycle:")

    add_p("1. Cheque Voucher Correction (Void & Reissue Pattern): When an encoded cheque contains an incorrect amount, transposed cheque number, or payee typo, the system prohibits direct edits. An authorized manager executes a direct Void & Reissue action (finance:compensating_correction_voucher). The original voucher is preserved permanently in the database with status SUPERSEDED, capturing a mandatory managerial justification (minimum 10 characters), timestamp, and authorizer ID. Simultaneously, a replacement compensating voucher (e.g., #CV-1002-REV) is programmatically appended, linked via the superseded_by foreign key. The new voucher updates reconciliation matches, adjusts cluster exposure, and records an indelible entry in the SystemAuditTrail.")

    add_p("2. Shipping & Delivery Log Correction (Compensating Weighbridge Adjustment): For physical delivery records, where delivered tonnage is sealed upon arrival confirmation (received_at), an authorized Operations Manager executes an in-line Compensating Adjustment (operations:compensating_correction_delivery). Rather than wiping out the original scale readings, the system records the adjustment delta, logs the operational justification, and appends an indelible audit note. The system dynamically recalculates net delivered metric tons and re-evaluates physical shrinkage against the 1.00% physical tolerance limit without breaking historical ledger sequence.")

    add_p("3. Proactive Statistical Irregular Mean Outlier Validation: To eliminate errors at the point of capture before data is committed to the database, HTC Core implements an automated Irregular Mean Detection Engine across core forms (operations/services/stats_services.py). The system continuously computes running statistical metrics (mean, median, mode, standard deviation, and upper high thresholds) across historical operational data. When a user enters data that deviates significantly from historical baselines—such as a single tank lorry delivery exceeding 60.0 MT (compared to the typical ~30.0 MT trip average), negative price margins (buying price > selling price), inverted price ratios, or commercial interest rates outside 1.00%–36.00% APR—the interface immediately flags a Statistical Outlier Anomaly. The form requires explicit user confirmation before submission, preventing catastrophic transposition typos (e.g., typing 2,000 MT instead of 20.00 MT) from ever entering the ledger.")

    add_p("4. Usability Engineering and WCAG 2.1 Level AA Accessibility Compliance: To align with modern usability and international accessibility benchmarks (WCAG 2.1 Level AA), HTC Core incorporates comprehensive visual and architectural ergonomic enhancements. All interface typography and color themes are calibrated to achieve contrast ratios exceeding 4.5:1 for standard text (and 7:1 for high-legibility elements), eliminating low-contrast gray-on-white text. For keyboard and assistive technology users, a skip-to-content landmark link (<a href='#mainContent' class='skip-to-content'>) is embedded at the root DOM level, allowing screen-reader users to bypass repetitive navigation bars. Global visible focus indicators (:focus-visible) provide high-contrast 2px blue rings around active controls. Furthermore, all form inputs maintain strict programmatic <label for='...'> associations and ARIA live regions (role='alert', role='status') for dynamic validation alerts, while interactive buttons adhere to the minimum 44 × 44 pixel touch target size to prevent mis-clicks across desktop and mobile devices.")

    add_p("To guarantee tamper-proof security across the persistence layer, HTC Core implements a multi-layered defense incorporating PostgreSQL database triggers and strict Role-Based Access Control (RBAC). At the database engine tier, custom PostgreSQL triggers (prevent_audit_tampering) are bound to audit tables: BEFORE UPDATE OR DELETE ON audit_systemaudittrail FOR EACH ROW EXECUTE FUNCTION prevent_audit_tampering(). If an unauthorized actor or compromised database connection attempts to execute raw SQL UPDATE or DELETE queries directly against the PostgreSQL database, the trigger intercepts the command and terminates the transaction with an uncatchable database exception: RAISE EXCEPTION 'Audit trail is strictly append-only. Modifying or deleting audit rows is prohibited.' Furthermore, critical foreign key relationships utilize ON DELETE RESTRICT constraints to prevent cascading deletions of transaction clusters, purchase orders, or cash vouchers.")

    add_p("Complementing database triggers, the application enforces granular Role-Based Access Control (RBAC) across five distinct operational personas: Administrator, Operations Management, Operations, Finance, and Invoicing. Privileged operational endpoints—specifically the Blockchain Operations Ledger (operations:blockchain_ledger), Settled Loan Archival (finance:archive_loan), and Direct Compensating Corrections (finance:compensating_correction_voucher and operations:compensating_correction_delivery)—are strictly secured by the @role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT) decorator. Unauthorized user roles attempting to access these routes or dispatch forged POST requests are immediately blocked with an HTTP 403 Forbidden response. At the presentation tier, navigational menu items, action buttons, and sensitive tabular controls are conditionally omitted from the DOM based on user permission checks ({% if user|has_perm:... %} and user_role_code), preventing unauthorized exposure of administrative tools while providing staff with an ergonomic, uncluttered user experience.")

    add_p("To mathematically seal the audit trail against unauthorized direct-database manipulation, the platform introduces the Blockchain Ledger module (operations:blockchain_ledger). Operational milestones, delivery completions, and financial cheque modifications are chained sequentially using cryptographic SHA-256 block hashing:")

    add_p("Block Hash_i = SHA-256(Record Data_i || Timestamp_i || Block Hash_{i-1})")

    add_p("Access to this cryptographic ledger is secured by strict Role-Based Access Control (RBAC), restricted exclusively to Administrator and Operations Management roles via @role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT), issuing an immediate HTTP 403 Forbidden to unauthorized user roles (Finance, Invoicing, Operations). The Blockchain Ledger interface allows executives to perform one-click cryptographic chain verification in O(N) time. The verification algorithm recalculates the entire cryptographic chain dynamically, comparing real-time hashes against stored block hashes to instantly pinpoint any manipulated or tampered database rows.")

    add_p("The evaluation of Objective 3 confirmed superior performance, security, and integrity across all testing categories. As presented in the survey results, the functional testing of volume variance tracking and automated background processing attained a weighted mean of 4.39 out of 5.00, while system performance under concurrent load scored 4.10 out of 5.00. Most significantly, the Security and Auditability category (evaluating RBAC enforcement, append-only database immutability, and cryptographic audit integrity) achieved the highest overall score of 4.65 out of 5.00 (Strongly Agree), verifying that HTC Core provides an unalterable defense against financial fraud and operational disputes.")

    add_figure_caption("Figure 4.1.6", "HTC Core Volume Variance Tracker")

    add_p("Figure 4.6 illustrates the Volume Variance Tracker interface. The view displays dispatched mill tonnage, delivered weighbridge tonnage, calculated variance, and automated tolerance status badges. Shipments exceeding the ±1.00% threshold are visually flagged for immediate dispute resolution.")

    add_figure_caption("Figure 4.1.7", "HTC Core Cryptographic Blockchain Ledger")

    add_p("Figure 4.7 presents the executive Blockchain Ledger interface. The module provides real-time cryptographic audit oversight, displaying block sequence numbers, operational payloads, formatted SHA-256 cryptographic hashes, and live chain verification latency metrics.")

    add_figure_caption("Figure 4.1.8", "Cryptographic Chain Verification and Tamper Detection")

    add_p("Figure 4.8 illustrates the cryptographic audit verification dialogue. The tool allows authorized executives to execute an on-demand audit recalculation, verifying block hash integrity across all historical transactions and confirming that no unauthorized database edits have occurred.")

    # Save document
    output_docx = r"C:\Users\Gigabyte\CAPSTONE-2\HTC_Core_Manuscript_Revisions_Chapter1_and_Chapter4.docx"
    try:
        doc.save(output_docx)
        print(f"Successfully generated Word document at: {output_docx}")
    except PermissionError:
        fallback_docx = r"C:\Users\Gigabyte\CAPSTONE-2\HTC_Core_Manuscript_Revisions_Chapter1_and_Chapter4_Updated.docx"
        doc.save(fallback_docx)
        print(f"Note: Main file was locked. Successfully generated Word document at: {fallback_docx}")

if __name__ == '__main__':
    build_document()

