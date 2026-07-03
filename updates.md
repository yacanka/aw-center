## 1. Pagination geçiş notları

1. Backend tarafında standart response contract `count`, `next`, `previous`, `results` olacak şekilde merkezi DRF pagination eklendi.
2. APIView tabanlı büyük listeler için ortak `paginated_response(...)` helper'ı eklendi ve kullanıcılar, permission listesi, DCC, DDF/compdoc factory listeleri ile history endpointlerinde kullanılmaya başlandı.
3. Frontend geçiş döneminde hem legacy array response'ları hem de paginated response'ları okuyabilen helper ile mevcut tabloların kırılması engellendi.
4. Sonraki aşamada tablo bileşenlerine page/page_size state'i bağlanmalı ve filtreler Axios `params` üzerinden server-side taşınmalıdır.

## 2. Tablo pagination ve server-side filtreleme geçişi

1. CompDoc, DDF ve Users tablolarında `page`, `page_size` ve toplam kayıt sayısı backend pagination metadata'sına bağlandı.
2. İlgili store aksiyonları Axios `params` kullanarak pagination ve filtre query parametrelerini backend'e taşır.
3. Backend generic list helper'ı sadece model alanlarını allowlist olarak kabul eden güvenli server-side filtreleme uygular; bilinmeyen query parametreleri yok sayılır.
4. Sonraki aşamada Naive UI kolon filtrelerinin tamamı için frontend tipleri netleştirilmeli ve array/JSON alan filtreleri domain-specific backend lookup'larına ayrılmalıdır.

## 3. DCC ve çoklu filtre pagination tamamlaması

1. DCC Watcher tablosu da remote `page`, `page_size` ve backend `count` metadata'sına bağlandı.
2. Genel server-side filter helper tekrarlı query parametrelerini `__in` lookup'a dönüştürür; tekil metin alanları `icontains`, diğer alanlar exact lookup kullanır.
3. Frontend pagination query tipi boolean ve string/number array filtre değerlerini kabul edecek şekilde genişletildi.
4. JSON alanlarda generic lookup yerine ileride domain-specific filtre endpoint sözleşmeleri kullanılmalıdır; SQLite JSON lookup limitleri nedeniyle bu bilinçli olarak generic filtreye zorlanmadı.

## 4. Cookie-only login hardening revision

1. Token'ın response body içinde dönülmesi ve frontend storage'a yazılması güvenlik gerekçesiyle tercih edilmedi; login yalnızca HttpOnly cookie ile kimlik doğrular.
2. Frontend login başlangıcında eski/stale `Authorization` header ve storage token temizlenir; böylece eski token cookie-auth akışını gölgeleyemez.
3. Auth cookie adı, ömrü, `SameSite` ve `Secure` ayarları environment üzerinden yönetilebilir hale getirildi.
4. Regression testleri token sızdırılmadığını, cookie'nin HttpOnly/SameSite ayarlarıyla set edildiğini ve `/auth/me/` endpoint'inin login sonrası cookie ile çalıştığını doğrular.

## 5. Login bootstrap without immediate auth/me dependency

1. Login response now returns a safe serialized user payload while keeping the token HttpOnly-cookie-only.
2. The login page initializes the user store from that safe payload instead of calling `/auth/me/` immediately after login.
3. `/auth/me/` remains the bootstrap/session validation endpoint for page refresh and existing sessions, not the critical post-login transition dependency.
4. This avoids false login failures when the browser has not made the new HttpOnly cookie available to the next request yet or when cookie policy debugging is still in progress.

## 6. Refresh bootstrap cache fallback

1. Startup `/auth/me/` calls can now suppress auth-warning side effects during bootstrap.
2. If `/auth/me/` fails during page refresh but a cached user exists, the frontend restores that user state and keeps the user in the app instead of forcing a login redirect.
3. Backend APIs remain the security boundary; cached frontend state only prevents false UI logout and does not grant server access.
4. Normal authenticated API calls still clear auth state and warn on 401, so expired/invalid cookies are handled outside the bootstrap fallback path.

## 7. Single-source auth bootstrap cleanup

1. Current-user validation is now centralized in `main.ts`; `MainView.vue` no longer performs a second `/auth/me/` request after bootstrap.
2. Removing the duplicate MainView auth check prevents the default 401 handler from clearing cached user state immediately after startup fallback succeeds.
3. Cookie token authentication now reads the configured `AUTH_COOKIE_NAME`, keeping login, logout, and authentication middleware aligned when deployments customize cookie names.
4. Release note checks remain best-effort UI work and no longer control navigation to the login page.

## 8. Idempotent logout flow

1. Logout is now idempotent and public: it returns success and deletes the browser cookie even when the backend no longer sees an authenticated user.
2. If a valid authenticated user is present, logout deletes the server-side DRF token before clearing the cookie.
3. The frontend suppresses auth-required warnings during logout and always clears local auth state after the logout attempt.
4. Regression tests cover anonymous stale-cookie logout and authenticated server-token deletion.

## 9. Cross-origin cookie and auth notification cleanup

1. Auth cookie `SameSite` default is now `None`; this supports cross-origin SPA deployments where Lax cookies are not sent on XHR/fetch requests.
2. `AUTH_COOKIE_SECURE` remains configurable and defaults to enabled when `SameSite=None` or outside DEBUG; HTTPS deployments should keep it enabled for cross-site cookies.
3. Shared request handling no longer calls endpoint-level error callbacks for default 401 handling, preventing duplicate `Login required` plus backend credential notifications.
4. Tests cover both local Lax cookie policy and secure cross-site cookie policy.


## 10. Protected endpoint credential transport cleanup

1. Public `AllowAny` endpoints returning 200 do not prove auth cookies are being sent; protected endpoints like preferences and pptxgallery are the reliable signal.
2. Axios now forces `withCredentials=true` through a request interceptor so every request, including calls with custom config objects, carries cookies consistently.
3. The auth cookie `SameSite=None` default aligns browser behavior with cross-origin SPA API calls, and the secure-cookie default follows browser requirements; deployments that are strictly same-site can override it to `Lax`.
4. Protected endpoints remain protected; the fix is credential transport consistency, not weakening permissions.


## 11. Stale cookie login recovery

1. DRF authenticates before permission checks, so a stale auth cookie can block even `AllowAny` login requests before credentials are validated.
2. Cookie authentication now treats invalid cookie tokens as anonymous instead of raising immediately; protected endpoints still return 401 through `IsAuthenticated`.
3. Header token failures remain strict because explicit `Authorization` headers are caller-controlled credentials and should fail closed.
4. Login overwrites stale cookies with a fresh HttpOnly token cookie after valid username/password verification.

## 12. Endpoint-specific lazy import cleanup

1. Heavy optional libraries (`pandas`, `openpyxl`, `docxtpl`, `docx`, `jira`, `bs4`) were moved out of the inspected view modules' import path and into the endpoints/actions that actually execute those workflows.
2. Lightweight Django/DRF imports remain top-level so URL/view discovery stays simple and stable.
3. Circular-import exposure is reduced because the moved imports are third-party libraries loaded only at request/action execution time, not during Django app boot.
4. Backend boot timing should be re-measured in a dependency-complete environment with `python manage.py check`; the current container is missing Django, so only Python compilation could be verified here.

## 13. Development auth cookie default correction

1. Refresh-only auth failures were traced to the default debug cookie policy: `SameSite=None` plus `Secure=True` is appropriate for HTTPS cross-site deployments, but browsers reject or do not send that cookie on plain HTTP local development.
2. The auth cookie now defaults to `SameSite=Lax` and `Secure=False` when `DEBUG=True`, while production still defaults to `SameSite=None` and `Secure=True` for HTTPS cross-origin SPA/API deployments.
3. Deployments can still override both `AUTH_COOKIE_SAMESITE` and `AUTH_COOKIE_SECURE` explicitly from environment variables.
4. Logout now deletes the cookie with the configured `SameSite` attribute so stale browser cookies are less likely to survive policy transitions.

## 14. Frontend mount-first auth bootstrap

1. `main.ts` artık Vue uygulamasını `/auth/me/` çağrısını beklemeden mount eder; oturum doğrulaması `initializeSession()` akışıyla mount sonrasında çalışır.
2. `App.vue`, auth bootstrap tamamlanana kadar hafif bir loading shell gösterir ve böylece boş ekran algısını azaltır.
3. Başarısız `/auth/me/` durumunda login yönlendirmesi mount sonrasında yapılır; backend auth halen güvenlik sınırı olmaya devam eder.
4. Geçici performans ölçümü için browser Performance API ile `first-contentful-paint` ve `auth ready` süreleri console'a yazılır.

## 15. Frontend route-level code splitting

1. Router startup path now keeps only the critical `Welcome` and `Login` views eager-loaded; all non-critical and heavy screens are lazy route components.
2. Heavy routes such as Home, DCC/ECD, DDF Assistant, Outlook, PPTX Gallery, Translator, compare tools, DOORS tools, and compdoc tools now use centralized async route loading.
3. Lazy route loading uses one shared skeleton component to avoid repeated loading UI implementations and to keep navigation feedback consistent.
4. Vite build produced separate route chunks for the prioritized heavy screens, while the main vendor chunk is still large and should be considered for manual vendor chunking in a follow-up.

## 16. Authenticated SSE credential transport fix

1. Protected streaming endpoints were reached through `EventSource`, which does not inherit Axios interceptors or `withCredentials=true` defaults.
2. A shared frontend `createAuthenticatedEventSource(...)` helper now creates EventSource connections with `{ withCredentials: true }`, so HttpOnly auth cookies are sent to IsAuthenticated streaming endpoints.
3. DCC, Word, Excel and Outlook streaming consumers now use the shared helper instead of constructing unauthenticated EventSource instances directly.
4. Backend regression coverage now documents that stale auth cookies are treated as unauthenticated with 401, while valid auth cookies can access protected endpoints.

## 17. Normal request auth fallback and stable people pagination

1. Normal Axios requests can fail in cross-origin plain HTTP development when browsers reject or omit `SameSite=None; Secure` cookies, so backend login now has an environment-gated token response fallback.
2. `AUTH_TOKEN_RESPONSE_ENABLED` defaults to `DEBUG`; production remains cookie-only by default unless explicitly overridden.
3. The frontend stores and restores the optional fallback token in the existing `Authorization: Token ...` header path, while still preferring the HttpOnly cookie in production.
4. SSE uses cookie-backed EventSource when no fallback token exists and fetch-streaming with the `Authorization` header when the fallback token exists.
5. People list pagination now orders by primary key to avoid DRF `UnorderedObjectListWarning` and inconsistent page results.

## 18. Deployment foundations

1. Backend and frontend Dockerfiles were added with separate Django runtime and Vite-to-Nginx static asset image paths.
2. Docker Compose now orchestrates backend, frontend static serving, and a PostgreSQL database candidate while keeping runtime secrets external to images.
3. GitHub Actions CI now installs Python and npm dependencies, runs Django checks/tests, performs frontend typecheck/build, and runs dependency audits.
4. Deployment documentation now lists backend and frontend environment variables read by the application and calls out the current SQLite-to-PostgreSQL migration boundary.

## 19. Static architecture and readiness documentation

1. Added a `docs/` directory with architecture, production-readiness, enterprise-roadmap, refactoring, testing, DevOps, and code-quality reviews.
2. Each document is based on static repository evidence from the Django project configuration, frontend routing/HTTP/build configuration, dependency manifests, and app-level Django files.
3. The documents include severity, location, explanation, recommendation, business value, technical value, complexity, risk, confidence, rollback, and testing strategy for major improvements.

## 20. Browser cookie-token CSRF enforcement

1. Browser authentication strategy is explicitly cookie-backed DRF token auth, not Django session auth.
2. Cookie-backed token requests now run Django CSRF validation before accepting unsafe POST, PUT, PATCH, and DELETE requests.
3. Login forces a readable `csrftoken` cookie so the SPA can send `X-CSRFToken` while keeping the auth token HttpOnly.
4. Axios now attaches `X-CSRFToken` from the `csrftoken` cookie for unsafe methods and continues using `withCredentials=true`.
5. Regression tests document missing-vs-valid CSRF behavior for POST, PUT, PATCH, and DELETE, plus the non-browser header-token CSRF exemption.

### Cross-site deployment assumptions

- Same-site deployments should use `AUTH_COOKIE_SAMESITE=Lax` unless there is a tested requirement for cross-site XHR credentials.
- Cross-site SPA/API deployments must use HTTPS with `AUTH_COOKIE_SAMESITE=None`, `AUTH_COOKIE_SECURE=True`, explicit `CORS_ALLOWED_ORIGINS`, and matching `CSRF_TRUSTED_ORIGINS`.
- `AUTH_COOKIE_SECURE=False` is only appropriate for local HTTP development; modern browsers reject cross-site `SameSite=None` cookies without `Secure`.

## 21. Incremental DCC view refactor foundation

1. Added characterization coverage for DCC text parsing helpers before moving behavior out of `backend/dcc/views.py`.
2. Extracted pure DCC parsing and classification helpers into `backend/dcc/service/text_parsing.py`, keeping existing view imports and route behavior stable.
3. Reduced `backend/dcc/views.py` by removing helper implementations from the API module; endpoint functions continue to call the same helper names through imports.
4. Full Django test execution could not run in the current container because Django is not installed; Python compilation was used as the available syntax check.

## 22. Oversized file refactor expansion

1. Applied the same incremental extraction pattern to `backend/word/views.py` by moving document comparison and DOCX rendering helpers into focused service modules.
2. Added Word comparison characterization tests to protect normalization, tokenization, threshold, and paragraph-alignment behavior.
3. Split the compliance-document Pinia store out of `frontend/src/stores/api.ts` into `frontend/src/stores/compdoc.ts` while preserving the existing `useCompdocStore` export from `api.ts`.
4. Extracted pure CompDoc table query, retry, concurrency, and document-number collection helpers from `CompDocTable.vue` into `frontend/src/composables/compdoc/table.ts`.
5. Public routes, store names, and existing component imports remain backward-compatible for current consumers.

## 23. Frontend quality gate scripts and CI

1. Frontend package scripts now expose `typecheck`, `format:check`, `test:unit`, and `test:e2e` commands for local and CI quality gates.
2. Dev dependency declarations now include Prettier, Vitest, Vue Test Utils, jsdom, and Playwright so the scripts have explicit tool ownership in the frontend package manifest.
3. GitHub Actions frontend CI now runs `npm ci`, `npm run typecheck`, unit tests, Playwright browser installation, end-to-end tests, and `npm run build` from the frontend directory.
4. The current repository still has existing TypeScript and Prettier issues that should be fixed in follow-up work before these gates can be required as passing branch protection.

## 24. Frontend formatting and CI stabilization

1. Applied the committed Prettier rules to the frontend source, configuration, and postbuild script so `npm run format:check` no longer fails on style drift.
2. Simplified the frontend GitHub Actions job to run the gates that are currently owned by the repository: dependency install, Prettier check, Vue syntax/type transpilation check, Vite build, and npm audit.
3. Added workflow safety defaults with read-only permissions, job timeouts, and concurrency cancellation to reduce stuck or duplicated CI runs.
4. Removed placeholder unit/e2e package scripts and dev dependencies because no test files or Playwright configuration are committed yet; they should be restored with real tests and lockfile updates.

## 25. PyTorch CVE dependency removal

1. Removed default backend installation of `sentence-transformers` and `transformers` because they pull PyTorch, and currently available torch releases are flagged by CVE-2025-3000 with no patched PyPI version.
2. Kept Word translation and paraphrase integrations as optional runtime features by lazy-loading NLP packages only when those features are invoked.
3. Added explicit runtime error messages so operators understand why NLP features are unavailable in the default secure dependency set.
4. Verified the touched Word service modules compile without the optional NLP packages installed.

## 26. Frontend npm audit dependency floor update

1. Frontend direct dependency floors were raised for Axios, Markdown-It, Vite, and the Vue Vite plugin to move installs beyond the high-severity audit ranges reported by GitHub Actions.
2. npm `overrides` now pins security floor versions for vulnerable transitive packages (`brace-expansion`, `esbuild`, `follow-redirects`, `form-data`, `lodash`, `lodash-es`, `picomatch`, and `postcss`) so CI installs cannot resolve back into known vulnerable ranges.
3. The container's npm registry access returned 403 responses, so package-lock refresh and `npm audit fix` must be re-run in CI or a developer environment with registry access.

## 27. FFmpeg media conversion application

1. Added an authenticated Media Converter application to the AW Center menu and router for image, audio, and video conversion workflows.
2. Added backend `media_tools` endpoints for output-size preview and FFmpeg conversion, with extension allowlisting, upload-size validation, shell-free subprocess arguments, bounded timeouts, and `.env`-backed `FFMPEG_EXECUTABLE` configuration.
3. Added a frontend conversion screen where users can upload media, choose output extension, set frame dimensions and bitrates, preview estimated output size before processing, then download the converted file.
4. Added backend service tests covering extension validation, bitrate-based size estimation, configured executable usage, and preview fallback behavior.

## 28. Media Converter upload UX correction

1. Fixed the Media Converter upload control by adding an explicit Naive UI dragger trigger, because `n-upload` without trigger content can render no visible clickable area.
2. Styled the upload trigger as a centered square drag-and-drop area for a clearer media import experience.
3. Replaced free-only bitrate inputs with video and audio bitrate preset dropdowns plus an `Other` option that reveals custom kbps input fields.

## 29. GitHub Actions Node.js 24 action runtime update

1. CI workflow actions were updated from Node.js 20-targeting major versions to Node.js 24-compatible major versions.
2. `actions/checkout` now uses v5 in both backend and frontend jobs.
3. `actions/setup-python` now uses v6, and `actions/setup-node` now uses v5 to remove the Node.js 20 deprecation warning path.
4. The frontend project runtime remains pinned to Node.js 22 for dependency/build compatibility; this is separate from the GitHub Action implementation runtime.

## 30. JIRA subtask generator dynamic field persistence

1. Changed the `UserPreferences.jira_list` default shape from an object to an array so the frontend receives the list shape it renders.
2. Persisted selected dynamic JIRA columns inside each saved subtask list, allowing every list to keep its own field set.
3. Moved the JIRA field loading action into the subtask list toolbar next to the searchable field selector.
4. Kept the default subtask row minimal by rendering only Summary until the user adds JIRA fields as columns.

## 31. DCC Subtask Generator due-date UI cleanup

1. Removed the optional due-date selector from `SubtaskGenerator.vue` together with its local state, handlers, request payload field, and disabled-button dependency.
2. Kept the JIRA subtask generation payload focused on the URL, session ID, and editable subtask list.
3. Moved the local progress indicator into a single conditional full-width row directly below the generate action, so the form no longer reserves empty progress space before generation starts.
4. Added an initial progress message before the SSE stream starts returning progress events.

## 32. Python launcher for online/offline project validation

1. Added a root `launcher.py` with online, offline, and auto-detected workflows for backend/frontend dependency installation and project checks.
2. Added offline preparation support that downloads backend wheels and warms an npm cache under a configurable offline bundle directory.
3. Backend checks now include Django system checks, pending model-change detection with `makemigrations --check --dry-run`, and unapplied migration detection with `migrate --check`.
4. Added launcher unit tests for platform-specific executable resolution, offline pip command construction, auto mode detection, and safe development environment defaults.

## 33. Launcher usage documentation

1. Added README guidance for `launcher.py` commands, online setup, auto detection, offline bundle preparation, offline installation, and validation-only checks.
2. Documented launcher options, expected artifacts, and trade-offs around offline npm cache completeness and development-only environment defaults.

## 34. DCC reminder email hourly rate limit

1. DCC Watcher reminder emails now reserve one hourly send slot per `JIRA_DCC` table record before Outlook/JIRA work starts.
2. Repeated reminder attempts inside the one-hour cooldown return HTTP 429 with `retry_after_seconds` in the standardized error payload.
3. The cooldown state is stored on the DCC row with an atomic conditional database update to reduce duplicate sends from rapid repeated clicks.
4. Regression tests cover initial reservation, one-hour expiry, and endpoint throttling behavior.

## 35. Project definition metadata type

1. Added a frozen `ProjectDefinition` dataclass for shared project metadata under `backend/projects/types.py`.
2. Kept deployment-specific filesystem paths out of the type and exposed `dcc_parent_path_setting` as an environment-setting key field instead.
3. Used immutable tuple defaults for `capabilities` and `tags` so project definitions remain safe to share as constants.

## 36. Project registry foundation

1. Added a central read-only project registry for the existing project applications under `backend/projects/registry.py`.
2. Each registry entry uses the existing frozen `ProjectDefinition` dataclass and stores only safe metadata identifiers, avoiding credentials, network paths, and secrets.
3. Active and inactive project state is represented explicitly; `blok4050` and `gokbey` are registered with `enabled=False`.
4. Regression tests document required registry keys, read-only mapping behavior, DCC metadata, and inactive project flags.

## 37. Registry-driven project URL routing

1. Added `projects.routing.get_project_urlpatterns()` as the single helper for enabled project URL patterns.
2. Root URL configuration now includes project routes through the registry helper instead of duplicating each project route manually.
3. Project registry `app_label` values now point to importable project packages so URL imports fail during routing/test setup when misconfigured.
4. Regression tests verify enabled project URL modules are importable and disabled projects do not produce routes.

## 38. DCC template path resolver

1. Added a DCC template resolver that accepts only non-empty plain `.docx` filenames from project definitions.
2. Rejected path traversal and path separator usage before filesystem resolution to avoid directory escape attempts.
3. Verified the resolved template remains inside the configured template directory and raises controlled domain exceptions for invalid or missing templates.
4. Added regression tests for valid template names, traversal attempts, wrong extensions, and empty values.

## 39. DCC create flow registry/template resolution

1. `create_dcc_action` now resolves the DCC project from JIRA issue components through `resolve_project_from_jira_components(issue_f.components)` instead of scanning the legacy enum in-place.
2. DCC document generation now resolves the DOCX template through `resolve_dcc_template_path(project_definition)`, keeping template path validation in the dedicated resolver.
3. Progress messages now use the resolved project definition display name with the existing issue summary, while unsupported project failures keep the existing SSE error event shape.
4. Regression tests cover unsupported component SSE errors and successful template-path usage while preserving the existing success filename/download payload.

## 40. Authenticated project registry API

1. Added an authenticated `/projects/registry/` API that returns only frontend-safe registry fields: slug, display name, route, enabled state, capabilities, and tags.
2. Kept internal app labels, URL prefixes, JIRA/template identifiers, environment setting names, filesystem paths, and mail metadata out of the response contract.
3. Added `capability` and `enabled` query filters so the frontend can gate menus/features without receiving internal registry details.
4. Added response contract tests covering authentication, field allowlisting, route shape, and combined filter behavior.

## 41. Project registry/database alignment validation

1. Documented that `orgs.Project.slug` is the only business-facing bridge to `ProjectDefinition.slug` values in the central registry.
2. Added a read-only `check_project_registry` management command that fails when enabled registry projects have no matching `orgs.Project` row.
3. The command reports active database project rows absent from the registry as warnings and never creates, updates, or deletes project rows.
4. Added regression tests for successful alignment, missing enabled projects, database-only project warnings, and keeping technical registry fields out of `orgs.Project`.

## 42. Frontend project registry consumption

1. Added a typed frontend project registry service backed by the authenticated backend registry API and a safe fallback list.
2. Main navigation now builds Compliance Docs project menu entries from registry metadata while preserving disabled-state behavior.
3. Home dashboard project tabs now load from registry metadata, keep disabled projects disabled, and show a user-facing warning before using fallback options when refresh fails.

## 43. orgs project registry synchronization command

1. Added an idempotent `sync_projects` management command that creates missing `orgs.Project` rows from the central project registry.
2. Existing project display names are preserved by default so user-maintained labels are not overwritten unless `--update-display-name` is explicitly supplied.
3. Disabled registry entries are skipped by default and only included when `--include-disabled` is supplied.
4. Added dry-run reporting and command regression tests for create, no-op, dry-run, display-name update, and disabled-project inclusion behavior.

## 44. Project capability contract hardening

1. Added a backend project capability allowlist with initial supported values `dcc`, `compdocs`, and `orgs`.
2. Registry invariant and API contract tests now verify that declared and frontend-facing capabilities stay inside the documented allowlist.
3. The registry API rejects unknown capability filters so unsupported values cannot become implicit contracts.
4. Frontend project registry typing and runtime parsing now use the same documented capability set, and both backend/frontend constants document that adding a capability requires a coordinated contract update.

## 45. Launcher Python version guard

1. The root launcher now validates that both the active launcher interpreter and an existing `.venv` use Python 3.11 or newer.
2. Existing Python 3.9 virtual environments now fail fast with a clear remediation message instead of being reused silently.
3. README launcher guidance documents explicit `py -3.11` and `python3.11` commands for rebuilding stale environments.

## 46. Compliance document flexible Excel import

1. Added a tolerant compliance-document Excel header mapping helper that scans the first two rows for headers, maps multilingual/static aliases to model fields, and falls back to conservative fuzzy matching for close header typos.
2. Updated the shared compdoc upload endpoint to use the detected header row and normalized model-field names before serializer validation, preserving existing response behavior for row-level import errors.
3. Added focused import-mapping regression tests that do not require optional Excel dependencies in the local container.

## 47. Compliance document import preview confirmation

1. Compliance-document Excel upload now performs a preview request before saving, showing the detected header row, mapped columns, unmapped columns, and row validation warnings.
2. The backend upload endpoint now separates preview from confirmed import and rejects non-preview save attempts without explicit confirmation.
3. The frontend keeps the selected file in memory between preview and confirmation, then re-submits it only after the user confirms.

## 48. Compliance import preview missing-column fix

1. Preview requests no longer fail with HTTP 400 when required columns are missing; they return the mapping preview with `missing_columns` so users can correct the Excel file.
2. Confirmed imports still reject missing required columns before any database write.
3. The preview modal now shows missing columns and row validation details directly instead of only showing a count.
