# AW Center

AW Center; proje-scoped compliance document yönetimi, DCC/JIRA akışları, durable document işleri, engineering integration'ları ve Office/PDF araçlarını aynı Django + Vue uygulamasında birleştirir.

Production hedefi tek ve bilinçli olarak dardır: Linux üzerinde immutable container image, same-origin HTTPS, PostgreSQL 17, Redis 7, private artifact volume ve bağımsız web/worker/notification/cleanup process'leri. Windows-only DOORS otomasyonu ayrı bir outbound mTLS agent ile çalışır; ana backend Windows üzerinde çalışmaz.

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
için korunur ve credential içermemelidir. Production bu dosyaları ve launcher'ı
kullanmaz: Docker Compose için canonical şablon repository kökündeki
`.env.example` dosyasıdır ve gerçek değerler checkout dışında veya secret
manager'da tutulur.

Varsayılan adresler:

- Vue development server: `http://127.0.0.1:5173/app/`
- Django API: `http://127.0.0.1:8000/api/`
- Liveness: `http://127.0.0.1:8000/health/live/`
- Readiness: `http://127.0.0.1:8000/health/ready/`

`launcher.py dev`, Django, Vite, durable job worker, notification worker ve cleanup worker'ı foreground child process'ler olarak başlatır. Migration yalnız `--migrate` açıkça verildiğinde uygulanır. Launcher production server başlatmaz.

Local veriyi bilinçli olarak sıfırlamanız gerekiyorsa önce [local database reset rehberini](docs/local-database-reset.md) okuyun. Shared veya production database üzerinde bu akışı kullanmayın.

## Mimari özeti

```text
Browser
  └─ HTTPS / same-origin
      └─ Nginx ingress
          └─ Django + DRF + built Vue artifact
              ├─ PostgreSQL: business state, audit, jobs, leases
              ├─ Redis: shared cache, probe/capability coordination
              └─ private-artifacts volume: owner-scoped job files

Background lifecycles
  ├─ worker: local durable executors
  ├─ notification-worker: password-reset outbox + compliance notifications
  └─ cleanup-worker: preview and terminal-artifact retention

Windows DOORS agent
  └─ outbound HTTPS + mTLS → dedicated bridge ingress → /internal/bridge/v1/
```

Temel modül sınırları:

- `backend/awcenter/`: composition root, settings, root routes, health, logging, API/file security.
- `backend/compliance/`: tüm projeler için tek Compliance Document aggregate'i, import, lifecycle, review, notification ve audit davranışı.
- `backend/projects/`: read-only teknik capability registry'si ve küçük project policy strategy'leri.
- `backend/orgs/`: business project kayıtları, organizasyon verisi ve project-scoped roller.
- `backend/jobs/`: feature bağımsız durable job/workflow kernel'i, lease ve execution fencing.
- `backend/automations/`: static executor metadata kataloğu ve Windows bridge protocol'u.
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
- `/internal/bridge/v1/`: browser'a kapalı Windows agent data plane

Canonical `/api/` dışında root-level feature alias'ları ve unauthenticated file/download route'ları desteklenmez.

## Proje ve compliance modeli

`projects.registry.PROJECT_DEFINITIONS` teknik capability metadata'sının read-only kaynağıdır. `orgs.Project` bunun database karşılığıdır; fresh migration sekiz canonical project satırını seed eder. Alignment salt-okunur kontrol edilir:

```bash
cd backend
../.venv/bin/python manage.py check_project_registry
```

Proje başına Django app veya model yoktur. `compliance.ComplianceDocument`, `orgs.Project` foreign key'i ile scope edilir. Project-specific istisnalar yalnız küçük ve açık policy handler'larıdır; schema, serializer ve workflow kopyalanmaz.

## Durable işler ve private artifact'lar

Job create endpoint'leri private input artifact, SHA-256, owner, idempotency key ve static job kind sözleşmesini kaydeder. Local worker yalnız `local`, Windows bridge yalnız `windows` queue allowlist'ini claim eder. Her claim yeni execution token ve süreli lease alır; heartbeat lease'i yeniler, progress monotonic ve fenced'dir. Terminal publish tekrar row lock + token kontrolünden geçer. Recovery sonrası eski worker artifact yayımlayamaz.

Artifact'lar `PRIVATE_MEDIA_ROOT` altındaki owner-scoped storage'dadır. Nginx `/media/` isteğini 404 ile kapatır; download yalnız yetkili Django view ve stored SHA-256 doğrulaması üzerinden yapılır. `cleanup-worker`, expired confirmation preview'larını ve `JOB_ARTIFACT_RETENTION_DAYS` süresini aşan terminal job/artifact'ları temizler.

Outlook MSG attachment'ları parse response'unda URL taşımaz. Tarayıcı attachment'ı yalnız authenticated `POST /api/tools/outlook/msg/download/` body içindeki owner-bound, kısa ömürlü ve tek kullanımlık capability ile alabilir; backend cache'lenmiş byte'ların SHA-256 değerini response öncesi yeniden doğrular.

ECR akışı frontend'deki `/app/task/ecr` ekranından yönetilir. `GET/POST /api/workflows/ecr/` ve owner-scoped detail endpoint'i bounded PDF'den üretilen immutable review'u sunar; create `Idempotency-Key` ile tekrarlanabilir, approve/reject ise ayrı optimistic `version` mutation'larıdır. Yeni publish veya resume denemesi ephemeral JIRA session ve `Idempotency-Key` ister, approved snapshot'ı server-owned fenced job ile yayımlar. Sonucu belirsiz dış write `reconciliation_required` olur, otomatik retry edilmez; kullanıcı/provider sonucu doğruladıktan sonra explicit resume başlatır. Legacy client-side ECR orchestration veya compatibility route yoktur.

Windows hattı için [windows-bridge.md](docs/windows-bridge.md) belgesine bakın.

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

# Platform-bound, checksum manifestli offline bundle
python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
python launcher.py setup --mode offline --offline-dir offline

# Yalnız packageable Git değişiklikleri
python launcher.py package-changes
```

Launcher `.env` yazmaz, port değiştirmez, migration'ı örtülü uygulamaz ve production process'i supervise etmez. Ayrıntılar [launcher-runtime.md](docs/launcher-runtime.md) içindedir.

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

CI, fresh PostgreSQL ve Redis üzerinde migration, full Django tests, launcher/release tests, frontend format/type/test/build, dependency audit, immutable container build, CycloneDX SBOM, resolved image digest/frontend eşlik doğrulaması, session/rol/CompDoc/DCC/private-artifact+notification release smoke, readiness, worker heartbeat ve read-only source kontrollerini uygular. Ayrıntılar [testing-strategy.md](docs/testing-strategy.md) içindedir.

## Production ve release

Production'da `launcher.py` kullanılmaz. Desteklenen deploy akışı `deployment_preflight.py` ile `AWCENTER_IMAGE=repository@sha256:<digest>` biçimini zorunlu tutar ve schema-2 `release-manifest.json` ile `image-verification.json` evidence'ını birlikte alarak release, commit, manifest SHA-256, frontend tree/count ve image digest eşliğini fail-closed doğrular. Mutable tag desteklenmez. `backend/Dockerfile`:

1. Node 22 aşamasında Vite artifact'ını üretir.
2. Python 3.11 dependency aşamasında locked requirements'ı kurar ve `pip check` çalıştırır.
3. Runtime aşamasında frontend artifact'ını kopyalar, static collection ve artifact verification yapar.
4. Numeric non-root kimlik, dropped Linux capability'leri ve `no-new-privileges` ile çalışır; `/app` source tree'sini read-only bırakır.

Compose topology; `ingress`, `backend`, `worker`, `notification-worker`, `cleanup-worker`, `database` ve `redis` servislerinden oluşur. AW Center image release evidence digest'iyle; Dockerfile base image'ları ile Nginx, PostgreSQL ve Redis image'ları SHA-256 digest'leriyle, CI action'ları commit SHA ile pinlidir. Process environment ve volume'ları capability'ye göre daraltılmıştır: notification worker integration secret/private volume, cleanup worker integration/mail/model, backend ve local worker ise mail credential'ı almaz. Private artifact volume yalnız backend, local worker ve cleanup worker'da; model mount'u yalnız backend ve local worker'da bulunur.

Redis non-root kullanıcı ve restricted runtime config ile authenticated çalışır. Nginx healthcheck'leri public bypass eklemek yerine yalnız container-loopback readiness listener'ından backend readiness'i doğrular.

Opsiyonel `windows-bridge` profile'ı yalnız ayrı mTLS ingress'i ekler. Windows poller binary/service'i bu repository'nin veya Compose topolojisinin parçası değildir; ayrı onaylanan release ve Windows service supervision'ı operasyon ekibinin sorumluluğudur. Migration, operator superuser oluşturma ve iki aşamalı `run_release_smoke` one-shot container komutlarıdır; ingress ancak core/notification smoke, deploy checks, readiness ve worker health geçtikten sonra açılır.

Release evidence:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
export AWCENTER_RELEASE_EVIDENCE_ROOT=/srv/awcenter-release-evidence
printf '%s' "$AWCENTER_RELEASE" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
python scripts/build_release_metadata.py \
  --release "$AWCENTER_RELEASE" \
  --output "$AWCENTER_RELEASE_EVIDENCE_ROOT/$AWCENTER_RELEASE"
```

Evidence root repository checkout'u dışında ve operator erişimli olmalıdır. Komut clean Git worktree ister; tracked kaynak ve built frontend için SHA-256 manifest, frontend tree digest'i ve Python/npm dependency'lerinden CycloneDX SBOM üretir. CI ayrıca BuildKit resolved-image metadata'sını, release manifest hash'ini ve image içindeki frontend tree ile reviewed artifact eşliğini kaydeden `image-verification.json` dosyasını saklar. Preflight secret/host/database/Redis/runtime path contract'ına ek olarak bu iki evidence dosyasını ve immutable image reference'ını tek release zinciri olarak doğrular.

Kurulum, backup, forward-fix ve atomic ingress gate için [deployment.md](docs/deployment.md) belgesini izleyin.

## Dokümantasyon

- [Mimari](docs/architecture.md)
- [Deployment ve operasyon](docs/deployment.md)
- [Test stratejisi](docs/testing-strategy.md)
- [Local database reset](docs/local-database-reset.md)
- [Windows bridge](docs/windows-bridge.md)
- [Local launcher](docs/launcher-runtime.md)

Eski review/roadmap dosyaları yalnız tarihsel snapshot notlarıdır; operasyonel sözleşme olarak kullanılmaz.
