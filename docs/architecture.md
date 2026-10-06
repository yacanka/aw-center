# AW Center hedef mimarisi

Bu belge mevcut production contract'ın canonical açıklamasıdır. Tarihsel review ve refactoring snapshot'ları karar kaynağı değildir.

## Mimari hedef

AW Center tek deployable Django/Vue uygulamasıdır. Modüler monolith sınırları
korunur; ayrı process gerektiren işler launcher-owned worker lifecycle'larına
ayrılır. Güncel production aynı Windows cihaz ve kullanıcı oturumunda
`launcher.py prod`, doğrudan TLS ve ayrı SQLite state'iyle çalışır. Windows'a
bağımlı DOORS işleri aynı genel worker tarafından yürütülür. Linux container,
PostgreSQL ve Redis sonraki olgunluk aşamasıdır.

Temel ilkeler:

- Bir business aggregate'in tek model ve davranış sahibi vardır.
- Project scope URL, database relation ve authorization policy'de açıkça taşınır.
- HTTP request process'i uzun süren işi çalıştırmaz; durable job oluşturur.
- Feature executor'ları job kernel'ine import edilmez; composition root static catalog'dan çözer.
- Browser ve machine identity aynı authentication kanalını paylaşmaz.
- Private artifact hiçbir static veya unauthenticated file route'undan sunulmaz.
- Production release source'u değiştirilmez; runtime state repository dışında,
  sürümden bağımsız ve açıkça yapılandırılmış dizinlerdedir.

## Runtime topolojisi

```text
Windows browser
    │ HTTPS, same-origin session + CSRF
    ▼
launcher.py prod
    ├── Uvicorn/Django :443 ── /app, /api, /health
    ├── SQLite ─────────────── business state, audit, jobs, leases
    ├── file cache ─────────── process-shared ephemeral state
    ├── general job worker ─── local + isteğe bağlı DOORS queue
    ├── notification worker
    ├── cleanup worker
    ├── collected static ───── built Vue artifact
    └── private media ──────── owner-scoped input/output artifact
```

Uvicorn yalnız launcher'a açıkça verilen static IPv4 adresine bind edilir. TLS
certificate/private key repository dışında tutulur; certificate seçilen IPv4'ü
SAN olarak taşımalıdır. `/media/` public static route değildir. Gelecekteki
container ingress'i `/internal/` ve `/media/` yollarını ayrıca kapalı tutar.

Process sınırı yalnız command ayrımı değildir; secret ve filesystem capability'si de daraltılır:

| Lifecycle | Ek environment | Erişim |
|---|---|---|
| `backend` | Browser/API integration ayarları | SQLite, private artifact `rw`, AI/DOCX `ro` |
| `worker` | Local executor ve isteğe bağlı DOORS ayarları | SQLite, private artifact `rw`, AI/DOCX `ro` |
| `notification-worker` | Mail transport | SQLite |
| `cleanup-worker` | Retention ayarı | SQLite, private artifact `rw` |

Güncel Windows profilinde process'ler aynı production env dosyasını okur; uygulama
seviyesindeki sorumluluk sınırları yine korunur. Tek DOORS-capable worker dosya
kilidiyle zorlanır. SQLite yerel NTFS üzerinde, repository/OneDrive/network share
dışında ve `CONN_MAX_AGE=0` ile kullanılır. Repository dışındaki file cache geçici
JIRA session state'ini web ve worker arasında paylaşır. Başlangıç kontrolleri ve
JIRA oturum işlemleri aynı cache politikasını uygular: Windows-native production
repository dışında mutlak bir file cache dizini, container production Redis
gerektirir. Production JIRA credential'ı explicit Fernet anahtarıyla şifrelenir;
owner scope, TTL ve logout temizliği her iki profilde de korunur.
Container profilinde secret ve volume
capability'leri process başına daha dar biçimde ayrılmaya devam edecektir.

## Backend sınırları

| Modül | Sorumluluk | Bağımlılık kuralı |
|---|---|---|
| `awcenter` | Composition root, settings, root URLs, health, logging, API/file security | Feature business logic'i barındırmaz |
| `compliance` | Canonical Compliance Document aggregate, import, lifecycle, review, audit, notification | Project'e FK ile scope edilir; project app'i yoktur |
| `projects` | Read-only teknik project registry ve küçük policy strategy'leri | Business project satırı veya role sahibi değildir |
| `orgs` | `Project`, organizasyon verisi ve project-scoped role assignment | Registry slug'ıyla hizalanır |
| `jobs` | Durable job/workflow state, leases, fencing, private artifact lifecycle | Feature package import etmez |
| `automations` | Executor metadata catalog ve workflow use-case'leri | Generic workflow/event framework değildir |
| `attention` | Kullanıcının action/decision görünümü | Domain aggregate'lerini sahiplenmez |
| `integrations` | Vendor transport/session adapterları ile DOORS, Teamcenter ve DocProof HTTP/use-case yüzeyleri | Credential response/log üretmez; vendor başına kök Django app oluşturmaz |
| `dcc`, tools | Domain HTTP adapterı, validation ve executor | Kernel'e ters bağımlılık oluşturmaz |
| `users` | Browser session, users, invitations, preferences ve password-reset outbox | SMTP web process'ine verilmez |

`backend/awcenter/test_architecture.py`, production import graph'ini, jobs kernel bağımsızlığını, kaldırılmış runtime package'larını, browser auth sınırını ve canonical URL yüzeyini fitness function olarak kilitler.

### Merkezi AI ve asistan sınırı

`integrations.ai` immutable mesaj/configuration/policy sözleşmeleri, stateless
`complete_text`/`complete_json` ve bounded HTTPS transport'u içerir. Bağımlılık yönü
feature → client → transport'tur; çekirdek Django request, kullanıcı/project,
assessment, assistant veya job modüllerini import etmez. Prompt, domain şeması ve
yetki çağıran feature'da kalır. `integrations.assessment` mevcut DDF/Watcher çağrı
ve hata sözleşmesini bu client'a uyarlar; ayrı konuşmalar arasında history veya
mutable HTTP session paylaşılmaz.

`integrations.assistant` salt okunur yetkili rehber kataloğu, bounded bağlam,
prompt, sonuç doğrulaması ve authenticated catalog/chat endpoint'lerini sahiplenir.
Model yalnız o request'in yetkili kimliklerini önerebilir; backend bunları
canonical route kartlarına çözer. Yanıt düz metindir, model URL/kod/callable
çalıştırılmaz. Asistan gerçek belge/iş kayıtlarına erişmez ve iş başlatmaz.
Configuration durumunu gösteren `ai-chat` Integration Hub girdisi canlı probe
yapmaz; yerel `ai` toolkit'inden ayrıdır. Aile seçimi, API limitleri ve yeni
tüketici/rehber ekleme akışı [ai-assistant.md](ai-assistant.md) içindedir.

## Project ve compliance aggregate'i

Teknik project metadata'sı `projects.registry.PROJECT_DEFINITIONS` içindedir. Her definition `slug`, capability'ler ve güvenli server-side handler/template referanslarını taşır. `orgs.Project` business karşılığıdır; fresh migration canonical satırları seed eder. API yalnız registry'de bulunan, enabled ve kullanıcı rolüyle erişilebilen project'leri döndürür.

Compliance kayıtları tek `compliance.ComplianceDocument` tablosundadır ve `project` foreign key'i taşır. Cover page, workflow event, review, tracking, notification policy/log ve import audit aynı aggregate çevresindeki canonical modellerdir. Proje farkı schema/model kopyasıyla değil, gerekirse `projects/policies/` altındaki küçük ve testli strategy ile uygulanır.

Compliance Excel ve DOORS importları ortak önizleme/onay akışında organizasyon panel kataloğunu da günceller. Anahtar proje + normalize ATA chapter'dır: mevcut ATA'nın panel adı güncellenir, yeni ATA için panel adı ve ATA birlikte gerekir. Aynı ATA için kabul edilen belge satırları arasındaki son dolu panel adı kazanır; reddedilen satırlar kataloğa etki etmez. Mevcut kayıt tek alanla kesin eşleşiyorsa kullanılabilir. Panel kimliği, discipline ve sorumlu atamaları korunur; ad değişikliği aynı paneli kullanan diğer belgelere de yansır.

Önizleme salt okunurdur; `panel_changes` alanı ATA, eski/yeni ad ve işlemi gösterir. Panel durumu confirmation fingerprint'e dahildir ve onayda panel/belge değişiklikleri tek transaction'da uygulanır. Bu sınırlı katalog güncellemesi mevcut compliance editor import yetkisinin parçasıdır; doğrudan organizasyon düzenleme ve bağımsız panel importu için organization manager gerekliliği değişmez.

Project URL scope'u açıktır:

```text
/api/projects/<project_slug>/organization/
/api/projects/<project_slug>/compliance-documents/
```

Authorization her request'te URL project'i, object project'i ve `ProjectRoleAssignment` rolünü birlikte doğrular. Registry'deki internal handler/template metadata'sı browser project catalog'una açılmaz.

## Durable job ve automation composition'ı

`jobs` aşağıdaki çekirdek sözleşmelere sahiptir:

- owner-scoped job ve immutable event geçmişi;
- idempotency key + input SHA-256 eşitliği;
- queued → running claim için row lock;
- her claim'de benzersiz execution token ve süreli lease;
- ayrı heartbeat ile lease renewal;
- cancellation intent ve monotonic progress;
- terminal state ve output publish için token-fenced compare-and-set;
- expired lease recovery ve yeni token;
- private output + yetkili download + retention.

Executor metadata'sının tek kaynağı `automations.catalog.EXECUTOR_CATALOG`'dur.
Her kayıt `kind`, dotted callable path, `queue`, upload policy ve timeout içerir.
Normal worker `local` allowlist'ini; development ve Windows production'da DOORS
etkinse varsayılan olarak ayrıca `doors` allowlist'ini composition root üzerinden
çözer. Her iki runtime'daki `--exclude-doors` açık opt-out'tur.
Böylece job kernel feature koduna, feature kodu da worker implementation'ına bağlanmaz.

Workflow/handoff servisleri workflow-agnostic `jobs.persistence` primitive'lerini kullanır. Import graph'ta `services ↔ workflow_services ↔ handoffs` cycle'ı yoktur.

### ECR workflow

ECR feature sözleşmesi owner-scoped `GET/POST /api/workflows/ecr/` collection ve `GET /api/workflows/ecr/<uuid>/` detail yüzeyidir. `Idempotency-Key` isteyen create, bounded PDF'yi private source ve immutable review snapshot'ına dönüştürür. Review sonucu aynı endpoint'te örtülü değiştirilmez; `POST .../approve/` ve `POST .../reject/` güncel optimistic `version` ile ayrı transition'lardır.

`POST .../publish/` ve `POST .../resume/` yeni attempt için kullanıcının ephemeral JIRA session'ını ve `Idempotency-Key` header'ını zorunlu tutar; credential job payload/database'e kopyalanmaz. Approved version, project set ve owner server-owned `automations.publish_ecr_jira` job'una fence edilir. Provider sonucu belirsizse aggregate ve job `reconciliation_required` durumuna geçer; otomatik retry yoktur. Provider marker/state doğrulandıktan sonra yalnız explicit, yeni idempotent resume attempt'i ilerler. Frontend'in canonical route'u `/app/task/ecr`'dir; client-owned orchestration veya legacy/compatibility route bulunmaz.

### JIRA subtask ve Watcher reminder

Subtask Creator'ın manual ve Excel girişleri `/api/dcc/subtasks/` altında birleşir. HTTP katmanı parent issue, project capability, DCC operator rolü ve canlı/sanitize edilmiş JIRA create metadata'sını doğrular; Excel yalnız bounded ilk sheet'ten credential-free JSON plana normalize edilir. `dcc.create_jira_subtasks` local durable job'ı her satır için owner/idempotency tabanlı marker arar, yalnız eksik kaydı oluşturur. Provider sonucu belirsizse job `reconciliation_required` olur ve aynı marker planını koruyan explicit resume gerekir.

Watcher reminder endpoint'i owner/assignee scope'undaki DCC kaydını, optimistic `version` değerini ve operator rolünü doğrular. Açık JIRA subtasks'tan bounded ve doğrulanmış e-posta listesi çıkarılır; adresler API response'una yazılmaz. Web process'i SMTP çağrısı yapmaz. `DccReminderDelivery` outbox'ı notification worker tarafından row lease, retry ve stable `Message-ID` ile teslim edilir; aynı kayıt için yeni gönderim bir saatlik cooldown'a tabidir.

Ortak mail adapter'ında `EMAIL_TIMEOUT` varsayılan 10 saniyelik socket bekleme sınırıdır; değer pozitif, en fazla 30 saniye ve notification lease'inden kısa olmalıdır. Bu sınır DNS çözümlemesi veya tüm SMTP konuşması için toplam süre garantisi değildir. Worker her kuyrukta mevcut batch sayısı sınırını koruyarak kayıtları gönderimden hemen önce tek tek claim eder; sırada bekleyen kayıtların lease'i tüketilmez. Her kayıt aynı turda en fazla bir kez denenir; lease/retry süresi tur içinde dolsa da yeniden seçilmez. Timeout `MAIL_DELIVERY_TIMEOUT` ile mevcut retry akışına girer; Message-ID ve password-reset link'i korunur. Süresi dolmuş veya değişmiş lease ile gönderim başlatılmaz ve terminal sonuç yazılmaz. SMTP kabulünden sonra bağlantı kaybolursa retry yineleme riski taşır; stable Message-ID tam olarak bir kez teslim garantisi vermez.

## Authentication ve authorization

Browser sözleşmesi:

- Django server-side session cookie `HttpOnly`'dir.
- `GET /api/session/` anonymous/authenticated state'i verir ve CSRF cookie hazırlar.
- Login/logout unsafe method olduğu için CSRF korumalıdır.
- DRF default authentication `SessionAuthentication`, permission `IsAuthenticated`'dır.
- Frontend tüm istekleri merkezi `apiClient` ile `withCredentials` kullanarak gönderir; unsafe method'da `csrftoken` → `X-CSRFToken` ekler.
- Route guard protected route'tan önce session bootstrap eder; public olmayan route fail-closed authenticated kabul edilir.
- Project capability/role görünürlüğü backend project catalog'undan gelir; frontend yalnız UX katmanıdır, backend authorization otoritedir.

Password-reset request'i public response'ta account existence ayrımı yapmadan bir `PasswordResetDelivery` outbox kaydı oluşturur. Web process'i mail secret'ı taşımaz. Notification worker row lease ile claim eder, account-state fingerprint'ini yeniden doğrular ve deterministic Message-ID/stable token timestamp ile gönderir. Raw reset token'ı saklanmaz. Yalnız aktif lease terminal state yayımlayabilir; dış mail transport'unda sonucu belirsiz kalan tekrar aynı Message-ID ve token timestamp'iyle yürür. Reset capability'si query yerine URL fragment'ında taşınır ve login shell belleğe aldıktan hemen sonra `history.replaceState` ile adres çubuğu/history'den temizlenir.

Güncel Windows profilinde DOORS general worker doğrudan SQLite job kuyruğunu ve
private artifact dizinini kullanır; browser request process'i COM çalıştırmaz.

## API ve hata yüzeyi

Beklenmeyen API hatasının JSON log'u `api.unhandled_exception`, request ID ve exception türüne ek olarak yalnız en iç frame'in modül, fonksiyon ve satırını `exception_location` içinde taşır. Worker'ın `error_type`/`failure_stage` ve bildirim kimlikleri allowlist üzerinden korunur; ham exception mesajı, traceback kaynak metni, local değişkenler, payload ve filesystem yolu eklenmez. Browser'a dönen `INTERNAL_ERROR` yanıtı genel kalır.

Release note `bulk-seen` girdisi en fazla 1.000 pozitif signed64 integer ID kabul eder; boyut kontrolü child doğrulamasından önce yapılır. Oluşturma ve ön okuma aynı transaction içindedir; sıralı `get_or_create` sayesinde aynı kullanıcı/not çifti eşzamanlı çağrılarda tek kayıt oluşturur. `created`, yalnız o isteğin gerçekten eklediği kayıt sayısıdır; boş liste, tekrarlar ve aktif olmayan/bulunmayan ID'ler sayıyı artırmaz. İstemci uzun okunmamış listelerini 1.000'lik gruplar halinde gönderir.

Canonical root surface:

- `/api/session/`, `/api/users/`
- `/api/projects/` ve project-scoped organization/compliance
- `/api/attention/`, `/api/dcc/`, `/api/jobs/`, `/api/workflows/` ve `/api/workflows/ecr/`
- `/api/integrations/...`, `/api/tools/...`, `/api/releases/`
- `/app/`, `/health/live/`, `/health/ready/`, `/admin/`

API error'ları `awcenter.api_errors` ile `{ detail, code, ... }` biçimindedir; request correlation middleware `X-Request-ID`/`request_id` üretir. Structured JSON log yalnız bounded operational alanları içerir. Cookie, authorization, payload, private path ve upstream secret loglanmaz.

## File, static ve private artifact sınırı

Upload request'i önce absolute body limitinden, sonra domain `UploadPolicy` ad/uzantı/boyut/imza/arşiv kontrollerinden geçer. Dosya adı veya client MIME tek başına güven kaynağı değildir.

Runtime verileri dört ayrı sınıfta tutulur:

1. `frontend/dist`: release öncesi üretilen Vue artifact.
2. Collected static: `%LOCALAPPDATA%\AWCenter\static` altında yeniden üretilebilir state.
3. AI ağırlıkları: `%LOCALAPPDATA%\AWCenter\assets\<set>\ai-models` altında read-only kullanım.
4. Operator-managed DOCX şablonları: aynı asset set içindeki `document-templates` dizini.
5. Job input/output: `%LOCALAPPDATA%\AWCenter\private-media` altında owner-scoped ve hash'li state.

Private media static olarak servis edilmez. Private download, authenticated owner
authorization kontrolü ve stored SHA-256 doğrulamasıyla Django üzerinden akar.

Job silme sinyali input/output storage ve adlarını sabitler; dosyaları ilgili
database bağlantısının başarılı commit'inden sonra siler. Rollback/savepoint
rollback sırasında dosyalar korunur. Geçici filesystem hatası diğer artifact'ın
silinmesini durdurmaz; güvenli log kaydı bırakılır. Cleanup worker eski ve artık
referans edilmeyen input dosyalarını da tarayarak başarısız veya process kapanması
nedeniyle kaçırılmış temizliği tekrar dener. Retention dış transaction içinde
çağrıldığında orphan taraması da commit sonrasına ertelenir; deferred tarama
sayıları senkron `CleanupResult` içinde sıfırdır.
Backend, worker ve cleanup aynı açıkça yapılandırılmış dizini görür.

Cache-backed Outlook MSG attachment'ları ayrı fakat aynı ilkeye bağlı bir private transferdir: parse response'u `download_url` açığa çıkarmaz; 48 karakterlik owner-bound capability yalnız authenticated `POST /api/tools/outlook/msg/download/` body içinde kullanılır. Capability kısa ömürlü ve tek kullanımlıktır; backend cache'lenmiş byte'ların SHA-256 değerini indirme response'undan önce yeniden hesaplar.

Payload yalnız cache kaydını başarıyla silen çağrıya döner. Windows file cache'inde
silme ve integration probe `add` işlemleri process'ler arası işletim sistemi
kilidiyle korunur; kilit en fazla iki saniye beklenir, alınamazsa işlem reddedilir.
Kilit dosyaları `CACHE_DIRECTORY/.operation-locks/` altında en fazla 256 sabit
stripe kullanır ve capability içermez. `cache.clear()` bu dosyaları korur;
çalışan process'ler varken kilit dizinini silmeyin. Process kapanınca işletim
sistemi kilidi bırakır; payload süresi ve temizliği Django cache tarafından yönetilir.

## Frontend sınırları

- `frontend/src/app/`: bootstrap, lazy router, protected/public layout ve navigation composition'ı.
- `frontend/src/shared/`: tek HTTP/CSRF client'ı, canonical API URL/error/download sözleşmeleri ve küçük UI primitive'leri.
- `frontend/src/features/<feature>/api/`: feature'ın typed request/response sınırı.
- `frontend/src/features/<feature>/composables/`: route controller'ları ile form/query/list state'i.
- `features/session/stores/session.ts`, `features/projects/stores/projectCatalog.ts` ve credential içermeyen JIRA connection store'u: yalnız uygulama ömürlü state.
- `features/assistant/stores/assistant.ts`: session-scoped, yalnız bellekte bounded sohbet ve yetkili katalog; protected shell paneli ilk açılışta lazy yükler.

Asistanın konuşması route değişimi ve panel kapatma/açmada korunur. Yeni sohbet,
logout, kimlik değişimi ve session expiry abort/generation fence ile bekleyen
sonucun yeni oturuma yazılmasını engeller; local/session storage veya database
konuşma deposu yoktur. Frontend exact registered internal route kontrolü backend
yetkisinin yerine geçmez. Panel ortak NConfigProvider/useThemeVars ve mevcut
session/CSRF client'ını kullanır.

CompDoc, organization, user administration, DDF, presentation, Outlook ve DOORS ekran state'i route-local controller/API'lere aittir. Pinia fitness allowlist'i yeni route store'u eklenmesini engeller.

View/component'ler doğrudan Axios import etmez, global store locator kullanmaz ve credential'ı Web Storage'a yazmaz. Fitness testleri bu sınırları tarar.

## Deployment ve migration ilkeleri

Güncel production Windows'ta versioned release checkout'undan `launcher.py prod`
ile çalışır. Database ayrı production SQLite dosyasıdır; development database'iyle
paylaşılmaz. Project seed migration'ın parçasıdır. Frontend ayrı Vite server olarak
çalışmaz; build edilmiş artifact Django/WhiteNoise üzerinden sunulur.

Release geçişinde web ve worker process'leri birlikte durdurulur; SQLite ile private
media aynı bakım penceresinde birlikte yedeklenir. Yeni release için dependency ve
frontend build hazırlanır, `launcher.py prod --migrate` bir kez çalıştırılır. Write
alındıktan sonra eski schema'ya dönmek yerine corrective migration ile forward-fix
uygulanır.

Docker/Compose profili gelecekteki hedef olarak korunur. O profilde production
PostgreSQL 17, authenticated Redis 7, immutable digest-pinned image ve Nginx kullanır.
Aşağıdaki zincir yalnız bu gelecek profil içindir:

Release kimliği aşağıdaki doğrulanabilir zincirdir:

```text
review edilmiş commit
  → schema-2 source/frontend SHA-256 manifest + dependency SBOM
  → BuildKit resolved image digest
  → manifest-hash + image içindeki frontend tree doğrulaması
  → repository@sha256:<digest> production reference
```

Environment preflight mutable tag, placeholder secret, geçersiz PostgreSQL/Redis/runtime path contract'ı ve tutarsız database password'ünü reddeder. Ayrıca güvenilir CI kaynağından operatorun verdiği release manifest ile image verification kaydını release, commit, manifest digest, frontend tree/count ve `AWCENTER_IMAGE` digest'i üzerinden eşleştirir. Preflight evidence imzası veya registry trust otoritesi değildir; evidence provenance ve repository dışında erişim kontrollü saklama operator sorumluluğudur.

Container environment preflight'i mutable tag, placeholder secret, geçersiz
PostgreSQL/Redis/runtime path contract'ı ve tutarsız database password'ünü reddeder;
bu kontroller bugünkü Windows env dosyasının yerine geçmez. Ayrıntılı güncel akış
[deployment.md](deployment.md), disposable local reset ise
[local-database-reset.md](local-database-reset.md) içindedir.

## Bilinçli non-goals

- Microservice extraction
- Generic event bus veya plugin framework
- Project başına Django app/model
- Browser için ikinci authentication mekanizması
- Unauthenticated artifact server
- Güncel Windows SQLite production'ını yatay ölçeklemek
- Agent'ın PostgreSQL veya Redis'e doğrudan bağlanması
