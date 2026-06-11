# AW Center Mimari Denetim ve Güvenli Geliştirme Planı

## 1. Kısa mimari özet

AW Center, Django tabanlı bir backend ile Vue 3/Vite tabanlı bir frontend'i birleştiren, mühendislik dokümantasyonu ve uyumluluk iş akışlarına odaklı bir uygulamadır. Backend tarafında `backend/awcenter` ana proje ayarlarını, `users`, `common`, `dcc`, `ddf`, `doors`, `excel`, `word`, `pdf`, `outlook`, `orgs`, `pptxgallery`, `releases` ve `projects/<project>` uygulamaları domain sorumluluklarını taşır. Frontend tarafında route bazlı ekranlar `frontend/src/views`, tekrar kullanılabilir UI parçaları `frontend/src/components`, paylaşılan state `frontend/src/stores`, HTTP ayarları `frontend/src/services/http.ts` ve hata/request yardımcıları `frontend/src/composables/promise.ts` altında toplanmıştır.

Backend–frontend iletişimi Axios üzerinden REST benzeri endpoint'lerle yürür. Authentication, DRF TokenAuthentication'ın hem `Authorization: Token ...` header'ını hem de `auth_token` HttpOnly cookie'sini kabul eden özel sınıfla yapılır. Vue Router tarafında bazı route'lar lokal kullanıcı state'ine göre korunur; backend tarafında global DRF permission varsayılanı `IsAuthenticated` olarak ayarlanmıştır.

## 2. Kritik riskler

1. **Public user registration riski:** `auth/users/` POST endpoint'i `AllowAny` ile çalışıyor. Bu ürün kapalı kurumsal kullanım için tasarlandıysa self-service kayıt kapatılmalı veya davet/onay akışı eklenmelidir.
2. **Cookie token + CSRF tasarımı:** Auth token HttpOnly cookie ile taşındığında klasik token header yaklaşımına göre CSRF tehdidi yeniden değerlendirilmelidir. `SameSite=Lax` riski azaltır; yine de kritik state-changing endpoint'ler için CSRF veya çift-submit token stratejisi netleştirilmelidir.
3. **Frontend route koruması lokal storage'a bağımlı:** `isAuthenticated()` sadece local user varlığına bakıyor. Uygulama açılışında `/auth/me/` çağrısı bunu büyük ölçüde dengelese de 401 sonrasında lokal state temizliği tutarlı olmalıdır.
4. **Standart hata contract'ı yok:** Backend bazı yerlerde `detail`, bazı yerlerde `message`, bazı yerlerde düz string veya `error` döndürüyor. Frontend hata gösterimi bu heterojenliği telafi etmeye çalışıyor.
5. **Dosya işleme yüzeyi geniş:** PDF/Excel/Word/Outlook/PPTX upload ve dönüştürme akışları büyük dosya, path traversal, temp file temizliği, MIME doğrulama ve subprocess güvenliği açısından öncelikli denetlenmelidir.
6. **Pagination eksikliği olası:** Bazı list endpoint'leri `.all()` ile tüm veriyi döndürüyor. Veri büyüdükçe performans ve bellek kullanımı riski artar.
7. **Build doğrulanabilirliği sorunu:** Repo notlarına göre frontend build için gerekli `frontend/index.html` eksik olabilir; CI/CD kalitesini etkiler.
8. **Çok uzun modül/fonksiyonlar:** Özellikle bazı domain view/service dosyalarında bakım maliyetini artıran uzun fonksiyonlar ve tekrarlar görülüyor.

## 3. Backend iyileştirmeleri

- User registration politikasını ürün ihtiyacına göre netleştir: kapalı sistem ise `auth.add_user` permission veya invite-only akışı uygula.
- API hata formatını standartlaştır: `{ "detail": string, "code": string, "errors"?: object }` gibi tek contract belirle.
- File upload endpoint'leri için merkezi validator ekle: uzantı, MIME, maksimum boyut, geçici dosya temizliği ve güvenli dosya adı normalizasyonu.
- List endpoint'lerine DRF pagination ekle; frontend tabloları ile birlikte kademeli uyumlandır.
- Queryset optimizasyonlarını yaygınlaştır: `select_related`, `prefetch_related`, `only/defer` ve serializer kaynaklı N+1 ölçümleri.
- Long-running Excel/Word/PDF işlemleri için job modeli veya queue contract'ı standardize et.
- Settings tarafında production env zorunluluklarını dokümante et; debug CORS davranışı local ile sınırlı tutulmalı.

## 4. Frontend iyileştirmeleri

- Axios hata yönetimini tek yerde standartlaştır; 401 auth durumlarında local auth state tutarlı temizlensin, 403 yetki hataları ise kullanıcıya ayrı gösterilsin.
- Store'larda `any` kullanımını azalt; request/response DTO tipleri ekle.
- Büyük `stores/api.ts` dosyasını domain servislerine böl: `dccApi`, `orgsApi`, `fileApi`, `pptxApi` gibi.
- Route meta policy'sini genişlet: auth, permission ve role gereksinimleri route seviyesinde açık tanımlansın.
- Loading/error state'lerini merkezi hale getir; aynı pattern her store'da tekrar edilmesin.
- Vite build giriş dosyası ve build script'i doğrulanabilir hale getirilsin; eksik `index.html` sorunu giderilsin.
- Ağ çağrılarında query parametreleri string interpolation yerine Axios `params` ile verilsin.

## 5. API contract önerileri

- Başarılı cevaplarda domain kaynakları doğrudan veya `{ data, meta }` formatıyla dönmeli; endpoint bazında string/data karışımı azaltılmalı.
- Hatalar için önerilen minimum format:
  - `detail`: kullanıcıya veya log'a uygun kısa açıklama
  - `code`: frontend'in karar verebileceği makine-okunur kod
  - `errors`: field bazlı validasyon detayları
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
3. **P1 - API hata formatı standardı:** Backend ve frontend için ortak hata contract'ını belirle ve yeni endpoint'lerde zorunlu kıl.
4. **P1 - File upload güvenlik denetimi:** PDF/Office/Outlook/PPTX endpoint'lerinde boyut, tip, dosya adı ve temp cleanup kontrollerini sırayla iyileştir.
5. **P1 - Pagination:** Kullanıcılar, dokümanlar, DCC/DDF ve organizasyon listelerinde server-side pagination planla.
6. **P2 - Store/API modülerleştirme:** `frontend/src/stores/api.ts` dosyasını domain servislerine böl.
7. **P2 - Build doğrulanabilirliği:** Frontend entry/build sorunlarını gider ve CI komutlarını netleştir.
8. **P2 - Query ölçüm testleri:** Kritik list endpoint'lerine regression amaçlı query count testleri ekle.

## 9. Uygulanacak ilk küçük patch planı

İlk patch, davranışı değiştirme riski düşük ve güvenlik faydası yüksek olduğu için frontend ortak request helper'ına odaklanacaktır:

1. `frontend/src/composables/promise.ts` içindeki hata ayrıştırma ve auth cleanup mantığını küçük, test edilebilir helper fonksiyonlara ayır.
2. Sadece `Invalid token.` metnine bağlı kalmadan tüm 401 auth hatalarında local `token`, `user`, `project` state'ini ve Authorization header'ını temizle.
3. Kullanıcıya mevcut uyarı davranışını koruyarak login gerektiğini bildir.
4. Hata mesajı formatlamasını merkezi hale getir; `detail`, `message`, `error`, field errors ve JSON string durumlarını koru.
5. Build/type-check komutlarını çalıştır; ortam veya repo eksikleri varsa açıkça belgeleyerek bir sonraki patch'e taşı.

## Mevcut davranışı bozma riskleri

- Frontend bazı endpoint'lerde 403'ü auth değil yetki hatası olarak kullanıcıya göstermeyi bekliyor olabilir. Bu nedenle ilk patch 403'te local auth state'i temizlemez; sonraki adımda backend `code` alanı ile `TOKEN_INVALID` ve `FORBIDDEN` ayrımı yapılmalıdır.
- `handleRequest` halen hata durumunda exception fırlatır; mevcut çağıran kodların çoğu zaten bu davranışa göre çalışıyor. Bu patch exception davranışını korumayı hedefler.
- Console log azaltımı geliştirici debug alışkanlıklarını etkileyebilir; production güvenliği ve kullanıcı deneyimi için merkezi hata yönetimi tercih edilmiştir.
