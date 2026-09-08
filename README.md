# AW Center

AW Center; proje-scoped compliance document yönetimi, DCC/JIRA akışları, durable document işleri, engineering integration'ları ve Office/PDF araçlarını aynı Django + Vue uygulamasında birleştirir.

Güncel production hedefi aynı Windows kullanıcı oturumunda `launcher.py prod`, doğrudan same-origin HTTPS, ayrı SQLite/private-artifact state'i ve launcher-owned worker process'leridir. Windows-only DOORS otomasyonu aynı oturumdaki tek genel worker'da çalışır. Immutable Linux container, PostgreSQL 17 ve Redis 7 uygulamanın sonraki olgunluk aşaması olarak repository'de korunur.

## Hızlı başlangıç

Gereksinimler:

- CPython 3.11+
- Node.js 22 ve npm
- Local development için gerekli native document araçları; production image bunları içerir

```bash
cp backend/.env.example backend/.env
python launcher.py setup
python launcher.py check
python launcher.py dev --migrate
```

`backend/.env.example` local development için doğrudan çalışabilen, secret
içermeyen örnektir. Kopyalanan `backend/.env` Git tarafından yok sayılır;
makineye özel değerleri burada veya daha yüksek öncelikli process environment'da
verin. Tracked `.env.development` yalnız eski profil seçen kurulumlarla uyumluluk
için korunur ve credential içermemelidir. Windows production için
`backend/.env.production` dosyasını `%LOCALAPPDATA%\AWCenter\config\production.env`
konumuna kopyalayın ve gerçek değerleri yalnız bu ignored, checkout dışı dosyada
tutun. Repository kökündeki `.env.example` gelecekteki Compose profilidir.

Varsayılan adresler:

- Vue development server: `http://127.0.0.1:5173/app/`
- Django API: `http://127.0.0.1:8000/api/`
- Liveness: `http://127.0.0.1:8000/health/live/`
- Readiness: `http://127.0.0.1:8000/health/ready/`

`launcher.py dev`, Django, Vite, durable job worker, notification worker ve cleanup worker'ı foreground child process'ler olarak başlatır. `DOORS_ENABLED=True` ise durable worker development ve production'da varsayılan olarak DOORS queue'sunu da tüketir; bunu kapatmak için ilgili komuta `--exclude-doors` eklenir. Development migration'ı yalnız `launcher.py dev --migrate` ile uygulanır. `launcher.py prod` ise Windows'ta tek TLS-enabled Uvicorn process'i ve production worker lifecycle'larını başlatır.

Local yapay zekâ ağırlıkları kaynak koddan ayrı, Git tarafından yok sayılan
`.runtime/ai-models/` altında tutulur:

```text
.runtime/ai-models/
├── opus-mt-tr-en/
├── opus-mt-en-tr/
├── paraphrase-multilingual/
└── ms-marco-cross-encoder/
```

Operator tarafından sağlanan DOCX şablonları ağırlıklardan ayrı tutulur:

```text
.runtime/document-templates/
├── cover_page_template.docx
└── <project>_dcc_template.docx
```

Windows production aynı ayrımı `%LOCALAPPDATA%\AWCenter\assets\sets\<asset-set-id>\`
altındaki `ai-models` ve `document-templates` dizinleriyle korur. Development ve
production aynı seçilmiş asset setini okuyabilir; SQLite ve private-media yollarını
paylaşmaz. Gelecekteki container karşılıkları `/app/ai-models:ro` ve
`/app/document-templates:ro` olarak kalır.

Repository içindeki Django/Vue `models/` dizinleri kaynak koddur. HTML mail gövdeleri
de ilgili feature altında, örneğin `backend/users/templates/users/` ve
`backend/compliance/templates/compliance/`, tracked kaynak olarak tutulur. Üretilmiş
SPA `backend/templates/index.html` dosyası ise build artifact'ı olarak ignore edilir.
Makineye özel farklı bir konum gerekirse yolları ignore edilen `backend/.env`
içinde değiştirin.

Local veriyi bilinçli olarak sıfırlamanız gerekiyorsa önce [local database reset rehberini](docs/local-database-reset.md) okuyun. Shared veya production database üzerinde bu akışı kullanmayın.

## Mimari özeti

```text
Browser
  └─ HTTPS / same-origin
      └─ Windows Uvicorn + Django/DRF + built Vue artifact
          ├─ SQLite: business state, audit, jobs, leases
          └─ LocalAppData private-media: owner-scoped job files

Background lifecycles
  ├─ worker: local durable executors
  ├─ notification-worker: password-reset outbox + compliance notifications
  └─ cleanup-worker: preview and terminal-artifact retention

Windows DOORS execution
  └─ tek launcher-owned worker → allowlisted doors queue → OLE/COM
```

Temel modül sınırları:

- `backend/awcenter/`: composition root, settings, root routes, health, logging, API/file security.
- `backend/compliance/`: tüm projeler için tek Compliance Document aggregate'i, import, lifecycle, review, notification ve audit davranışı.
- `backend/projects/`: read-only teknik capability registry'si ve küçük project policy strategy'leri.
- `backend/orgs/`: business project kayıtları, organizasyon verisi ve project-scoped roller.
- `backend/jobs/`: feature bağımsız durable job/workflow kernel'i, lease ve execution fencing.
- `backend/automations/`: static executor metadata kataloğu ve workflow use-case'leri.
- `backend/integrations/` ve domain app'leri: dış sistem adapterları.
- `frontend/src/app/`, `frontend/src/shared/`, `frontend/src/features/`: composition/router, ortak HTTP-güvenlik primitive'leri ve feature-owned API/composable/UI sınırları. Page/component doğrudan HTTP client kullanmaz; route-local state global Pinia'ya taşınmaz.

Ayrıntılar için [architecture.md](docs/architecture.md) belgesine bakın.

## Kimlik doğrulama ve API

Browser kimliği yalnız Django server-side session'ıdır:

- `GET /api/session/` session bootstrap eder ve CSRF cookie'sini sağlar.
- `POST /api/session/` CSRF korumalı login yapar.
- `DELETE /api/session/` session'ı ve kullanıcıya bağlı geçici integration state'ini sonlandırır.
- DRF varsayılanı `SessionAuthentication` ve `IsAuthenticated`'dır.
- Frontend `withCredentials`, `csrftoken` ve `X-CSRFToken` sözleşmesini merkezi `frontend/src/shared/api/http.ts` içinde uygular.

Browser credential'ı response body, URL veya Web Storage içinde tutulmaz. Public endpoint'ler sınırlı ve açıkça testlidir. API hataları `{ detail, code, ... }`, gerektiğinde `request_id` sözleşmesini kullanır.

Password-reset request'i web process'inde SMTP credential kullanmaz veya mail göndermez; account existence sızdırmadan fenced durable outbox kaydı oluşturur. Notification worker deterministic Message-ID ile teslim eder, retry sırasında aynı token/link'i yeniden üretir ve recoverable reset token'ını database'e yazmaz. Link capability'si URL fragment'ında taşınır; login shell capability'yi belleğe aldıktan hemen sonra fragment'ı browser history'sinden temizler.

Canonical yüzey:

- `/api/projects/`: erişilebilir proje kataloğu
- `/api/projects/<slug>/organization/`: project-scoped organizasyon
- `/api/projects/<slug>/compliance-documents/`: canonical compliance aggregate
- `/api/dcc/`, `/api/jobs/`, `/api/workflows/` ve owner-scoped `/api/workflows/ecr/`
- `/api/integrations/` ve `/api/tools/...`

Canonical `/api/` dışında root-level feature alias'ları ve unauthenticated file/download route'ları desteklenmez.

## Proje ve compliance modeli

`projects.registry.PROJECT_DEFINITIONS` teknik capability metadata'sının read-only kaynağıdır. `orgs.Project` bunun database karşılığıdır; fresh migration sekiz canonical project satırını seed eder. Alignment salt-okunur kontrol edilir:

```bash
cd backend
../.venv/bin/python manage.py check_project_registry
```

Proje başına Django app veya model yoktur. `compliance.ComplianceDocument`, `orgs.Project` foreign key'i ile scope edilir. Project-specific istisnalar yalnız küçük ve açık policy handler'larıdır; schema, serializer ve workflow kopyalanmaz.

## Durable işler ve private artifact'lar

Job create endpoint'leri private input artifact, SHA-256, owner, idempotency key ve static job kind sözleşmesini kaydeder. Windows production'daki tek genel worker `local` ve açıkça etkinleştirilmiş `doors` queue allowlist'lerini claim eder. Her claim yeni execution token ve süreli lease alır; heartbeat lease'i yeniler, progress monotonic ve fenced'dir. Terminal publish tekrar transaction + execution token kontrolünden geçer; belirsiz DOORS write işlemi reconciliation gerektirir.

Artifact'lar `PRIVATE_MEDIA_ROOT` altındaki owner-scoped storage'dadır. Nginx `/media/` isteğini 404 ile kapatır; download yalnız yetkili Django view ve stored SHA-256 doğrulaması üzerinden yapılır. `cleanup-worker`, expired confirmation preview'larını ve `JOB_ARTIFACT_RETENTION_DAYS` süresini aşan terminal job/artifact'ları temizler.

Outlook MSG attachment'ları parse response'unda URL taşımaz. Tarayıcı attachment'ı yalnız authenticated `POST /api/tools/outlook/msg/download/` body içindeki owner-bound, kısa ömürlü ve tek kullanımlık capability ile alabilir; backend cache'lenmiş byte'ların SHA-256 değerini response öncesi yeniden doğrular.

ECR akışı frontend'deki `/app/task/ecr` ekranından yönetilir. `GET/POST /api/workflows/ecr/` ve owner-scoped detail endpoint'i bounded PDF'den üretilen immutable review'u sunar; create `Idempotency-Key` ile tekrarlanabilir, approve/reject ise ayrı optimistic `version` mutation'larıdır. Yeni publish veya resume denemesi ephemeral JIRA session ve `Idempotency-Key` ister, approved snapshot'ı server-owned fenced job ile yayımlar. Sonucu belirsiz dış write `reconciliation_required` olur, otomatik retry edilmez; kullanıcı/provider sonucu doğruladıktan sonra explicit resume başlatır. Legacy client-side ECR orchestration veya compatibility route yoktur.

JIRA, orijinal `Subtask Generator (List)` ve `Subtask Generator (Excel)` sekmelerini korur. List sekmesinde isimlendirilmiş listeler, çift tıklayarak yeniden adlandırma, dinamik JIRA sütunları, toplu `Set Values` ve `Save` bulunur; mevcut `jira_list` kullanıcı tercihleri aynı veri biçimiyle okunup kaydedilir. Excel sekmesi ilk sheet'in sütunlarını Summary, Description, Assignee ve Due Date alanlarıyla eşler; Summary ve Description seçilmelidir. Gün/ay/yıl tarih biçimleri desteklenir.

İki ekran da `/api/dcc/subtasks/...` sözleşmesini kullanır. Tarayıcı yalnız canonical JIRA session endpoint'ine tek seferlik credential gönderir; subtask payload'ı credential içermez. Oluşturma server-owned durable job'dır; ilerleme eski ekranın progress bar'ında gösterilir. Belirsiz dış write otomatik tekrarlanmaz. Başarısız/belirsiz bir işlemden sonra Generate, aynı marker'larla orijinal listeyi sürdürme veya mevcut formdan yeni batch oluşturma seçimini açıkça sorar; yeni batch mevcut subtasks'ları çoğaltabilir. Job Center üzerinden iptal ve özel sonuç indirme kullanılabilir.

Watcher reminder akışı `/api/dcc/records/<uuid>/reminders/` üzerinden güncel record `version`, DCC operator rolü ve saatlik kayıt bazlı cooldown doğrular. Alıcılar açık JIRA subtasks assignee adreslerinden server tarafında alınır; browser'a dönmez. Web process'i yalnız durable outbox kaydı üretir, SMTP gönderimi lease-fenced notification worker'da stable `Message-ID` ile yapılır.

Windows hattı için [doors-worker.md](docs/doors-worker.md) belgesine bakın.

## Local komutlar

```bash
# Dependency kurulumu
python launcher.py setup
python launcher.py setup --skip-frontend
python launcher.py setup --skip-backend

# Salt-okunur kalite kapıları
python launcher.py check
python launcher.py test

# Development
python launcher.py dev
python launcher.py dev --migrate

# Windows production
python launcher.py prod --help

# Platform-bound, checksum manifestli offline bundle
python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
python launcher.py setup --mode offline --offline-dir offline

# Yalnız packageable Git değişiklikleri
python launcher.py package-changes
```

Launcher `.env` yazmaz, port değiştirmez ve migration'ı örtülü uygulamaz.
`dev` development process'lerini; Windows'a özel `prod` ise TLS web server ile
production worker process'lerini birlikte supervise eder. Ayrıntılar
[launcher-runtime.md](docs/launcher-runtime.md) içindedir.

## Test ve build

Ana local kapılar:

```bash
python launcher.py check
python launcher.py test
```

Explicit katman kontrolleri:

```bash
cd backend
../.venv/bin/python manage.py check
../.venv/bin/python manage.py makemigrations --check --dry-run
../.venv/bin/python manage.py migrate --check
../.venv/bin/python manage.py test
../.venv/bin/python manage.py check_project_registry

cd ..
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run test:ci
npm --prefix frontend run test:e2e
npm --prefix frontend run build

cd backend
../.venv/bin/python manage.py collectstatic --clear --noinput
../.venv/bin/python manage.py verify_frontend_artifact
```

İlk local Playwright çalıştırmasından önce `frontend/` dizininde `npx playwright install chromium` çalıştırın. `test:e2e` login+CSRF, protected deep-link ve `reconciliation_required` ECR publication'ın yeni idempotent attempt ile resume edilmesi browser smoke'larını Chromium üzerinde yürütür; backend/container smoke'larının yerine geçmez.

CI, güncel production hedefi için Windows üzerinde SQLite migration/deploy check ve
launcher/worker regresyonlarını çalıştırır. PostgreSQL/Redis testleri, immutable
container build, CycloneDX SBOM ve image evidence kontrolleri gelecekteki container
profilinin çürümesini önler. Ortak kapılarda full Django testleri ile frontend
format/type/test/build ve dependency audit çalışır. Ayrıntılar
[testing-strategy.md](docs/testing-strategy.md) içindedir.

## Windows production

Windows production `launcher.py prod` ile çalışır. `backend/.env.production`, gerçek
değerlerin yazılacağı dosya değil; `%LOCALAPPDATA%\AWCenter\config\production.env`
için tracked şablondur. Production SQLite ve private-media development'tan ayrıdır.

İlk çalıştırmadan önce frontend artifact'ını üretin:

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
```

Production komutu deploy check, pending migration, static collection ve frontend
artifact kapılarını geçmeden HTTPS server veya worker açmaz:

```powershell
python launcher.py prod `
  --env-file "$env:LOCALAPPDATA\AWCenter\config\production.env" `
  --host 192.0.2.10 `
  --tls-cert-file "$env:LOCALAPPDATA\AWCenter\tls\application\tls.crt" `
  --tls-key-file "$env:LOCALAPPDATA\AWCenter\tls\application\tls.key" `
  --migrate
```

Normal yeniden başlatmada `--migrate` kaldırılır. DOORS etkinse production worker
DOORS queue'sunu varsayılan olarak tüketir; yalnız local queue'lar için komuta
`--exclude-doors` eklenir. Aynı kullanıcı oturumunda ikinci DOORS-capable worker
başlatılamaz.

Docker Compose, immutable image, PostgreSQL ve Redis dosyaları silinmemiştir;
bunlar bugünkü production komutu değil, sonraki olgunluk/migration aşamasıdır.
Kurulum, yedekleme, TLS ve dizin ayrıntıları için [deployment.md](docs/deployment.md)
belgesini izleyin.

## Dokümantasyon

- [Mimari](docs/architecture.md)
- [Numarator entegrasyon tasarımı](docs/numarator-integration.md)
- [Deployment ve operasyon](docs/deployment.md)
- [Test stratejisi](docs/testing-strategy.md)
- [Local database reset](docs/local-database-reset.md)
- [Windows DOORS execution](docs/doors-worker.md)
- [Launcher runtime](docs/launcher-runtime.md)

Eski review/roadmap dosyaları yalnız tarihsel snapshot notlarıdır; operasyonel sözleşme olarak kullanılmaz.
