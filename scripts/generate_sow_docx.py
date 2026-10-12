import os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, hex_color):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('w:top', top), ('w:bottom', bottom), ('w:left', left), ('w:right', right)]:
        node = OxmlElement(m)
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def style_table_header(row, col_widths=None):
    for idx, cell in enumerate(row.cells):
        set_cell_background(cell, "1E3A8A") # Navy
        set_cell_margins(cell, top=120, bottom=120, left=150, right=150)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in p.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(9.5)
        if col_widths and idx < len(col_widths):
            cell.width = col_widths[idx]

def style_table_data_cells(table, col_widths=None):
    for r_idx, row in enumerate(table.rows[1:]):
        bg = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, cell in enumerate(row.cells):
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=80, bottom=80, left=140, right=140)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(30, 41, 59)
            if col_widths and c_idx < len(col_widths):
                cell.width = col_widths[c_idx]

def add_callout(doc, text, title=None, border_color="2563EB", bg_color="EFF6FF"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    # Left border only
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:top w:val="none"/>'
        f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/>'
        f'  <w:bottom w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    if title:
        r_title = p.add_run(f"{title}\n")
        r_title.bold = True
        r_title.font.size = Pt(9.5)
        r_title.font.color.rgb = RGBColor(30, 58, 138)
    r_body = p.add_run(text)
    r_body.font.size = Pt(9)
    r_body.font.italic = True
    r_body.font.color.rgb = RGBColor(51, 65, 85)

def add_sign_block(doc, left_title, left_name, left_role, right_title, right_name, right_role):
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    
    col_w = Inches(3.2)
    for c_idx, cell in enumerate(tbl.rows[0].cells):
        cell.width = col_w
        set_cell_background(cell, "F8FAFC")
        set_cell_margins(cell, top=140, bottom=140, left=160, right=160)
        tcPr = cell._tc.get_or_add_tcPr()
        borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'  <w:top w:val="single" w:sz="6" w:color="CBD5E1"/>'
            f'  <w:left w:val="single" w:sz="6" w:color="CBD5E1"/>'
            f'  <w:bottom w:val="single" w:sz="6" w:color="CBD5E1"/>'
            f'  <w:right w:val="single" w:sz="6" w:color="CBD5E1"/>'
            f'</w:tcBorders>'
        )
        tcPr.append(borders)
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        if c_idx == 0:
            p_badge = p.add_run(f"DEVELOPER SIGN-OFF: {left_title}\n")
            p_badge.bold = True
            p_badge.font.size = Pt(8.5)
            p_badge.font.color.rgb = RGBColor(37, 99, 235)
            
            p.add_run(f"Representative: {left_name}\n")
            p.add_run(f"Designation: {left_role}\n\n")
            p.add_run("Signature: ___________________________\n")
            p.add_run("Date Signed: _____ / _____ / 2026")
        else:
            p_badge = p.add_run(f"CLIENT SIGN-OFF: {right_title}\n")
            p_badge.bold = True
            p_badge.font.size = Pt(8.5)
            p_badge.font.color.rgb = RGBColor(22, 101, 52)
            
            p.add_run(f"Representative: {right_name}\n")
            p.add_run(f"Designation: {right_role}\n\n")
            p.add_run("Signature: ___________________________\n")
            p.add_run("Date Signed: _____ / _____ / 2026")

def build_docx():
    doc = Document()
    
    # Page setup: Standard Letter, 0.75" margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
        
        # Header & Footer
        header = section.header
        p_hdr = header.paragraphs[0]
        p_hdr.text = "HTC Core — Scope of Work, Agile Milestone Acceptance & System Requirements"
        p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_hdr.runs[0].font.size = Pt(8)
        p_hdr.runs[0].font.color.rgb = RGBColor(148, 163, 184)
        
        footer = section.footer
        p_ftr = footer.paragraphs[0]
        p_ftr.text = "Heindrich Trading Corporation (HTC) — Capstone 2 Project Documentation | Confidential"
        p_ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_ftr.runs[0].font.size = Pt(8)
        p_ftr.runs[0].font.color.rgb = RGBColor(148, 163, 184)

    # Document Title Block
    p_org = doc.add_paragraph()
    r_org = p_org.add_run("HEINDRICH TRADING CORPORATION (HTC)")
    r_org.font.bold = True
    r_org.font.size = Pt(11)
    r_org.font.color.rgb = RGBColor(37, 99, 235)
    p_org.paragraph_format.space_after = Pt(2)

    p_title = doc.add_paragraph()
    r_title = p_title.add_run("PROJECT MASTER SPECIFICATION:\nSCOPE OF WORK, AGILE MILESTONE ACCEPTANCE & SYSTEM REQUIREMENTS")
    r_title.bold = True
    r_title.font.size = Pt(18)
    r_title.font.color.rgb = RGBColor(15, 23, 42)
    p_title.paragraph_format.space_after = Pt(4)

    p_sub = doc.add_paragraph()
    r_sub = p_sub.add_run("Platform: HTC Core Trading & Logistics Management System (Capstone 2)\nRelease: v2.3.0-prod | Production Host: https://htccore.tech/ | Date: October 12, 2026")
    r_sub.font.size = Pt(9.5)
    r_sub.font.color.rgb = RGBColor(71, 85, 105)
    p_sub.paragraph_format.space_after = Pt(14)

    # Document Control Table
    doc.add_heading("Document Control & Revision History", level=2)
    tbl_ctrl = doc.add_table(rows=6, cols=5)
    tbl_ctrl.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Version", "Release Date", "Author / Role", "Summary of Deliverable / Changes", "Status"]
    for i, h in enumerate(headers):
        tbl_ctrl.cell(0, i).text = h
    style_table_header(tbl_ctrl.rows[0], [Inches(0.8), Inches(1.1), Inches(1.3), Inches(2.6), Inches(1.0)])

    rows_data = [
        ("v1.0.0", "2026-06-20", "Lead Architect", "Initial Project Inception & Master Data Architecture", "Approved"),
        ("v1.5.0", "2026-10-03", "Full-Stack Team", "Phase 1.5 UAT Execution, MRO Linking, Elderly Usability (A+)", "Approved"),
        ("v2.0.0", "2026-10-10", "Systems Architect", "Multi-Batch Delivery Ledger, Freight Rates & Suggestive Invoicing", "Approved"),
        ("v2.2.0", "2026-10-11", "Lead Engineer", "EC2 Production Deployment, Dual-Auth Loan Approval, Strict Isolation", "Approved"),
        ("v2.3.0", "2026-10-12", "Full-Stack Team", "AWS Textract Document AI OCR, PO View Manual Input & Scan Preview", "FINAL SIGN-OFF"),
    ]
    for r_idx, data in enumerate(rows_data):
        row = tbl_ctrl.rows[r_idx + 1]
        for c_idx, val in enumerate(data):
            row.cells[c_idx].text = val
    style_table_data_cells(tbl_ctrl, [Inches(0.8), Inches(1.1), Inches(1.3), Inches(2.6), Inches(1.0)])

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # =========================================================================
    # SECTION I: SCOPE OF WORK (SOW)
    # =========================================================================
    doc.add_heading("Section I: Scope of Work (SOW)", level=1)
    
    p = doc.add_paragraph()
    p.add_run("1.1 Business Background & Project Objectives\n").bold = True
    p.add_run(
        "Heindrich Trading Corporation (HTC) engages in commercial bulk commodity trading of raw sugar, refined sugar, "
        "and molasses across the Philippines, sourcing directly from partner sugar mills (BUSCO, Hawaiian-Philippine, "
        "BISCOM, CASA, Lopez Sugar, URC-SONEDCO) and distributing to premier industrial food and beverage manufacturers "
        "(San Miguel Corporation, Ginebra San Miguel, Distileria Bago, Universal Robina, ADI). Prior manual workflows "
        "relied on fragmented spreadsheets, creating risks of transit shrinkage exceeding 1.0%, untracked freight rates, "
        "delayed customer billing, and disjointed release permits.\n\n"
        "The Scope of Work for HTC Core encompasses the complete engineering, validation, and cloud deployment of an "
        "integrated web application automating the procurement-to-cash lifecycle."
    )
    
    doc.add_heading("1.2 In-Scope Functional Modules", level=2)
    modules = [
        ("Module 1: Master Data Management (MDM)", "Relational directories for Clients, Sugar Mills, Planter Associations, and Logistics Freight Partners with active/inactive status and validation governance."),
        ("Module 2: Parent Purchase Orders & Sourcing Clusters", "Parent PO contract definition (contracted metric tons, selling price, purchasing cost, quality specs), sourcing transaction clusters, and auto-generated reference codes (PO-YYYYMMDD-XXX)."),
        ("Module 3: Incremental Multi-Batch Delivery Ledger", "Partial delivery tracking fulfilling parent POs, dynamic multi-mill sourcing per batch, dynamic destination selection, and automated over-delivery rejection guards."),
        ("Module 4: Multi-Batch Freight Rates & Transportation Economics", "Per-batch land trucking and marine barging rates (₱/MT), carrier attribution, vessel identification, mill departure / destination arrival timestamps, and automated logistics fee synchronization."),
        ("Module 5: Molasses Release Order (MRO) Permitting & Document AI", "Digital MRO ledger, cluster permit binding, AWS Textract Document AI OCR parsing, PO-level manual input matching HTC system form, instant client-side scan preview (PDF/Image), and in-page document modal viewer."),
        ("Module 6: Financial Treasury, Capital Loans & Reconciliation", "Capital loan facility tracking, dynamic daily interest accruals, executive dual-authorization verification, suggestive invoicing (delivered_mt * selling_price), cash expense vouchers, and 3-step payment matching."),
        ("Module 7: Access Governance, Assistive AI & Usability", "Seven RBAC roles, administrative registration approval, TOTP 2FA, immutable audit trail (django-simple-history), HTC Copilot natural language assistant, and High-Legibility Elderly Usability Mode (A+) with 17px body base and 48px touch targets."),
    ]
    for m_title, m_desc in modules:
        p_m = doc.add_paragraph()
        r1 = p_m.add_run(f"• {m_title}: ")
        r1.bold = True
        r1.font.color.rgb = RGBColor(30, 58, 138)
        p_m.add_run(m_desc)

    doc.add_heading("1.3 In-Scope Cloud Infrastructure & DevOps", level=2)
    p_dev = doc.add_paragraph()
    p_dev.add_run(
        "• Docker Compose Microservices: Multi-container stack (web, celery_worker, celery_beat, db, redis, nginx).\n"
        "• Amazon EC2 Production Host: Ubuntu 24.04 LTS host (18.140.166.84) with Elastic IP mapping.\n"
        "• Edge Routing & Security: Nginx 1.27 reverse proxy with Let's Encrypt TLS/SSL encryption (https://htccore.tech/).\n"
        "• Asynchronous Queue & DB: Redis 7 broker, Celery worker for OCR offloading, and PostgreSQL 16 on persistent EBS storage.\n"
        "• Deployment Automation: Production bash script (scripts/deploy_ec2.sh) automating git pull, container builds, migrations, and static asset collection."
    )

    doc.add_heading("1.4 Explicit Out-of-Scope Boundaries", level=2)
    p_out = doc.add_paragraph()
    p_out.add_run(
        "To prevent scope creep, the following elements are explicitly OUT OF SCOPE:\n"
        "1. Direct automated core-banking API scraping or direct electronic wire fund execution (bank receipts are verified via reference vouchers).\n"
        "2. Direct IoT telemetry integration with physical weighbridge scale hardware (certified weighbridge tickets are inputted).\n"
        "3. Live satellite GPS transponder feeds from marine barges (transit milestones recorded via departure/arrival logs).\n"
        "4. Automated bidirectional synchronization with third-party external ERPs (SAP/QuickBooks); platform provides native self-balancing ledgers with CSV export."
    )

    doc.add_heading("1.5 SOW Formal Sign-Off Agreement", level=2)
    add_callout(
        doc,
        "By signing below, Heindrich Trading Corporation and the Capstone 2 Engineering Team formally agree that the scope described "
        "above represents the full, agreed-upon operational boundaries of the HTC Core platform and has been delivered in full.",
        title="STATEMENT OF SCOPE ACCEPTANCE"
    )

    # Formal SOW Sign-Off Table
    tbl_sow = doc.add_table(rows=4, cols=2)
    tbl_sow.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_w = Inches(3.3)
    
    sow_signatories = [
        ("Client Executive Sponsor", "Heindrich Trading Corporation", "Lead Systems Architect", "Capstone Engineering Team"),
        ("Client Operations Lead", "Heindrich Trading Corporation", "Lead Full-Stack Developer", "Capstone Engineering Team"),
        ("Client Finance Officer", "Heindrich Trading Corporation", "DevOps & QA Lead", "Capstone Engineering Team"),
    ]
    for idx, (c_role, c_org, d_role, d_org) in enumerate(sow_signatories):
        row = tbl_sow.rows[idx + 1]
        cell_c, cell_d = row.cells[0], row.cells[1]
        for cell, role, org, prefix in [(cell_c, c_role, c_org, "CLIENT"), (cell_d, d_role, d_org, "DEVELOPER")]:
            set_cell_background(cell, "F8FAFC")
            set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
            p = cell.paragraphs[0]
            p.add_run(f"[{prefix}] {role}\n").bold = True
            p.add_run(f"Organization: {org}\n")
            p.add_run("Signature: ___________________________\n")
            p.add_run("Date: _____ / _____ / 2026")
    
    # Header for SOW sign table
    tbl_sow.cell(0, 0).text = "CLIENT STAKEHOLDERS (HTC)"
    tbl_sow.cell(0, 1).text = "DEVELOPMENT TEAM (CAPSTONE 2)"
    style_table_header(tbl_sow.rows[0], [col_w, col_w])

    doc.add_page_break()

    # =========================================================================
    # SECTION II: AGILE DEVELOPMENT METHODOLOGY & PER-MILESTONE SIGN-OFF
    # =========================================================================
    doc.add_heading("Section II: Agile Development Methodology & Per-Milestone Sign-Off", level=1)
    
    p_agile = doc.add_paragraph()
    p_agile.add_run(
        "The project adopted an empirical Agile / Scrum framework structured into five (5) progressive Milestones. "
        "Each milestone required automated test validation, stakeholder demonstration, and dual sign-off from both "
        "the Lead Developer (engineering acceptance) and Client Representatives (operational acceptance)."
    )

    milestones_data = [
        (
            "Milestone 1: Inception, Architecture & Master Data Management",
            "Weeks 1 – 3",
            "v1.0.0-rc1",
            [
                "Docker Compose multi-service containerization baseline.",
                "Relational schema for Clients, Sugar Mills, Planters, and Haulers.",
                "Custom User authentication model with 7 RBAC roles and admin approval gating.",
                "TOTP Two-Factor Authentication (2FA) with QR code setup and single-use emergency recovery codes.",
            ],
            "14 Unit Tests Passed (100% pass rate). Zero security vulnerabilities identified.",
            ("Lead Systems Architect", "Capstone Team", "Lead Systems Architect"),
            ("Client Project Lead", "HTC Representative", "Client Project Manager")
        ),
        (
            "Milestone 2: Operations Engine, Parent POs & Incremental Delivery Ledger",
            "Weeks 4 – 7",
            "v1.5.0-rc2",
            [
                "Parent Purchase Order contract modeling with dynamic remaining balance tracking.",
                "Incremental multi-batch delivery ledger fulfilling parent contracts across multiple sourcing mills.",
                "Real-time volume variance calculation flagging shrinkage > 1.0% with dispute banners.",
                "Multi-batch freight rate economics capturing trucking (₱/MT), barging (₱/MT), and vessel tracking.",
                "Strict over-delivery guard preventing dispatches exceeding remaining contracted volume.",
            ],
            "18 Unit Tests Passed (100% pass rate). Over-delivery validation verified at model and API levels.",
            ("Lead Software Engineer", "Capstone Team", "Lead Full-Stack Developer"),
            ("HTC Operations Manager", "Heindrich Trading Corp.", "Head of Operations & Dispatch")
        ),
        (
            "Milestone 3: Financial Treasury, Capital Loans & Reconciliation",
            "Weeks 8 – 11",
            "v2.0.0-rc1",
            [
                "Capital sourcing loan facilities with dynamic daily interest accruals calculated from elapsed days.",
                "Dual-Authorization executive governance requiring admin verification to activate loan facilities.",
                "Suggestive customer invoicing engine deriving billing amounts from confirmed delivered metric tons (delivered_mt * selling_price).",
                "Cash expense vouchers across haulage, barging, milling, and operational categories.",
                "3-Step Payment Reconciliation matching customer bank payments against vouchers and loan settlements.",
                "Role-based isolation blocking operations accounts from accessing loans and reconciliation workspaces.",
            ],
            "22 Unit Tests Passed (100% pass rate). Financial interest formulas mathematically verified.",
            ("Lead Software Engineer", "Capstone Team", "Financial Systems Engineer"),
            ("HTC Lead Finance Officer", "Heindrich Trading Corp.", "Chief Finance Officer")
        ),
        (
            "Milestone 4: Molasses Release Orders (MRO) & Document AI OCR",
            "Weeks 12 – 14",
            "v2.2.0-rc2",
            [
                "Centralized Molasses Release Order ledger and cluster permit binding pipeline.",
                "AWS Textract Document AI OCR automated metadata extraction with confidence indicators.",
                "Method Chooser modal prompting users: Scanned Upload (OCR) vs. Manual Input vs. Existing Permit.",
                "PO View manual MRO input form matching HTC standard entry fields.",
                "Instant client-side supporting document live preview (<iframe> for PDF, <img> for images).",
                "In-page View Scan modal viewer allowing document inspection directly inside the PO detail view.",
            ],
            "28 Unit Tests Passed (100% pass rate). Direct PO creation and supporting document preview verified.",
            ("Lead Software Engineer", "Capstone Team", "Full-Stack AI Specialist"),
            ("HTC Operations Manager", "Heindrich Trading Corp.", "Operations & Logistics Lead")
        ),
        (
            "Milestone 5: Security Hardening, Elderly Usability & AWS EC2 Deployment",
            "Weeks 15 – 16",
            "v2.3.0-prod",
            [
                "High-Legibility Elderly Usability Mode (A+) with 17px body base, 48px touch targets, and contrast scaling.",
                "HTC Copilot AI Assistant processing queries locally via scoped Django ORM execution.",
                "Immutable append-only audit trail logging user actions and entity state diffs.",
                "AWS EC2 production deployment (18.140.166.84) with Nginx SSL edge and automated deploy scripts.",
                "User Acceptance Testing (UAT) completed across 12 scripts with 100% pass rate and 4.8/5.0 score.",
            ],
            "31 Unit Tests Passed (100% pass rate). Zero open Severity 1 or 2 defects. Live on https://htccore.tech/.",
            ("Lead Systems Architect", "Capstone Team", "DevOps & Cloud Lead"),
            ("Client Executive Sponsor", "Heindrich Trading Corp.", "President & General Manager")
        ),
    ]

    for m_title, m_cadence, m_ver, m_items, m_verif, dev_sig, client_sig in milestones_data:
        doc.add_heading(m_title, level=2)
        p_info = doc.add_paragraph()
        p_info.add_run(f"Sprint Cadence: {m_cadence} | Release Baseline: {m_ver}\n").bold = True
        p_info.runs[0].font.color.rgb = RGBColor(30, 58, 138)
        
        p_del = doc.add_paragraph()
        p_del.add_run("Key Milestone Deliverables:\n").bold = True
        for item in m_items:
            p_del.add_run(f"  • {item}\n")
        
        add_callout(doc, m_verif, title="TECHNICAL VERIFICATION & QUALITY EVIDENCE", border_color="16A34A", bg_color="F0FDF4")
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        
        # Per-Milestone Sign-Off Block
        add_sign_block(
            doc,
            left_title="MILESTONE ACCEPTANCE",
            left_name=dev_sig[1],
            left_role=dev_sig[2],
            right_title="CLIENT STAKEHOLDER ACCEPTANCE",
            right_name=client_sig[1],
            right_role=client_sig[2]
        )
        doc.add_paragraph().paragraph_format.space_after = Pt(8)

    doc.add_page_break()

    # =========================================================================
    # SECTION III: FUNCTIONAL REQUIREMENTS (NEEDS SPECIFICATION)
    # =========================================================================
    doc.add_heading("Section III: Functional Requirements (Needs Specification)", level=1)
    
    p_fr_intro = doc.add_paragraph()
    p_fr_intro.add_run(
        "The following matrix outlines the complete, definitive functional requirements implemented within the HTC Core platform. "
        "Each requirement maps directly to production capabilities, domain models, and acceptance criteria."
    )

    tbl_fr = doc.add_table(rows=16, cols=4)
    tbl_fr.alignment = WD_TABLE_ALIGNMENT.CENTER
    fr_headers = ["Req ID", "Functional Capability / Need", "Specification & Business Logic", "Target Module"]
    for i, h in enumerate(fr_headers):
        tbl_fr.cell(0, i).text = h
    style_table_header(tbl_fr.rows[0], [Inches(0.9), Inches(1.8), Inches(3.0), Inches(1.1)])

    fr_data = [
        ("FR-01", "User Approval Gating", "New sign-ups are inactive by default; Administrator must explicitly approve and assign RBAC role before session login is permitted.", "accounts"),
        ("FR-02", "TOTP 2FA Enforcement", "RFC 6238 compliant TOTP Two-Factor Authentication with QR code setup, time-window verification, and 5 single-use emergency recovery codes.", "accounts"),
        ("FR-03", "Master Data Directories", "Full CRUD management for Clients, Sugar Mills, Planters, and Haulers with tax ID, active flags, and entity relationships.", "masters"),
        ("FR-04", "Parent PO Contracts", "Modeling of total contracted metric tons, customer, selling price, unit purchasing cost, and quality specs with real-time remaining balance calculation.", "operations"),
        ("FR-05", "Multi-Source Sourcing Clusters", "Sourcing transaction clusters linking PO demand to mill production, auto-generating sequential PO-YYYYMMDD-XXX reference numbers.", "operations"),
        ("FR-06", "Incremental Delivery Ledger", "Tracking partial delivery batches against an open PO, allowing dynamic selection of sourcing mills and client destinations per batch.", "operations"),
        ("FR-07", "Over-Delivery Guard", "Model-level and API validation rejecting any delivery batch whose volume exceeds remaining PO contracted volume (HTTP 400 error).", "operations"),
        ("FR-08", "Multi-Batch Freight Economics", "Capturing land trucking (₱/MT) and marine barging (₱/MT) rates, carriers, vessel names, and departure/arrival timestamps per batch.", "operations"),
        ("FR-09", "1.0% Variance Shrinkage Alert", "Automatic formula calculating (Loaded MT - Received MT) / Loaded MT * 100; triggering crimson warning and dispute flag when shrinkage exceeds 1.0%.", "operations"),
        ("FR-10", "MRO Permitting & Linking", "Ledger tracking release permits, planters, and crop years; binding active permits to transaction clusters with volume allocation.", "operations"),
        ("FR-11", "AWS Textract Document AI OCR", "Automated document parsing for uploaded permit PDF/images, returning structured metadata with per-field confidence scores.", "operations"),
        ("FR-12", "PO View MRO Manual Entry & Preview", "Creating MROs directly from PO view with standard fields, supporting scan upload, instant live preview (iframe/img), and in-page modal viewer.", "operations"),
        ("FR-13", "Capital Loans & Daily Accrual", "Tracking capital sourcing loans with principal, APR, release date, and daily dynamic accrued interest: Principal * (APR/100) * (Days/365).", "finance"),
        ("FR-14", "Dual-Authorization Loan Gate", "Loan facility activation requires secondary administrative verification before funds are marked active and usable.", "finance"),
        ("FR-15", "Suggestive Customer Invoicing", "Auto-calculation of customer billing derived from confirmed delivered volume: total_delivered_mt * selling_price.", "finance"),
    ]
    for r_idx, data in enumerate(fr_data):
        row = tbl_fr.rows[r_idx + 1]
        for c_idx, val in enumerate(data):
            row.cells[c_idx].text = val
    style_table_data_cells(tbl_fr, [Inches(0.9), Inches(1.8), Inches(3.0), Inches(1.1)])

    doc.add_page_break()

    # =========================================================================
    # SECTION IV: NON-FUNCTIONAL REQUIREMENTS (QUALITY ATTRIBUTES)
    # =========================================================================
    doc.add_heading("Section IV: Non-Functional Requirements (Quality Attributes)", level=1)
    
    p_nfr_intro = doc.add_paragraph()
    p_nfr_intro.add_run(
        "Non-functional requirements specify architectural constraints, security standards, performance benchmarks, "
        "and usability criteria enforced across the system."
    )

    tbl_nfr = doc.add_table(rows=9, cols=4)
    tbl_nfr.alignment = WD_TABLE_ALIGNMENT.CENTER
    nfr_headers = ["Req ID", "Attribute Domain", "Quality Standard / Architecture Constraint", "Verification Method"]
    for i, h in enumerate(nfr_headers):
        tbl_nfr.cell(0, i).text = h
    style_table_header(tbl_nfr.rows[0], [Inches(0.9), Inches(1.5), Inches(3.2), Inches(1.2)])

    nfr_data = [
        ("NFR-01", "Performance & Latency", "Core operational pages load within 1.2 seconds; database queries optimized with select_related executing in fewer than 15 queries.", "Load Testing / APM"),
        ("NFR-02", "Asynchronous Offloading", "CPU-intensive tasks (Document AI OCR, Excel bulk parsing) are offloaded to Redis/Celery background workers without blocking HTTP threads.", "Celery Monitoring"),
        ("NFR-03", "Transport & Data Security", "Enforced TLS 1.3 encryption (HTTPS); Content-Security-Policy, CSRF tokens on all POST requests, PBKDF2 password hashing (600,000 rounds).", "OWASP Security Scan"),
        ("NFR-04", "Elderly Eye Usability", "Persistent High-Legibility Mode (A+) scaling body text to 17px base, headlines to 24-32px, and expanding buttons to 48px touch targets.", "Accessibility Audit"),
        ("NFR-05", "High Availability & Uptime", "Target 99.9% availability during business hours (07:00-19:00 PHT); Docker Compose restart policies (unless-stopped) with automated health checks.", "Uptime Monitoring"),
        ("NFR-06", "Data Precision & Accuracy", "Currency stored with Decimal(14,2); metric tonnage stored with Decimal(14,5) to prevent floating-point rounding errors.", "Unit Test Assertions"),
        ("NFR-07", "Auditability & Immutability", "Append-only activity audit trail tracking user, timestamp, table, and changed fields via django-simple-history.", "Audit Table Inspection"),
        ("NFR-08", "Disaster Recovery", "Automated nightly PostgreSQL database dumps (pg_dump) archived to persistent EBS storage; RTO < 30 min, RPO < 24 hrs.", "Backup Drill"),
    ]
    for r_idx, data in enumerate(nfr_data):
        row = tbl_nfr.rows[r_idx + 1]
        for c_idx, val in enumerate(data):
            row.cells[c_idx].text = val
    style_table_data_cells(tbl_nfr, [Inches(0.9), Inches(1.5), Inches(3.2), Inches(1.2)])

    doc.add_page_break()

    # =========================================================================
    # SECTION V: COMPREHENSIVE MASTER PROJECT SIGN-OFF
    # =========================================================================
    doc.add_heading("Section V: Comprehensive Master Project Sign-Off", level=1)
    
    add_callout(
        doc,
        "The signatures below officially confirm that the HTC Core Trading & Logistics Management Platform (Capstone 2) "
        "has completed all design, development, unit testing, User Acceptance Testing (UAT), and cloud deployment phases. "
        "The software is live, operational, and accepted without reservation by both Heindrich Trading Corporation and the Development Team.",
        title="MASTER ACCEPTANCE & HANDOVER STATEMENT",
        border_color="1E3A8A",
        bg_color="EFF6FF"
    )

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # Master Sign-Off Block (6 Signatories)
    tbl_master = doc.add_table(rows=7, cols=2)
    tbl_master.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_mw = Inches(3.3)
    
    tbl_master.cell(0, 0).text = "HEINDRICH TRADING CORPORATION (CLIENT)"
    tbl_master.cell(0, 1).text = "CAPSTONE 2 DEVELOPMENT TEAM (CONTRACTOR)"
    style_table_header(tbl_master.rows[0], [col_mw, col_mw])

    master_roles = [
        ("1. Client Executive Sponsor", "President & General Manager", "4. Lead Systems Architect", "Systems Architect & Technical Lead"),
        ("2. Client Operations Lead", "Head of Operations & Logistics", "5. Lead Full-Stack Developer", "Full-Stack Software Engineer"),
        ("3. Client Finance Officer", "Chief Finance Officer / Treasury Head", "6. DevOps & QA Lead", "Quality Assurance & Cloud Engineer"),
    ]
    for idx, (c_num_role, c_title, d_num_role, d_title) in enumerate(master_roles):
        row = tbl_master.rows[idx + 1]
        cell_c, cell_d = row.cells[0], row.cells[1]
        
        # Client side
        set_cell_background(cell_c, "F8FAFC")
        set_cell_margins(cell_c, top=120, bottom=120, left=150, right=150)
        p_c = cell_c.paragraphs[0]
        p_c.add_run(f"{c_num_role}\n").bold = True
        p_c.add_run(f"Title: {c_title}\n")
        p_c.add_run("Printed Name: ___________________________\n")
        p_c.add_run("Signature: ______________________________\n")
        p_c.add_run("Date: _____ / _____ / 2026")
        
        # Developer side
        set_cell_background(cell_d, "F8FAFC")
        set_cell_margins(cell_d, top=120, bottom=120, left=150, right=150)
        p_d = cell_d.paragraphs[0]
        p_d.add_run(f"{d_num_role}\n").bold = True
        p_d.add_run(f"Title: {d_title}\n")
        p_d.add_run("Printed Name: ___________________________\n")
        p_d.add_run("Signature: ______________________________\n")
        p_d.add_run("Date: _____ / _____ / 2026")

    output_path = os.path.join("docs", "HTC_Core_Scope_of_Work_Agile_Milestones_and_Requirements.docx")
    doc.save(output_path)
    print(f"Document successfully created at: {output_path}")

if __name__ == "__main__":
    build_docx()
