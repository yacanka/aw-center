# Source Download Verification Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Manager source checks trace a locked sample package through repository metadata, version selection, a complete download and integrity verification, with actionable access failures at each stage.

**Architecture:** Keep source orchestration in `scripts/manager/source_checks.py`. Add focused standard-library HTTP/transfer and package-metadata helpers. Reuse existing source-mode selection, system plus selected CA trust, worker cancellation and structured reports. Download only to disposable temporary storage; never install or execute packages or provision runtimes.

**Tech Stack:** CPython 3.11 standard library, existing Manager worker/event protocol and unittest.

**Spec:** The user's 10.11.2026 request and approved preceding explanation: a complete, hash-checked locked sample per permitted Python/npm repository; trace repository access end to end and explicitly identify access failures. Runtime archives use the existing reviewed catalog SHA-256 pins. A sample result must not claim coverage of all locked dependencies.

## Global Constraints

- Preserve corporate/offline source boundaries, required TLS verification and additive system/selected CA trust.
- No new dependencies, runtime installation, package execution, changes to application environments, persistent package caches or database state.
- Never report raw responses/exceptions, URL credentials, query strings, request headers or filesystem paths. Report stage, source ordinal, safe host, HTTP status and reviewed reason.
- Bound metadata bytes, artifact bytes, request/transfer time and redirects. Observe cancellation while streaming; always close responses and remove temporary downloads.
- Preserve unrelated local `artifacts/` and preceding uncommitted changes; implement in the current feature checkout without commits or a new worktree.

## Review Focus

- An index returning a login page with HTTP 200 must not pass package resolution.
- A reachable index whose file server fails must retain successful earlier stages and explicitly fail download.
- Cross-host HTTPS file links and redirects must be traced without becoming public-registry fallback or leaking signed query parameters.
- Missing/malformed expected hashes and truncated bodies must never be reported as verified.
- A failed source must not hide other source results; cancellation retains completed stages and stops later requests.

### Task 1: Bounded HTTP transfers and reviewed transport errors

**Files:** create `scripts/manager/source_probe.py`, test `scripts/test_manager_source_probe.py`.

- [x] Write failing tests for full-body reading, size/time bounds, truncation, HTTP/proxy/TLS/DNS failures, HTTPS redirects, cancellation and temporary-file cleanup.
- [x] Run tests and inspect expected failures.
- [x] Implement streaming transfer results, strong digest comparison and sanitized access diagnostics with no external dependencies.
- [x] Run the new tests.

### Task 2: Locked package and runtime verification

**Files:** create `scripts/manager/source_packages.py`; modify `scripts/manager/source_checks.py`, `scripts/manager/payload.py`; test `scripts/test_manager_sources.py` and package-helper tests.

- [x] Add failing tests for Python Simple HTML/JSON metadata, exact pinned sample selection, npm scoped metadata/version/lock integrity, malformed/login responses, missing versions, separate file-server failure and successful runtime SHA-256 verification.
- [x] Implement per-stage rows/progress and complete temporary downloads. Use a platform-independent Python wheel sample and a locked npm package; document unsupported samples instead of inventing resolver semantics.
- [x] Include the new modules in the explicit Manager source payload.
- [x] Verify source-mode isolation, continued diagnostics after failures, cancellation and partial evidence retention.

### Task 3: Honest summary, documentation and verification

**Files:** modify `scripts/manager/view_model.py`, `scripts/test_manager_view.py`, `docs/windows-manager.md` and payload tests.

- [x] Add failing tests ensuring failed/incomplete source diagnostics cannot produce a successful/usable installation summary.
- [x] Update source-check summary and document sample guarantees, download bounds and stage-specific remedies.
- [x] Run focused tests, the Manager suite and relevant launcher/source/package contract tests; run `git diff --check`.
- [x] Obtain a fresh final code review; fix material findings with regression tests. Report native Windows or corporate-network checks that cannot run locally.

## Execution Record

- Initial investigation: the previous implementation checks only HTTP status; it does not read metadata or package bodies. The preceding npm URL fix and its regression test are retained.
- Execution method: inline. No changes to dependency sources/locks or application behavior are required.
- Focused orchestration/parsing/transport tests: 54 passed after the review fixes; an additional per-hop error-route regression is included in the final suite.
- Related launcher/source/package contract verification: 176 tests passed.
- Full Manager suite before review fixes: 397 tests passed, 9 native/environment skips. An earlier sandbox run could not bind localhost; the unrestricted rerun passed without changing the lifecycle code.
- Public repository smoke: the actual locked `annotated-doc==0.0.4` wheel (5,303 bytes) and `@antfu/install-pkg==2.1.0` tarball (2,837 bytes) fully downloaded and passed SHA-256/SHA-512 respectively.
- Final review: four material findings reproduced with failing tests and fixed in one pass: unbounded inherited redirect-body reads/response closure, copied authentication headers, stale per-hop proxy attribution, and storage close/cleanup misclassification.
- Ruling: retain a cooperative 120-second transfer budget with bounded socket inactivity and per-hop remaining-budget propagation; explicitly document that standard-library DNS/header processing is not a strict wall-clock guarantee. Enforcing that guarantee would require a separate transport/process design beyond this diagnostic change.
- Final verification after the review fix pass: 405 Manager tests, 396 passed and 9 native/environment skips; `git diff --check` passed. No lifecycle/environment assertions were removed or skipped to obtain this result.
- Final real-network smoke after the redirect fixes: 14/14 stages passed. The locked Python/npm samples and all three reviewed runtime archives were completely downloaded and hash-verified, including the real GitHub-to-release-assets HTTPS redirect. Runtime sizes were Python 48,749,854 bytes, Node.js 35,604,229 bytes and npm 2,714,849 bytes. Temporary files were removed; no packages or runtimes were installed.
- Remaining environment validation: native Windows packaging and the user's corporate proxy/CA/repository access were not available on this macOS host. No review findings were deferred.
