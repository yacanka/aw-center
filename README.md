# AW Center — Automated Workflows & Compliance Center

AW Center; mühendislik dokümantasyonu, değişiklik yönetimi, uyumluluk izlenebilirliği ve sertifikasyon hazırlığı süreçlerini tek merkezde toplayan Django + Vue tabanlı bir otomasyon platformudur.

Platform; JIRA, DOORS, Excel, Word, PDF, Outlook, DocProof, PowerPoint ve medya dönüştürme iş akışlarını tek bir web arayüzünden yönetmek için tasarlanmıştır. Ana hedef; manuel doküman üretimini azaltmak, denetim izlerini güçlendirmek, proje bazlı uyumluluk durumunu görünür kılmak ve tekrar eden mühendislik operasyonlarını kontrollü şekilde otomatikleştirmektir.

---

## İçindekiler

- [Temel Kabiliyetler](#temel-kabiliyetler)
- [Uygulama Mimarisi](#uygulama-mimarisi)
- [Modüller ve Fonksiyonel Özellikler](#modüller-ve-fonksiyonel-özellikler)
- [Proje Registry ve Proje Bazlı Uygulamalar](#proje-registry-ve-proje-bazlı-uygulamalar)
- [Launcher: Kurulum, Çalıştırma ve Doğrulama](#launcher-kurulum-çalıştırma-ve-doğrulama)
- [Environment Değişkenleri](#environment-değişkenleri)
- [Geliştirme Komutları](#geliştirme-komutları)
- [Test ve Kalite Kapıları](#test-ve-kalite-kapıları)
- [Güvenlik Notları](#güvenlik-notları)
- [Deployment Temelleri](#deployment-temelleri)
- [Sık Karşılaşılan Sorunlar](#sık-karşılaşılan-sorunlar)

---

## Temel Kabiliyetler

AW Center aşağıdaki iş akışlarını destekler:

- **DCC / ECD yönetimi:** JIRA tabanlı Design Change Control kayıtlarını izleme, oluşturma, güncelleme, değerlendirme, e-posta gönderimi ve gerçek template dry-render kanıtlı, insan onaylı belge üretimi.
- **DDF ve CompDoc takibi:** Proje bazlı compliance document listeleri, upsert destekli Excel içe aktarma, dosya/kullanıcı/projeye bağlı imzalı önizleme onayı, create/update/unchanged/reject etki özeti, SHA-256 kaynak kanıtlı import audit'i, alan keşfi, dinamik kolon ayarları, grafikler ve durum takibi.
- **JIRA otomasyonları:** JIRA issue arama, issue detay okuma, subtask üretimi, Excel tabanlı toplu subtask üretimi ve akış durumlarının SSE ile canlı izlenmesi.
- **Analiz → JIRA inceleme köprüsü:** Bütünlüğü doğrulanmış özel Word analiz raporunu owner-scoped Task taslağına dönüştürür; optimistic concurrency, açık insan onayı, ayrı yayın yetkisi, içeriksiz audit izi ve marker tabanlı mükerrer kayıt kurtarması sağlar.
- **DOORS otomasyonları:** Excel verisinden DXL script üretimi, DOORS çalıştırma entegrasyonu ve PoC linkleme ekranları.
- **Doküman karşılaştırma:** Excel, Word ve PDF karşılaştırma araçları.
- **Word işleme:** Word compare, analyze ve translate kuyrukları.
- **PDF işleme:** PDF bölme ve PDF karşılaştırma.
- **Outlook `.msg` işlemleri:** Plain-text e-posta inceleme, kullanıcıya bağlı süreli ek indirme, kalıcı Word eki çıkarma ve Outlook → Word analiz köprüsü.
- **PowerPoint gallery:** Sunum ve slayt yükleme, listeleme, görsel önizleme ve dış dönüşüm araçlarıyla galeri oluşturma.
- **Medya dönüştürme:** FFmpeg tabanlı görüntü/ses/video dönüştürme, önizleme ve çıktı boyutu tahmini.
- **Organizasyon yönetimi:** Proje, panel, sorumlu ve kişi kayıtlarının CRUD yönetimi, kişi Excel yükleme ve ad/sicil/e-posta üzerinde sunucu-sıralamalı, typo-tolerant, sayfalı kişi arama. NSearch sonuçları toplam kayıt ve sonraki sayfa bilgisini korur; People tablosu aynı sunucu filtresiyle çalışır.
- **Kullanıcı ve yetki yönetimi:** Yönetici kontrollü hesap açma, 24 saatlik tek kullanımlık davetler, davet yaşam döngüsü denetimi, login/logout, HttpOnly token cookie, CSRF koruması, parola değiştirme, parola sıfırlama, kullanıcı tercihleri ve izin listesi. Anonim self-signup yoktur.
- **Integration Hub:** JIRA, Teamcenter, DOORS, DocProof, Office ve medya köprülerinin secretsız yapılandırma/capability görünümü, isteğe bağlı canlı sağlık kontrolleri, circuit breaker koruması ve ilgili araçlara hızlı geçiş.
- **Job Center ve Workflow Accelerator:** Uzun süren işlemler için kalıcı sahiplik, ilerleme, kooperatif iptal, atomik/idempotent retry, worker lease recovery, audit olayları ve güvenli artifact indirme merkezi. Allowlist tabanlı recipe'ler bir aracın doğrulanmış çıktısını tarayıcıya indirmeden sonraki adıma aktarır; Word çeviri → analiz ve Outlook Word eki → analiz süreçleri tek izlenebilir akışta çalışır.
- **Dikkat Merkezi:** Kullanıcının başarısız işlerini, bekleyen/başarısız JIRA taslaklarını, yetkili olduğu sorunlu CompDoc importlarını, DCC üretiminden sonra değişmiş CompDoc kaynaklarını ve süresi yaklaşan davetleri tek önceliklendirilmiş ana sayfa kuyruğunda birleştirir; her kayıt doğrudan düzeltme ekranına gider ve kullanıcıya özel 24 saat erteleme/kapatma kararları desteklenir. API: `GET /action-center/`, `POST /action-center/decisions/`.
- **Hızlı Komut:** `Ctrl/⌘ + K` ile tüm etkin araçları, proje akışlarını ve entegrasyon köprülerini Türkçe/İngilizce eşanlamlı veya küçük yazım hatalı aramayla açan, yetki filtreli ve kullanıcıya özel son-komut geçmişi.
- **Merkezi erişim politikası:** Public allowlist dışındaki ekranlar varsayılan korumalıdır; route, sol menü ve Hızlı Komut aynı staff/permission kararını kullanır. Yetkisiz erişim açıklayıcı 403 ekranına, anonim erişim ise güvenli post-login dönüşüyle Login'e gider.
- **Release notes:** Kullanıcı bazlı görülmemiş sürüm notları, toplu görüldü işaretleme ve onaylama.
- **SPA shell serving:** Vue uygulamasının `/app/` altında Django tarafından servis edilmesi.

---

## Uygulama Mimarisi

### Backend

- **Framework:** Django + Django REST Framework.
- **Proje paketi:** `backend/awcenter/`.
- **Giriş noktaları:**
  - `backend/manage.py`: Django yönetim komutları.
  - `backend/awcenter/wsgi.py` ve `backend/awcenter/asgi.py`: WSGI/ASGI girişleri.
  - `backend/run_cheroot.py`: Cheroot HTTPS sunucusu.
- **Ana URL yönlendirme:** `backend/awcenter/urls.py`.
- **Kimlik doğrulama:** `awcenter.authentication.CookieTokenAuthentication` ile DRF token; standart `Authorization: Token ...` header'ı ve `auth_token` cookie desteklenir.
- **Varsayılan yetki:** DRF için global `IsAuthenticated`; public route'lar merkezi test allowlist'iyle sınırlandırılır.
- **İstek korelasyonu:** Her response `X-Request-ID` taşır; aynı değer standart API hatalarında ve backend loglarında destek referansı olarak bulunur.
- **Veritabanı:** Varsayılan olarak SQLite (`backend/db.sqlite3`) ve eski veri için ikinci SQLite bağlantısı (`backend/db_old.sqlite3`).
- **Statik dosyalar:** `/core/` URL kökü ve WhiteNoise `CompressedManifestStaticFilesStorage`.
- **Medya dosyaları:** `backend/media`.
- **Production güvenliği:** `DEBUG=False` iken HTTPS redirect, secure cookie, HSTS, content-type nosniff, same-origin referrer policy ve `X_FRAME_OPTIONS="DENY"` aktif olur.

### Frontend

- **Framework:** Vue 3 + Vite + TypeScript.
- **UI:** Naive UI; only template-used components are registered globally, with source synchronization tests and raw/gzip bundle budgets enforced by the production build.
- **State:** Pinia.
- **Domain state sınırları:** DCC, DDF, DOORS, DocProof, organizasyon, Excel, PowerPoint ve Outlook işlemleri ayrı typed Pinia store'larında tutulur; bileşenler merkezi bir API-store facade'ı yerine ilgili domain store'unu doğrudan kullanır.
- **Router:** Vue Router, browser history kökü `/app/`.
- **Route güvenliği:** `welcome`, `login` ve `invite` açıkça public işaretlenir; diğer route'lar deny-by-default authenticated kabul edilir. Hassas ekranlar merkezi access policy üzerinden staff veya doğrudan/grup kaynaklı Django permission kontrolü uygular.
- **HTTP:** Axios merkezi yapılandırması `frontend/src/services/http.ts`.
- **Build base:** Vite üretim base'i `/core/`.
- **Kod bölme:** Ağır route'lar lazy-load edilir ve ortak loading skeleton kullanır.
- **Build çıktısı:** `frontend/dist` altında üretilir; Django `FRONTEND_DIST_DIR` üzerinden SPA shell ve `/core/assets/...` statik asset'lerini servis edebilir.

### Ana Dizinler

```text
backend/                  Django backend
frontend/                 Vue/Vite frontend
backend/projects/         Proje bazlı DCC, CompDoc ve organizasyon uygulamaları
backend/dcc/              JIRA/DCC/ECD süreçleri
backend/ddf/              DDF süreçleri
backend/doors/            DOORS/DXL süreçleri
backend/excel/            Excel compare ve cover page üretimi
backend/word/             Word compare/analyze/translate süreçleri
backend/pdf/              PDF split ve compare
backend/outlook/          Outlook .msg parse/download
backend/pptxgallery/      PowerPoint gallery
backend/media_tools/      FFmpeg medya dönüştürme
backend/orgs/             Organizasyon verileri
backend/users/            Kullanıcı, auth ve preferences
backend/releases/         Release notes
launcher.py               Kurulum/çalıştırma/doğrulama launcher'ı
scripts/starter.py        Daha küçük geliştirme starter'ı
docs/                     Mimari, deployment ve kalite dokümantasyonu
```

---

## Modüller ve Fonksiyonel Özellikler

### 1. DCC / ECD ve JIRA Otomasyonları

Backend route kökü: `/dcc/`
Frontend ekranları: `/app/dcc`, `/app/compare/...`, `/app/compdocs/...`

Özellikler:

- JIRA DCC kayıtlarını listeleme ve detaylarını görüntüleme.
- Yeni DCC kaydı ekleme.
- JIRA issue arama ve issue detaylarını çekme.
- JIRA üzerinde issue/subtask oluşturma.
- Liste tabanlı subtask üretimi.
- Excel tabanlı toplu subtask üretimi.
- Geçici JIRA oturumuyla tek seferlik, kimlik bilgisi içermeyen ve kullanıcıya bağlı kaynak anlık görüntüsü yakalama.
- Aynı immutable snapshot üzerinde gerçek proje template'iyle dry-render; proje, çıktı adı, panel sayısı, kaynak zamanı, eksik önerilen alanlar ve 15 dakikalık onay süresini worker başlamadan gösterme.
- Template, önerilen JIRA alanları, panel kapsamı ve seçili CompDoc kaynaklarının teknik referans/otorite olgunluğunu ağırlıklı 0-100 readiness skoru ve açıklanabilir kontrol listesiyle değerlendirme.
- Captured JIRA başlıkları, panel değerlendirmeleri, ATA, cover-page ve teknik doküman referanslarından yetki kontrollü, açıklanabilir CompDoc önerileri üretme; öneriler otomatik bağlanmaz ve en fazla 500 adaydan en güçlü 8 eşleşmeyle sınırlıdır.
- Kullanıcının seçtiği önerileri JIRA'yı yeniden okumadan aynı bütünlüğü doğrulanmış snapshot'tan yeni bir immutable preview'a aktarma; eski preview atomik olarak superseded edilir ve iki sürüm `source_job` ile izlenir.
- Readiness warning'lerinin tamamını kullanıcıya açıkça onaylatma; eksik veya değiştirilmiş acknowledgment listesini backend'de reddetme ve kabul edilen warning kodlarını içeriksiz immutable job audit event'i olarak saklama.
- Compliance Documents ekranında seçilen en fazla 50 kaydı, JIRA component'inden çözülen aynı projeye ait olma ve proje `view_compdoc` yetkisiyle doğrulayıp son history sürümleriyle immutable DCC snapshot'ına bağlama.
- Seçili CompDoc kayıtlarının canonical SHA-256 fingerprint'ini, durum dağılımını ve eksik teknik doküman referans sayısını önizlemede gösterme; doğrulanmış referansları template değişikliği gerektirmeyen bir DOCX izlenebilirlik eki olarak üretme.
- Onaylanan CompDoc kaynaklarının ters DCC geçmişini ilgili kayıt detayında gösterme; kaynak history sürümü, fingerprint, güncel/eski kaynak durumu ve korunmuş job/retry durumu audit olarak saklanır.
- Son 14 günde değişen ve en yeni onaylı DCC'si eski history sürümüne bağlı kalan CompDoc'ları çift yetki kontrollü Action Center uyarısına dönüştürme; uyarı doğrudan ilgili kayıt ve DCC geçmişini açar, yeni history sürümü önceki kapatma kararından bağımsız tekrar görünür.
- Manuel CompDoc güncellemelerinde güncel Simple History sürümünü zorunlu optimistic concurrency anahtarı olarak kullanma; transaction ve row lock altında eski yazımları 409 ile reddetme, başarılı history kaydına aktörü bağlama ve yetkili kullanıcıya mevcut DCC etkisini kaydetmeden önce açıkça onaylatma.
- Açık kullanıcı onayı verilene kadar worker'ın göremediği `awaiting_confirmation` durumu; onaydan sonra JIRA'yı yeniden okumadan aynı özel snapshot ile doğrulanmış DOCX üretme.
- ECD dosyası yükleme ve assessment işlemleri.
- DCC reminder/e-posta gönderimi.
- Subtask ve Excel subtask operasyonları için kullanıcıya bağlı geçici SSE progress stream; DCC doküman üretimi için kalıcı job/event ilerlemesi.
- JIRA dynamic field metadata okuma.
- JIRA session kontrolü ve attachment ekleme.
- Proje registry üzerinden JIRA component -> proje eşleştirme.
- DCC template dosyalarının güvenli path resolver ile çözülmesi.
- Açıklanabilir analiz raporundan düzenlenebilir JIRA Task taslağı, sürüm kontrollü onay ve ayrı `dcc.publish_jiraissuedraft` yetkisiyle yayınlama.
- Canlı JIRA create metadata ön kontrolü; desteklenen zorunlu alanları taslak içinde doldurma, geçersiz/desteklenmeyen gereksinimler için eyleme dönük bloklar ve yayın anında tekrar doğrulama.
- Belirsiz JIRA create yanıtlarında sunucu üretimli tekil label ile önce mevcut issue'yu arayan mükerrer kayıt kurtarması; `JSESSIONID` hiçbir draft/event kaydında tutulmaz.

Önemli endpoint örnekleri:

- `GET/POST /dcc/api/`
- `GET/PUT/DELETE /dcc/api/<id>/`
- `GET /dcc/issues/`
- `POST /dcc/create_issue/`
- `POST /dcc/jobs/create-document/preview/`
- `POST /dcc/jobs/create-document/<job-id>/confirm/`
- `POST /dcc/jobs/create-document/<job-id>/compdoc-recommendations/`
- `GET /dcc/compdoc-traceability/?project=<slug>&compdoc_id=<uuid>`
- `POST /dcc/issue-drafts/<id>/preflight/`
- `POST /dcc/issue-drafts/<id>/publish/`
- `POST /dcc/send_mail/`
- `POST /dcc/upload/`
- `GET /dcc/create_dcc_stream/<uuid>/`
- `GET /dcc/create_subtask_stream/<uuid>/`
- `GET /dcc/create_subtask_excel_stream/<uuid>/`
- `GET /dcc/subtask_fields/`
- `POST /dcc/issue-drafts/`
- `GET/PATCH /dcc/issue-drafts/<uuid>/`
- `POST /dcc/issue-drafts/<uuid>/approve/`
- `POST /dcc/issue-drafts/<uuid>/publish/`

### 2. DDF Assistant

Backend route kökü: `/ddf/`
Frontend ekranı: `/app/ddfAssistant`

Özellikler:

- DDF kayıtlarını listeleme.
- Tekil DDF kaydı görüntüleme/güncelleme/silme.
- Excel dosyasından DDF import.
- DDF assessment işlemleri.
- Grafik ve durum takibi bileşenleri.

Endpointler:

- `GET/POST /ddf/`
- `GET/PUT/DELETE /ddf/<id>/`
- `POST /ddf/upload/`
- `POST /ddf/assessment/`

### 3. Compliance Documents / CompDoc

Frontend ekranları: `/app/compdocs/:project`, `/app/compdocs/coverpagecreator`, `/app/compdocs/docAnalyzer`

Özellikler:

- Proje bazlı compliance document listeleri.
- Server-driven alan metadata endpointleri.
- Dinamik kolon seçimi ve kullanıcı bazlı kolon tercihleri.
- Excel import önizleme ve yalnız aynı dosya, kullanıcı ve proje için geçerli imzalı onay sonrası kayıt.
- Eksik kolon, unmapped kolon ve satır validation uyarılarını gösterme.
- `cover_page_no` üzerinden create/update upsert; create/update/unchanged/reject etki özeti ve deterministik duplicate-key reddi.
- Değişmeyen satırlarda gereksiz model/history yazımını atlama.
- Dosya adı/boyutu/SHA-256, importing user, request reference, detected mappings ve create/update/unchanged/reject sayılarını saklayan import audit izi.
- `common.view_compdocimportaudit` yetkisine bağlı proje bazlı geçmiş ve detay görünümü.
- Audit kanıtını, reddedilen satırları, düzeltme önerilerini ve kolon kararlarını formül enjeksiyonuna dayanıklı Excel raporu olarak indirme.
- Server-side pagination ve filtreleme.
- DocProof arama entegrasyonu.
- Durum akışı ve gecikme göstergeleri.
- Cover page üretimi.
- Doküman analiz ekranı.
- Yetkili kullanıcıların mevcut sayfalar arasında en fazla 50 CompDoc seçip doğrudan DCC Creator'a geçmesi; seçimler backend'de tekrar UUID, proje, kayıt varlığı ve yetki kontrolünden geçirilir.

CompDoc API'leri yalnız oturum kontrolüne güvenmez; her proje uygulamasının kendi Django
model yetkileri backend'de uygulanır:

- `<project>.view_compdoc`: liste, UUID detay, geçmiş, alan metadata'sı ve Excel export.
- `<project>.add_compdoc` + `<project>.change_compdoc`: manuel create/upsert ve Excel import.
- `<project>.change_compdoc`: mevcut kaydı güncelleme.
- `<project>.delete_compdoc`: tekil silme; toplu silme ayrıca `view_compdoc`, güncel kayıt
  sayısı ve proje adını içeren tam onay cümlesi gerektirir.

Production kullanıcı grupları oluşturulurken bu yetkiler proje bazında açıkça atanmalıdır.
Frontend kontrolleri yalnız kullanıcı deneyimi sağlar; aynı matris bütün API uçlarında yeniden
doğrulanır.

CompDoc -> DCC köprüsü için kullanıcıda hem `dcc.add_jira_dcc` hem seçilen projenin
`view_compdoc` yetkisi bulunmalıdır. DCC önizlemesi, idempotent replay ve confirmation anlarında
CompDoc yetkisi yeniden denetlenir. Seçili kayıtlar değişse bile üretilen belge kullanıcının açıkça
incelediği immutable history sürümlerini ve bunların SHA-256 fingerprint'ini taşır.

Onay sonrası ters izlenebilirlik kaydı job retention'dan bağımsız saklanır. CompDoc detayındaki DCC
geçmişini okumak için hem `dcc.view_jira_dcc` hem ilgili projenin `view_compdoc` yetkisi gerekir.
Kaynak sonradan değişirse kayıt “older source version” olarak görünür; Job Center bağlantısı ise
yalnız işi oluşturan kullanıcıya açılır. Preview veya süresi dolmuş onaysız işler kullanım audit'i
oluşturmaz.

DCC confirmation isteği, önizlemedeki `readiness_warning_codes` listesini
`acknowledged_warning_codes` alanında eksiksiz taşır. Warning yoksa boş liste gönderilir. Backend
yalnız güncel önizlemenin tam warning kümesini kabul eder; böylece UI kontrolünün atlanması veya eski
bir önizleme kararının yeni risklere uygulanması mümkün değildir. CompDoc bağlamak opsiyoneldir ve
tek başına skoru düşürmez; kaynak bağlandığında eksik teknik referanslar ve authority approval'a
ulaşmamış durumlar insan incelemesi gerektirir.

CompDoc önerileri yalnız ilgili proje modelinin `view_compdoc` yetkisi olan DCC sahibine gösterilir.
Skor; açık cover-page/teknik referans, ATA, panel adı ve anlamlı doküman adı terimlerini deterministik
ağırlıklarla birleştirir ve her eşleşmenin nedenini döndürür. Kullanıcı seçim yapmadıkça preview
girdisine CompDoc eklenmez. Seçim uygulandığında endpoint source preview'ın SHA-256 doğrulanmış özel
JSON girdisini kullanır; JIRA credential istemez veya JIRA'yı yeniden çağırmaz. Yeni preview başarıyla
oluşursa eski preview çift confirmation riskini önlemek için retry edilemez superseded duruma geçer.

Proje bazlı CompDoc route'ları registry ile etkin projeler için bağlanır: `ozgur`, `piku`, `aesa`, `havasoj`, `hys`, `blok30`.

Audit endpointleri:

- `GET /projects/import-audits/`
- `GET /projects/import-audits/<uuid>/`
- `GET /projects/import-audits/<uuid>/report/`

### 4. DOORS Araçları

Backend route kökü: `/doors/`
Frontend ekranları: `/app/doors/scripter`, `/app/doors/agent`, `/app/doors/poclinker`

Özellikler:

- Excel/structured data üzerinden DXL script üretimi.
- DOORS executable ile DXL çalıştırma.
- PoC linkleme iş akışı.
- DOORS Agent ekranı ile gereksinim modülü kontrol senaryoları için arayüz.

Endpointler:

- `POST /doors/script/`
- `POST /doors/run_dxl/`
- `GET /doors/test/`

> Not: DOORS entegrasyonu Windows/DOORS ortamı ve `DOORS_EXECUTABLE` değişkeni gerektirir. Bu özellik platform bağımlıdır.

### 5. DocProof Entegrasyonu

Backend route kökü: `/docproof/`

Özellikler:

- DocProof servisinde doküman arama.
- Entegrasyon bağlantı testi.

Endpointler:

- `GET /docproof/test/`
- `GET/POST /docproof/search/`

### 6. Excel Araçları

Backend route kökü: `/excel/`
Frontend ekranı: `/app/compare/excel`

Özellikler:

- Excel dosyalarının kolonlarını okuma.
- Excel karşılaştırma raporu üretme.
- Excel'den cover page üretim kuyruğu.
- Uzun süren Excel işlemleri için SSE progress stream.

Endpointler:

- `POST /excel/get_excel_columns/`
- `POST /excel/compare/`
- `POST /excel/jobs/cover-pages/`

### 7. Word Araçları

Backend route kökü: `/word/`
Frontend ekranları: `/app/compare/word`, `/app/translator`

Özellikler:

- Word doküman karşılaştırma.
- Açıklanabilir, kontrol listesi seçilebilir özel Word uyumluluk analizi.
- Yerel modelle buluta içerik göndermeyen Word çevirisi.
- Kalıcı Job Center üzerinden ilerleme, iptal, güvenli retry ve sahip-yetkili çıktı indirme.
- Başarılı Word çevirisi çıktısını SHA-256 ve hedef dosya politikası doğrulamasıyla, indirme/yükleme yapmadan açıklanabilir belge analizine devretme.
- Çeviri ve analizi tek komutla başlatan, adım durumlarını/audit izini koruyan, hata ve retry sonrasında aynı adımdan devam eden Workflow Accelerator recipe'si.
- Model/runtime hazırlığını dosya yolu veya belge içeriği göstermeden raporlayan Integration Hub kontrolü.

Endpointler:

- `POST /word/compare/`
- `POST /word/jobs/translate/`
- `POST /word/jobs/analyze/`
- `GET /jobs/<uuid>/`
- `GET /jobs/<uuid>/download/`
- `POST /jobs/<uuid>/handoffs/analyze-translated-document/`
- `GET /jobs/workflows/recipes/`
- `GET/POST /jobs/workflows/`
- `GET /jobs/workflows/<uuid>/`
- `POST /jobs/workflows/<uuid>/cancel/`

### 8. PDF Araçları

Backend route kökü: `/pdf/`
Frontend ekranları: `/app/pdf/split`, `/app/compare/pdf`

Özellikler:

- PDF dosyasını parçalara ayırıp ZIP olarak indirme.
- PDF dosyalarını karşılaştırma.

Endpointler:

- `POST /pdf/split_pdf_zip/`
- `POST /pdf/compare/`

### 9. Outlook ve ECR İş Akışları

Backend route kökü: `/outlook/`
Frontend ekranları: `/app/outlook`, `/app/task/ecr`

Özellikler:

- Outlook `.msg` dosyasını ham HTML çalıştırmadan, boyutu sınırlı plain-text içerikle inceleme.
- Yüksek entropili, 30 dakikalık ve mesajı ayrıştıran kullanıcıya bağlı ek indirme linkleri.
- Inline/base64 ek gövdesi yerine authenticated Blob indirme.
- `.msg` içindeki tek `.docx` ekini OOXML güvenlik kontrolünden geçirip kalıcı Job Center çıktısı olarak çıkarma.
- Outlook mesajı → Word eki çıkarma → açıklanabilir analiz Workflow Accelerator recipe'si.
- Sıfır veya birden fazla Word eki için sessiz seçim yerine kararlı hata kodu ve düzeltme yönlendirmesi.
- ECR task ekranı.
- ECR upload popup bileşenleri.

Endpointler:

- `POST /outlook/msg/parse/`
- `GET /outlook/msg/download/`
- `POST /outlook/jobs/extract-word-attachment/`
- `POST /jobs/<uuid>/handoffs/analyze-outlook-word-attachment/`

### 10. PowerPoint Gallery

Backend route kökü: `/pptxgallery/`
Frontend ekranı: `/app/pptxGallery`

Özellikler:

- Sunum kayıtlarını yönetme.
- Slayt kayıtlarını yönetme.
- PPT/PPTX yükleme.
- Slayt görselleri ve carousel/list görünümleri.
- LibreOffice (`SOFFICE_BIN`) ve Poppler (`PDFTOPPM_BIN`) gibi dış araçlarla dönüştürme.

Endpoint grupları:

- `/pptxgallery/presentations/`
- `/pptxgallery/slides/`

### 11. Media Converter

Backend route kökü: `/media-tools/`
Frontend ekranı: `/app/media-converter`

Özellikler:

- Görüntü, ses ve video format dönüştürme.
- FFmpeg komutlarının shell kullanılmadan güvenli argüman listesiyle çalıştırılması.
- Dosya uzantısı allowlist kontrolü.
- Upload boyutu ve işlem timeout sınırları.
- Çıktı boyutu önizleme.
- Video/audio bitrate presetleri ve özel bitrate girişi.

Endpointler:

- `POST /media-tools/preview/`
- `POST /media-tools/convert/`

### 12. Organizasyon Yönetimi

Backend route kökü: `/orgs/`
Frontend ekranı: `/app/organization`

Özellikler:

- Proje kayıtları.
- Panel kayıtları.
- Responsible kayıtları.
- People kayıtları.
- Excel ile kişi yükleme.
- Proje slug alanının project registry ile hizalanması.

Endpoint grupları:

- `/orgs/projects/`
- `/orgs/panels/`
- `/orgs/responsibles/`
- `/orgs/people/`
- `/orgs/upload_people/`

### 13. Kullanıcı, Auth ve Preferences

Backend route kökü: `/auth/`
Frontend ekranları: `/app/login`, `/app/invite`, `/app/users`, `/app/profile`, `/app/settings`

Özellikler:

- Token tabanlı login.
- HttpOnly auth cookie.
- CSRF token cookie ve unsafe method'lar için `X-CSRFToken` gönderimi.
- Logout sırasında server token silme ve cookie temizleme.
- Stale cookie recovery.
- `/auth/me/` ile oturum bootstrap.
- Kullanıcı CRUD.
- E-postaya bağlı, 24 saatlik ve tek kullanımlık yönetici davetleri.
- Davet durumlarını arama/filtreleme ve aktif daveti atomik iptal etme.
- Yetki listesi.
- Parola değiştirme.
- Parola sıfırlama request/confirm akışı.
- Kullanıcı tercihleri ve extra settings.
- Theme tercihi ve frontend theme bootstrap.

Endpointler:

- `POST /auth/token/`
- `POST /auth/logout/`
- `GET /auth/me/`
- `GET /auth/permissions/`
- `GET/POST /auth/users/`
- `GET/PUT/DELETE /auth/users/<id>/`
- `GET/POST /auth/invitations/`
- `DELETE /auth/invitations/<id>/`
- `POST /auth/invitations/inspect/`
- `POST /auth/invitations/accept/`
- `POST /auth/change_password/`
- `GET/PUT /auth/preferences/`
- `POST /auth/preferences/reset/`
- `GET/POST /auth/preferences/extra/`
- `GET/PUT/DELETE /auth/preferences/extra/<key>/`
- `POST /auth/password-reset/`
- `POST /auth/password-reset/confirm/`

### 14. Release Notes

Backend route kökü: `/releases/`

Özellikler:

- Kullanıcıya gösterilmemiş release note kayıtlarını çekme.
- Tekil release note'u görüldü işaretleme.
- Toplu görüldü işaretleme.
- Onay gerektiren notları ack ile onaylama.

Endpointler:

- `GET /releases/release-notes/unseen`
- `POST /releases/release-notes/<id>/seen`
- `POST /releases/release-notes/bulk-seen`
- `POST /releases/release-notes/<id>/ack`

### 15. Core SPA ve Dosya İndirme

Özellikler:

- `/` isteğini `/app/` SPA arayüzüne yönlendirme.
- `/app/*` altında Vue uygulamasını döndürme.
- `/download/<filename>/` ile üretilmiş dosya indirme.
- `DEBUG=True` iken media dosyalarını Django üzerinden servis etme.

---

## Proje Registry ve Proje Bazlı Uygulamalar

AW Center, teknik proje uygulama metadata'sını `backend/projects/registry.py` içinde merkezi ve read-only bir registry olarak tutar. Business-facing proje kayıtları ise `orgs.Project` tablosundadır. Bu iki katman arasındaki ortak anahtar `slug` alanıdır.

Registry'de tanımlı projeler:

| Slug | Görünen Ad | Durum | Kabiliyetler | JIRA Component |
|---|---|---:|---|---|
| `ozgur` | Ozgur | Aktif | `dcc`, `compdocs`, `orgs` | `OZGUR` |
| `piku` | Piku | Aktif | `dcc`, `compdocs`, `orgs` | `PIKU` |
| `aesa` | AESA | Aktif | `dcc`, `compdocs`, `orgs` | `AESA` |
| `havasoj` | Havasoj | Aktif | `dcc`, `compdocs`, `orgs` | `HAVASOJ` |
| `hys` | HYS | Aktif | `dcc`, `compdocs`, `orgs` | `HYS` |
| `blok30` | Blok 30 | Aktif | `dcc`, `compdocs`, `orgs` | `BLOK30` |
| `blok4050` | Blok 40/50 | Pasif | `dcc`, `compdocs`, `orgs` | `BLOK4050` |
| `gokbey` | Gokbey | Pasif | `dcc`, `compdocs`, `orgs` | `GOKBEY` |

Kurallar:

- Aktif registry projelerinin `orgs.Project.slug` değerleriyle hizalı olması gerekir.
- Pasif registry projeleri otomatik route üretmez.
- Registry API yalnızca frontend için güvenli alanları döndürür; internal import path, template adı, JIRA metadata veya dosya yolu sızdırmaz.
- Yeni capability eklemek backend allowlist, API contract, frontend type ve menü davranışında koordineli değişiklik gerektirir.

Doğrulama komutları:

```bash
cd backend
python manage.py check_project_registry
python manage.py sync_projects --dry-run
python manage.py sync_projects
```

---

## Launcher: Kurulum, Çalıştırma ve Doğrulama

Kök dizindeki `launcher.py`, Django backend ve Vue frontend'i repository
yapısından keşfeden sade komut yüzeyidir. AW Center adına, sabit settings
paketine veya kalıcı launcher state'ine bağlı değildir.

### Neden Launcher Var?

- Backend ve frontend komutlarını tek yerde standartlaştırır.
- `manage.py`, Vue içeren `package.json`, lockfile ve npm scriptlerini keşfeder.
- Shell açmadan argument vector ile süreç çalıştırır.
- `.env` veya `.env.local` dosyası yazmaz; `.runtime`/PID state'i tutmaz.
- Development için host/port ve `VITE_API_URL` yalnız child process environment'ına verilir.
- Port çakışmasında sessizce başka porta geçmez.
- Online/offline kurulum ve güvenli ZIP paketleme akışlarını aynı arayüzde tutar.

### Gereksinimler

- Python **3.11+**.
- Node.js ve npm.
- Backend için `requirements.txt`.
- Frontend için `frontend/package-lock.json` bulunduğundan launcher `npm ci` kullanır.

### Komut Özeti

| Komut | Amaç |
|---|---|
| `setup` | Backend ve frontend bağımlılıklarını online veya offline kaynaktan kurar. |
| `check` | Django migration/system kontrolleri ile mevcut frontend format/typecheck scriptlerini çalıştırır. |
| `test` | Repository'nin backend ve frontend test komutlarını çalıştırır. |
| `dev` | Django ve Vue development serverlarını foreground child process olarak çalıştırır. |
| `prod` | Frontend build, deployment check ve collectstatic sonrası WSGI serverını çalıştırır. |
| `prepare-offline` | Python wheel'larını indirir ve npm cache'i ısıtır. |
| `package-offline` | Offline kurulum için gerekli proje dosyalarını ve paketleri ZIP'e koyar. |
| `package-changes` | Git değişikliklerini ZIP olarak paketler. |

### En Sık Kullanılan Akışlar

İlk kurulum ve doğrulama:

```bash
python launcher.py setup
python launcher.py check
```

Sadece kontroller:

```bash
python launcher.py check
```

Backend ve frontend geliştirme sunucularını başlatma:

```bash
python launcher.py dev
```

Port seçerek çalıştırma:

```bash
python launcher.py dev --host 127.0.0.1 --backend-port 8000 --frontend-port 5173
```

Production profiliyle çalıştırma:

```bash
python launcher.py prod --host 0.0.0.0 --backend-port 8000
```

`prod`, Unix sistemlerde `manage.py` içinden WSGI import'unu keşfedip Gunicorn
çalıştırır. Windows veya özel server kullanımı için `--production-command`
verilebilir. Migration varsayılan olarak yalnız kontrol edilir; uygulamak için
`--migrate` açıkça verilmelidir. TLS, secret ve deployment environment ayarları
launcher tarafından üretilmez.

Backend kapsamında `jobs/management/commands/run_job_worker.py` bulunduğunda
launcher, `dev` ve `prod` modlarında kalıcı job worker'ını web süreciyle birlikte
başlatır ve denetler. `--skip-backend` kullanıldığında worker da başlatılmaz.

Sadece backend:

```bash
python launcher.py setup --skip-frontend
python launcher.py check --skip-frontend
python launcher.py dev --skip-frontend
```

Sadece frontend:

```bash
python launcher.py setup --skip-backend
python launcher.py check --skip-backend
python launcher.py dev --skip-backend
```

### Offline Hazırlık ve Kurulum

İnternet erişimi olan makinede offline paketleri hazırla:

```bash
python launcher.py prepare-offline --offline-dir offline
```

Offline taşınabilir ZIP üret:

```bash
python launcher.py package-offline --offline-dir offline --offline-zip aw-center-offline.zip
```

Offline makinede kur:

```bash
python launcher.py setup --mode offline --offline-dir offline
```

Offline modda backend kurulumu şu şekilde yapılır:

```bash
pip install --no-index --find-links offline/wheels -r requirements.txt
```

Frontend kurulumu şu mantığı kullanır:

```bash
npm ci --offline --cache offline/npm-cache
```

### Migration ve Environment Sözleşmesi

`check`, migration üretmez veya uygulamaz. `dev` ve `prod` da varsayılan olarak
veritabanını değiştirmez; yalnız açık `--migrate` parametresi migration uygular.
Launcher `.env` okumaz/yazmaz. Django projesinin mevcut dotenv/settings davranışı
ve shell environment'ı aynen korunur.

### Launcher Seçenekleri

| Seçenek | Açıklama |
|---|---|
| `--root <path>` | Otomatik keşif yerine proje kökünü açıkça seçer. |
| `--mode online|offline` | `setup` paket kaynağını seçer. |
| `--offline-dir <path>` | Offline wheel/cache dizini. Varsayılan `offline`. |
| `--offline-zip <path>` | `package-offline` çıktısı. |
| `--changes-zip <path>` | `package-changes` çıktısı. |
| `--skip-frontend` | Frontend adımlarını atlar. |
| `--skip-backend` | Backend adımlarını atlar. |
| `--migrate` | `dev`/`prod` başlamadan önce migration uygular. |
| `--host <host>` | Server bind host'u. Varsayılan `127.0.0.1`. |
| `--backend-port <port>` | Tercih edilen Django portu. Varsayılan `8000`. |
| `--frontend-port <port>` | Tercih edilen Vite portu. Varsayılan `5173`. |
| `--no-backend-reload` | Django autoreload kapatılır. |
| `--ignore-packages` | Paket ilişkili operasyonları paketleme senaryolarında atlamak için kullanılır. |
| `--production-command <argv>` | Özel WSGI server komutu seçer. |

### Launcher Trade-off'ları

- Offline npm kurulumu cache'in eksiksiz olmasına bağlıdır. Eksik tarball/metadata varsa online makinede `prepare-offline` tekrar çalıştırılmalıdır.
- `package-offline` yalnız Git tarafından izlenen kaynakları alır; taşınması gereken
  untracked kaynaklar önce bilinçli olarak Git kapsamına eklenmelidir.
- Launcher production secret/TLS üretmez; bunlar deployment platformu tarafından yönetilmelidir.

---

## Environment Değişkenleri

Backend `.env` dosyası `backend/.env` konumundan okunur. Gerçek secret, token, parola, sertifika veya production endpoint bilgileri commit edilmemelidir.

### Minimum Local Development Örneği

```env
DEBUG=True
SECRET_KEY=aw-center-local-development-secret-key-change-before-production-2026
IPV4_ADDRESS=127.0.0.1
PORT=8000
DOCPROOF_URL=http://localhost/docproof
DOORS_EXECUTABLE=doors
JIRA_LEGACY_URL=http://localhost/jira-legacy
JIRA_BTB_URL=http://localhost/jira
JIRA_DEFAULT_PROJECT_KEY=CHN
AW_USERNAME=
AW_PASSWORD=
ALLOWED_HOSTS=127.0.0.1,localhost
DEV_FRONTEND_PORT=5173
DEV_SERVER_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000
AUTH_COOKIE_SAMESITE=Lax
AUTH_COOKIE_SECURE=False
AUTH_TOKEN_RESPONSE_ENABLED=True
FFMPEG_EXECUTABLE=ffmpeg
```

### Backend Değişkenleri

| Değişken | Zorunluluk / Varsayılan | Açıklama |
|---|---|---|
| `SECRET_KEY` | `DEBUG=False` iken zorunlu; `DEBUG=True` iken dev fallback var | Django secret key. Production'da güçlü ve gizli olmalı. |
| `DEBUG` | Varsayılan `False` | Debug modu, CORS davranışı ve güvenlik ayarlarını belirler. |
| `IPV4_ADDRESS` | Zorunlu | Allowed hosts varsayılanı, reset URL ve Cheroot bind host için kullanılır. |
| `PORT` | Zorunlu integer | Reset URL ve Cheroot bind port için kullanılır. |
| `DOCPROOF_URL` | Zorunlu | DocProof entegrasyon base URL'i. |
| `DOORS_EXECUTABLE` | Zorunlu | DOORS executable path'i. |
| `DOORS_DATABASE` | Varsayılan boş | Opsiyonel DOORS `port@host` database seçimi. |
| `DOORS_OLE_PROG_ID` | Varsayılan `DOORS.Application` | Windows OLE automation program ID. |
| `DOORS_AUTO_START_CLIENT` | Varsayılan `False` | Aktif istemci yoksa DOORS'u açıkça başlatır. |
| `DOORS_STARTUP_TIMEOUT_SECONDS` / `DOORS_RUN_TIMEOUT_SECONDS` | `30` / `120` | OLE başlangıç ve DXL çalışma sınırları. |
| `DOORS_MAX_RESULT_BYTES` | Varsayılan `10485760` | DXL result dosyasının maksimum boyutu. |
| `TEAMCENTER_BASE_URL` | Entegrasyon için zorunlu | Teamcenter web-tier context root'u. |
| `TEAMCENTER_SERVICE_ROOT` | Varsayılan `RestServices` | `RestServices` veya deployment sözleşmesi. |
| `TEAMCENTER_AUTH_MODE` | Varsayılan `password` | Server-side `password` veya `cookie` authentication. |
| `TEAMCENTER_USERNAME` / `TEAMCENTER_PASSWORD` | Password mode için zorunlu | Secret manager'da tutulacak servis hesabı. |
| `TEAMCENTER_JSESSIONID` / `TEAMCENTER_XSRF_TOKEN` | Cookie mode için | Aynı Teamcenter session'a ait server-side secret'lar. |
| `TEAMCENTER_VERIFY_SSL` | Varsayılan `true` | Boolean veya internal CA bundle path'i; production'da kapatılamaz. |
| `TEAMCENTER_CONNECT_TIMEOUT_SECONDS` / `TEAMCENTER_READ_TIMEOUT_SECONDS` | `10` / `60` | Bounded HTTP timeout değerleri. |
| `TEAMCENTER_MAX_READ_RETRIES` | Varsayılan `2` | Yalnızca idempotent read çağrılarının retry sayısı. |
| `TEAMCENTER_MAX_RESPONSE_BYTES` | Varsayılan `10485760` | Stream edilen Teamcenter response boyut sınırı. |
| `JIRA_LEGACY_URL` | Zorunlu | Legacy JIRA URL'i. |
| `JIRA_BTB_URL` | Zorunlu | Ana JIRA URL'i. |
| `JIRA_DEFAULT_PROJECT_KEY` | `CHN` | Analizden üretilen yeni issue taslaklarının düzenlenebilir başlangıç projesi. |
| `JIRA_DRAFT_PUBLISH_STALE_SECONDS` | `300` (minimum etkin değer `60`) | Kesilmiş bir yayın rezervasyonunun marker ile güvenli kurtarmaya açılacağı süre. |
| `AW_USERNAME` | Varsayılan boş | DocProof/DOORS gibi entegrasyonlarda kullanılır; hassas kabul edilmelidir. |
| `AW_PASSWORD` | Varsayılan boş | DocProof/DOORS gibi entegrasyonlarda kullanılır; hassas kabul edilmelidir. |
| `FFMPEG_EXECUTABLE` | Varsayılan `ffmpeg` | Media Converter için FFmpeg binary adı/path'i. |
| `AWCENTER_MAX_DOCUMENT_UPLOAD_BYTES` | 50 MiB | PDF ve Office dokümanları için endpoint boyut sınırı. |
| `AWCENTER_MAX_IMAGE_UPLOAD_BYTES` | 10 MiB | Slide görseli yükleme sınırı. |
| `AWCENTER_MAX_ATTACHMENT_UPLOAD_BYTES` | 100 MiB | JIRA gibi köprülere gönderilen ek dosya sınırı. |
| `OUTLOOK_MAX_ATTACHMENTS` | `100` | Tek Outlook mesajında ayrıştırılabilecek maksimum ek sayısı. |
| `OUTLOOK_PARSE_RATE` | `60/hour` | Kullanıcı başına senkron `.msg` önizleme/cache oluşturma hız sınırı. |
| `AWCENTER_MAX_MEDIA_UPLOAD_BYTES` | 500 MiB | FFmpeg media input sınırı. |
| `AWCENTER_ABSOLUTE_MAX_UPLOAD_BYTES` | 600 MiB | Multipart stream işlenirken uygulanan deployment-wide acil durdurma sınırı. |
| `AWCENTER_MAX_ARCHIVE_EXPANDED_BYTES` | 250 MiB | OOXML/ZIP içeriğinin toplam açılmış boyut sınırı. |
| `AWCENTER_MAX_ARCHIVE_ENTRIES` | 5000 | OOXML/ZIP içindeki maksimum entry sayısı. |
| `AWCENTER_MAX_COMPDOC_IMPORT_ROWS` | 10000 | Tek CompDoc Excel importunda işlenecek maksimum veri satırı. |
| `COMPDOC_IMPORT_PREVIEW_TTL_SECONDS` | `900` | İmzalı CompDoc Excel önizleme onayının geçerlilik süresi. |
| `DATABASE_URL` | Varsayılan `backend/db.sqlite3` | Primary database URL'i. Production için PostgreSQL önerilir. |
| `DB_OLD_URL` | Varsayılan `backend/db_old.sqlite3` | Legacy database bağlantısı. |
| `DATABASE_CONN_MAX_AGE` | Varsayılan `60` | Persistent database connection süresi. |
| `CACHE_URL` | Varsayılan local memory cache | Redis gibi production cache backend URL'i. |
| `PRIVATE_MEDIA_ROOT` | Varsayılan `backend/private_media` | Job input/output artifact'larının public media servisinden ayrılmış özel storage kökü. |
| `LOG_LEVEL` | Varsayılan `INFO` | Django ve uygulama console log seviyesi. |
| `FRONTEND_DIST_DIR` | Varsayılan `frontend/dist` | Django'nun SPA shell ve Vite asset çıktısını aradığı dizin. |
| `FRONTEND_RESET_URL` | Ortama göre hesaplanır | Parola reset linklerinde kullanılan frontend login URL'i. |
| `FRONTEND_INVITATION_URL` | Ortama göre hesaplanır | Tek kullanımlık kullanıcı davetlerinin public kayıt ekranı; ham token URL fragment'ına eklenir. |
| `TRUSTED_PROXY_COUNT` | Varsayılan `0` | Rate-limit istemci kimliği için güvenilen ters proxy sayısı; doğrudan bağlantıda `0`, tek Nginx katmanında `1`. |
| `ALLOWED_HOSTS` | `IPV4_ADDRESS`, `127.0.0.1`, `localhost`; `DEBUG=True` iken `ALLOW_ALL_DEBUG_HOSTS=True` ile `*` | Django host doğrulaması. Dev ortamında wildcard yalnızca Bad Request üreten local/LAN host farklılıklarını engellemek için açıktır. |
| `ALLOW_ALL_DEBUG_HOSTS` | `DEBUG=True`: `True` | Sadece local geliştirmede Django `DisallowedHost` kaynaklı Bad Request hatalarını önler. Production için etkisiz tutulmalıdır. |
| `DEV_FRONTEND_PORT` | Varsayılan `5173` | Debug modunda Vite origin varsayılanlarını üretir. |
| `DEV_SERVER_ORIGINS` | Debug modunda localhost/127.0.0.1 frontend ve backend originleri | Debug CORS ve CSRF trusted origin listelerinin ortak kaynağıdır. |
| `CORS_ALLOWED_ORIGINS` | `DEBUG=False` iken zorunlu | Production CORS origin allowlist. |
| `CORS_ALLOWED_ORIGIN_REGEXES` | Debug modunda localhost/127.0.0.1 port regexleri | Port değiştiğinde local Vite/Django CORS preflight isteklerini ayrıca env yazmadan karşılar. |
| `CSRF_TRUSTED_ORIGINS` | Debug modunda `DEV_SERVER_ORIGINS`; production varsayılan boş | Cross-site POST/PUT/PATCH/DELETE için trusted origin listesi. |
| `SECURE_SSL_REDIRECT` | `DEBUG=True`: `False`, `DEBUG=False`: `True` | HTTP isteklerini HTTPS'e yönlendirir. TLS proxy arkasında topolojiye göre ayarlanmalıdır. |
| `USE_X_FORWARDED_HOST` | `DEBUG=False` iken varsayılan `True` | Reverse proxy host header'ını kullanır. |
| `AUTH_COOKIE_NAME` | Varsayılan `auth_token` | DRF token cookie adı. |
| `AUTH_COOKIE_MAX_AGE` | Varsayılan 14 gün | Auth cookie ömrü, saniye cinsinden. |
| `AUTH_COOKIE_SAMESITE` | `DEBUG=True`: `Lax`, `DEBUG=False`: `None` | Browser cookie SameSite politikası. |
| `AUTH_COOKIE_SECURE` | `DEBUG=True`: `False`, `DEBUG=False`: `True` | Auth cookie için Secure bayrağı. |
| `SESSION_COOKIE_SECURE` | `DEBUG=True`: `False`, `DEBUG=False`: `True` | Session cookie için Secure bayrağı. |
| `CSRF_COOKIE_SECURE` | `DEBUG=True`: `False`, `DEBUG=False`: `True` | CSRF cookie için Secure bayrağı. |
| `AUTH_TOKEN_RESPONSE_ENABLED` | Varsayılan `DEBUG` | Local fallback için token'ın response body'de dönülmesine izin verir. Production'da kapalı kalmalıdır. |
| `SECURE_HSTS_SECONDS` | `DEBUG=True`: `0`, `DEBUG=False`: `31536000` | HSTS süresi. |
| `SOFFICE_BIN` | Varsayılan `soffice` | PPT/PDF dönüşümünde LibreOffice binary. |
| `PDFTOPPM_BIN` | Varsayılan `pdftoppm` | Poppler PDF-to-image binary. |
| `PPTX_CONVERSION_TIMEOUT_SECONDS` | Varsayılan `180` | LibreOffice ve Poppler komutları için ayrı ayrı uygulanan timeout. |
| `WORD_TRANSLATION_TR_EN_MODEL` / `WORD_TRANSLATION_EN_TR_MODEL` | `backend/models/...` | Cloud'a içerik göndermeyen iki yerel Word çeviri modelinin dizinleri. |
| `WORD_ANALYZER_BI_MODEL` / `WORD_ANALYZER_CROSS_MODEL` | `backend/models/...` | Açıklanabilir uyumluluk analizi için yerel bi-encoder ve cross-encoder model dizinleri. |
| `WORD_ANALYZER_MAX_UNITS` | `10000` | Tek bir analiz işinde indekslenebilecek maksimum paragraf/tablo semantik birimi. |
| `COVER_PAGE_TEMPLATE_PATH` | `backend/custom_templates/cover_page_template.docx` | Varsa kullanılan güvenilir DocxTemplate; yoksa yerleşik güvenli cover-page düzeni kullanılır. |
| `COVER_PAGE_MAX_ROWS` | `1000` | Tek bir cover-page job'ında işlenebilecek maksimum workbook satırı. |
| `INTEGRATION_PROBE_CONNECT_TIMEOUT_SECONDS` / `INTEGRATION_PROBE_READ_TIMEOUT_SECONDS` | `2` / `3` | Integration Hub dış servis erişilebilirlik timeout'ları. |
| `INTEGRATION_PROBE_CACHE_SECONDS` | `30` | Canlı health sonucunun cache süresi. |
| `INTEGRATION_PROBE_REFRESH_COOLDOWN_SECONDS` | `5` | Aynı kullanıcının forced refresh çağrıları arasındaki minimum süre. |
| `INTEGRATION_PROBE_FAILURE_THRESHOLD` | `3` | Circuit breaker açılmadan önceki ardışık başarısızlık sayısı. |
| `INTEGRATION_PROBE_FAILURE_WINDOW_SECONDS` | `300` | Probe başarısızlık sayacının yaşam süresi. |
| `INTEGRATION_PROBE_CIRCUIT_COOLDOWN_SECONDS` | `120` | Açık circuit'in dış çağrıları durdurduğu süre. |
| `JOB_LEASE_SECONDS` | `60` | Worker kesintisini algılamak için job lease süresi. |
| `JOB_HEARTBEAT_SECONDS` | `2` | Uzun çalışan executor'ların iptal ve lease kontrol aralığı. |
| `JOB_WORKER_STALE_SECONDS` | `10` | Job Center'da worker'ın çevrimdışı sayılacağı heartbeat yaşı. |
| `JOB_EXECUTION_TIMEOUT_SECONDS` | `900` | Bir job executor için mutlak çalışma sınırı. |
| `JOB_MAX_OUTPUT_BYTES` | `1 GiB` | Worker tarafından kalıcı storage'a alınabilecek maksimum tekil çıktı boyutu. |
| `JOB_ARTIFACT_RETENTION_DAYS` | `30` | Terminal job kayıtları ve özel artifact'ların saklama süresi. |
| `DCC_PREVIEW_TTL_SECONDS` | `900` | Dry-render edilmiş özel DCC snapshot'ının onaylanabileceği süre; 60 saniye ile 24 saat arasında sınırlandırılır. |

### Frontend Değişkenleri

| Değişken | Açıklama |
|---|---|
| `VITE_API_URL` | Axios base URL. Launcher tarafından otomatik yazılır. |
| `VITE_API_TIMEOUT_MS` | Axios request timeout değeri. Varsayılan 10000 ms. |
| `VITE_API_BASE_URL` | Launcher'ın compatibility için yazdığı backend URL adı. |
| `VITE_BACKEND_URL` | Launcher'ın compatibility için yazdığı backend URL adı. |
| `VITE_SERVER_URL` | Launcher'ın compatibility için yazdığı backend URL adı. |
| `VITE_JIRA_SERVER` | Frontend JIRA linkleri için gösterim URL'i; yoksa fallback kullanılır. |
| `VITE_VERSION` | Main view'de sürüm gösterimi. |
| `VITE_APP_TITLE` | Home ekranı başlığı. |
| `VITE_SHOW_DELAYED_COMPDOCS` | CompDoc gecikme göstergeleri için production-safe Vite değişken adı. |

Boolean Vite değişkenleri merkezi parser üzerinden değerlendirilir; `false`, `0`, `no` ve `off` metinleri kapalı kabul edilir. Böylece environment string değerleri yanlışlıkla bir özelliği etkinleştirmez.

### Production Cookie/CORS Önerileri

Aynı site deployment:

```env
AUTH_COOKIE_SAMESITE=Lax
AUTH_COOKIE_SECURE=True
```

Cross-site SPA/API deployment:

```env
AUTH_COOKIE_SAMESITE=None
AUTH_COOKIE_SECURE=True
CORS_ALLOWED_ORIGINS=https://frontend.example.com
CSRF_TRUSTED_ORIGINS=https://frontend.example.com
```

> `SameSite=None` cookie'leri modern browser'larda `Secure=True` olmadan kabul edilmez. Cross-site senaryolarda HTTPS zorunlu kabul edilmelidir.

---

## Geliştirme Komutları

### Backend

```bash
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
npm run format:check
npm run test:ci
npm run typecheck
npm run build
```

Repository kökündeki bağımlılıksız private npm manifesti aynı komutları
`frontend/` manifestine yönlendirir; böylece yanlış dizinde çalıştırılan `npm run build`,
`typecheck`, `format:check` ve `test:ci` farklı veya gevşetilmiş bir kalite yolu kullanmaz.

### Alternatif Starter

`launcher.py` ana önerilen yüzeydir. Daha küçük starter hâlen mevcuttur:

```bash
python scripts/starter.py check
python scripts/starter.py install
python scripts/starter.py check-backend
python scripts/starter.py start
```

Starter; `.venv` oluşturma, bağımlılık kurma, local `backend/.env` üretme ve Django/Vite süreçlerini birlikte başlatma gibi temel geliştirme işlerini yapar.

---

## Test ve Kalite Kapıları

Önerilen minimum kontroller:

```bash
python launcher.py check
```

Launcher `check` şunları çalıştırır:

- Backend Django system check.
- `makemigrations --check --dry-run` ile eksik migration kontrolü.
- `migrate --check` ile uygulanmamış migration kontrolü.
- Frontend Prettier check.
- Frontend Vue/TypeScript check.

Daha kapsamlı doğrulama:

```bash
cd backend
python manage.py test

cd ../frontend
npm run build
```

CI workflow'u `.github/workflows/ci.yml` altında gerçek strict TypeScript, salt-okunur format kontrolü, migration drift, backend/frontend testleri, dependency audit, Django SPA/static artefakt smoke testi ve birleşik runtime image build kapılarını uygular.

---

## Teamcenter ve DOORS Entegrasyonları

Teamcenter ve IBM Rational DOORS istemcileri AW Center backend'ine gömülü adapter katmanları olarak entegredir. Frontend menüsündeki `Teamcenter` ve `DOORS > Agent` ekranları yalnızca sunucuda yapılandırılmış hesap/oturumları kullanır; tarayıcıdan Teamcenter parolası, `JSESSIONID`, XSRF token veya DOORS kimlik bilgisi alınmaz.

`/app/integrations` ekranı ve authenticated `GET /integrations/` endpoint'i tüm köprüleri tek secretsız katalogda gösterir. Kullanıcı tarafından başlatılan `?probe=true` kontrolü dış servislerde credential göndermeyen kısa `HEAD` erişilebilirlik ölçümleri, yerel araçlarda process başlatmayan executable/package kontrolleri yapar. Kontroller paralel, cache'li, kullanıcı başına refresh-limitli ve ardışık hatalarda circuit-breaker korumalıdır; internal URL, credential veya ham exception metni response'a eklenmez.

Teamcenter için `TEAMCENTER_BASE_URL`, authentication mode ve ilgili server-side secret'ları `.env`/secret manager üzerinden tanımlayın. Production'da HTTPS ve TLS doğrulaması zorunludur. Okuma endpoint'leri authenticated kullanıcılara; property update endpoint'i yalnızca admin kullanıcılara açıktır. İstekler timeout, sınırlı read retry ve maksimum response boyutu ile çalışır.

DOORS OLE entegrasyonu Windows, `pywin32` ve oturum açılmış bir DOORS desktop client gerektirir. Varsayılan davranış aktif istemciye bağlanmaktır; `DOORS_AUTO_START_CLIENT=False` güvenli varsayılan olarak korunur. Açılması gerekiyorsa executable ve opsiyonel database yalnızca subprocess argüman listesiyle aktarılır. Object listeleme 1000 kayıtla, DXL sonuç dosyası da yapılandırılabilir byte limitiyle sınırlandırılmıştır. Object create/update endpoint'leri yalnızca admin kullanıcılar içindir.

Başlıca API yüzeyleri:

- Teamcenter: `/teamcenter/status/`, `/teamcenter/probe/`, `/teamcenter/saved-queries/`, `/teamcenter/objects/load/`, `/teamcenter/objects/properties/`.
- DOORS: `/doors/status/`, `/doors/modules/check/`, `/doors/objects/`, `/doors/objects/detail/`.

Tüm environment anahtarlarının secrets içermeyen örnekleri [`.env.example`](.env.example) içinde bulunur.

### API hata ve kurtarma sözleşmesi

API hata cevapları aşağıdaki ortak alanları taşır:

```json
{
  "detail": "The uploaded file is too large.",
  "code": "UPLOAD_TOO_LARGE",
  "retryable": false,
  "recovery_hint": "Reduce the file size or split it into smaller inputs.",
  "request_id": "support-reference"
}
```

`retryable`, istemcinin aynı işlemi yeniden denemesinin anlamlı olup olmadığını; `recovery_hint`, kullanıcıya gösterilecek secretsız sonraki adımı belirtir. `request_id` backend log korelasyonu içindir ve destek talebine eklenmelidir. Field validation hataları ayrıca `errors` alanını kullanır. Frontend bütün standart hataları merkezi olarak biçimlendirir; domain bileşenlerinde doğrudan `response.data` ayrıştırılmamalıdır.

---

## Güvenlik Notları

- `.env`, SQLite database, media upload, node_modules, build artifact, sertifika ve private key dosyaları commit edilmemelidir.
- `AW_USERNAME`, `AW_PASSWORD`, DRF token, `auth_token` cookie ve JIRA/DocProof credential değerleri secret kabul edilmelidir.
- Global DRF permission `IsAuthenticated` olduğu için public endpoint açarken `AllowAny` bilinçli ve testli kullanılmalıdır.
- Frontend route/menu filtreleri savunma ve kullanıcı deneyimi katmanıdır; gerçek yetkilendirme kararı her zaman backend endpoint permission sınıflarında uygulanmalıdır.
- Login sonrası dönüş yalnız `/app/` içindeki normalize edilmiş yolları kabul eder; dış URL, protocol-relative URL, kontrol karakteri ve auth döngüsü oluşturabilecek hedefler reddedilir.
- Cookie-backed token auth unsafe method'lar için CSRF kontrolü uygular.
- Production'da `DEBUG=False`, güçlü `SECRET_KEY`, explicit `CORS_ALLOWED_ORIGINS` ve doğru `CSRF_TRUSTED_ORIGINS` kullanılmalıdır.
- File upload endpointlerinde dosya türü, boyut, path traversal ve temporary file cleanup riskleri dikkate alınmalıdır.
- DOORS, LibreOffice, Poppler ve FFmpeg gibi dış binary entegrasyonlarında shell fragment kullanılmamalı; argüman listesiyle çalıştırma korunmalıdır.
- `AUTH_TOKEN_RESPONSE_ENABLED=True` production için önerilmez; HttpOnly cookie-only model daha güvenlidir.

---

## Deployment Temelleri

Repository aşağıdaki deployment yapı taşlarını içerir:

- `backend/Dockerfile`: Vite artefaktını ayrı Node aşamasında üreten, Django/WhiteNoise statiklerini image içinde toplayan ve Gunicorn çalıştıran birleşik immutable runtime.
- `frontend/Dockerfile`: Gerektiğinde CDN veya bağımsız statik servis için kullanılabilecek opsiyonel Vite + Nginx image temeli.
- `docker-compose.yml`: Aynı-origin backend/SPA, worker, PostgreSQL ve Redis içeren local production-like orchestration.
- `.env.example`: Production environment sözleşmesi için secrets içermeyen örnek.
- `deploy/nginx/awcenter.conf`: TLS terminasyonu önündeki reverse proxy için başlangıç Nginx örneği.
- `.github/workflows/ci.yml`: Backend/frontend check, build, audit, integrated artifact smoke ve runtime image adımları.
- `docs/deployment.md`: Deployment detayları.

Önemli deployment kararları:

- Mevcut Django settings local varsayılan olarak SQLite kullanır; production `DATABASE_URL` ile PostgreSQL'e geçirilmelidir.
- Frontend build çıktısı backend image içindeki `/app/frontend-dist` konumuna immutable olarak kopyalanır; image build, SPA shell ve toplanmış `/core/assets/...` dosyalarını Django üzerinden doğrulamadan tamamlanmaz.
- Production secret yönetimi environment/secret manager üzerinden yapılmalıdır.
- HTTPS, HSTS, secure cookie ve CORS/CSRF listeleri deployment topolojisine göre doğrulanmalıdır.

### Production İlk Kurulum Akışı

```bash
docker compose build
docker compose run --rm backend python manage.py migrate --noinput
docker compose up -d
curl -fsS http://localhost:8080/health/ready/
curl -fsS http://localhost:8080/app/
```

`docker-compose.yml` içindeki örnek secret ve parolalar sadece local doğrulama içindir. Production'da bunlar secret manager veya platform environment ayarlarıyla değiştirilmelidir.

---

## Sık Karşılaşılan Sorunlar

### `SECRET_KEY must be defined when DEBUG is False`

`DEBUG=False` ise `SECRET_KEY` zorunludur. Local development için `DEBUG=True` kullanın veya `.env` içine güçlü bir `SECRET_KEY` ekleyin.

### Backend check `.env` değişkenleri yüzünden başlamıyor

`IPV4_ADDRESS`, `PORT`, `DOCPROOF_URL`, `DOORS_EXECUTABLE`, `JIRA_LEGACY_URL`, `JIRA_BTB_URL` zorunlu okunur. Launcher env dosyası üretmez. Local yapılandırmayı açıkça oluşturup gözden geçirin:

```bash
cp .env.example backend/.env
python launcher.py check --skip-frontend
```

### Login sonrası auth cookie gönderilmiyor

- Local HTTP geliştirmede `AUTH_COOKIE_SAMESITE=Lax` ve `AUTH_COOKIE_SECURE=False` kullanın.
- Cross-site HTTPS deployment'ta `AUTH_COOKIE_SAMESITE=None`, `AUTH_COOKIE_SECURE=True`, `CORS_ALLOWED_ORIGINS` ve `CSRF_TRUSTED_ORIGINS` değerlerini birlikte ayarlayın.

### Frontend API çağrıları yanlış backend'e gidiyor

`dev`, seçilen backend adresini Vite child process'ine `VITE_API_URL` olarak
geçici verir. Ayrı bir frontend süreci çalıştırıyorsanız aynı değeri shell
environment'ında açıkça tanımlayın:

```bash
VITE_API_URL=http://127.0.0.1:8000 npm --prefix frontend run dev
```

### DOORS işlemleri çalışmıyor

Backend Windows üzerinde çalışmalı, `pywin32` kurulu olmalı ve varsayılan akışta kullanıcı DOORS desktop client'a giriş yapmış olmalıdır. `DOORS_EXECUTABLE`, `DOORS_OLE_PROG_ID` ve gerekiyorsa `DOORS_DATABASE` değerlerini doğrulayın.

### Teamcenter bağlantısı çalışmıyor

`TEAMCENTER_BASE_URL` web-tier context root'u göstermeli (örneğin `https://host/tc`), `TEAMCENTER_SERVICE_ROOT` deployment ile eşleşmeli ve seçilen authentication mode için server-side secret'lar tanımlanmalıdır. Internal CA kullanılıyorsa `TEAMCENTER_VERIFY_SSL` değerini CA bundle path'i olarak ayarlayın; production'da TLS doğrulamasını kapatmayın.

### PPTX/PDF preview çalışmıyor

`SOFFICE_BIN` ve `PDFTOPPM_BIN` binary'lerinin sistemde kurulu ve PATH üzerinden erişilebilir olduğunu doğrulayın.

### Media Converter çalışmıyor

`FFMPEG_EXECUTABLE` doğru binary'yi göstermelidir. FFmpeg kurulu değilse media convert endpointleri başarısız olur.

### Offline kurulum npm cache hatası veriyor

Offline cache eksiktir. İnternetli ortamda tekrar çalıştırın:

```bash
python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline
```

---

## Referans Dokümanlar

- `docs/architecture-review.md`
- `docs/production-readiness-report.md`
- `docs/deployment.md`
- `docs/devops-review.md`
- `docs/code-quality-review.md`
- `docs/testing-strategy.md`
- `docs/refactoring-plan.md`
- `docs/enterprise-roadmap.md`
