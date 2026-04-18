# Antigravity Workflow: Enterprise C-Flow (Phase-Gate Lifecycle) v2.0
**Target:** 15-Agent Dynamic Matrix (3C Hardware & Cloud Orchestration)

## 1. Workflow Objective & Core Discipline
This workflow defines the standard operating procedure for the hardware and software development lifecycle, scaling from Market Evaluation to Mass Production. It strictly follows the C0 to C4 Phase-Gate process.

* **Strict Discipline 1:** No Phase Transition without a formalized Gating Review.
* **Strict Discipline 2:** No Engineering Code/CAD without an `{ISSUE_TRACKER}` ID and approved PRD.
* **Strict Discipline 3:** Business Viability First. If `$$ANALYST` vetoes the market feasibility in C0, the project is terminated before R&D resource allocation.

## 2. Global Execution Rules
* **Orchestrator:** `$$PM` is the master orchestrator, responsible for generating Artifacts and formally logging phase approvals.
* **Collaboration Syntax:** Agents MUST actively pass the baton to the next role using the exact format: `>> [To $$ROLE]: <Instruction>`.
* **Verification (Reality Check):** No phase is considered complete until its Definition of Done (DoD) is autonomously verified by the assigned Gatekeeper Agents (e.g., `$$QA`, `$$CERT`, `$$TOOLING`).

---

## 3. The Expanded C0~C4 Phase-Gate Protocols

### Phase C0: Project Inception, Strategy & Evaluation (立項企劃與市場評估階段)
* **Trigger:** User initiates a new project idea.
* **Actors:** `$$ANALYST` (The Gatekeeper), `$$PMM`, `$$ID`, `$$PM`.
* **Action 1:** `$$ANALYST` executes the 12-Module Business Analysis (TAM/SAM/SOM, Financial Model, Competitor Radar). If ROI is negative, VETO the project.
* **Action 2:** `$$PMM` drafts the Product Requirements Document (PRD) and Selling Points.
* **Action 3:** `$$ID` generates initial aesthetic and CMF (Color, Material, Finish) concepts.
* **Action 4:** `$$PM` generates the [Artifact: TMB035 Project Evaluation Form].
* **DoD:** Market viability approved by Analyst. PRD and CMF locked. Issue ID assigned.
* **Handoff:** `>> [To $$ME/$$HW/$$FW/$$SW/$$SCM]: C0 Approved. Proceed to C1 (EVT) Engineering.`

### Phase C1: Engineering Verification Test - EVT (工程開發階段)
* **Actors:** `$$ME`, `$$HW`, `$$FW`, `$$SW`, `$$SCM`.
* **Action 1:** `$$ME` creates 3D CAD based on `$$ID`'s design, managing stacking and thermal.
* **Action 2:** `$$HW` defines Schematics, PCB layout, and collaborates with `$$ME` on spatial interference.
* **Action 3:** `$$SCM` analyzes BOM, retrieves lead times, and recommends alternative ICs for cost control.
* **Action 4:** `$$FW` and `$$SW` write R&D code adhering to strict memory limits and low-latency APIs.
* **DoD:** 3D CAD locked without interference. Gerber/BOM readied and priced. Source code compiled without syntax errors.
* **Handoff:** `>> [To $$QA/$$TOOLING/$$CERT]: C1 complete. Initiate C2 (DVT) testing and DFM protocol.`

### Phase C2: Design Verification Test - DVT & Certification (設計與安規驗證階段)
* **Actors:** `$$QA`, `$$TOOLING`, `$$CERT` (The Gatekeepers).
* **Action 1:** `$$QA` strictly executes DVT Test Plans (Terminal scripts, physical drop tests, memory leaks).
* **Action 2:** `$$TOOLING` executes DFM (Design for Manufacturing) review on `$$ME`'s CAD. Rejects insufficient draft angles or sink marks.
* **Action 3:** `$$CERT` audits the design for FCC/CE RF compliance and UN38.3 battery safety.
* **Action 4:** Failures are logged. Fatal/Severe bugs activate [Protocol ZR].
* **DoD:** DFM approved. Pre-compliance passed. All `$$QA` scripts return Exit Code 0. ZERO Fatal bugs.
* **Handoff:** `>> [To $$PM]: C2 DVT passed. Ready for Gating Review and C3 Trial Run.`

### Phase C3: Production Verification Test - PVT (試產驗證階段)
* **Actors:** `$$TOOLING`, `$$HW`, `$$QA`, `$$PM`.
* **Action 1:** `$$TOOLING` generates Factory Assembly SOPs and oversees the mold opening/trial run yield.
* **Action 2:** `$$QA` performs end-to-end system integration testing simulating a mass-production environment.
* **Action 3:** `$$PM` conducts the final Gating Review to assess BOM cost, yield rate, and stability.
* **DoD:** Target factory yield reached. Integration tests pass. PVT acceptance checklist is fully checked off.
* **Handoff:** `>> [To $$DOC/$$MKT]: C3 complete. System is stable. Initiate C4 Mass Production.`

### Phase C4: Mass Production, Marketing & Release (量產、行銷與結案階段)
* **Actors:** `$$DOC`, `$$MKT`, `$$PM`.
* **Action 1:** `$$DOC` scans the repository, cleans up dev artifacts, and generates Dual-Layer User Manuals and API Docs.
* **Action 2:** `$$MKT` launches Go-To-Market (GTM) campaigns, sending cold emails and ad scripts based on `$$PMM`'s PRD.
* **Action 3:** `$$PM` formally closes the C-Flow loop in ZenTao.
* **DoD:** Repo cleaned, Documentation generated, and Marketing active. Final release tagged.
* **Handoff:** `>> [To User & $$CS]: C4 Mass Production Release complete. Product is live.`

### Post-Phase C4: Lifecycle & Support (產品生命週期維護)
* **Actors:** `$$CS` (Customer Success), `$$FW`, `$$SW`.
* **Action:** `$$CS` continuously monitors RMA rates, customer feedback, and server crash logs.
* **Decision:** If hardware yields drop or fatal software bugs are reported by users, `$$CS` immediately triggers [Protocol ZR].

---

## 4. Emergency Exception Protocol
**[Protocol ZR: Bug Log & RCA-Fix]**
* Can be triggered at any phase (or Post-C4 by `$$CS`) if a Fatal/Severe issue (e.g., OOM, FCC failure, Mold defect) is detected.
* `$$PM` will halt phase progression.
* Assign `$$QA` or `$$CS` to extract logs.
* Task the responsible engineering agents (`$$FW/$$SW/$$ME/$$HW`) with immediate Root Cause Analysis (RCA) and remediation before C-Flow resumes.