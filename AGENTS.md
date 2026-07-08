# AGENTS.md — AW Center Repository Guide

This file provides project-specific instructions for AI agents and maintainers working in this repository. It is based only on files present in the repository. When a detail cannot be confirmed from repository files, it is explicitly marked **Verify in repository**.

## Project Identity

- **Name:** AW Center — Automated Workflows & Compliance Center.
- **Purpose:** A centralized automation and compliance management platform for engineering documentation, change management, and traceability workflows across JIRA, DOORS, Excel, Word, PDF, Outlook, and DocProof-related processes.
- **Domain emphasis:** Certification readiness, audit traceability, document generation, requirement linking, change tracking, and compliance monitoring.
- **Primary application shape:** Django backend serving REST-style endpoints and a Vue 3/Vite frontend mounted under `/app/`, with built frontend assets copied into Django template/static directories for production-style serving.

## Architecture Overview

### Backend

- Located under `backend/`.
- Django project package: `backend/awcenter/`.
- Entry points:
  - `backend/manage.py` for Django management commands.
  - `backend/awcenter/wsgi.py` and `backend/awcenter/asgi.py` for WSGI/ASGI.
  - `backend/run_cheroot.py` for a Cheroot HTTPS server using `AWCenter.crt` and `AWCenter.key` in its working directory.
- Main URL router: `backend/awcenter/urls.py`.
- Authentication:
  - Django REST Framework token authentication is customized in `backend/awcenter/authentication.py`.
  - Tokens are accepted from the standard `Authorization: Token ...` header or from the `auth_token` cookie.
  - Default DRF permission class is `IsAuthenticated`.
- Persistence:
  - SQLite databases are configured in `backend/awcenter/settings.py` as `db.sqlite3` and `db_old.sqlite3` under `backend/`.
- Static/media:
  - `STATIC_URL` is `/core/`.
  - Static files are collected into `backend/static` and include `backend/core` as a static files directory.
  - Media uploads use `backend/media`.
- Production security settings are enabled when `DEBUG=False`, including HTTPS redirect, secure session/CSRF cookies, HSTS, content-type nosniff, same-origin referrer policy, and `X_FRAME_OPTIONS="DENY"`.

### Frontend

- Located under `frontend/`.
- Vue 3 application built with Vite and TypeScript.
- Uses Naive UI, Pinia, Vue Router, Axios, Chart.js, Markdown-It, and related chart/date plugins.
- Main entry: `frontend/src/main.ts`.
- Root component: `frontend/src/App.vue`.
- Router: `frontend/src/router/index.ts`.
- HTTP configuration: `frontend/src/services/http.ts`.
- Vite alias: `@` resolves to `frontend/src`.
- Vue Router uses browser history rooted at `/app/`.
- Vite production base is `/core/`; development base is `./`.
- `npm run build` executes `vite build` and then `frontend/scripts/postbuild.js`, which copies:
  - `frontend/dist/index.html` to `backend/templates/index.html`.
  - `frontend/dist/assets` to `backend/core/assets`.

### Integration Boundaries

- JIRA integration is primarily under `backend/dcc/` and `backend/dcc/service/`.
- DOORS integration is under `backend/doors/` and uses `DOORS_EXECUTABLE`, base64-decoded `AW_USERNAME`/`AW_PASSWORD`, and Windows COM-related imports where available.
- Excel, Word, and PDF operations are separated into `backend/excel/`, `backend/word/`, and `backend/pdf/`.
- PowerPoint gallery features are under `backend/pptxgallery/` and use external conversion binaries configured by environment variables.
- Outlook `.msg` parsing endpoints are under `backend/outlook/`.
- Project-specific compliance document modules live under `backend/projects/<project>/`.

## Tech Stack Confirmed in Repository

### Backend

- Python 3.14-compatible backend dependency set with Django 6.0 declared in `requirements.txt`.
- Django REST Framework.
- DRF token authentication.
- SQLite.
- django-cors-headers.
- django-simple-history.
- WhiteNoise.
- django-environ.
- Cheroot HTTPS serving script.
- File/data processing imports found in backend code include Pandas, NumPy, openpyxl, python-docx/docxtpl/docx2txt, pypdf/pdfplumber, BeautifulSoup, Pillow, requests, JIRA, and Office/Windows automation libraries.
- Root `requirements.txt` is committed for backend Python dependencies and targets Python 3.14 compatibility. There is no `pyproject.toml`, `Pipfile`, or lock file committed for backend Python dependencies.

### Frontend

- Vue `^3.5.13`.
- Vite `^6.3.5`.
- TypeScript `^5.8.3`.
- Vue Router `^4.3.0`.
- Pinia `^3.0.2`.
- Naive UI `^2.41.0`.
- Axios `^1.9.0`.
- Chart.js `^4.5.0` and chart plugins.
- Markdown-It `^14.1.0`.
- Lock file: `frontend/package-lock.json`.

## Folder Structure

```text
.
├── README.md                       # Product overview and high-level tech stack
├── AGENTS.md                       # Agent instructions for this repository
├── backend/
│   ├── manage.py                   # Django management entry point
│   ├── run_cheroot.py              # Cheroot HTTPS server entry point
│   ├── awcenter/                   # Django project settings, URLs, auth, middleware
│   ├── common/                     # Shared models/serializers/views and management commands
│   ├── core/                       # Django app route for frontend shell/static-serving support
│   ├── dcc/                        # DCC/JIRA workflows
│   ├── ddf/                        # DDF workflows
│   ├── docproof/                   # DocProof integration endpoints
│   ├── doors/                      # DOORS/DXL workflows
│   ├── excel/                      # Excel processing endpoints
│   ├── orgs/                       # Organization/project/panel/people APIs
│   ├── outlook/                    # Outlook message parsing/downloading endpoints
│   ├── pdf/                        # PDF split/compare tools and comparer package
│   ├── pptxgallery/                # Presentation/slide gallery and conversion code
│   ├── projects/                   # Project-specific apps: ozgur, piku, aesa, hys, blok30, blok4050, havasoj, gokbey
│   ├── releases/                   # Release note APIs
│   ├── users/                      # Users, auth token, preferences, password reset
│   ├── utils/                      # Shared Python utilities
│   └── word/                       # Word compare/translation queue workflows
└── frontend/
    ├── package.json                # Frontend scripts and dependencies
    ├── package-lock.json           # npm lock file
    ├── vite.config.ts              # Vite/Vue config
    ├── tsconfig.json               # TypeScript compiler settings
    ├── .prettierrc                 # Frontend formatting settings
    ├── scripts/postbuild.js        # Copies built frontend into backend template/static dirs
    ├── public/                     # Public frontend assets
    └── src/
        ├── assets/                 # Styles/assets
        ├── components/             # Vue components
        ├── composables/            # Vue composables/helpers
        ├── icons/                  # Vue icon wrappers
        ├── models/                 # TypeScript interfaces/models
        ├── router/                 # Vue Router config
        ├── services/               # Axios/http, notifications, storage
        ├── stores/                 # Pinia stores and related JS/TS stores
        ├── types/                  # Global type declarations
        ├── utils/                  # Frontend utilities
        └── views/                  # Routed view components
```

## Plan and Memory

If plan.md file exist, read the plan file and remove items from it based on the changes you've made successfully and completely. If you need to add new plans or you have any future recommendation, update to the plan.md file. You can update updates.md for explaning what you'have done.

## Setup Instructions

### Backend Setup

1. Work from the backend directory for Django commands:

   ```bash
   cd backend
   ```

2. Install backend Python dependencies from the committed root manifest:

   ```bash
   python -m pip install -r ../requirements.txt
   ```

3. Create `backend/.env` with the environment variables listed below. Do not commit `.env` files.

4. Apply migrations after dependencies and environment variables are available:

   ```bash
   python manage.py migrate
   ```

### Project Starter

From the repository root, use the cross-platform starter for package checks, installation, and concurrent Django/Vite development servers:

```bash
python scripts/starter.py check
python scripts/starter.py install
python scripts/starter.py check-backend
python scripts/starter.py start
```

The starter creates `.venv`, installs `requirements.txt`, installs frontend packages with `npm ci` when `package-lock.json` is present, writes a local ignored `backend/.env` with safe development placeholders when absent, and sets `VITE_API_URL` for the Vite process.

### Frontend Setup

Run all frontend commands from `frontend/`:

```bash
cd frontend
npm install
```

Use `npm install` because `frontend/package-lock.json` is committed. If CI requires reproducibility, prefer `npm ci`; **Verify in repository** because no CI file is committed.

## Run, Build, Test, Lint, and Migration Commands

### Backend Commands

Run from `backend/`:

| Purpose | Command | Source / Notes |
|---|---|---|
| Django development server | `python manage.py runserver` | Standard `manage.py` entry point is present. Requires backend dependencies and env vars. |
| Apply migrations | `python manage.py migrate` | Django migrations are committed under app `migrations/` folders. |
| Create migrations | `python manage.py makemigrations` | Use only after intentional model changes. Review generated migration files carefully. |
| Run backend tests | `python manage.py test` | App-level `tests.py` files are present. Requires backend dependencies and env vars. |
| Django system check | `python manage.py check` | Useful before committing backend changes. |
| Cross-platform starter check | `python ../scripts/starter.py check-backend` | Uses root `.venv`, ensures local dev env, then runs Django checks. |
| Cheroot HTTPS server | `python run_cheroot.py` | Uses `IPV4_ADDRESS`, `PORT`, `AWCenter.crt`, and `AWCenter.key`. |
| Copy users management command | `python manage.py copy_users` | Command exists at `backend/common/management/commands/copy_users.py`. Confirm behavior before running against real data. |

### Frontend Commands

Run from `frontend/`:

| Purpose | Command | Source / Notes |
|---|---|---|
| Install dependencies | `npm install` | `package-lock.json` is committed. |
| Start Vite dev server | `npm run dev` | Runs `vite`. |
| Build frontend and copy assets into backend | `npm run build` | Runs `vite build && node scripts/postbuild.js`. |
| Preview built frontend | `npm run serve` | Runs `vite preview`. |
| Deploy script | `npm run deploy` | Runs `bash scripts/deploy.sh`, but **Verify in repository** because `frontend/scripts/deploy.sh` is not present in the current tree. |
| Start script | `npm run start` | Runs `node server.js`, but **Verify in repository** because `frontend/server.js` is not present in the current tree. |

### Lint and Formatting Commands

- Frontend Prettier configuration exists at `frontend/.prettierrc`, but no npm `format` or `lint` script is defined in `frontend/package.json`.
- No ESLint, Biome, Ruff, Black, isort, mypy, pytest, or tox configuration file is committed.
- **Verify in repository:** Preferred Python formatter/linter and frontend lint command are not defined in repository files.

## Environment Variables

### Backend `.env` Variables

`backend/awcenter/settings.py` reads `backend/.env` with django-environ.

| Variable | Required / Default | Usage |
|---|---|---|
| `SECRET_KEY` | Required when `DEBUG=False`; dev fallback only when `DEBUG=True` | Django secret key. Never commit real values. |
| `DEBUG` | Defaults to `False` | Controls debug mode, CORS behavior, and production security settings. |
| `IPV4_ADDRESS` | Required | Used for allowed hosts, reset URL default, and Cheroot bind host. |
| `PORT` | Required integer | Used for reset URL default and Cheroot bind port. |
| `DOCPROOF_URL` | Required | DocProof integration base URL. |
| `DOORS_EXECUTABLE` | Required | DOORS executable path. |
| `JIRA_LEGACY_URL` | Required | Legacy JIRA URL. |
| `JIRA_BTB_URL` | Required | Main JIRA URL used by DCC views. |
| `AW_USERNAME` | Optional default `""` | Used by DocProof/DOORS integrations. DOORS code base64-decodes it. |
| `AW_PASSWORD` | Optional default `""` | Used by DocProof/DOORS integrations. DOORS code base64-decodes it. |
| `FRONTEND_RESET_URL` | Optional computed default | Password reset frontend link. |
| `ALLOWED_HOSTS` | Optional list default includes `IPV4_ADDRESS`, `127.0.0.1`, `localhost` | Django allowed hosts. |
| `CORS_ALLOWED_ORIGINS` | Required when `DEBUG=False` | Production CORS origin allowlist. |
| `CSRF_TRUSTED_ORIGINS` | Optional list default `[]` | Django CSRF trusted origins. |
| `SECURE_HSTS_SECONDS` | Optional default `31536000` when `DEBUG=False` | HSTS duration. |
| `SOFFICE_BIN` | Optional default `soffice` | PowerPoint/PDF conversion helper. |
| `PDFTOPPM_BIN` | Optional default `pdftoppm` | PowerPoint/PDF conversion helper. |

### Frontend Environment Variables

Used via `import.meta.env` in frontend code:

| Variable | Usage |
|---|---|
| `VITE_API_URL` | Axios base URL in `frontend/src/services/http.ts`. |
| `VITE_VERSION` | Displayed in `frontend/src/views/MainView.vue`. |
| `VITE_APP_TITLE` | Used in `frontend/src/views/Home.vue`. |
| `SHOW_DELAYED_COMPDOCS` | Used in compdoc/dashboard stores and views to flag delayed documents. |

> Note: Vite exposes only `VITE_`-prefixed variables to client code by default. This repository also references `SHOW_DELAYED_COMPDOCS` without the `VITE_` prefix. **Verify in repository** whether the local Vite configuration or runtime environment intentionally exposes this variable.

## Coding Standards

### Repository-Wide Standards

- Write production-oriented changes: small, focused, testable, and reversible.
- Prefer meaningful full-word names over abbreviations except for established domain terms already used in the project, such as DCC, DDF, ECD, JIRA, DOORS, PoC, ATA, and UBM.
- Keep domain-specific behavior in the domain app where it belongs (`dcc`, `ddf`, `doors`, `projects/<project>`, etc.).
- Do not move project-specific models, serializers, URLs, or views into shared modules unless multiple apps already need them.
- Preserve existing URL contracts unless the change intentionally includes a migration path for frontend calls.
- Do not commit generated runtime data: SQLite databases, media uploads, static build outputs, logs, certificates, `.env` files, or `node_modules`.

### Backend Python / Django

- Keep Django app boundaries clear:
  - Models in `models.py`.
  - Serializers in `serializers.py`.
  - URL registrations in `urls.py`.
  - Views/API endpoints in `views.py`.
  - Domain services in existing service/helper modules such as `dcc/service/` or `pdf/comparer/`.
- When changing models, create and commit migrations in the affected app's `migrations/` directory.
- Avoid adding database access in loops when a queryset can be optimized. Use Django ORM filtering, selection, and prefetching where appropriate.
- Keep authentication and permission behavior explicit. Many APIs rely on global `IsAuthenticated`; use `AllowAny` only for intentional public endpoints such as login/password reset flows.
- Be careful with file-processing endpoints. Validate uploaded files, limit assumptions about file type/size, and clean temporary files.
- **Verify in repository:** No Python formatter or linter is configured. Match nearby style and keep code simple.

### Frontend Vue / TypeScript

- Follow the committed Prettier settings:
  - No semicolons.
  - 2-space indentation.
  - Single quotes.
  - Print width 100.
  - No trailing commas.
- TypeScript is configured with `strict: true`; do not introduce avoidable `any` types.
- Use the `@/` alias for imports from `frontend/src` when consistent with nearby code.
- Keep API calls centralized through Axios defaults from `frontend/src/services/http.ts` and store/service modules.
- Keep routed pages under `frontend/src/views/` and reusable UI under `frontend/src/components/`.
- Use Pinia stores under `frontend/src/stores/` for shared state.
- Do not hard-code backend hostnames in components; use `VITE_API_URL` / Axios base URL behavior.

## Git Workflow

- Before editing, inspect `git status --short` and avoid overwriting unrelated user changes.
- Keep commits focused on one logical change.
- Include generated Django migrations in the same commit as the model change that requires them.
- Do not commit ignored/generated artifacts. Important ignored paths include `.env*`, SQLite databases, `media/`, `static/`, `dist/`, `node_modules/`, logs, certificates, and Office/export files.
- For frontend dependency changes, update and commit `frontend/package-lock.json` together with `frontend/package.json`.
- For backend dependency changes, **Verify in repository** where dependencies are managed before adding new packages because no backend dependency manifest is committed.

## Security Rules

- Never commit secrets, tokens, passwords, certificates, private keys, database files, JIRA session IDs, DocProof credentials, or production `.env` files.
- Treat `AW_USERNAME` and `AW_PASSWORD` as sensitive even though defaults are empty strings.
- Treat `auth_token` cookies and DRF tokens as credentials.
- Keep `DEBUG=False` for production. With `DEBUG=False`, the settings require `SECRET_KEY` and `CORS_ALLOWED_ORIGINS` and enable secure cookie/HSTS behavior.
- Do not loosen `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, or `CSRF_TRUSTED_ORIGINS` without a specific deployment reason.
- Do not disable CSRF middleware or global authentication to make local testing easier.
- Validate and sanitize file uploads and generated file paths. Several apps process Office/PDF files and expose download behavior.
- Be careful with subprocess and COM automation code in DOORS and conversion workflows. Never pass untrusted shell fragments.
- Keep external binary paths (`DOORS_EXECUTABLE`, `SOFFICE_BIN`, `PDFTOPPM_BIN`) configurable and do not hard-code local workstation paths.

## Debugging Guidance

### Backend

- Start with Django's built-in checks:

  ```bash
  cd backend
  python manage.py check
  ```

- If settings fail to import, inspect missing required environment variables in `backend/awcenter/settings.py`.
- If authentication fails, check whether the client sends either `Authorization: Token ...` or an `auth_token` cookie.
- If production CORS fails, verify `DEBUG=False`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, and `axios.defaults.withCredentials = true` on the frontend.
- If file downloads or generated documents fail, inspect `MEDIA_ROOT`, ignored media/static paths, and temporary file handling in the relevant app.
- If Cheroot does not start, verify `IPV4_ADDRESS`, `PORT`, `AWCenter.crt`, and `AWCenter.key` in the process working directory.
- If DOORS automation fails outside Windows/DOORS environments, check the guard behavior in `backend/doors/views.py` and the installed COM dependencies.

### Frontend

- Confirm `VITE_API_URL` before debugging API calls; Axios uses it as the base URL.
- Confirm the app is opened under `/app/` when using the Django-served route, because Vue Router is configured with `createWebHistory('/app/')`.
- For production builds, remember that `npm run build` also copies files into backend directories. Ensure `backend/templates` and `backend/core` exist before relying on `postbuild.js`.
- If delayed compdoc behavior is unexpected, inspect `SHOW_DELAYED_COMPDOCS` usage and verify whether it is exposed to the client build.
- If imports fail, check the `@` alias in `frontend/vite.config.ts` and `frontend/tsconfig.json`.

## Common Pitfalls

- Backend commands can fail immediately if required `.env` variables are missing, even for checks/tests. `python scripts/starter.py install` creates a local ignored development `.env` when absent.
- Backend dependencies are listed in root `requirements.txt`; update it when backend imports/settings require new packages, keeping the Python 3.14-compatible dependency bounds current.
- `frontend/package.json` defines `deploy` and `start`, but the referenced `scripts/deploy.sh` and `server.js` are not present in the current repository tree.
- Frontend build requires a Vite entry file such as `frontend/index.html`; that file is not present in the current repository tree, so `npm run build` fails until the entry file is restored or Vite is reconfigured.
- Frontend build post-processing assumes Django template/static target directories exist.
- `SHOW_DELAYED_COMPDOCS` is referenced without a `VITE_` prefix in frontend code; verify intended exposure before depending on it.
- SQLite database files are ignored and should not be used as source-of-truth fixtures unless a committed fixture strategy is added.
- `run_cheroot.py` uses relative certificate filenames, so its working directory matters.
- The repository contains many project-specific apps with similar structure. Make changes in the exact project app requested; do not assume all projects should change together.

## User-Provided Custom Instructions

### Agent Identity

- Act as a 25+ years experienced Senior Software Architect.
- Apply Clean Code, Design Patterns, and SOLID expertise.
- Use a security-first approach.
- Stay performance-aware in development decisions.

### Working Principles

1. Understand first, then write.
2. Explain the reason for every change.
3. State trade-offs.
4. Suggest alternative approaches where useful.
5. Never compromise security.
6. Produce production-ready code.
7. Do not deliver code without tests or documented checks.

### Code Writing Rules

- Maximum function length: 20 lines.
- Maximum file length: 200 lines.
- Maximum cyclomatic complexity: 10.
- Maximum nesting depth: 3.
- Document every public function.
- Use meaningful names with full words.
- Write code and identifiers in English.

### Response Format

For each task, structure responses with these sections when applicable:

1. Current state analysis.
2. Prioritized to-do list.
3. Code changes, including complete file contents when requested or appropriate.
4. Test files.
5. Change explanation.
6. Points requiring attention.
7. Suggested next steps.

## Agent Checklist

Before making changes:

- [ ] Read this `AGENTS.md` and any more-specific `AGENTS.md` files if added later.
- [ ] Run `git status --short` and identify existing user changes.
- [ ] Inspect the relevant app/module before editing.
- [ ] Confirm whether the change affects backend, frontend, migrations, environment variables, or generated assets.

While making changes:

- [ ] Keep the change scoped and project-specific.
- [ ] Preserve existing API routes and data shapes unless intentionally changing them.
- [ ] Add or update Django migrations for model changes.
- [ ] Update TypeScript models/stores when backend response shapes change.
- [ ] Avoid committing secrets, local databases, generated exports, build output, or dependency folders.
- [ ] Follow frontend Prettier settings and nearby Python style.

Before committing:

- [ ] Run applicable checks from this file. At minimum, use `python manage.py check` for backend changes and `npm run build` for frontend changes when dependencies/env allow.
- [ ] Run targeted tests when a test command is available and dependencies/env allow.
- [ ] Document any command that cannot run because of missing dependencies, missing env vars, or platform-specific integrations.
- [ ] Review `git diff` for accidental generated files or unrelated edits.
- [ ] Commit only the intended files.
