# Manager system tool selection

## Intent

Use existing Python and Node.js installations before downloading runtime archives.
Add a remembered Node command/executable field alongside Python. The user explicitly
requests automatic download when no usable installation is found.

## Approach

Extend the existing operator-installed Python pattern to Node rather than copying
system installations into managed directories. Managed downloads keep their reviewed
catalog/hash policy. Shell expressions are never executed. System executables remain
operator-trusted, and are probed before use and again on prepared restart.

Automatic selection searches PATH and standard Windows locations. A missing or
incompatible automatic candidate permits managed fallback; explicit invalid input
produces an actionable error. Cancellation never initiates a fallback download.
The optional Python checkbox explicitly forces the managed Python; default is auto.

## Compatibility

- Python remains CPython 3.11 x64 with venv and ensurepip.
- Node requires x64, Windows on Windows hosts, and Node 22.12+ within major 22,
  or Node 24+. These ranges cover the checked-in Vite/Vitest engine intersection
  and the project's TypeScript stripping commands; unsupported/prerelease versions
  are rejected.
- Managed npm remains pinned to 10.9.4 (`frontend/package.json` packageManager).
  Compatible installed stable npm 10.9.4+ within major 10 or npm 11 is reused;
  otherwise only the reviewed npm archive is acquired. Issue #131 clarified the
  requirement with Node 26.12.1/npm 11.18.0; runtime pins and locks remain unchanged.
- System tools are never modified. Profile metadata stores executable pointers;
  form preferences store Node command/path with the same safeguards as Python.

## Offline bundle

The user requested no redundant runtime downloads during bundle preparation too.
When system tools are used, a version 2 bundle manifest declares those tools as host
requirements and omits their runtime archives. It exports versions, never producer
filesystem paths. Only omitted tools may differ from catalog runtime versions,
and only within supported runtime constraints; all included archives remain pinned.
Existing complete version 1 bundles remain valid. Default CLI packaging still
produces complete version 1 bundles; Manager explicitly opts into host requirements.
An offline target without required tools reports the missing prerequisite rather
than silently using a different runtime or contacting the network.

## Validation

Real subprocess probes and mocked network boundaries cover discovery, incompatible
versions/architecture, quoting, cancellation, npm reuse, fallback without duplicate
downloads, profile restart, persistence and both bundle formats. Keep the Manager
stdin isolation and safe error-reporting contracts. No new dependency or unrelated
Windows UI repair is included.
