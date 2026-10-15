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

Apply forward migrations `0011_project_status_catalog` and `0012_seed_project_statuses` before serving the updated application. Seeding preserves current values and history, and creates only current project statuses plus Unknown. Future projects receive Unknown automatically. No database reset is needed.

Known status codes retain existing delay, approval and risk calculations. Custom codes appear in counts/charts under their own label but acquire no implicit workflow semantics.

## Document field contract (issue #123)

Document metadata uses `number` and `issue`, distinct from the nested
`cover_page.number` and `cover_page.issue`. The field metadata schema is version 4.
Document CRUD, search/filter/sort, register export, DocProof, numbering snapshots,
notifications and dashboard consumers use the canonical names. Existing risk
weights and workflow behavior are unchanged; the revised target still takes precedence.

Migration `0016_canonical_document_fields` renames `tech_doc_no`, `tech_doc_issue`,
`ubm_target_date`, `ubm_revised_target_date` and `ubm_delivery_date` in both live and
historical tables, preserving their values. It drops `delivered_tech_doc_issue`,
`delivered_tech_doc_issue_2`, `tech_doc_no_2` and `tech_doc_issue_2`, including their
historical values. This deletion is intentional: these fields have never been used
in production and require no archive. The second reference and delivered-issue UI,
search and DocProof lookup support are removed. A document now has one reference.

Excel/DOORS source headers using the former primary names remain recognized, but
mapping targets and API fields use only the new names. Removed-field headers are
excluded before fuzzy matching so they cannot overwrite a primary reference.
Saved DOORS mappings are migrated; removed target links are dropped. Historical
import audit records and completed numbering snapshots remain original evidence.

Deploy the backend and frontend together with web/worker processes stopped.
Resolve every unfinished cover-page numbering allocation using the previous
application version first; the migration refuses to proceed while any remain.
Apply the forward migration without resetting the database, then restart services.
Old Excel/DOORS preview tokens require a fresh preview. Browser-local column
layouts from earlier metadata versions reset to recommended columns; other
preferences are unaffected. No legacy API aliases are provided.
