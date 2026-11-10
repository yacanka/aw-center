# Private DCC signatory policy

The existing `gokbey` DCC controller adds mandatory reviewers to three panels.
Names are business configuration and must not be committed, embedded in tests,
printed in logs or included in deployment evidence. This does not add organization
records or change JIRA assignments, stored snapshots, HTTP payloads or DOCX fields.
The `gokbey_jandarma` and `gokbey_sivil` controllers retain their existing separate
rules, including the optional `GOKBEY_SOFTWARE_AS_NAME` setting.

## File and environment

Create an operator-managed UTF-8 JSON file **outside the repository**, separate
from private artifacts and generated output. Set its absolute path in the private
`AWCENTER_ENV_FILE` or process environment:

```dotenv
GOKBEY_DCC_POLICY_FILE=/absolute/private/config/gokbey-dcc-policy.json
```

Synthetic example only; replace the three values through an approved private
channel with the existing approved reviewers. Preserve these keys exactly:

```json
{
  "schema_version": 1,
  "panel_responsibles": {
    "flight": "Example Flight Reviewer",
    "human factor": "Example Human Factors Reviewer",
    "electrical systems/e3": "Example Electrical Reviewer"
  }
}
```

The schema requires all three panels, nonempty names of at most 255 characters,
and no control characters. Unknown or duplicate keys and files above 64 KiB are
rejected. There is no built-in person-name fallback. Only the `gokbey` controller
requires this file. Missing/invalid configuration stops its preview or document
job with `DCC_POLICY_UNAVAILABLE`, without publishing an incomplete document or
exposing the file path/content in the API error. Other project controllers and
mail delivery do not read it.

The file is read afresh for every render; replace it atomically after validation.
Preview and worker must see the same approved version: pause affected submissions,
drain affected jobs, update the file, then generate a fresh preview. Editing it
between a preview and a queued render can change mandatory reviewers, as these
reviewers are render policy rather than part of the captured JIRA snapshot.

The original panel matching, person order, Turkish name comparison and JIRA-name
combination behavior are preserved. Canonical snapshots remain unchanged. Both
DOCX field contracts retain their existing precedence: an explicit lowercase
`as_name` captured from JIRA stays authoritative for that alias; the mandatory
reviewer is added to `Panel_AS_Name`, as before.

## Permissions and deployment

On POSIX, the runtime user must own the file, with no group or other permissions
(e.g. `chmod 600`), and the dedicated parent directory should use `chmod 700`.
The loader verifies owner and file mode; review extended ACLs separately. A symlink
cannot bypass the rule excluding the checkout.

On Windows, use a dedicated private configuration directory, disable inherited
access, and restrict access to the AW Center runtime account and approved system
administrators according to institutional policy. Review **both directory and file
ACLs** with `icacls` before use and after replacement. POSIX mode checks do not
validate NTFS ACLs. No Windows ACL validation has been run on the development Mac.

The current local development assignments have been transferred directly into the
private JSON without printing their values. Existing data and JIRA records were
not modified. The environment on another machine still needs this private file
and path configured; restart its backend and job worker after changing the env.
Compare a synthetic DCC preview and DOCX before resuming normal work. Never use
real names in test fixtures or send migration content through public chat/logs.

For the future Compose profile, place the policy in the operator-managed
`DOCUMENT_TEMPLATE_DIRECTORY` as `gokbey-dcc-policy.json`; backend and job worker
already mount that directory read-only. The runtime path is
`/app/document-templates/gokbey-dcc-policy.json`. Provision ownership for container
UID 10001 with owner-only read access. Notification and cleanup workers receive
neither this path setting nor this mount. Do not mount the policy inside the
writable private-artifact volume.

## DocProof CA configuration

There is no institution-specific CA filename default. Leave
`DOCPROOF_CERTIFICATE_FILE` unset/empty for the existing TLS verification flag and
system trust behavior; normal secure operation requires `DOCPROOF_VERIFY_SSL=True`.
For an internal CA, configure the absolute path of the existing approved external
CA bundle in the private environment:

```dotenv
DOCPROOF_VERIFY_SSL=True
DOCPROOF_CERTIFICATE_FILE=/absolute/private/certificates/docproof-ca.pem
```

An explicitly configured missing, relative or non-file path now fails safely
before login, rather than silently falling back. Production `check --deploy`
reports `awcenter.E039` for these paths. Existing valid bundles are still passed to
Requests for the live client and anonymous probe. Actual certificate validity and
service connectivity require a check on the machine that hosts the integration.
Do not disable TLS verification to work around a migration error.

## Mail behavior

No fixed institutional recipient list was found in the current tracked source.
Watcher reminders keep using valid assignee addresses from unfinished JIRA
subtasks, with deduplication. Compliance notifications keep using the selected
panel's organization assignments/custom responsible selection. Outbox fencing,
retry behavior, idempotency and notification-worker-only SMTP credentials remain
unchanged. Historical branches, backups and Git history are separate findings.

Explicit DocProof CA selection is passed to both login and search requests.
`REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE` cannot replace an explicitly selected
CA file. Integration HTTPS clients (JIRA, Teamcenter, Numarator, DocProof and AI),
including anonymous probes and HTTPS proxy connections, use additive trust:
Windows CA/ROOT and OpenSSL system defaults plus Requests' public CA roots remain
trusted when a custom CA is selected. With no custom CA, those defaults are used;
the existing Requests environment-bundle precedence is retained and the resolved
environment bundle also supplements default trust. Trust contexts are isolated
per session and client-certificate identity. TLS validity and SAN hostname
verification remain enabled; a malformed selected CA fails before connection.
