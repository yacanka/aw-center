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
---


## 🧩 Project Registry and Organization Project Slugs

AW Center keeps technical project application metadata in the read-only backend project registry (`backend/projects/registry.py`) and keeps business-facing organization projects in the `orgs.Project` table. The shared contract between these two layers is the project slug.

Rules:

- `orgs.Project.slug` values must match registry `ProjectDefinition.slug` values for every enabled registry project.
- Disabled registry projects may exist in the registry without an `orgs.Project` row until they are enabled or intentionally seeded.
- `orgs.Project` must remain business data only; do not add technical registry fields such as `app_label`, `serializer_path`, `model_path`, filesystem paths, template paths, or internal import paths to that model.
- Database project rows whose slug is not present in the registry are treated as active database-only records and should be investigated before introducing routes or automated workflows for them.

Run the read-only alignment check from `backend/`:

```bash
python manage.py check_project_registry
```

The command is intentionally non-destructive. It fails when an enabled registry project is missing from `orgs.Project`, and it prints warnings for database project rows that are not registered. If rows need to be created, add a separate explicit seed data migration or a dedicated seeding management command so validation never mutates production data.

## 🚀 Development Starter

The repository includes a cross-platform starter for macOS, Windows, and Linux. It creates and uses a root `.venv`, installs backend packages from `requirements.txt`, installs frontend packages from `frontend/package-lock.json`, creates a local-only `backend/.env` when absent, and can run Django and Vite together.

```bash
python scripts/starter.py check
python scripts/starter.py install
python scripts/starter.py check-backend
python scripts/starter.py start
```

Useful options:

- `--skip-backend` or `--skip-frontend` limits package installation to one side.
- `--host`, `--backend-port`, and `--frontend-port` customize local server binding.
- `VITE_API_URL` is set automatically for the frontend server when using `start`.

> The generated `backend/.env` contains only development placeholders and is ignored by Git. Replace integration URLs and credentials locally when testing JIRA, DocProof, DOORS, Outlook, or Office automation.

## 🧭 Project Launcher

Use the root `launcher.py` when you need one command surface for dependency installation,
offline preparation, backend database checks, and frontend quality checks. The launcher is
designed for macOS, Windows, and Linux, and it never passes commands through a shell string.

### Command Summary

| Command | Purpose | Typical Use |
|---|---|---|
| `prepare-offline` | Downloads Python wheels and warms an npm cache. | Run on an internet-connected machine before moving artifacts to an offline environment. |
| `install` | Installs backend and frontend dependencies. | Run after cloning the repository or after copying an offline bundle. |
| `check` | Runs Django checks, migration checks, and frontend format/type checks. | Run before committing or before validating a prepared workstation. |
| `all` | Installs dependencies and then runs all checks. | Use as the safest first-run workflow in online or prepared offline environments. |

### Scenario 1: First Setup in an Online Environment

Run the full online workflow when the workstation has internet access:

```bash
python launcher.py all --mode online
```

This creates `.venv` when needed, installs backend packages from `requirements.txt`,
installs frontend packages with `npm ci`, validates Python dependencies with `pip check`,
runs Django system and migration checks, and executes frontend format/type checks.

### Scenario 2: Let the Launcher Detect Online or Offline Mode

Use `auto` mode when you want the launcher to decide based on a small PyPI connectivity
probe:

```bash
python launcher.py all --mode auto
```

If the probe succeeds, the launcher uses online package installation. If the probe fails,
it uses offline installation paths and expects the offline bundle to already exist.

### Scenario 3: Prepare an Offline Bundle

On a machine with internet access, prepare dependency artifacts:

```bash
python launcher.py prepare-offline --offline-dir offline
```

This stores backend wheels under `offline/wheels` and populates an npm cache under
`offline/npm-cache`. Copy the repository and the `offline/` directory to the offline
machine after this step.

### Scenario 4: Install in an Offline Environment

After copying the prepared offline bundle to the target machine, install without package
index access:

```bash
python launcher.py install --mode offline --offline-dir offline
```

Backend dependencies are installed with `pip --no-index --find-links offline/wheels`.
Frontend dependencies are installed with `npm ci --offline --cache offline/npm-cache`.

### Scenario 5: Run Only Validation Checks

When dependencies are already installed and you only want validation:

```bash
python launcher.py check
```

This runs:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate --check`
- `npm run format:check`
- `npm run typecheck:ci`

### Useful Options

- `--skip-backend` skips backend dependency installation during `install` or `all`.
- `--skip-frontend` skips frontend dependency installation during `install` or `all`.
- `--offline-dir <path>` changes where offline wheels and npm cache are read or written.
- `--mode online`, `--mode offline`, and `--mode auto` control package installation mode.

### Important Notes and Trade-offs

- `prepare-offline` must be run while internet access is available.
- Offline npm installation depends on cache completeness. If package metadata or tarballs
  are missing from the cache, rerun `prepare-offline` in an online environment.
- `check` assumes dependencies already exist. Use `all` for a complete install-and-check
  workflow.
- The generated `backend/.env` contains development-only placeholders; do not use it as a
  production secrets file.

## 🚢 Deployment Foundations

Container and CI foundations are documented in [`docs/deployment.md`](docs/deployment.md). The repository includes separate backend and frontend Dockerfiles, a local `docker-compose.yml` with a PostgreSQL database candidate, and a GitHub Actions workflow for backend checks, frontend checks, builds, and dependency audits.
