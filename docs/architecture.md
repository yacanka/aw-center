# AW Center hedef mimarisi

Bu belge mevcut production contract'ın canonical açıklamasıdır. Tarihsel review ve refactoring snapshot'ları karar kaynağı değildir.

## Mimari hedef

AW Center tek deployable Django/Vue uygulamasıdır. Modüler monolith sınırları korunur; ayrı process gerektiren işler aynı image'dan çalışan worker lifecycle'larına ayrılır. Production ortamı Linux container, PostgreSQL ve Redis'tir. Windows'a bağımlı DOORS otomasyonu ana uygulamanın dışında, yalnız outbound HTTPS kullanan mTLS agent ile çalışır.

Temel ilkeler:

- Bir business aggregate'in tek model ve davranış sahibi vardır.
- Project scope URL, database relation ve authorization policy'de açıkça taşınır.
- HTTP request process'i uzun süren işi çalıştırmaz; durable job oluşturur.
- Feature executor'ları job kernel'ine import edilmez; composition root static catalog'dan çözer.
- Browser ve machine identity aynı authentication kanalını paylaşmaz.
- Private artifact hiçbir static veya unauthenticated file route'undan sunulmaz.
- Production source/image immutable, runtime state açık volume veya dış servistedir.

## Runtime topolojisi

```text
Internet/browser
    │ HTTPS, same-origin session + CSRF
    ▼
Nginx ingress :443
    │ /app, /api, /health
    ▼
Django/Gunicorn backend
    ├── PostgreSQL 17 ── business state, audit, jobs, leases
    ├── Redis 7 ──────── shared cache, probes, one-use capabilities
    ├── frontend-dist ── image içindeki immutable Vue artifact
    └── private volume ─ owner-scoped input/output artifact

Same image, ayrı lifecycle
    ├── durable job worker
    ├── password-reset + compliance notification worker
    └── retention cleanup worker

Windows DOORS agent
    │ outbound HTTPS + client certificate
    ▼
Dedicated mTLS ingress :8443
    │ yalnız /internal/bridge/v1/
    └── Django bridge API
```

Ana ingress `/internal/bridge/` ve `/media/` yollarını 404 ile kapatır. Bridge ingress yalnız internal bridge path'ini proxy eder. Backend doğrudan host portuna publish edilmez.

Process sınırı yalnız command ayrımı değildir; secret ve filesystem capability'si de daraltılır:

| Lifecycle | Ek environment | Writable/read-only mount |
|---|---|---|
| `backend` | Browser/API integration ayarları | private artifact `rw`, model `ro` |
| `worker` | Yalnız local executor'ların JIRA/Teamcenter ayarları | private artifact `rw`, model `ro` |
| `notification-worker` | Yalnız mail transport | Ek volume yok |
| `cleanup-worker` | Yalnız retention ayarı | private artifact `rw` |
| `windows-bridge-ingress` | Yalnız bridge enable gate'i ve hostname | Nginx config ve mTLS dosyaları `ro` |

Tüm Django lifecycle'ları aynı image ve minimum ortak database/cache/runtime ayarlarını kullanır; tablodaki capability'ler bunun üstündeki farklardır. Bunlar numeric non-root UID/GID ile, tüm Linux capability'leri drop edilmiş ve `no-new-privileges` altında çalışır. Bir lifecycle'a başka capability'nin credential veya volume'unu vermek desteklenen trust boundary'yi genişletir. Windows poller bu topolojinin servisi değildir; repository dışında versionlanan ve Windows üzerinde ayrıca supervise edilen outbound agent'tır.

## Backend sınırları

| Modül | Sorumluluk | Bağımlılık kuralı |
|---|---|---|
| `awcenter` | Composition root, settings, root URLs, health, logging, API/file security | Feature business logic'i barındırmaz |
| `compliance` | Canonical Compliance Document aggregate, import, lifecycle, review, audit, notification | Project'e FK ile scope edilir; project app'i yoktur |
| `projects` | Read-only teknik project registry ve küçük policy strategy'leri | Business project satırı veya role sahibi değildir |
| `orgs` | `Project`, organizasyon verisi ve project-scoped role assignment | Registry slug'ıyla hizalanır |
| `jobs` | Durable job/workflow state, leases, fencing, private artifact lifecycle | Feature package import etmez |
| `automations` | Executor metadata catalog ve Windows bridge protocol | Generic workflow/event framework değildir |
| `attention` | Kullanıcının action/decision görünümü | Domain aggregate'lerini sahiplenmez |
| `integrations` | Vendor transport/session adapterları ile DOORS, Teamcenter ve DocProof HTTP/use-case yüzeyleri | Credential response/log üretmez; vendor başına kök Django app oluşturmaz |
| `dcc`, tools | Domain HTTP adapterı, validation ve executor | Kernel'e ters bağımlılık oluşturmaz |
| `users` | Browser session, users, invitations, preferences ve password-reset outbox | Machine bridge authentication'ına karışmaz; SMTP web process'ine verilmez |

`backend/awcenter/test_architecture.py`, production import graph'ini, jobs kernel bağımsızlığını, kaldırılmış runtime package'larını, browser auth sınırını ve canonical URL yüzeyini fitness function olarak kilitler.

## Project ve compliance aggregate'i

Teknik project metadata'sı `projects.registry.PROJECT_DEFINITIONS` içindedir. Her definition `slug`, capability'ler ve güvenli server-side handler/template referanslarını taşır. `orgs.Project` business karşılığıdır; fresh migration canonical satırları seed eder. API yalnız registry'de bulunan, enabled ve kullanıcı rolüyle erişilebilen project'leri döndürür.

Compliance kayıtları tek `compliance.ComplianceDocument` tablosundadır ve `project` foreign key'i taşır. Cover page, workflow event, review, tracking, notification policy/log ve import audit aynı aggregate çevresindeki canonical modellerdir. Proje farkı schema/model kopyasıyla değil, gerekirse `projects/policies/` altındaki küçük ve testli strategy ile uygulanır.

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

Executor metadata'sının tek kaynağı `automations.catalog.EXECUTOR_CATALOG`'dur. Her kayıt `kind`, dotted callable path, `queue`, upload policy ve timeout içerir. `awcenter.job_executors` yalnız `local` callable'ları composition root'ta resolve eder. Windows bridge yalnız `windows` allowlist'ini claim eder. Böylece job kernel feature koduna, feature kodu da worker implementation'ına bağlanmaz.

Workflow/handoff servisleri workflow-agnostic `jobs.persistence` primitive'lerini kullanır. Import graph'ta `services ↔ workflow_services ↔ handoffs` cycle'ı yoktur.

### ECR workflow

ECR feature sözleşmesi owner-scoped `GET/POST /api/workflows/ecr/` collection ve `GET /api/workflows/ecr/<uuid>/` detail yüzeyidir. `Idempotency-Key` isteyen create, bounded PDF'yi private source ve immutable review snapshot'ına dönüştürür. Review sonucu aynı endpoint'te örtülü değiştirilmez; `POST .../approve/` ve `POST .../reject/` güncel optimistic `version` ile ayrı transition'lardır.

`POST .../publish/` ve `POST .../resume/` yeni attempt için kullanıcının ephemeral JIRA session'ını ve `Idempotency-Key` header'ını zorunlu tutar; credential job payload/database'e kopyalanmaz. Approved version, project set ve owner server-owned `automations.publish_ecr_jira` job'una fence edilir. Provider sonucu belirsizse aggregate ve job `reconciliation_required` durumuna geçer; otomatik retry yoktur. Provider marker/state doğrulandıktan sonra yalnız explicit, yeni idempotent resume attempt'i ilerler. Frontend'in canonical route'u `/app/task/ecr`'dir; client-owned orchestration veya legacy/compatibility route bulunmaz.

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

Windows agent identity browser session'ından tamamen ayrıdır. Dedicated ingress client certificate'i doğrular; Django yalnız trusted proxy IP'den gelen escaped certificate'i parse edip SHA-256 fingerprint ve subject'i kendisi üretir.

## API ve hata yüzeyi

Canonical root surface:

- `/api/session/`, `/api/users/`
- `/api/projects/` ve project-scoped organization/compliance
- `/api/attention/`, `/api/dcc/`, `/api/jobs/`, `/api/workflows/` ve `/api/workflows/ecr/`
- `/api/integrations/...`, `/api/tools/...`, `/api/releases/`
- `/internal/bridge/v1/`
- `/app/`, `/health/live/`, `/health/ready/`, `/admin/`

API error'ları `awcenter.api_errors` ile `{ detail, code, ... }` biçimindedir; request correlation middleware `X-Request-ID`/`request_id` üretir. Structured JSON log yalnız bounded operational alanları içerir. Cookie, authorization, payload, certificate, private path ve upstream secret loglanmaz.

## File, static ve private artifact sınırı

Upload request'i önce absolute body limitinden, sonra domain `UploadPolicy` ad/uzantı/boyut/imza/arşiv kontrollerinden geçer. Dosya adı veya client MIME tek başına güven kaynağı değildir.

Üç farklı veri sınıfı vardır:

1. `frontend/dist` ve collected static: image build sırasında üretilen immutable artifact.
2. Model dizini: deployment tarafından `/app/models:ro` mount edilir.
3. Job input/output: `/app/private_media` shared volume'unda owner-scoped ve hash'li state.

Nginx `/media/` servis etmez. Private download, authenticated owner authorization kontrolü ve stored SHA-256 doğrulamasıyla Django üzerinden akar. Backend, worker ve cleanup aynı private volume'u görür.

Cache-backed Outlook MSG attachment'ları ayrı fakat aynı ilkeye bağlı bir private transferdir: parse response'u `download_url` açığa çıkarmaz; 48 karakterlik owner-bound capability yalnız authenticated `POST /api/tools/outlook/msg/download/` body içinde kullanılır. Capability kısa ömürlü ve tek kullanımlıktır; backend cache'lenmiş byte'ların SHA-256 değerini indirme response'undan önce yeniden hesaplar.

## Frontend sınırları

- `frontend/src/app/`: bootstrap, lazy router, protected/public layout ve navigation composition'ı.
- `frontend/src/shared/`: tek HTTP/CSRF client'ı, canonical API URL/error/download sözleşmeleri ve küçük UI primitive'leri.
- `frontend/src/features/<feature>/api/`: feature'ın typed request/response sınırı.
- `frontend/src/features/<feature>/composables/`: route controller'ları ile form/query/list state'i.
- `features/session/stores/session.ts`, `features/projects/stores/projectCatalog.ts` ve credential içermeyen JIRA connection store'u: yalnız uygulama ömürlü state.

CompDoc, organization, user administration, DDF, presentation, Outlook ve DOORS ekran state'i route-local controller/API'lere aittir. Pinia fitness allowlist'i yeni route store'u eklenmesini engeller.

View/component'ler doğrudan Axios import etmez, global store locator kullanmaz ve credential'ı Web Storage'a yazmaz. Fitness testleri bu sınırları tarar.

## Deployment ve migration ilkeleri

Production yalnız immutable combined image ile çalışır. Database schema fresh migration baseline'dan kurulur; project seed migration'ın parçasıdır. Production database contract'ı PostgreSQL'dir; source-mounted runtime, ayrı frontend server veya launcher-supervised web process desteklenmez.

Release kimliği aşağıdaki doğrulanabilir zincirdir:

```text
review edilmiş commit
  → schema-2 source/frontend SHA-256 manifest + dependency SBOM
  → BuildKit resolved image digest
  → manifest-hash + image içindeki frontend tree doğrulaması
  → repository@sha256:<digest> production reference
```

Environment preflight mutable tag, placeholder secret, geçersiz PostgreSQL/Redis/runtime path contract'ı ve tutarsız database password'ünü reddeder. Ayrıca güvenilir CI kaynağından operatorun verdiği release manifest ile image verification kaydını release, commit, manifest digest, frontend tree/count ve `AWCENTER_IMAGE` digest'i üzerinden eşleştirir. Preflight evidence imzası veya registry trust otoritesi değildir; evidence provenance ve repository dışında erişim kontrollü saklama operator sorumluluğudur.

Normal schema evolution yeni forward migration ile yapılır. Upgrade öncesi PostgreSQL ve private artifact state birlikte yedeklenir. Migration sonrası sorunlarda write alınmışsa eski schema'ya dönmek yerine corrective image/migration ile forward-fix yapılır. Ayrıntılı gate [deployment.md](deployment.md), local disposable reset [local-database-reset.md](local-database-reset.md) içindedir.

## Bilinçli non-goals

- Microservice extraction
- Generic event bus veya plugin framework
- Project başına Django app/model
- Browser için ikinci authentication mekanizması
- Unauthenticated artifact server
- Windows üzerinde ana backend/web supervisor
- Agent'ın PostgreSQL veya Redis'e doğrudan bağlanması
