# Private project mappings and DDF assessment policy

Technical project slugs, capability sets, routes, controller allowlists and
`orgs.Project` identities are unchanged. Business display names remain in the
existing database. Historical migrations are preserved. No automatic data import,
project creation, role grant or database synchronization occurs when a JSON file
is read. The public project catalog keeps its existing safe field set and
continues to work without private integration configuration.

## Files and setup

Provision two UTF-8 JSON files outside the checkout and private-artifact storage.
Set their absolute paths in the existing private `AWCENTER_ENV_FILE` or process
environment; process values retain precedence:

```dotenv
PROJECT_CONFIGURATION_FILE=/absolute/private/config/project-configuration.json
DDF_ASSESSMENT_POLICY_FILE=/absolute/private/config/ddf-assessment-policy.json
```

These files use the same bounded private-file reader as the DCC signatory policy:
maximum 64 KiB, schema version 1, no duplicate JSON keys, absolute external path
including resolved symlink targets, current POSIX owner and no group/other access.
Use mode 0600 on files and 0700 on the dedicated directory; review extended ACLs.
Windows operators must restrict and verify file **and directory** NTFS ACLs.
The development Mac does not establish Windows ACL correctness.

The selected local mappings and the full DDF prompt prefix were exported directly
before removing their source defaults. Actual values were not printed or added
to fixtures. Copy the approved files to other machines through the institution's
approved private channel; do not reconstruct real mappings from synthetic examples.

## Project configuration schema

The following is a **partial synthetic illustration**, not a deployable file:
all installed JIRA-capable project slugs must be present exactly once. Existing
compliance-only project capabilities remain static and cannot be added here.

```json
{
  "schema_version": 1,
  "projects": {
    "hys": {
      "jira_component": "Example Component",
      "aliases": ["EXAMPLE-ALIAS"],
      "dcc_label": "Example Document Label",
      "dcc_template_name": "example_dcc.docx",
      "mail_template_name": "example_mail_template"
    }
  },
  "cover_pages": {
    "match_text": "EXAMPLE",
    "match_label": "Example Work Package",
    "default_label": "Example Project"
  }
}
```

JIRA component matching preserves trimming, case folding, Turkish dotted-I
normalization and explicit aliases. Duplicate/ambiguous components are rejected.
Labels and component names are bounded nonempty printable strings; aliases are
bounded lists. DOCX template names are plain `.docx` filenames resolved under the
existing trusted template directory. The JSON cannot choose an arbitrary path,
controller, callable, capability or authorization role. Unknown schema fields,
missing project entries and invalid template names reject the configuration.

`projects.registry.PROJECT_DEFINITIONS` is now purely technical. Internal adapter
consumers explicitly join the private metadata when resolving a JIRA project or
choosing a document template. Private fields are not added to browser catalog
responses. Technical navigation grouping and stable route keys remain unchanged;
this is not a project-renaming or historical-data-anonymization operation.

Cover-page selection retains the previous case-insensitive **contains** rule.
The first workbook row chooses one label for every DOCX in the ZIP, including a
mixed workbook. This migration does not switch to per-row selection. Existing
filenames, workbook columns, fallback template and document placeholders remain
unchanged. The retired `COVER_PAGE_B30_PROJECT_LABEL` and
`COVER_PAGE_DEFAULT_PROJECT_LABEL` env keys are no longer read; move their effective
values into this JSON rather than leaving obsolete overrides in an env file.

Unavailable or invalid project configuration returns sanitized
`PROJECT_CONFIGURATION_UNAVAILABLE` for affected requests/document jobs.
There is no built-in institutional metadata fallback. Authorization checks and
owner scoping remain in their existing feature services; configuration never
creates or broadens access.

## DDF policy schema

```json
{
  "schema_version": 1,
  "prompt_prefix": "Synthetic classification instructions.\nComments:\n        "
}
```

Provision the **original approved prefix**, including all whitespace, line breaks,
Unicode and the trailing indentation. The existing numbered comment list is
appended using its previous string representation. This is plain data, not an
executable template: no format expression, Jinja, arbitrary import or evaluation
is performed on file contents. The four existing classification labels, response
format, order and `comment_types` persistence remain unchanged.

DDF comment text is approved for the existing internal AI service and continues
to use `AI_API_*`. No additional record metadata or document file is sent by this
change. Missing/invalid policy returns sanitized `DDF_POLICY_UNAVAILABLE` before
an AI call or classification write. Existing DDF records remain intact.
AI is nondeterministic; an unchanged prompt and request contract do not guarantee
identical live classifications. Live provider and retention controls must be
verified on the actual integration host.

## Deployment and updates

Deploy the files to both backend and applicable job-worker environments before
restarting them. Pause affected submissions, drain related queued work, atomically
replace each approved file and restart all participating processes together.
Regenerate previews before resuming. Files are read afresh; do not change project
mapping/template policy between a preview and its worker render. Existing stored
snapshots, document IDs and role assignments are not rewritten.

For the future Compose profile, put `project-configuration.json` and
`ddf-assessment-policy.json` in the operator-owned `DOCUMENT_TEMPLATE_DIRECTORY`,
already mounted read-only at `/app/document-templates`. Provision read access
for runtime UID 10001 with no group/other permissions. Backend and job worker
receive the project policy path; only backend receives the DDF policy path.
Notification and cleanup workers receive neither path. Do not put these files
inside the writable artifact volume or the image build context.

After installation, run the existing checks, then use synthetic input to verify:
JIRA resolution and project role rejection, DCC preview/template selection,
reminder subject and recipients, custom/fallback DOCX cover-page text, and DDF
classification/persistence. No live institutional endpoint is needed for the
automated test suite: its test runner provisions synthetic private files, including
for spawned workers, and restores the previous settings afterwards.

### DDF assessment integrity

Assessment requires `ddf.change_ddf` and ownership of the existing record.
The request's comments must match the saved comments; a stale request returns
`409 DDF_ASSESSMENT_CONFLICT` before any AI transmission. Reload before retrying.
The AI response must contain exactly one of the four supported classifications
per comment. An invalid response returns `ASSESSMENT_RESPONSE_INVALID` without
changing the saved result. A conditional database write also rejects a result if
comments or classifications changed, or the record was deleted, during the AI
request. No database lock is held during the network call. Existing records are
not migrated or rewritten by deployment.

JIRA component batches use one validated private configuration snapshot per
resolution operation. No process-global cache delays operator configuration changes.
