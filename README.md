# 🌐 AW Center – Automated Workflows & Compliance Center

> **AW Center** is a centralized automation and compliance management platform designed to streamline engineering documentation, change management, and traceability processes across JIRA, DOORS, Excel, and Word environments.  
> Built for certification readiness (TC/STC), it integrates with legacy systems to reduce manual effort, improve audit readiness, and accelerate project delivery.

---

## 📌 Project Overview

AW Center enables seamless automation of document generation, requirement linking, change tracking, and compliance monitoring across engineering workflows.

All tools are designed with **reusability**, **integration capability**, and **audit traceability** in mind.

---

## 🛠️ Core Tools

### ✅ JIRA Integration Tools

| Tool | Description |
|------|-----------|
| **DCC Creator** | Automatically generates DCC (Design Change Control) forms from JIRA Tasks under the "Design Change Management for Certification after TC/STC" project. Ensures compliance with certification documentation standards. |
| **JIRA Subtask Generator (List)** | Creates multiple Sub-tasks under a selected JIRA Task using predefined data from an internal list. Ideal for repetitive, structured workflows. |
| **JIRA Subtask Generator (Excel)** | Bulk creates Sub-tasks by reading data from an Excel file. Supports dynamic field mapping and validation. |

---

### 📚 DOORS Integration Tools

| Tool | Description |
|------|-----------|
| **PoC Linker** | Automates bulk linking of PoCs (Proof of Compliance) in DOORS’ Requirements module to the Cover Page module. Enables traceability and simplifies compliance reporting. |
| **Script Generator** | Converts structured data from Excel into executable DXL (DOORS eXtension Language) scripts for automated DOORS operations (e.g., creation, update, validation). |

---

### 🔍 Compare & Diff Tools

| Tool | Description |
|------|-----------|
| **Excel Compare** | Compares two Excel files and generates a detailed report (in Excel format) highlighting differences. Supports cell-level change tracking and export. |
| **Word Compare** | Compares two Word documents and generates side-by-side reports in **both Excel and Word formats**. Includes configurable **Equal Ratio** parameters to control sensitivity (e.g., ignore whitespace, case, or minor formatting). |

---

## 🚧 Development Phase Tools (Under Active Development)

| Tool | Status | Description |
|------|--------|-----------|
| **CompDoc Watcher** | 🔧 In Development | Monitors compliance documents (e.g., DDF, DCC) in real-time. Integrates with JIRA, DocProof, DOORS, and Outlook. Features dynamic dashboards and visual trend graphs for proactive risk management. |
| **JIRA Watcher** | 🔧 In Development | Real-time monitoring of newly added JIRA Tasks. Synchronizes with JIRA API and automatically sends email notifications to responsible users for open Sub-tasks. |
| **DOORS Agent** | 🔧 In Development | Analyzes DOORS Requirements module for logical inconsistencies (e.g., missing Chapter for a discipline, invalid status transitions). Provides actionable insights and suggestions for correction. |
| **DDF Assistant** | 🔧 In Development | Streamlines DDF (Design Data File) tracking and lifecycle management. Automates status updates, reminders, and approvals to accelerate process flow. |

---

## 📦 Tech Stack

- **Backend**: Python (Django)
- **Frontend**: Vue.js (+ Naive UI), Typescript, HTML/CSS/JS
- **Database**: SQLite
- **Authentication**: CSRF Token
- **File Processing**: Pandas, openpyxl, python-docx, docx2txt
- **APIs**: JIRA REST API, DOORS DXL, Excel/Word parsing libraries
- **Deployment**: GitLab CI/CD (not yet)
