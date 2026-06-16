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

## 18. Static architecture and readiness documentation

1. Added a `docs/` directory with architecture, production-readiness, enterprise-roadmap, refactoring, testing, DevOps, and code-quality reviews.
2. Each document is based on static repository evidence from the Django project configuration, frontend routing/HTTP/build configuration, dependency manifests, and app-level Django files.
3. The documents include severity, location, explanation, recommendation, business value, technical value, complexity, risk, confidence, rollback, and testing strategy for major improvements.

## 19. Browser cookie-token CSRF enforcement

1. Browser authentication strategy is explicitly cookie-backed DRF token auth, not Django session auth.
2. Cookie-backed token requests now run Django CSRF validation before accepting unsafe POST, PUT, PATCH, and DELETE requests.
3. Login forces a readable `csrftoken` cookie so the SPA can send `X-CSRFToken` while keeping the auth token HttpOnly.
4. Axios now attaches `X-CSRFToken` from the `csrftoken` cookie for unsafe methods and continues using `withCredentials=true`.
5. Regression tests document missing-vs-valid CSRF behavior for POST, PUT, PATCH, and DELETE, plus the non-browser header-token CSRF exemption.

## Cross-site deployment assumptions

- Same-site deployments should use `AUTH_COOKIE_SAMESITE=Lax` unless there is a tested requirement for cross-site XHR credentials.
- Cross-site SPA/API deployments must use HTTPS with `AUTH_COOKIE_SAMESITE=None`, `AUTH_COOKIE_SECURE=True`, explicit `CORS_ALLOWED_ORIGINS`, and matching `CSRF_TRUSTED_ORIGINS`.
- `AUTH_COOKIE_SECURE=False` is only appropriate for local HTTP development; modern browsers reject cross-site `SameSite=None` cookies without `Secure`.
