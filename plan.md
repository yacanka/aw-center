# AW Center Mimari Denetim ve Güvenli Geliştirme Planı

## 1. Kısa mimari özet

AW Center, Django tabanlı bir backend ile Vue 3/Vite tabanlı bir frontend'i birleştiren, mühendislik dokümantasyonu ve uyumluluk iş akışlarına odaklı bir uygulamadır. Backend tarafında `backend/awcenter` ana proje ayarlarını, `users`, `common`, `dcc`, `ddf`, `doors`, `excel`, `word`, `pdf`, `outlook`, `orgs`, `pptxgallery`, `releases` ve `projects/<project>` uygulamaları domain sorumluluklarını taşır. Frontend tarafında route bazlı ekranlar `frontend/src/views`, tekrar kullanılabilir UI parçaları `frontend/src/components`, paylaşılan state `frontend/src/stores`, HTTP ayarları `frontend/src/services/http.ts` ve hata/request yardımcıları `frontend/src/composables/promise.ts` altında toplanmıştır.

Backend–frontend iletişimi Axios üzerinden REST benzeri endpoint'lerle yürür. Authentication, DRF TokenAuthentication'ın hem `Authorization: Token ...` header'ını hem de `auth_token` HttpOnly cookie'sini kabul eden özel sınıfla yapılır. Vue Router tarafında bazı route'lar lokal kullanıcı state'ine göre korunur; backend tarafında global DRF permission varsayılanı `IsAuthenticated` olarak ayarlanmıştır.

## 2. Kritik riskler

1. **Public user registration riski:** `auth/users/` POST endpoint'i `AllowAny` ile çalışıyor. Bu ürün kapalı kurumsal kullanım için tasarlandıysa self-service kayıt kapatılmalı veya davet/onay akışı eklenmelidir.
2. **Cookie token + CSRF tasarımı:** Auth token HttpOnly cookie ile taşındığında klasik token header yaklaşımına göre CSRF tehdidi yeniden değerlendirilmelidir. `SameSite=Lax` riski azaltır; yine de kritik state-changing endpoint'ler için CSRF veya çift-submit token stratejisi netleştirilmelidir.
3. **Frontend route koruması lokal storage'a bağımlı:** `isAuthenticated()` sadece local user varlığına bakıyor. Uygulama açılışında `/auth/me/` çağrısı bunu büyük ölçüde dengelese de 401 sonrasında lokal state temizliği tutarlı olmalıdır.
4. **Standart hata contract'ı merkezi hale getirildi:** DRF exception akışı ve manuel DRF `Response(...)` hata cevapları artık `{ "detail": string, "code": string, "errors"?: object }` contract'ına çevriliyor. Frontend geçiş döneminde legacy gövdeleri de okuyabildiği için uyum sorunu yaşamamalıdır.
5. **Dosya işleme yüzeyi geniş:** PDF/Excel/Word/Outlook/PPTX upload ve dönüştürme akışları büyük dosya, path traversal, temp file temizliği, MIME doğrulama ve subprocess güvenliği açısından öncelikli denetlenmelidir.
6. **Pagination eksikliği olası:** Bazı list endpoint'leri `.all()` ile tüm veriyi döndürüyor. Veri büyüdükçe performans ve bellek kullanımı riski artar.
7. **Build doğrulanabilirliği sorunu:** Repo notlarına göre frontend build için gerekli `frontend/index.html` eksik olabilir; CI/CD kalitesini etkiler.
8. **Çok uzun modül/fonksiyonlar:** Özellikle bazı domain view/service dosyalarında bakım maliyetini artıran uzun fonksiyonlar ve tekrarlar görülüyor.

## 3. Backend iyileştirmeleri

- User registration politikasını ürün ihtiyacına göre netleştir: kapalı sistem ise `auth.add_user` permission veya invite-only akışı uygula.
- API hata formatını standartlaştır: DRF exception handler ve manuel DRF response normalizer devrede; yeni endpoint'lerde okunabilirlik için yine `awcenter.api_errors.error_response(...)` tercih edilmelidir.
- File upload endpoint'leri için merkezi validator ekle: uzantı, MIME, maksimum boyut, geçici dosya temizliği ve güvenli dosya adı normalizasyonu.
- List endpoint'lerine DRF pagination ekle; frontend tabloları ile birlikte kademeli uyumlandır. İlk geçişte global DRF pagination, ortak APIView pagination helper'ı ve frontend paginated response unwrap desteği eklendi; tablo bazlı page controls sonraki iterasyona bırakıldı.
- Queryset optimizasyonlarını yaygınlaştır: `select_related`, `prefetch_related`, `only/defer` ve serializer kaynaklı N+1 ölçümleri.
- Long-running Excel/Word/PDF işlemleri için job modeli veya queue contract'ı standardize et.
- Settings tarafında production env zorunluluklarını dokümante et; debug CORS davranışı local ile sınırlı tutulmalı.

## 4. Frontend iyileştirmeleri

- Axios hata yönetimini tek yerde standartlaştır: `formatApiError` standart contract'ı önceleyerek legacy `detail`/`message`/`error`/JSON-string gövdeleri geçiş dönemi için destekler; 401 auth durumlarında local auth state tutarlı temizlensin, 403 yetki hataları ise kullanıcıya ayrı gösterilsin.
- Store'larda `any` kullanımını azalt; request/response DTO tipleri ekle.
- Büyük `stores/api.ts` dosyasını domain servislerine böl: `dccApi`, `orgsApi`, `fileApi`, `pptxApi` gibi.
- Route meta policy'sini genişlet: auth, permission ve role gereksinimleri route seviyesinde açık tanımlansın.
- Loading/error state'lerini merkezi hale getir; aynı pattern her store'da tekrar edilmesin.
- Vite build giriş dosyası ve build script'i doğrulanabilir hale getirilsin; eksik `index.html` sorunu giderilsin.
- Ağ çağrılarında query parametreleri string interpolation yerine Axios `params` ile verilsin.

## 5. API contract standardı

- Başarılı cevaplarda domain kaynakları doğrudan veya `{ data, meta }` formatıyla dönmeli; endpoint bazında string/data karışımı azaltılmalı.
- Hatalar için zorunlu minimum format:
  - `detail`: kullanıcıya veya log'a uygun kısa açıklama.
  - `code`: frontend'in karar verebileceği büyük harfli makine-okunur kod.
  - `errors`: opsiyonel field bazlı validasyon detayları.
- Backend standardı: DRF exception'ları `awcenter.api_errors.api_exception_handler` ile, manuel DRF error response'ları `ApiErrorContractMiddleware` ile normalize edilir; yeni manuel hata dönen endpoint'ler okunabilirlik için `awcenter.api_errors.error_response(...)` kullanmalıdır.
- Frontend standardı: yeni hata gösterimleri `frontend/src/services/apiError.ts` içindeki `formatApiError(...)` üzerinden geçmelidir; bileşen içinde `err.response.data.message` gibi contract'a özel olmayan doğrudan erişimler eklenmemelidir.
- Pagination contract'ı DRF standardına yakın tutulmalı: `count`, `next`, `previous`, `results`.
- File upload endpoint'leri aynı hata ve progress semantics'ini kullanmalı.
- SSE/stream endpoint'leri için event tipi, hata event'i, retry ve completion contract'ı yazılı hale getirilmeli.

## 6. Güvenlik önerileri

- Public signup kapatılmadan bırakılacaksa rate limit, CAPTCHA/approval ve audit log eklenmeli.
- HttpOnly cookie auth devam edecekse CSRF stratejisi açıkça uygulanmalı veya cookie sadece same-site deployment varsayımıyla dokümante edilmeli.
- Token/session invalidation sonrası frontend local user, project ve token state'i merkezi temizlenmeli.
- Dosya yüklemelerinde path traversal'a karşı `safe_join`, random server-side file names ve allowlist kullanılmalı.
- Subprocess çağrılarında shell stringlerinden kaçınılmalı; argüman listeleri ve timeout zorunlu olmalı.
- Production `DEBUG=False`, `SECRET_KEY`, CORS, CSRF trusted origins ve HTTPS ayarları deployment checklist'e bağlanmalı.
- Log'larda token, cookie, JIRA/DocProof credential ve dosya içerikleri maskelenmeli.

## 7. Performans önerileri

- Büyük tablo endpoint'leri için pagination ve filtreleme server-side yapılmalı.
- Serializer N+1 kontrolleri için Django Debug Toolbar benzeri local ölçüm veya query count testleri eklenmeli.
- Excel/PDF/Word üretimlerinde streaming response veya async job yaklaşımı değerlendirilmeli.
- Frontend route component'lerinde lazy loading yaygınlaştırılmalı; şu anda çoğu route eager import ediliyor.
- Chart ve büyük UI kütüphaneleri bundle analizine alınmalı.
- Gereksiz tekrar API çağrıları için store-level cache invalidation stratejisi belirlenmeli.

## 8. Önceliklendirilmiş yapılacaklar listesi

1. **P0 - Güvenli auth state temizliği:** Frontend ortak request helper'ında 401 sonrası local auth state temizliğini standartlaştır.
2. **P0 - Public signup kararı:** `auth/users/` POST endpoint'inin public kalıp kalmayacağına karar ver; gerekirse permission ile kapat.
3. **P1 - API hata formatı standardı:** Ortak contract belirlendi; DRF exception path'i ve manuel DRF error response'ları merkezi olarak normalize ediliyor. Kalan iş, domain-specific hata kodlarını zenginleştirmek.
4. **P1 - File upload güvenlik denetimi:** PDF/Office/Outlook/PPTX endpoint'lerinde boyut, tip, dosya adı ve temp cleanup kontrollerini sırayla iyileştir.
5. **P1 - Pagination:** Kullanıcılar, dokümanlar, DCC/DDF ve organizasyon listelerinde server-side pagination planla.
6. **P2 - Store/API modülerleştirme:** `frontend/src/stores/api.ts` dosyasını domain servislerine böl.
7. **P2 - Build doğrulanabilirliği:** Frontend entry/build sorunlarını gider ve CI komutlarını netleştir.
8. **P2 - Query ölçüm testleri:** Kritik list endpoint'lerine regression amaçlı query count testleri ekle.

## 9. Uygulanan hata contract patch'i

Bu patch, davranışı kontrollü değiştirmek ve eski endpoint'leri kırmamak için backend exception path'ini standartlaştırıp frontend'de geriye uyumlu parser ekledi:

1. `backend/awcenter/api_errors.py` ortak hata contract builder, DRF exception handler ve manuel endpoint helper'ı sağlar.
2. `REST_FRAMEWORK["EXCEPTION_HANDLER"]` ayarı, DRF exception'larının tamamını `{ detail, code, errors? }` formatına normalleştirir.
3. `ApiErrorContractMiddleware`, eski manuel `Response({"message": ...}, status=400)`, `Response({"error": ...}, status=400)`, serializer error dict ve düz string hata gövdelerini render öncesinde aynı contract'a çevirir.
4. `frontend/src/services/apiError.ts`, standart contract'ı birincil kabul eder; geçiş döneminde legacy `detail`, `message`, `error`, field errors ve JSON string durumlarını okumaya devam eder.
5. `frontend/src/composables/promise.ts` ve doğrudan upload/login hata gösterimleri, hata formatlamasını merkezi helper'a devreder ve mevcut 401 auth cleanup davranışını korur.
6. `backend/awcenter/tests.py`, validation, not-found, manuel helper ve legacy manuel response normalizasyonunu regression testi ile güvenceye alır.

## Mevcut davranışı bozma riskleri ve trade-off'lar

- Frontend bazı endpoint'lerde 403'ü auth değil yetki hatası olarak kullanıcıya göstermeyi bekliyor olabilir. Bu nedenle 403'te local auth state'i temizlenmez; sonraki adımda backend `code` alanı ile token-invalid ve forbidden ayrımı daha görünür yapılmalıdır.
- `handleRequest` halen hata durumunda exception fırlatır; mevcut çağıran kodların çoğu zaten bu davranışa göre çalışıyor. Bu patch exception davranışını korumayı hedefler.
- Console log azaltımı geliştirici debug alışkanlıklarını etkileyebilir; production güvenliği ve kullanıcı deneyimi için merkezi hata yönetimi tercih edilmiştir.


## 10. Sonraki hata contract adımları

1. OpenAPI/README seviyesinde hata contract'ını yayınla; yeni endpoint code review checklist'ine `detail/code/errors` uyumunu ekle.
2. Domain-specific hata kodları için kontrollü enum listesi oluştur: ör. `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `JIRA_UNAVAILABLE`, `DOCUMENT_NOT_FOUND`.
3. HTTP `JsonResponse`/`HttpResponse` ile dönen API hataları varsa bunları DRF `Response` veya explicit contract helper'ına taşı; middleware bilinçli olarak dosya/stream response'larını değiştirmez.
4. Frontend'de yeni hata gösterimlerinde doğrudan `err.response.data.*` erişimini code review ile engelle; `formatApiError(...)` veya `handleRequest(...)` kullanılmalıdır.


## 11. Pagination geçiş notları

1. Backend tarafında standart response contract `count`, `next`, `previous`, `results` olacak şekilde merkezi DRF pagination eklendi.
2. APIView tabanlı büyük listeler için ortak `paginated_response(...)` helper'ı eklendi ve kullanıcılar, permission listesi, DCC, DDF/compdoc factory listeleri ile history endpointlerinde kullanılmaya başlandı.
3. Frontend geçiş döneminde hem legacy array response'ları hem de paginated response'ları okuyabilen helper ile mevcut tabloların kırılması engellendi.
4. Sonraki aşamada tablo bileşenlerine page/page_size state'i bağlanmalı ve filtreler Axios `params` üzerinden server-side taşınmalıdır.

## 12. Tablo pagination ve server-side filtreleme geçişi

1. CompDoc, DDF ve Users tablolarında `page`, `page_size` ve toplam kayıt sayısı backend pagination metadata'sına bağlandı.
2. İlgili store aksiyonları Axios `params` kullanarak pagination ve filtre query parametrelerini backend'e taşır.
3. Backend generic list helper'ı sadece model alanlarını allowlist olarak kabul eden güvenli server-side filtreleme uygular; bilinmeyen query parametreleri yok sayılır.
4. Sonraki aşamada Naive UI kolon filtrelerinin tamamı için frontend tipleri netleştirilmeli ve array/JSON alan filtreleri domain-specific backend lookup'larına ayrılmalıdır.

## 13. DCC ve çoklu filtre pagination tamamlaması

1. DCC Watcher tablosu da remote `page`, `page_size` ve backend `count` metadata'sına bağlandı.
2. Genel server-side filter helper tekrarlı query parametrelerini `__in` lookup'a dönüştürür; tekil metin alanları `icontains`, diğer alanlar exact lookup kullanır.
3. Frontend pagination query tipi boolean ve string/number array filtre değerlerini kabul edecek şekilde genişletildi.
4. JSON alanlarda generic lookup yerine ileride domain-specific filtre endpoint sözleşmeleri kullanılmalıdır; SQLite JSON lookup limitleri nedeniyle bu bilinçli olarak generic filtreye zorlanmadı.

## 14. Cookie-only login hardening revision

1. Token'ın response body içinde dönülmesi ve frontend storage'a yazılması güvenlik gerekçesiyle tercih edilmedi; login yalnızca HttpOnly cookie ile kimlik doğrular.
2. Frontend login başlangıcında eski/stale `Authorization` header ve storage token temizlenir; böylece eski token cookie-auth akışını gölgeleyemez.
3. Auth cookie adı, ömrü, `SameSite` ve `Secure` ayarları environment üzerinden yönetilebilir hale getirildi.
4. Regression testleri token sızdırılmadığını, cookie'nin HttpOnly/SameSite ayarlarıyla set edildiğini ve `/auth/me/` endpoint'inin login sonrası cookie ile çalıştığını doğrular.

## 15. Login bootstrap without immediate auth/me dependency

1. Login response now returns a safe serialized user payload while keeping the token HttpOnly-cookie-only.
2. The login page initializes the user store from that safe payload instead of calling `/auth/me/` immediately after login.
3. `/auth/me/` remains the bootstrap/session validation endpoint for page refresh and existing sessions, not the critical post-login transition dependency.
4. This avoids false login failures when the browser has not made the new HttpOnly cookie available to the next request yet or when cookie policy debugging is still in progress.

## 16. Refresh bootstrap cache fallback

1. Startup `/auth/me/` calls can now suppress auth-warning side effects during bootstrap.
2. If `/auth/me/` fails during page refresh but a cached user exists, the frontend restores that user state and keeps the user in the app instead of forcing a login redirect.
3. Backend APIs remain the security boundary; cached frontend state only prevents false UI logout and does not grant server access.
4. Normal authenticated API calls still clear auth state and warn on 401, so expired/invalid cookies are handled outside the bootstrap fallback path.

## 17. Single-source auth bootstrap cleanup

1. Current-user validation is now centralized in `main.ts`; `MainView.vue` no longer performs a second `/auth/me/` request after bootstrap.
2. Removing the duplicate MainView auth check prevents the default 401 handler from clearing cached user state immediately after startup fallback succeeds.
3. Cookie token authentication now reads the configured `AUTH_COOKIE_NAME`, keeping login, logout, and authentication middleware aligned when deployments customize cookie names.
4. Release note checks remain best-effort UI work and no longer control navigation to the login page.

## 18. Idempotent logout flow

1. Logout is now idempotent and public: it returns success and deletes the browser cookie even when the backend no longer sees an authenticated user.
2. If a valid authenticated user is present, logout deletes the server-side DRF token before clearing the cookie.
3. The frontend suppresses auth-required warnings during logout and always clears local auth state after the logout attempt.
4. Regression tests cover anonymous stale-cookie logout and authenticated server-token deletion.

## 19. Cross-origin cookie and auth notification cleanup

1. Auth cookie `SameSite` default is now `None`; this supports cross-origin SPA deployments where Lax cookies are not sent on XHR/fetch requests.
2. `AUTH_COOKIE_SECURE` remains configurable and defaults to enabled when `SameSite=None` or outside DEBUG; HTTPS deployments should keep it enabled for cross-site cookies.
3. Shared request handling no longer calls endpoint-level error callbacks for default 401 handling, preventing duplicate `Login required` plus backend credential notifications.
4. Tests cover both local Lax cookie policy and secure cross-site cookie policy.


## 20. Protected endpoint credential transport cleanup

1. Public `AllowAny` endpoints returning 200 do not prove auth cookies are being sent; protected endpoints like preferences and pptxgallery are the reliable signal.
2. Axios now forces `withCredentials=true` through a request interceptor so every request, including calls with custom config objects, carries cookies consistently.
3. The auth cookie `SameSite=None` default aligns browser behavior with cross-origin SPA API calls, and the secure-cookie default follows browser requirements; deployments that are strictly same-site can override it to `Lax`.
4. Protected endpoints remain protected; the fix is credential transport consistency, not weakening permissions.
