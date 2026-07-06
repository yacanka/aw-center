# AW Center Mimari Denetim ve Güvenli Geliştirme Planı

## 1. Kısa mimari özet

AW Center, Django tabanlı bir backend ile Vue 3/Vite tabanlı bir frontend'i birleştiren, mühendislik dokümantasyonu ve uyumluluk iş akışlarına odaklı bir uygulamadır. Backend tarafında `backend/awcenter` ana proje ayarlarını, `users`, `common`, `dcc`, `ddf`, `doors`, `excel`, `word`, `pdf`, `outlook`, `orgs`, `pptxgallery`, `releases` ve `projects/<project>` uygulamaları domain sorumluluklarını taşır. Frontend tarafında route bazlı ekranlar `frontend/src/views`, tekrar kullanılabilir UI parçaları `frontend/src/components`, paylaşılan state `frontend/src/stores`, HTTP ayarları `frontend/src/services/http.ts` ve hata/request yardımcıları `frontend/src/composables/promise.ts` altında toplanmıştır.

Backend–frontend iletişimi Axios üzerinden REST benzeri endpoint'lerle yürür. Authentication, DRF TokenAuthentication'ın hem `Authorization: Token ...` header'ını hem de `auth_token` HttpOnly cookie'sini kabul eden özel sınıfla yapılır. Vue Router tarafında bazı route'lar lokal kullanıcı state'ine göre korunur; backend tarafında global DRF permission varsayılanı `IsAuthenticated` olarak ayarlanmıştır.

## 2. Kritik riskler

1. **Public user registration riski:** `auth/users/` POST endpoint'i `AllowAny` ile çalışıyor. Bu ürün kapalı kurumsal kullanım için tasarlandıysa self-service kayıt kapatılmalı veya davet/onay akışı eklenmelidir.
2. **Cookie token + CSRF tasarımı:** Auth token HttpOnly cookie ile taşınır; unsafe browser requests now require Django CSRF validation. Cross-site deployments must keep HTTPS, `AUTH_COOKIE_SAMESITE=None`, `AUTH_COOKIE_SECURE=True`, explicit CORS origins, and matching CSRF trusted origins aligned.
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
- HttpOnly cookie auth için CSRF enforcement eklendi; cross-site deployment ayarları `AUTH_COOKIE_SAMESITE`, `AUTH_COOKIE_SECURE`, CORS ve CSRF trusted origins birlikte yönetilmelidir.
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

1. **P0 - Public signup kararı:** `auth/users/` POST endpoint'inin public kalıp kalmayacağına karar ver; gerekirse permission ile kapat.
2. **P1 - API hata formatı standardı:** Ortak contract belirlendi; DRF exception path'i ve manuel DRF error response'ları merkezi olarak normalize ediliyor. Kalan iş, domain-specific hata kodlarını zenginleştirmek.
3. **P1 - File upload güvenlik denetimi:** PDF/Office/Outlook/PPTX endpoint'lerinde boyut, tip, dosya adı ve temp cleanup kontrollerini sırayla iyileştir.
4. **P1 - Pagination:** Kullanıcılar, dokümanlar, DCC/DDF ve organizasyon listelerinde server-side pagination planla.
5. **P2 - Store/API modülerleştirme:** `frontend/src/stores/api.ts` dosyasını domain servislerine böl.
6. **P2 - Build doğrulanabilirliği:** Frontend entry/build sorunları giderildi; kalan iş tam TypeScript strict hata listesini modül modül kapatmak.
7. **P2 - Query ölçüm testleri:** Kritik list endpoint'lerine regression amaçlı query count testleri ekle.

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

## 11. Project registry cleanup follow-up

1. **P2 - Legacy Projects enum removal:** One-release deprecation window sonunda `backend/awcenter/enums.py` içindeki `Projects` enum'unun kalan dış bağımlılıkları tekrar `rg "awcenter.enums|Projects" backend frontend` ile doğrulanmalı ve kullanılmıyorsa enum tamamen kaldırılmalıdır.

## 12. Project app ortaklaşma değerlendirmesi

1. **Karar - Over-abstraction geri alındı:** `projects.common` factory yaklaşımı view/serializer sınıflarını gereğinden katı hale getirdiği için geri alındı.
2. **Sıradaki adım - Daha esnek yaklaşım:** Tekrarlanan alanlar için önce test kapsamı ve küçük mixin/helper adayları çıkarılmalı; final serializer/view sınıfları proje app içinde açık kalmalı.
3. **Sıradaki adım - Kademeli güvenlik:** AESA/Gokbey/Blok4050 gibi override davranışları olan app'lerde ortaklaştırma ancak app-local subclass davranışı korunarak ve endpoint contract testleri yazılarak değerlendirilmeli.

## 13. Compliance document import follow-up

1. **P2 - Project-specific aliases:** If projects use different local naming conventions, add project-level alias configuration while keeping the common default mapping as fallback.
2. **P2 - Import audit trail:** Store uploaded filename, importing user, detected mappings, and import result counts for compliance traceability.

## 50. Frontend artifact deployment follow-up

1. **P1 - Deployment pipeline alignment:** Update production deployment scripts to build frontend as an immutable artifact and mount/copy only `frontend/dist` to the runtime path configured by `FRONTEND_DIST_DIR`.
2. **P2 - CDN/static offload:** For higher traffic deployments, serve `/core/assets/` from Nginx/CDN object storage while keeping Django responsible only for the SPA fallback and API routes.
3. **P2 - Build artifact smoke test:** Add a CI smoke test that runs `npm run build` and verifies Django can return `/app/` with `FRONTEND_DIST_DIR` pointed at the generated artifact.
