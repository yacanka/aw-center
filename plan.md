# AW Center Mimari Denetim ve Güvenli Geliştirme Planı

## 1. Kısa mimari özet

AW Center, Django tabanlı bir backend ile Vue 3/Vite tabanlı bir frontend'i birleştiren, mühendislik dokümantasyonu ve uyumluluk iş akışlarına odaklı bir uygulamadır. Backend tarafında `backend/awcenter` ana proje ayarlarını, `users`, `common`, `dcc`, `ddf`, `doors`, `excel`, `word`, `pdf`, `outlook`, `orgs`, `pptxgallery`, `releases` ve `projects/<project>` uygulamaları domain sorumluluklarını taşır. Frontend tarafında route bazlı ekranlar `frontend/src/views`, tekrar kullanılabilir UI parçaları `frontend/src/components`, paylaşılan state `frontend/src/stores`, HTTP ayarları `frontend/src/services/http.ts` ve hata/request yardımcıları `frontend/src/composables/promise.ts` altında toplanmıştır.

Backend–frontend iletişimi Axios üzerinden REST benzeri endpoint'lerle yürür. Authentication, DRF TokenAuthentication'ın hem `Authorization: Token ...` header'ını hem de `auth_token` HttpOnly cookie'sini kabul eden özel sınıfla yapılır. Vue Router public allowlist dışında deny-by-default çalışır; merkezi route policy auth, staff ve doğrudan/grup kaynaklı permission kararlarını menü ve Hızlı Komut ile paylaşır. Backend tarafında global DRF permission varsayılanı `IsAuthenticated` olarak ayarlanmıştır ve güvenlik otoritesi backend'dir.

## 2. Kritik riskler

1. **Public user registration kapatıldı:** Anonim self-signup route'u ve frontend ekranı kaldırıldı; kullanıcı oluşturma yalnızca yetkili yönetim API'si veya Django admin üzerinden yapılır.
2. **Cookie token + CSRF tasarımı:** Auth token HttpOnly cookie ile taşınır; unsafe browser requests now require Django CSRF validation. Cross-site deployments must keep HTTPS, `AUTH_COOKIE_SAMESITE=None`, `AUTH_COOKIE_SECURE=True`, explicit CORS origins, and matching CSRF trusted origins aligned.
3. **Tamamlandı - Frontend stale session temizliği:** Route guard local user verisini hızlı başlangıç sinyali olarak kullansa da `/auth/me/` 401 cevabı artık uyarı bastırılsa bile token, user ve project state'ini kesin temizler; yalnız gerçek ağ kesintilerinde cached fallback korunur.
4. **Tamamlandı - Akıllı hata contract'ı ve korelasyon:** API hataları `detail`, `code`, `retryable`, `recovery_hint`, opsiyonel `errors` ve `request_id` alanlarını taşır; güvenli domain kataloğu kullanıcıya sonraki adımı, aynı kimlik ise response header ve backend log korelasyonunu sağlar.
5. **Dosya işleme yüzeyi geniş:** PDF/Excel/Word/Outlook/PPTX upload ve dönüştürme akışları büyük dosya, path traversal, temp file temizliği, MIME doğrulama ve subprocess güvenliği açısından öncelikli denetlenmelidir.
6. **Tamamlandı - Çekirdek pagination:** Kullanıcı, CompDoc, DDF, DCC, people ve davet listeleri server-side pagination/filter metadata'sına bağlandı; yeni büyük listeler aynı contract'ı kullanmalıdır.
7. **Tamamlandı - Frontend UI bundle bütçesi:** Tüm Naive UI eklentisi yerine kullanılan 70 bileşen açık allowlist ile kaydedildi; ortak chunk 1.196,94 kB'den 910,75 kB'ye, gzip boyutu 310,39 kB'den 233,85 kB'ye indirildi. Template kullanımı/kayıt eşitliği testi ve 950 KiB ham/250 KiB gzip build bütçesi regresyonu engelliyor.
8. **Çok uzun modül/fonksiyonlar:** Özellikle bazı domain view/service dosyalarında bakım maliyetini artıran uzun fonksiyonlar ve tekrarlar görülüyor.

## 3. Backend iyileştirmeleri

- Kullanıcı provisioning politikasını yönetici kontrollü tut; 24 saatlik tek kullanımlık davetler ve yaşam döngüsü audit ekranı eklendi, ileride otomatik e-posta teslimi değerlendirilebilir.
- API hata formatını standartlaştır: DRF exception handler ve manuel DRF response normalizer devrede; yeni endpoint'lerde okunabilirlik için yine `awcenter.api_errors.error_response(...)` tercih edilmelidir.
- Merkezi upload validator tamamlandı: uzantı, MIME çelişkisi, magic byte, OOXML türü, güvenli dosya adı, endpoint boyutu, streaming absolute limit ve ZIP bomb sınırları uygulanıyor. Sonraki güvenlik katmanı staging antivirus/CDR entegrasyonudur.
- List endpoint'lerine DRF pagination ekle: global pagination, ortak APIView helper'ı, güvenli allowlist filtreleme ve çekirdek frontend tablolarında remote page controls tamamlandı.
- Queryset optimizasyonlarını yaygınlaştır: `select_related`, `prefetch_related`, `only/defer` ve serializer kaynaklı N+1 ölçümleri.
- Kalıcı job modeli, worker lease/recovery, audit, iptal, retry ve artifact sözleşmesi eklendi; mevcut medya, Word, Excel, Outlook ve DCC job üreticileri gerçek worker adaptörlerine bağlıdır. Yeni job türleri aynı üretici-dispatch-tamamlama sözleşmesi ve uçtan uca testle eklenmelidir.
- Settings tarafında production env zorunluluklarını dokümante et; debug CORS davranışı local ile sınırlı tutulmalı.

## 4. Frontend iyileştirmeleri

- Axios hata yönetimini tek yerde standartlaştır: `formatApiError` standart contract'ı önceleyerek legacy `detail`/`message`/`error`/JSON-string gövdeleri geçiş dönemi için destekler; 401 auth durumlarında local auth state tutarlı temizlensin, 403 yetki hataları ise kullanıcıya ayrı gösterilsin.
- Store'larda `any` kullanımını azalt; request/response DTO tipleri ekle.
- Büyük `stores/api.ts` dosyasını domain servislerine böl: `dccApi`, `orgsApi`, `fileApi`, `pptxApi` gibi.
- Tamamlandı: Public allowlist dışındaki route'lar varsayılan authenticated kabul edilir; Users, DDF Assistant ve Developer/DOORS için merkezi permission/staff policy'si router, menü ve Hızlı Komut tarafından ortak kullanılır.
- Tamamlandı: Menü registry'sinden türeyen `Ctrl/⌘ + K` Hızlı Komut; normalize eşanlamlı/fuzzy arama, klavye navigasyonu, etkin proje/yetki filtreleme ve kullanıcıya özel recent sıralaması sağlar.
- Loading/error state'lerini merkezi hale getir; aynı pattern her store'da tekrar edilmesin.
- Gerçek `vue-tsc --noEmit`, Prettier ve production build kontrolleri CI kalite kapısı olarak korunmalı.
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

- Public endpoint allowlist regression testini koru; yeni `AllowAny` kullanımı açık güvenlik kararı gerektirmelidir.
- HttpOnly cookie auth için CSRF enforcement eklendi; cross-site deployment ayarları `AUTH_COOKIE_SAMESITE`, `AUTH_COOKIE_SECURE`, CORS ve CSRF trusted origins birlikte yönetilmelidir.
- Tamamlandı: Token/session invalidation sonrası frontend user, project ve token state'i merkezi temizleniyor; 401 temizliği uyarı görünürlüğünden ayrıldı, ikinci process-local kullanıcı cache'i kaldırıldı ve invalid session bootstrap tarayıcıda Login yönlendirmesiyle doğrulandı.
- Tamamlandı: Frontend route guard deny-by-default çalışıyor; güvenli post-login dönüşü yalnız iç uygulama yollarını kabul ediyor ve yetkisiz hedefler kullanıcı bağlamını kaybetmeden açıklayıcı 403 ekranına yönleniyor.
- Dosya yüklemelerinde path traversal'a karşı `safe_join`, random server-side file names ve allowlist kullanılmalı.
- Subprocess çağrılarında shell stringlerinden kaçınılmalı; argüman listeleri ve timeout zorunlu olmalı.
- Production `DEBUG=False`, `SECRET_KEY`, CORS, CSRF trusted origins ve HTTPS ayarları deployment checklist'e bağlanmalı.
- Log'larda token, cookie, JIRA/DocProof credential ve dosya içerikleri maskelenmeli.

## 7. Performans önerileri

- Büyük tablo endpoint'leri için pagination ve filtreleme server-side yapılmalı.
- Serializer N+1 kontrolleri için Django Debug Toolbar benzeri local ölçüm veya query count testleri eklenmeli.
- Excel/PDF/Word üretimlerinde streaming response veya async job yaklaşımı değerlendirilmeli.
- Frontend route component'lerinde lazy loading yaygınlaştırılmalı; şu anda çoğu route eager import ediliyor.
- Naive UI başlangıç chunk'ı yaklaşık %24 küçültüldü ve build bütçesine bağlandı; sonraki anlamlı adım route bazlı yerel bileşen kaydıyla 500 kB altına inmeyi ölçmektir.
- Gereksiz tekrar API çağrıları için store-level cache invalidation stratejisi belirlenmeli.

## 8. Önceliklendirilmiş yapılacaklar listesi

1. **Tamamlandı - Public signup:** Anonim kayıt route'u ve frontend formu kaldırıldı; yönetici kontrollü provisioning zorunlu.
2. **Tamamlandı - API hata formatı ve recovery standardı:** DRF exception ve manuel response yolları normalize edildi; domain kodları ve HTTP fallback'leri secretsız `retryable`/`recovery_hint` kataloğuyla zenginleştirildi ve frontend bütün ekranlarda önerilen sonraki adımı gösteriyor.
3. **Tamamlandı - File upload güvenlik denetimi:** PDF, Office, Outlook, PPTX, DDF, DCC, organization, DOORS ve media endpoint'leri merkezi policy katmanına bağlandı; parser öncesi içerik doğrulaması ve streaming limit testleri eklendi.
4. **Tamamlandı - Çekirdek pagination:** Users, CompDoc, DCC, DDF, People ve invitation tabloları server-side page/page_size/count/filter sözleşmesine geçirildi.
5. **Tamamlandı - Store/API modülerleştirme:** 1.013 satırlık `frontend/src/stores/api.ts` kaldırıldı; DCC, DDF, DOORS, DocProof, organization, Excel, PowerPoint ve Outlook state/request sınırları doğrudan domain store'larına ayrıldı ve CI mimari sınır testi eklendi.
6. **Tamamlandı - Strict TypeScript kalite kapısı:** Model/nullability borçları temizlendi; gerçek `vue-tsc --noEmit`, Prettier ve production build kontrolleri geçiyor. Sıradaki adım CI'ın yalnızca bu strict komutu kullanmasını zorunlu kılmak.
7. **P2 - Query ölçüm testleri:** Kritik list endpoint'lerine regression amaçlı query count testleri ekle.
8. **Tamamlandı - Frontend format borcu:** Repository-wide Prettier sapmaları giderildi; `npm run format:check` kalite kapısı yeniden yeşil.
9. **P1 - Canlı Teamcenter/DOORS kabul testi:** Deployment secret'larıyla Teamcenter web-tier sözleşmesini ve Windows üzerinde gerçek DOORS OLE/DXL read/write akışlarını staging ortamında doğrula.
10. **Tamamlandı - Integration Hub canlı durumları:** Configuration-readiness kataloğu; paralel, kısa timeout'lu, cache'li, refresh-limitli, secret-sızdırmayan ve circuit-breaker korumalı canlı health sonuçlarıyla genişletildi.
11. **Tamamlandı - Job orchestration foundation:** Kalıcı owner-scoped job/event modelleri, idempotency, SHA-256 artifact bütünlüğü, kooperatif iptal, retry, lease recovery, ayrı worker process'i, retention cleanup ve Job Center eklendi; medya dönüşümü synchronous request'ten worker'a taşındı.
12. **Tamamlandı - Document job adapters:** Word translation ve Excel cover-page üretimi process-local cache/SSE modelinden kalıcı job executor'larına taşındı; yerel AI model readiness'i Integration Hub'a eklendi, JIRA session verisinin cover-page payload'ına karışması kaldırıldı ve eksik dış template için güvenli yerleşik renderer sağlandı.
13. **Tamamlandı - Açıklanabilir belge analizi:** Sabit Windows model yollarına ve process-local cache/SSE akışına bağlı Belge Analizörü; allowlist kontrol seti, özel JSON kanıt raporu, içeriksiz Job Center özeti, model readiness kontrolü ve güvenli retry/hata kodları olan kalıcı job executor'ına taşındı.
14. **Tamamlandı - Tek kullanımlık kullanıcı daveti:** Staff ve `auth.add_user` yetkili yöneticiler için e-postaya bağlı, 24 saatlik, tek kullanımlık ve yalnız hash'i saklanan davet linki; grup ataması, public kayıt ekranı, atomik tüketim, IP rate-limit koruması ve doğrudan-link başlangıç testiyle eklendi.
15. **Tamamlandı - Davet yaşam döngüsü yönetimi:** Yetkili yöneticiler için server-side sayfalı/aranabilir durum defteri, aktif-kullanılmış-süresi dolmuş-iptal edilmiş filtreleri, atomik ve idempotent iptal, secretsız audit görünümü ve production UI smoke testi eklendi.
16. **Tamamlandı - Hızlı Komut merkezi:** Tek menü registry'sinden türeyen klavye paleti, Türkçe/İngilizce alias ve typo-tolerant sıralama, devre dışı proje eleme, kullanıcı yönetimi yetki filtresi ve hesap-bazlı recent geçmişiyle eklendi.
17. **Tamamlandı - Deny-by-default frontend erişim politikası:** Public route allowlist'i, route meta access kuralları, doğrudan/grup permission çözümleme, staff sınırı, güvenli login dönüşü ve ortak menü/Hızlı Komut filtrelemesi eklendi.
18. **Tamamlandı - Typed tablo filtre altyapısı:** 405 satırlık `stores/datatable.ts` kaldırıldı; CompDoc kataloğu, saf filtre motoru ve izole filtre menüleri 200 satır altı modüllere ayrıldı. Tarih eşitliği ve production feature-flag sözleşmesi düzeltildi.
19. **Tamamlandı - CompDoc import audit izi:** Onaylı importlar `cover_page_no` upsert, SHA-256 kaynak parmak izi, importing user/request reference, kolon eşlemeleri, create/update/reject sayaçları ve güvenli satır hatalarıyla kaydediliyor; yetkili proje geçmişi/detayı eklendi.
20. **Tamamlandı - CompDoc Excel iyileştirme raporu:** Yetkili audit detayı; özet, reddedilen satırlar, alan hataları, düzeltme önerileri ve kolon eşlemelerini kaynak workbook içeriğini kopyalamadan, formül enjeksiyonuna dayanıklı XLSX olarak dışarı aktarabiliyor.
21. **Tamamlandı - Uygulamalar arası Dikkat Merkezi:** Sahip olunan çözülmemiş job hataları, yetkili CompDoc partial/failed importları ve altı saat içinde bitecek yönetici davetleri; kritik-seviyeli, 14 günlük sınırlı ve doğrudan ilgili detay ekranını açan tek ana sayfa kuyruğunda birleşti.
22. **Tamamlandı - Kişisel dikkat kararları:** Kullanıcılar yetkili attention itemlarını kaynak workflow durumunu değiştirmeden 24 saat erteleyebiliyor veya kendi kuyruklarından kalıcı kapatabiliyor; kararlar kullanıcı-item bazında tekil, atomik ve ownership/permission yeniden doğrulamalı.
23. **Tamamlandı - Ölçülebilir frontend UI bundle optimizasyonu:** Kullanılmayan Naive UI bileşenlerini başlangıç paketinden çıkaran açık kayıt kataloğu, template-katalog eşitlik testi ve production build'de ham/gzip boyut bütçesi eklendi; mevcut görsel davranış korunurken ilk UI payload'ı yaklaşık %24 azaltıldı.
24. **Tamamlandı - Güvenli işler arası artefakt devri:** Başarılı Word çevirisi, sahiplik ve SHA-256 bütünlüğü yeniden doğrulanarak özel storage içinde açıklanabilir belge analizine tek tıkla aktarılabiliyor; hedef upload policy'si tekrar uygulanıyor, işlem idempotent ve kaynak-hedef provenance bağlantısı çift taraflı audit olaylarında korunuyor.
25. **Tamamlandı - Immutable tek-origin production artefaktı:** Backend image Vite build'i ayrı Node aşamasında üretip `/app/frontend-dist` içine kopyalıyor, WhiteNoise statiklerini image içinde topluyor ve Django'nun nested SPA route'u ile gerçek JS/CSS entry assetlerini servis ettiğini build sırasında doğruluyor; Compose ayrı frontend container gerektirmiyor.
26. **Tamamlandı - İzlenebilir Workflow Accelerator:** Allowlist tabanlı recipe motoru Word çevirisi ile açıklanabilir analizi tek owner-scoped akışta otomatik zincirliyor; SHA-256 ve upload policy her devirde yeniden doğrulanıyor, adımlar atomik tek-çocuklu retry/cancel sözleşmesini koruyor, kesinti recovery'si idempotent ve UI her adımın durumunu/hatasını gösteriyor.
27. **Tamamlandı - Outlook → Word analiz köprüsü:** Recipe kataloğu dinamik input/parametre sözleşmesine taşındı; `.msg` içindeki tek DOCX eki özel job storage'da güvenlik ve SHA-256 kontrolüyle çıkarılıp açıklanabilir analize aktarılıyor. Ham HTML/base64 render kaldırıldı, geçici indirme tokenları kullanıcıya bağlandı ve belirsiz/tehlikeli ekler güvenli hata kodlarıyla durduruluyor.
28. **Tamamlandı - İnsan onaylı analiz → JIRA köprüsü:** Bütünlüğü doğrulanmış özel analiz raporu tekil owner-scoped Task taslağına dönüşüyor; tam sürüm kontrollü düzenleme onayı geçersizleştiriyor, dış yayın ayrı Django yetkisi ve geçici JIRA session'ı gerektiriyor, belirsiz create yanıtları tekil marker ile mükerrer kayıt oluşturmadan kurtarılıyor ve bekleyen/başarısız taslaklar Dikkat Merkezi'ne taşınıyor.
29. **Tamamlandı - JIRA canlı create-contract ön kontrolü:** Yetkili kullanıcı geçici session ile proje/Task create metadata'sını dış yazma olmadan denetleyebiliyor; desteklenen zorunlu alanları sürümlü taslakta tamamlıyor, eksik/geçersiz/desteklenmeyen gereksinimleri güvenli rehberle görüyor ve yayın aynı sözleşmeyi tekrar doğrulamadan başlamıyor.
30. **Tamamlandı - Outlook MSG → ECR PDF → JIRA Task zinciri:** Eski inline base64 bağımlılığı kaldırıldı; kullanıcıya bağlı süreli ek linki authenticated Blob/File olarak indirilip boyut ve PDF imzası yeniden doğrulanıyor. Her parse sonucu kaynak PDF ve oluşturulan JIRA issue ile açıkça eşleniyor, retry aynı issue/eki yeniden işlemiyor, başarısız veya süresi dolmuş ekler aynı isimli manuel PDF ile güvenli biçimde değiştirilebiliyor. Dış yazma ve SSE kuyrukları DCC oluşturma yetkisine, kuyruklar oluşturan kullanıcıya bağlandı.
31. **Tamamlandı - Kalıcı JIRA → DCC DOCX üretimi:** Process-local DCC cache/SSE ve base64 indirme kaldırıldı; JIRA session kullanıcı talebiyle tarayıcı local storage'ında yeniden kullanım için saklanıyor, ancak snapshot/job girdisi, artifact ve audit kayıtlarına alınmıyor ve logout/401 temizliğinde siliniyor. Sürümlü ve boyut sınırlı snapshot özel job girdisi olarak SHA-256 bütünlüğüyle saklanıyor, owner-scoped worker gerçek OOXML çıktısını doğruluyor, kesinti/retry/audit/indirme Job Center üzerinden yönetiliyor ve sıfır-alt görev ile çelişkili Responsible AS sınırları açıkça ele alınıyor.
32. **Tamamlandı - İmzalı CompDoc import onayı:** Önizleme; tam dosya SHA-256'sı, kullanıcı ve proje modeline bağlı 15 dakikalık imzalı onay üretiyor. Backend doğrudan veya farklı dosya/kullanıcı/proje ile onayı reddediyor; UI create/update/unchanged/reject etkisini gösteriyor, yinelenen anahtarları deterministik reddediyor ve değişmeyen satırlarda gereksiz history yazmıyor.
33. **Tamamlandı - Dry-render kanıtlı DCC onayı:** JIRA bir kez okunup owner-bound immutable snapshot oluşturuluyor; kayıtlı proje template'i aynı kaynakla gerçekten render edilmeden iş yaratılamıyor. Proje, çıktı, panel sayısı, kaynak zamanı ve eksik önerilen alanlar 15 dakikalık önizlemede gösteriliyor; worker yalnız açık onaydan sonra aynı snapshot'ı alıyor. Süresi dolan özel önizlemeler temizleniyor, Job Center incelemeye geri bağlıyor, cross-origin idempotency header'ı izinli ve geçici JIRA alanları parola autofill'inden korunuyor.
34. **Tamamlandı - Sunucu sıralamalı kişi arama:** NSearch sayfaya yüklenmiş kişi dizininden ayrıldı; iki karakterden sonra debounce ve gerçek HTTP cancellation ile DRF pagination endpoint'inden yalnız sınırlı sonuç alıyor. Backend ad, sicil ve e-postayı exact/prefix/contains/typo benzerliğiyle deterministik sıralıyor; aday ve sorgu sınırları, yükleniyor/boş/hata durumları ve regresyon testleri eklendi.
35. **Tamamlandı - Job worker süreç sürekliliği:** Tek desteklenen `launcher.py` yüzeyinin dev/prod modları web süreçleriyle birlikte kalıcı worker'ı da başlatıp denetliyor; yinelenen eski starter kaldırıldı. DCC onayının gerçek dry-render, queue, worker ve doğrulanmış DOCX tamamlanma zinciri tek regresyon testinde korunuyor. Job Center yalnız gerçekten `awaiting_confirmation` olan DCC preview'larında onay yönlendirmesi gösteriyor.
36. **Tamamlandı - Proje bazlı CompDoc yetkilendirmesi:** Liste, UUID detay/geçmiş, metadata, export, create/upsert, import, update ve delete uçları ilgili proje model yetkilerine deny-by-default bağlandı. Toplu silme `view + delete`, tam proje cümlesi ve güncel kayıt sayısı istiyor; silme geçmişi aktörle korunuyor ve frontend yalnız yetkili aksiyonları gösteriyor.
39. **Tamamlandı - Açıklanabilir DCC readiness ve risk acknowledgment:** Dry-render önizlemesi template, JIRA alanları ve panel kapsamını ağırlıklı skor ve eyleme dönük checklist olarak gösteriyor. Warning'lerin tam kod kümesi backend'de açık kullanıcı onayı olmadan queue'ya geçemiyor ve kabul kararı immutable Job event'inde saklanıyor.
40. **Tamamlandı - Production NSearch pagination:** Kişi dropdown'u DRF `count/next/results` sözleşmesini kaybetmeden relevance sırasının sonraki sayfalarını isteğe bağlı yüklüyor; debounce, gerçek cancellation, stale-response koruması, retry ve tekilleştirme sağlıyor. People tablosu aynı sunucu aramasına bağlandı, her sorguda ilk sayfaya dönüyor ve geç kalan isteklerin güncel tabloyu ezmesi engelleniyor.
41. **Tamamlandı - CoverPage -> CompDoc ilişkisi:** Proje kapsamlı canonical CoverPage kayıtları ile bire-çok CompDoc ilişkisi kuruldu; mevcut cover-page alanları ve Excel sözleşmesi geriye uyumlu tutulurken import kimliği aynı cover page altındaki farklı teknik dokümanları destekleyecek şekilde genişletildi.

## 9. Uygulanan hata contract patch'i

Bu patch, davranışı kontrollü değiştirmek ve eski endpoint'leri kırmamak için backend exception path'ini standartlaştırıp frontend'de geriye uyumlu parser ekledi:

1. `backend/awcenter/api_errors.py` ortak hata contract builder, DRF exception handler ve manuel endpoint helper'ı sağlar.
2. `REST_FRAMEWORK["EXCEPTION_HANDLER"]` ayarı, DRF exception'larının tamamını `{ detail, code, retryable, recovery_hint, errors? }` formatına normalleştirir.
3. `ApiErrorContractMiddleware`, eski manuel `Response({"message": ...}, status=400)`, `Response({"error": ...}, status=400)`, serializer error dict ve düz string hata gövdelerini render öncesinde aynı contract'a çevirir.
4. `frontend/src/services/apiError.ts`, standart contract'ı birincil kabul eder ve kullanıcıya güvenli sonraki adımı gösterir; legacy `detail`, `message`, `error`, field errors ve JSON string durumlarını da normalize eder.
5. `frontend/src/composables/promise.ts` ve doğrudan upload/login hata gösterimleri, hata formatlamasını merkezi helper'a devreder ve mevcut 401 auth cleanup davranışını korur.
6. `backend/awcenter/tests.py`, validation, not-found, manuel helper ve legacy manuel response normalizasyonunu regression testi ile güvenceye alır.

## Mevcut davranışı bozma riskleri ve trade-off'lar

- Frontend bazı endpoint'lerde 403'ü auth değil yetki hatası olarak kullanıcıya göstermeyi bekliyor olabilir. Bu nedenle 403'te local auth state'i temizlenmez; sonraki adımda backend `code` alanı ile token-invalid ve forbidden ayrımı daha görünür yapılmalıdır.
- `handleRequest` halen hata durumunda exception fırlatır; mevcut çağıran kodların çoğu zaten bu davranışa göre çalışıyor. Bu patch exception davranışını korumayı hedefler.
- Console log azaltımı geliştirici debug alışkanlıklarını etkileyebilir; production güvenliği ve kullanıcı deneyimi için merkezi hata yönetimi tercih edilmiştir.


## 10. Sonraki hata contract adımları

1. **Tamamlandı:** README seviyesinde `detail/code/retryable/recovery_hint/errors/request_id` sözleşmesi yayınlandı.
2. **Tamamlandı:** Upload, job, invitation, JIRA, Teamcenter, DOORS, Word/AI ve cover-page domain kodları merkezi güvenli recovery kataloğuna bağlandı; yeni kodlar prefix/status fallback alıyor.
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
2. **Tamamlandı - Import audit trail:** Dosya adı/boyutu/SHA-256, importing user, request reference, detected/missing/unmapped kolonlar, create/update/unchanged/reject sayaçları ve güvenli satır hataları permission-protected audit ekranına bağlandı.
3. **Tamamlandı - Preview-to-confirm bütünlüğü:** Kayıt isteği yalnız aynı kullanıcı, proje modeli ve tam dosya parmak izi için süresi geçmemiş imzalı önizleme kanıtıyla kabul ediliyor; önizleme veritabanına yazmıyor.
4. **Tamamlandı - Veritabanına bağlı atomik onay:** İmzalı önizleme artık yalnız dosyayı değil, workbook'taki business key'lerin güncel kayıt kimliği, Simple History sürümü ve planlanan aksiyonunu da doğruluyor; hedef değişmişse 409 ile yeni önizleme isteniyor ve beklenmeyen bir yazma hatasında tüm batch geri alınıyor.

## 50. Frontend artifact deployment follow-up

1. **Tamamlandı - Deployment pipeline alignment:** Backend multi-stage image frontend'i `npm ci` ile build edip immutable `/app/frontend-dist` konumuna kopyalıyor; Compose aynı-origin SPA/API topolojisini kullanıyor ve runtime static volume image içeriğini maskelemiyor.
2. **P2 - CDN/static offload:** For higher traffic deployments, serve `/core/assets/` from Nginx/CDN object storage while keeping Django responsible only for the SPA fallback and API routes.
3. **Tamamlandı - Build artifact smoke test:** Management command ve CI; nested `/app/jobs`, kaynak ve collectstatic asset bütünlüğü ile WhiteNoise JS/CSS cevaplarını workspace build ve birleşik container image içinde doğruluyor.

## 60. DocProof follow-up recommendations

1. **P1 - Service boundary:** Move DocProof HTTP client helpers from `views.py` into a dedicated `client.py` or `services.py` once adjacent integration modules can be updated safely.
2. **P1 - Contract tests with fixture payloads:** Capture representative DocProof JSON payload fixtures and add tests for missing keys, malformed payloads, and multiple document types.
3. **Tamamlandı - Authentication policy:** `docproof/search/` authenticated hale getirildi ve placeholder `docproof/test/` route'u kaldırıldı.

## 70. Production readiness hardening follow-up

1. **Tamamlandı - Health/readiness:** `/health/live/` ve `/health/ready/` eklendi; readiness database/cache kontrolü yapar.
2. **Tamamlandı - Env-driven runtime:** Primary/legacy database URL, Redis cache URL, logging level, proxy SSL header ve cookie SameSite ayarları environment üzerinden yönetilebilir.
3. **Tamamlandı - Container runtime:** Backend Dockerfile artık Django `runserver` yerine Gunicorn kullanır; Compose PostgreSQL ve Redis bağlantılarını production'a yakın URL sözleşmesiyle verir.
4. **Tamamlandı - Local migration state:** Local SQLite migration'ları güncel; production deploy yine immutable release adımı olarak `python manage.py migrate --noinput` çalıştırmalıdır.
5. **Kalan risk - Yerel Docker doğrulaması:** Bu ortamda Docker binary bulunmadığı için image build çalıştırılamadı; aynı build ve image-içi artefakt doğrulaması CI kalite kapısına eklendi ve ilk remote CI sonucu izlenmelidir.

## 71. İlk production güvenlik ve gözlemlenebilirlik

1. Tüm iş/veri endpoint'leri deny-by-default hale getirildi; health, login ve parola sıfırlama dışında `AllowAny` kullanımı merkezi test allowlist'iyle engelleniyor.
2. Anonim self-signup kaldırıldı; kullanıcı oluşturma yönetici yetkisine bağlandı.
3. Her isteğe güvenli `X-Request-ID` atanıyor; standart hata gövdesi ve backend logları aynı destek referansını taşıyor.
4. JIRA, Teamcenter, DOORS, DocProof, Office ve medya köprülerini secretsız readiness/capability sözleşmesinde birleştiren Integration Hub eklendi.
