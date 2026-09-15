# Bulk cover page numbering

Excel import accepts a missing **Cover Page Number** column or blank cells. Only
the document name is required. Unnumbered documents receive independent cover
pages and can use **Assign missing numbers** after import. Reimport matching still
uses cover number plus document name or technical number; export and retain the
document UUID when updating a document after its number has been assigned.

Editors can open **Assign missing numbers** beside **New** in the Compliance
Documents table. The preview uses only the active, unnumbered documents on the currently displayed
table page, after search and filters. It never fetches other pages. Users can deselect documents and choose one of the project's allowed
Numarator formats before submitting. Each selected format exposes its dynamic
context fields with required flags, default hints and maximum lengths. Supplied
Manual values apply to all selected documents and are frozen with each allocation request.
The exact, case-sensitive keywords `ata` and `moc` are filled automatically for each
document: `ata` uses its panel's ATA chapter with all hyphens removed (for example
`27-00` becomes `2700`, `05-10` becomes `0510`), preserving leading zeros and the
stored chapter value. Format length limits apply to the hyphen-free value. `moc` uses its
MOC value (including `0`). These fields are read-only in the numbering form and
follow document edits before submission. Missing required values or values longer
than the format allows prevent submission; correct the document first. Other
keyword names, including `ATA` and `ata_chapter`, remain manual.

Requests are submitted sequentially through the existing document allocation API.
Each document retains its own operation ID and versioned snapshot for retries.
Existing allocations are recovered first and keep their original format. Failed
rows do not prevent other selected rows from being queued. The panel polls results
while open and applies completed documents to the table. Queued work continues
when the panel closes; leaving the project stops submitting remaining rows.

**Retry unfinished** reuses existing allocations rather than generating replacement
numbers. After leaving the page, reopen the document editor to recover an unfinished
allocation, including a number already bound locally but awaiting Numarator's
mark-used confirmation. Version conflicts, archived documents and shared unnumbered
cover pages retain the existing allocation API's validation and audit behavior.

The list API accepts `missing_cover_page=true|false` in addition to its existing
project scope, archive filter, ordering and pagination. No schema change is required. The read-only
`compliance.describe_numbering_format` job reads the selected format through the
existing local worker and publishes an owner-scoped, verified JSON artifact.
The web process never receives the Numarator API key. Numarator configuration and a running allocation worker
are required to complete numbering.

Single-document numbering uses the same field component and validation. Optional
blank inputs use the defaults declared by Numarator; required fields prevent
submission. Format lookup errors block new allocations instead of silently
assuming a format has no custom fields. Legacy API callers that omit
`context_data` retain the implicit project context; explicit context objects are
forwarded as supplied except for `ata` and `moc` keys, which the backend resolves
from the validated document input (or existing document for omitted fields).
Only keys present in the context request trigger this mapping; no keywords are
added to unrelated formats. Resolved values are persisted when the allocation is
created and reused on retries. Empty document values are omitted, allowing optional
Numarator defaults while required-field validation still blocks number generation.
Project authorization remains tied to the route and model.
