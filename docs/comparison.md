# Unified Compare

The `/app/compare` page compares two files from the same family: Word (`.docx`, `.docm`), Excel (`.xlsx`, `.xlsm`), or PDF (`.pdf`). The old three page addresses redirect to this page. Existing `/api/tools/{word,excel,pdf}/compare/` endpoints remain compatible; new clients use `/api/tools/compare/`.

## Matching and scope

Comparison is content-only. Word paragraphs (including tables, headers, footers, footnotes and endnotes) and extractable PDF text use shared matching. PDF page/line and Word part/paragraph references appear in the report. There is no OCR, visual layout/image comparison or semantic AI. Textless or image-only scanned PDFs do not produce an “identical” result. Whitespace normalization is only used for matching; original text changes remain visible.

| Preset | Strong (`equal_ratio`) | Possible (`weak_equal_ratio`) |
| --- | --- | --- |
| Strict matching | 0.98 | 0.85 |
| Balanced (default) | 0.92 | 0.70 |
| Extensive revision | 0.85 | 0.55 |

Custom thresholds require finite numbers with `0 < weak_equal_ratio <= equal_ratio <= 1`. These are heuristic starting points, not calibrated accuracy guarantees. Exact equality is independent of matching strength. An accepted pair with changed content remains a change even at high similarity.

Excel compares one selected table per workbook. Inspection suggests a worksheet and a header within its first 20 rows; the user can change both, map renamed columns, select identity columns, or explicitly choose row order. Automatically inferred headers excluding populated rows require another inspection to confirm the choice. Excluded rows are disclosed in reports.

Identity candidates contain up to three mapped columns, are non-empty/unique in both tables, and have at least 80% overlap relative to the larger table. Search is bounded to 500 candidates. Without an identity, exact rows are paired before mutual-best content matching. Both best-vs-second-best margins must be at least 0.10 and the score must reach the strong threshold. Empty/empty cells do not inflate scores; numeric/date cells use exact equality. Uncertain matching or an exceeded fuzzy budget returns guidance requiring identity columns or explicit row order. Added/removed columns are reported alongside cell changes. Formula expressions are compared as content and never evaluated.

## HTTP and job contract

All endpoints require server-side session authentication; POSTs require CSRF and `Idempotency-Key`. No browser credentials are returned or placed in URLs. Error responses use the standard `{detail, code, request_id}` contract.

- `GET presets/`: canonical preset metadata and default preset ID.
- `POST inspections/`: enqueue `comparison.inspect` with multipart `first`, `second`, and a JSON `parameters` field. Accepts Excel only. Alternatively use `inspection_id` to reuse an owned completed inspection and revise its selections, without uploading files again.
- `GET inspections/<uuid>/`: verify ownership, job kind, completion, retention and output SHA-256; return private table preview, selections, matching guidance and effective options.
- `POST jobs/`: enqueue `comparison.compare`. Word/PDF use multipart `first`, `second`, `parameters`. Excel uses an owned resolved `inspection_id`; changing thresholds or selections requires reinspection. Output format may change without reinspection.

Parameters contain `preset`, custom `equal_ratio`/`weak_equal_ratio`, `output_type` (`word` or `excel`), and optional inspection `selection`. Selection fields:

```json
{
  "first": {"sheet": "Data", "header_row": 1},
  "second": {"sheet": "Data", "header_row": 1},
  "columns": [[0, 0], [1, 1]],
  "matching": {"mode": "keys", "keys": [0]}
}
```

Column indices are zero-based; header rows are one-based. `matching.mode` is `auto`, `keys`, or `position`. Keys reference old mapped column indices. Omitting column mappings requests unique case-insensitive name matching. Omitting sheet/header requests a suggestion. Invalid/unknown selection fields are rejected.

Both job kinds run on the existing local worker with a 900-second timeout. Inputs are deterministic server-created packages with exactly `manifest.json`, `first`, `second`; the manifest and job input SHA-256 protect the original immutable pair. Public ZIP uploads are not accepted. There are no new job states, model migrations or dependencies. Inspection details are private output artifacts, not `result_summary` or log content. Existing lease fencing, cancellation, authorized downloads and `JOB_ARTIFACT_RETENTION_DAYS` apply. Revision jobs copy the validated source input so later cleanup of their source does not invalidate the new job.

Keep the idempotency key across an uncertain retry of an unchanged request. A new operation/input uses a new key. Same-key/different-input requests return 409. The frontend invalidates pending restored jobs when files change and never automatically downloads a restored completed report.

## Reports and bounds

DOCX and XLSX are available for every supported input family. DOCX contains marked changes; XLSX contains Summary, Differences and Possible matches sheets. Both come from the same result model. Excel counts use cells and column headers; document counts use text blocks. XLSX neutralizes untrusted formula-leading strings. All actual changes remain visible.

Default bounds: 50 MiB per file through the existing upload policy; 101 MiB internal package (`COMPARE_MAX_PACKAGE_BYTES`); 100 worksheets; 100 columns and 10,000 rows in the selected table; 20 header candidates; 1,000 PDF pages; 10,000 document blocks; 2,000,000 extracted characters; 2,000 characters per changed fuzzy candidate; 250,000 candidate pairs; 100,000 report entries (10,000 for DOCX). Excel report cell text is limited to 32,760 characters. Exceeding limits fails explicitly or requests a safer Excel matching method; report data is not silently truncated. Worksheet previews are sampled and header labels in selectors may be shortened.

## Verification

```sh
python backend/manage.py test comparison.tests word.tests excel.tests pdf.tests jobs.tests.test_worker jobs.tests.test_api jobs.tests.test_artifacts jobs.tests.test_document_jobs jobs.tests.test_isolated_worker automations.test_architecture awcenter.test_architecture awcenter.test_endpoint_security --noinput
npm --prefix frontend run test:ci
npm --prefix frontend run typecheck
npm --prefix frontend run format:check
cd frontend && npx playwright test e2e/compare.spec.ts
```

Use the project's CPython 3.11 environment. Build the frontend and run `collectstatic --clear --noinput` and `verify_frontend_artifact` before release. Restart the local worker to load the new static executor catalog.
