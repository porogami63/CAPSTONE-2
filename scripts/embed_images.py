from pathlib import Path

doc_path = Path("docs/SYSTEM_ARCHITECTURE_DIAGRAMS_2026.md")
text = doc_path.read_text(encoding="utf-8")

# 1. ERD
target1 = "## 1. Entity-Relationship Diagram (ERD)\n\nThe following diagram captures all 17 primary database entities across the 6 core Django applications (`accounts`, `masters`, `operations`, `finance`, `audit`, and `chat`), documenting primary keys (`PK`), foreign keys (`FK`), and cardinalities."
rep1 = target1 + "\n\n> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/01_entity_relationship_diagram_erd.png) | [Vector SVG](diagrams/01_entity_relationship_diagram_erd.svg)\n>\n> ![HTC Core Entity-Relationship Diagram](diagrams/01_entity_relationship_diagram_erd.png)"

# 2. Level 0 DFD
target2 = "### 2.1 Level 0 DFD: Context Diagram\nThe Level 0 Context Diagram maps how data flows across the system boundary between authenticated internal staff, automated cloud microservices, and offline external business counterparties."
rep2 = target2 + "\n\n> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/02_dfd_level0_context_diagram.png) | [Vector SVG](diagrams/02_dfd_level0_context_diagram.svg)\n>\n> ![HTC Core Level 0 Context Diagram](diagrams/02_dfd_level0_context_diagram.png)"

# 3. Level 1 DFD
target3 = "### 2.2 Level 1 DFD: Process Decomposition Diagram\nThe Level 1 DFD decomposes HTC Core into its **10 major operational sub-processes**, showing data flows driven by internal authenticated staff and automated services across the 8 data stores."
rep3 = target3 + "\n\n> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/03_dfd_level1_process_decomposition.png) | [Vector SVG](diagrams/03_dfd_level1_process_decomposition.svg)\n>\n> ![HTC Core Level 1 Process Decomposition DFD](diagrams/03_dfd_level1_process_decomposition.png)"

# 4. Level 2 DFD
target4 = "### 2.3 Level 2 DFD: Process 5.0 (Parent PO & Incremental Multi-Batch Delivery Execution)\nTo highlight the drastic changes made to parent-child PO logistics, this Level 2 DFD drills directly into **Process 5.0**."
rep4 = target4 + "\n\n> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/04_dfd_level2_multi_batch_delivery.png) | [Vector SVG](diagrams/04_dfd_level2_multi_batch_delivery.svg)\n>\n> ![HTC Core Level 2 Multi-Batch Delivery DFD](diagrams/04_dfd_level2_multi_batch_delivery.png)"

# 5. Database Schema
target5 = "## 3. Comprehensive Database Schema Specification\n\nThis schema dictionary represents the **PostgreSQL 16** production database architecture backing HTC Core."
rep5 = target5 + "\n\n> 🖼️ **Rendered Schema Table Sheet:** [Download High-Res PNG](diagrams/06_database_schema_summary_tables.png)\n>\n> ![HTC Core Database Schema Summary Sheet](diagrams/06_database_schema_summary_tables.png)"

# 6. Use Case
target6 = "## 4. Use Case Diagram\n\nThe Use Case Diagram maps the functional interactions between the **6 system actors** (5 authenticated internal staff roles + 1 automated cloud microservice) and the **9 functional use case packages**."
rep6 = target6 + "\n\n> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/05_use_case_diagram.png) | [Vector SVG](diagrams/05_use_case_diagram.svg)\n>\n> ![HTC Core Use Case Diagram](diagrams/05_use_case_diagram.png)"

for t, r in [(target1, rep1), (target2, rep2), (target3, rep3), (target4, rep4), (target5, rep5), (target6, rep6)]:
    if t in text:
        text = text.replace(t, r)
    else:
        print("MISSING TARGET:", t[:40])

doc_path.write_text(text, encoding="utf-8")
print("Updated docs/SYSTEM_ARCHITECTURE_DIAGRAMS_2026.md successfully!")

# Create artifact version with absolute paths
art_path = Path(r"C:/Users/Gigabyte/.gemini/antigravity-ide/brain/473451ac-9352-4fab-b704-595612e0f03b/system_architecture_and_diagrams.md")
art_text = text.replace("](diagrams/", "](/C:/Users/Gigabyte/.gemini/antigravity-ide/brain/473451ac-9352-4fab-b704-595612e0f03b/diagrams/")
art_path.write_text(art_text, encoding="utf-8")
print("Updated artifact markdown successfully!")
