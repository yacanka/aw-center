# Manager automatic recovery implementation plan

> **For agentic workers:** Use test-first implementation with independent file ownership and one final code review.

**Goal:** Let desktop preparation exhaust safe local/network alternatives with useful progress and minimal required input.

**Architecture:** Extend existing SourceSettings acquisition and Manager orchestration. Preserve isolated worker, OS lease, TLS/hash, profile and migration boundaries.

**Tech Stack:** Python 3.11 standard library, Tk/ttk, existing pip/npm acquisition.

**Spec:** `docs/superpowers/specs/2026-11-05-manager-automatic-recovery-design.md`

## Global constraints

- Work in the existing workspace; preserve the previous turn's uncommitted storage diagnostics.
- Keep corporate selected-only, offline network-free, TLS/hash/cancellation failures closed.
- No dependencies, global runtime writes, data/ACL repair, Git history changes or release publishing.

## Review focus

- A truncated download retries without accepting partial bytes.
- An HTTP rejection tries only other permitted sources and retains a useful final code.
- A valid local package avoids unavailable network services; corrupt media is rejected.
- Existing output directories are preserved; destination leases cover automatic children.
- Bundle cache reuse does not mutate active tools or trust bytes without SHA-256.

## Tasks

1. Acquisition recovery — `installation_sources.py`, `installation_dependencies.py`, source/dependency tests. Write failing interrupted-transfer, transient-status, local-first and permission-boundary regressions; implement; run affected suites.
2. Full bundle reuse/preflight — `manager/distribution.py`, `installation_bundle.py`, distribution/bundle tests. Validate output before tool preparation; reuse newly downloaded and existing verified archives; prefer validated local dependencies; test offline second-stage completion and invalid-output early failure.
3. Desktop defaults and progress — `manager/operations.py`, `paths.py`, `view_model.py`, `view.py`, Manager tests. Default to restricted policy, create safe unique bundle outputs, report phases before locks/source checks, classify genuine source/distribution needs and surface successful output. Test form/worker admission and no overwrite.
4. Verify/document — launcher and Manager discovery, repository check, release metadata, scoped backend production/SQLite/worker tests, frontend build/static verification, independent final review. Document Windows-only limits and automatic recovery behavior.

## Execution record

- Planning: independent audits confirmed interrupted-transfer/classifier gaps, duplicate runtime acquisition, and uncategorized pre-phase admission failures.
- Ruling: continue in this workspace because this work extends the previous uncommitted changes; no branch/worktree change or commit is needed to make the result reviewable.
- Task 1: RED/GREEN complete; 72 focused acquisition tests passed. Real short Content-Length transfers retry; complete corrupt bytes remain fatal. Safe package-command categories now retain the genuine user need.
- Task 2: RED/GREEN complete; 117 related tests passed, 5 native tests skipped. Output admission precedes tools; new/existing archives are reused read-only. Lexical '..' normalization preserves the intended source boundary.
- Task 3: RED/GREEN complete; automatic targets are unique and claimed before the worker starts; selected existing directories are preserved; source/distribution failures report their actual phase. Offline form no longer blocks automatic local discovery.
- Final review: accepted and corrected three findings with RED/GREEN regressions: incidental package/path text misclassified as TLS; output overlapping verified input trees (including recursive asset copying); isolated npm acquisition timeout losing fallback. Precise error signatures, pre-lease desktop relocation / CLI rejection, and typed timeout limited to isolated npm acquisition address them. Affected suites: 98 tests passed before the final full discovery runs.
- Ruling: Python wheel/build and final offline installation timeouts remain terminal because a timeout alone does not establish a retry-safe network failure. Managed runtime/profile binding and explicit tool selections remain protected.
- Final verification: launcher discovery 366 tests / 12 skipped; Manager discovery 270 / 48 skipped; scoped production/SQLite/worker/DOORS-adapter backend 129 passed; release metadata 12 passed. Total distinct passing tests: 717, with 60 environment/native skips. Repository check (Django, migration consistency, frontend format/type checks), prod help, frontend build/budget, isolated collectstatic/frontend artifact verification, compileall and git diff --check passed.
- Remaining evidence: no native Windows EXE was built here; real Windows ACL/NTFS/LockFileEx/Tk and restricted corporate-network acceptance are still required. No commit, push, release publication, dependency lock, application data or environment credential changes.
