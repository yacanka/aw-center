# Compliance import with optional ATA

Approved in the conversation on 12.11.2026; implementation requested by the user.

Documents may share a panel name while referencing different ATA chapters. A missing ATA is accepted without choosing an existing chapter, even when one or more panels already use that name. Within a project, repeated names with missing ATA share one ATA-less panel. Matching trims surrounding whitespace and ignores case. Existing populated ATA matching remains unchanged.

The explicit ATA column is authoritative, including numeric-looking panel names: an absent chapter never infers ATA from the Panel column. Export writes the actual panel name and a separate ATA column so empty and populated references round-trip unambiguously. An explicitly empty ATA with an omitted Panel column retains an existing document's panel name and selects its ATA-less variant.

Later assignment changes the individual document's panel reference, never the shared ATA-less panel. An omitted ATA column preserves an existing document's ATA when its panel name is unchanged; an explicitly empty ATA cell selects the ATA-less panel. Omitted panel and ATA columns preserve the existing reference. Both explicitly empty fields retain the existing clear-panel behavior.

## Approaches

- Selecting a populated panel when ATA is missing was rejected: the user requires accepting the empty value.
- A shared `N/A` ATA was rejected: project/ATA uniqueness would merge unrelated panel names.
- Chosen: optional ATA on the existing `orgs.Panel`, with project/ATA uniqueness for populated chapters and project/normalized-name uniqueness for ATA-less panels. Keep the canonical compliance aggregate and existing foreign keys.

Represent missing catalog ATA as the empty string, retaining the string-shaped organization API; document ATA remains null in responses. Maintain a private Unicode-casefolded name key for database-enforced ATA-less uniqueness. Add a forward-only migration, preserving existing rows and IDs.

Imports remain non-mutating during preview. Only accepted document rows contribute panel creations, and confirmation binds the complete panel snapshot and proposed changes. Preserve project scope, CAS versions, tracking-recipient compatibility, transactions, and audit history. Excel export must retain names of ATA-less panels for round trips.

Update existing selectors and forms to retain panel names when ATA is cleared. Support resolving a named ATA-less reference during document saves without mutating the catalog during validation. Existing organization panel import continues requiring ATA; update its handling only where the new catalog state affects it. No dependency or theme changes.

Verify normalized-name uniqueness, repeated names, multiple ATA-less names, populated/empty variants, no inference from populated panels, omitted versus empty columns, per-document reassignment, invalid-row isolation, rollback, preview conflicts, API project scope, exports, selectors, and responsible assignment selection by stable panel ID.
