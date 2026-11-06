import os
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

template_path = r'C:\Users\Gigabyte\Downloads\HTC_CONFORMITY-MATRIX.docx'
doc = docx.Document(template_path)

# 1. Update Table 0 (Title & Date)
t0 = doc.tables[0]
t0.rows[0].cells[0].paragraphs[0].text = 'Title:'
t0.rows[0].cells[1].paragraphs[0].text = 'HTC Core: Integrated Procurement & Financial Tracking System'
t0.rows[1].cells[0].paragraphs[0].text = 'Date/ Time:'
t0.rows[1].cells[1].paragraphs[0].text = 'November 6, 2026'

for r in t0.rows:
    for c in r.cells:
        for p in c.paragraphs:
            if p.runs:
                p.runs[0].font.name = 'Arial'
                p.runs[0].font.size = Pt(10)
                if c == r.cells[0]:
                    p.runs[0].font.bold = True

# 2. Revisions data aligned with the latest revised manuscript: HTC REVISED MANUSCRIPT (1).pdf
revisions = [
    # Category, Nature of Revision, Page Reflected, Revision Description
    ('DOCUMENTATION', 
     'Keep the objectives brief, specific, and concise.', 
     'Page 8 (Chapter 1)', 
     'Streamlined the general and specific objectives into concise, outcome-oriented statements focusing on core business capabilities (procurement tracking, dynamic loan financing with cheque automation, and volume variance monitoring with immutable auditing) rather than lengthy technical implementation details.'),
    
    ('DOCUMENTATION', 
     'State the project objectives using clear, high-level language.', 
     'Page 8 (Chapter 1)', 
     'Rephrased all objectives using professional operational and managerial terminology accessible to enterprise stakeholders, eliminating framework-specific names and low-level source code mechanics.'),
    
    ('DOCUMENTATION', 
     'Review and improve the Definition of Terms by providing clear explanations of technical terms.', 
     'Pages 12–15 (Chapter 1)', 
     'Substantially expanded and organized the Definition of Terms alphabetically with comprehensive, operational explanations of all technical terms (e.g., Blockchain Ledger, Compensating Correction Pattern, Dynamic Interest Accrual Engine, EWT, Financing Module, High-Legibility Mode, Immutable System Audit Trail, PostgreSQL Triggers, and WCAG 2.1 AA Compliance).'),
    
    ('DOCUMENTATION', 
     "Correct the adviser's name throughout the documentation.", 
     'Title Page, Approval Sheet (p. ii), Acknowledgments (p. iv), Throughout Chapters 1–5', 
     'Systematically corrected and standardized the adviser’s name across all document sections, approval sheets, headers, and metadata to read correctly as "Jheanel E. Estrada, PhD".'),
    
    ('DOCUMENTATION', 
     'Clearly explain the four architecture layers: Presentation, Application, Asynchronous Processing, and Database.', 
     'Pages 49–53 (Chapter 3, Figure 3.5 & Subsections)', 
     'Substantially expanded Chapter 3 under Figure 3.5 (System Architecture) with dedicated narrative subsections detailing all layers: Presentation & Accessibility Layer (Bootstrap 5.3, WCAG 2.1 AA, p. 50), API Gateway & Security Firewall (Nginx 1.27, SSL/TLS, pp. 50–51), Core Application & Business Logic (Django 5, 5 RBAC roles, Celery asynchronous processing, pp. 51–52), Cryptographic & Immutable Audit (SHA-256 block hash chaining, p. 52), and Persistence & Infrastructure (PostgreSQL 16, AWS EC2 18.140.166.84, pp. 52–53).'),
    
    ('DOCUMENTATION', 
     'Document database triggers and RBAC to prevent unauthorized editing or deletion of records.', 
     'Pages 34, 51–53, 71 (Chapter 3) & Pages 83–86, 104 (Chapter 4)', 
     'Dived deeply into Chapter 3 under Section 1.3 User Management (p. 34), Core Application Layer (p. 51), Persistence Layer (pp. 52–53), and Security Assessment Table 3.9 (p. 71), formally documenting the PostgreSQL prevent_audit_tampering() BEFORE UPDATE OR DELETE trigger and ON DELETE RESTRICT constraints, paired with 5-tier Role-Based Access Control (RBAC) enforced via @role_required decorators.'),
    
    ('DOCUMENTATION', 
     'Specify the 1.0% volume-loss threshold that triggers system alerts.', 
     'Pages 51–52, 70 (Chapter 3) & Pages 83–84 (Chapter 4)', 
     'Dived into Chapter 3 under Core Application Layer (Reconciliation & Discrepancy Tolerance Engine, pp. 51–52) and Functional Testing Matrix Table 3.7 (p. 70), formally defining the mathematical shrinkage formula (Variance % = [(Disp MT - Recv MT) / Disp MT] * 100) and documenting the automated threshold logic: volume losses exceeding 1.00% programmatically trigger a DISPUTED_VARIANCE lock halting customer billing.'),
    
    ('DOCUMENTATION', 
     'Discuss UI usability and compliance with WCAG accessibility standards.', 
     'Pages 50, 53, 70 (Chapter 3) & Pages 76–77, 101–103 (Chapter 4)', 
     'Dived into Chapter 3 under Presentation & Accessibility Layer (p. 50), Frontend Framework Evaluation Table 3.3 (p. 53), and Usability Testing Matrix Table 3.7 (p. 70), detailing frontend usability principles and WCAG 2.1 Level AA accessibility compliance, including minimum 4.5:1 text contrast (surpassing 7.0:1 in High-Legibility Mode), :focus-visible outlines, skip-to-content links, and >= 44x44px touch targets.'),
    
    ('DOCUMENTATION', 
     'Simplify Chapter 1 objectives by removing technical jargon and moving detailed technical explanations to Chapters 2 and 3.', 
     'Page 8 (Chapter 1) & Pages 49–59, 69–72 (Chapter 3)', 
     'Decoupled high-level research objectives from technical execution by stripping framework flags and database implementation jargon from Chapter 1, moving detailed system architecture (Figure 3.5, pp. 49–53), framework comparisons (Tables 3.3–3.5, pp. 53–58), and testing matrices (Tables 3.7–3.9, pp. 70–72) into Chapter 3.'),
    
    ('DOCUMENTATION', 
     'Use colons appropriately to improve documentation structure and readability.', 
     'Throughout Chapters 1–4', 
     'Standardized punctuation across the manuscript, properly applying colons to introduce lists, define operational terms (pp. 12–15), and structure figure/table titles consistently (e.g., "Figure 3.5: System Architecture", "Table 3.7: Functional Testing Matrix").'),
    
    ('SYSTEM', 
     'Implement appropriate user access levels.', 
     'Chapter 3 (pp. 34, 51, 71) & Chapter 4 (pp. 83–86, 104) [System: accounts/permissions.py]', 
     'Engineered strict Role-Based Access Control (RBAC) across five user roles (Administrator, Operations Management, Operations, Finance, Invoicing) using @role_required view decorators and UI template restrictions that conceal unauthorized controls.'),
    
    ('SYSTEM', 
     'Improve the UI/UX to make the system user-friendly.', 
     'Chapter 3 (pp. 50, 53) & Chapter 4 (pp. 75–78, 101) [System: Global UI & Financing]', 
     'Streamlined user workflows across all modules, renamed the financial tab to concise "Financing", simplified modal forms with contextual input guards, cleaned up status badge styling, and ensured intuitive operational flows.'),
    
    ('SYSTEM', 
     'Make dashboard insights intuitive and easy to understand.', 
     'Chapter 3 (p. 34) & Chapter 4 (pp. 75–77) [System: Executive Dashboard]', 
     'Designed executive KPI summary cards displaying plain-language operational metrics (Active POs, Procurement Spend, Active Capital Loans, Dispatched vs Received Volume, Net Shrinkage Rate), visual fulfillment meters, and route risk alerts.'),
    
    ('SYSTEM', 
     'Ensure the website is responsive across different devices and screen sizes.', 
     'Chapter 3 (pp. 50, 53) & Chapter 4 (pp. 76–77, 98–101) [System: Global Responsive Layouts]', 
     'Implemented mobile-first responsive grid layouts using Bootstrap 5, collapsible sidebar navigation, touch-friendly interactive targets (>= 44x44px), and horizontally scrollable data table containers across desktop, tablet, and mobile screen sizes.'),
    
    ('SYSTEM', 
     'Add a printable report feature.', 
     'Chapter 3 (p. 70, Table 3.7) & Chapter 4 (pp. 78–80) [System: Billing & Financing Modules]', 
     'Integrated automated server-side PDF generation for BIR-compliant Sales Invoices (download_invoice_pdf) and Disbursement Cash/Cheque Vouchers (download_voucher_pdf), supplemented by print-optimized CSS media stylesheets (@media print).'),
    
    ('SYSTEM', 
     'Implement an immutable audit trail.', 
     'Chapter 3 (pp. 52, 71) & Chapter 4 (pp. 83–86, 104) [System: audit/models.py & PostgreSQL Triggers]', 
     'Implemented the SystemAuditTrail subsystem with overridden ORM save() and delete() methods blocking destructive operations, backed by PostgreSQL database triggers and SHA-256 block hash verification to guarantee audit record immutability.'),
    
    ('SYSTEM', 
     'Implement an error correction process that preserves audit log integrity.', 
     'Chapter 3 (pp. 52, 70) & Chapter 4 (pp. 83–85) [System: Compensating Workflow]', 
     'Implemented the Compensating Correction Pattern for human data errors: a "Void & Reissue" workflow (compensating_correction_voucher) for cheques marking the original as SUPERSEDED with mandatory justification, and a "Compensating Weighbridge Adjustment" (compensating_correction_delivery) for deliveries that preserves historical records while logging offsetting audit deltas.')
]

# 3. Populate Table 1 (List of Revisions)
t1 = doc.tables[1]
while len(t1.rows) > 2:
    t1._tbl.remove(t1.rows[-1]._tr)

current_cat = None
for cat, nature, page, rev in revisions:
    if cat != current_cat:
        current_cat = cat
        cat_row = t1.add_row()
        cat_cell = cat_row.cells[0]
        cat_row.cells[1].merge(cat_cell)
        cat_row.cells[2].merge(cat_cell)
        cat_p = cat_cell.paragraphs[0]
        cat_p.text = f'--- {cat} REVISIONS ---'
        cat_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if cat_p.runs:
            cat_p.runs[0].font.name = 'Arial'
            cat_p.runs[0].font.size = Pt(10)
            cat_p.runs[0].font.bold = True
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="E2E8F0"/>')
        cat_cell._tc.get_or_add_tcPr().append(shading)
        
    row = t1.add_row()
    c0 = row.cells[0]
    c1 = row.cells[1]
    c2 = row.cells[2]
    
    c0.paragraphs[0].text = nature
    c1.paragraphs[0].text = page
    c2.paragraphs[0].text = rev
    
    for c in (c0, c1, c2):
        p = c.paragraphs[0]
        if p.runs:
            p.runs[0].font.name = 'Arial'
            p.runs[0].font.size = Pt(9.5)
    if c0.paragraphs[0].runs:
        c0.paragraphs[0].runs[0].font.bold = True
    c1.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# Set cell widths
for row in t1.rows:
    if len(row.cells) == 3:
        row.cells[0].width = Inches(2.1)
        row.cells[1].width = Inches(1.3)
        row.cells[2].width = Inches(3.6)

# 4. Populate Table 2 (Proponents & Panelists)
t2 = doc.tables[2]
proponents = [
    'Bernardino, Denielle',
    'Cahindi, Joseph Francis',
    'Maranda, Sam',
    'Santos, Kurt Zildjian'
]
panelists = [
    'Dr. Melvin Ballera',
    'Mr. Jhon Angelo San Andres',
    'Ms. Khaela May Lee',
    'Mr. Kenner Rondilla'
]

for i in range(4):
    row_idx = i + 1
    t2.rows[row_idx].cells[0].paragraphs[0].text = proponents[i]
    t2.rows[row_idx].cells[1].paragraphs[0].text = panelists[i]
    for cell in t2.rows[row_idx].cells:
        p = cell.paragraphs[0]
        if p.runs:
            p.runs[0].font.name = 'Arial'
            p.runs[0].font.size = Pt(10)

# Save output with fallbacks if file is open in Word
targets = [
    r'C:\Users\Gigabyte\CAPSTONE-2\HTC_CONFORMITY_MATRIX_Latest.docx',
    r'C:\Users\Gigabyte\CAPSTONE-2\HTC_CONFORMITY_MATRIX_Updated.docx',
    r'C:\Users\Gigabyte\CAPSTONE-2\HTC_CONFORMITY_MATRIX_Completed.docx',
    r'C:\Users\Gigabyte\Downloads\HTC_CONFORMITY-MATRIX_Final.docx'
]

for t in targets:
    try:
        doc.save(t)
        print('Saved successfully:', t)
    except PermissionError:
        print('File open in Word, skipping:', t)
    except Exception as e:
        print('Error saving:', t, e)
