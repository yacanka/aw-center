# Compliance document statuses

Status options belong to a project and are shared by that project's users. A document has one current status; table filters accept multiple statuses. The previous global list is no longer an assignment allowlist.

## Import and editing

Excel and DOORS imports discover status options from valid rows. Preview shows proposed new options and rows using Unknown without writing the catalog. Confirmation creates options in the same transaction as the documents. Failed rows and rolled-back imports do not leave options behind.

New documents without a status start as `unknown`. When updating an existing document, an omitted status column preserves its current status; a mapped but blank status cell explicitly changes it to Unknown. A status change appends a workflow event without rewriting history. An explicit effective date must not precede the latest workflow event. When no effective date is supplied, import keeps the event chronology valid even for legacy records whose events used a future target date.

The original target (`target_date`), revised target (`revised_target_date`) and release (`release_date`) dates are independent document fields. Their order does not constrain imports or workflow event dates. The revised target takes precedence for current due and risk calculations while the original target remains available for reference.

Status names are single-line strings of at most 128 characters. Codes retain the legacy import normalization: trim whitespace, case-fold, remove periods, replace whitespace with underscores. The normalized code is also limited to 128 characters. Equivalent codes reuse the project's existing option and label. `unknown` is the protected default; `delayed` remains a calculated display state and cannot be assigned.

## Settings and permissions

The compliance settings page separates shared status options from browser-local table preferences. Viewers can read the catalog. Managers can add options and delete unused options; editors can introduce options through imports.

Any current use, including an archived document, prevents deletion. Historical use alone does not prevent deletion, and historical text remains intact. Unused options remain until a manager deletes them; options are never automatically garbage-collected. Development test-data reset clears non-default options alongside documents.

## API and migration

Under `/api/projects/<slug>/compliance-documents/`:

- `GET statuses/` returns `{id, value, label, usage_count, can_delete}` entries.
- `POST statuses/` accepts `{label}` and returns the created entry; equivalent existing codes return 409.
- `DELETE statuses/<uuid>/` returns 204, or 409 for protected/in-use options.

Document responses add `status_label`; the existing `status` string is unchanged. Field metadata and dashboard vocabulary are project-specific. Session authentication, CSRF, project roles, document versions and signed import confirmation remain enforced.

The fresh-install baseline creates the catalog schema in the initial migrations.
`compliance/0003_seed_default_statuses` adds Unknown to every project seeded by
`orgs/0002_seed_projects`. No historical document values are imported. Projects
created later receive Unknown automatically through the existing project signal.
This baseline does not upgrade earlier development databases; see the
[local reset runbook](local-database-reset.md).

Known status codes retain existing delay, approval and risk calculations. Custom codes appear in counts/charts under their own label but acquire no implicit workflow semantics.

## Document field contract (issue #123)

Document metadata uses `number` and `issue`, distinct from the nested
`cover_page.number` and `cover_page.issue`. The field metadata schema is version 4.
Document CRUD, search/filter/sort, register export, DocProof, numbering snapshots,
notifications and dashboard consumers use the canonical names. Existing risk
weights and workflow behavior are unchanged; the revised target still takes precedence.

The fresh baseline creates `number`, `issue`, `target_date`, `revised_target_date`
and `release_date` directly in live and historical document tables. The removed
`delivered_tech_doc_issue`, `delivered_tech_doc_issue_2`, `tech_doc_no_2` and
`tech_doc_issue_2` columns do not exist. The second reference and delivered-issue
UI, search and DocProof lookup support are removed. A document has one reference.

Excel/DOORS source headers using the former primary names remain recognized, but
mapping targets and API fields use only the new names. Removed-field headers are
excluded before fuzzy matching so they cannot overwrite a primary reference.
Newly saved DOORS mappings use canonical targets. Fresh installs contain no
previous import audits, saved mappings or pending numbering snapshots.

Install the backend and frontend together on an empty database. Earlier local
schemas require a deliberate reset following the local runbook. No compatibility
migration, content-copy step or unfinished-allocation guard is needed in this
fresh-only baseline. Browser-local column layouts from earlier metadata versions
reset to recommended columns; other preferences are unaffected. No legacy API
aliases are provided.
