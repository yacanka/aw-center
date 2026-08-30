# AW Center coding agent rehberi

## Kaynak ve modül sınırları

- Django kaynakları `backend/`, Vue kaynakları `frontend/src/` altındadır. `backend/awcenter/` yalnız composition root, settings, root URL, ortak HTTP/güvenlik ve deployment kontrollerini barındırır.
- Compliance Documents için tek canonical aggregate `backend/compliance/` içindedir. Proje başına Django app, model veya route üretme. Her kayıt `orgs.Project` foreign key'i ile scope edilir.
- `backend/projects/registry.py` teknik ve read-only proje capability kataloğudur. İş verisi ve erişim rolleri `backend/orgs/` içindedir; ortak kimlik `slug` değeridir. Proje farkı gerçekten gerekiyorsa yalnız küçük bir `backend/projects/policies/` strategy'si ekle.
- Durable job kernel'i `backend/jobs/`; statik executor metadata kataloğu `backend/automations/catalog.py`; callable çözümleme composition root'u `backend/awcenter/job_executors.py` içindedir. `jobs` feature app'lerini import etmez.
- Vendor/integration adapterları ve HTTP/use-case yüzeyleri `backend/integrations/` altında kalır; DOORS, Teamcenter veya DocProof için yeniden kök Django app oluşturma. Generic event bus, plugin framework veya yeni bir background-processing framework ekleme.
- Frontend composition ve route'ları `frontend/src/app/`; ortak HTTP/CSRF, hata, download ve küçük primitive'ler `frontend/src/shared/`; business UI/API/composable'ları `frontend/src/features/<feature>/` içindedir. Session bootstrap/guard `features/session/`, proje kataloğu `features/projects/` altındadır. Component/page doğrudan Axios/shared HTTP client import etmez; feature API veya composable kullanır.
- Kök `launcher.py` yalnız local setup/check/test/dev/offline-package girişidir. Üretim sunucusu veya Windows bridge supervisor'u değildir; davranışı `scripts/launcher/`, testleri `scripts/test_launcher*.py` içindedir.

## Korunacak güvenlik ve API sözleşmeleri

- Browser authentication yalnız Django server-side session cookie'sidir. DRF varsayılanı `SessionAuthentication` + `IsAuthenticated`; unsafe istekler CSRF gerektirir. Browser credential'ını response body, local/session storage veya URL içine koyma.
- Password-reset request web process'inde mail göndermez: account-existence-neutral response, durable/fenced outbox, deterministic Message-ID, stable retry token timestamp ve notification-worker-only SMTP credential sınırını koru. Raw reset token'ını persist etme.
- Public endpoint yalnız bilinçli `AllowAny` kararı ve testle eklenir. Canonical browser API `/api/`; SPA `/app/`; health `/health/live/` ve `/health/ready/`; Windows agent data plane `/internal/bridge/v1/` altındadır. Eski alias route ekleme.
- API hata sözleşmesi `{ detail, code, ... }` ve mümkün olduğunda `request_id` içerir. `awcenter.api_errors` ve frontend `shared/api/apiError.ts` kullan; exception, credential, filesystem veya upstream ayrıntısı sızdırma.
- Upload'larda `awcenter.file_security` boyut, ad, uzantı, imza ve arşiv politikalarını uygula. Job input/output artifact'ları yalnız `PRIVATE_MEDIA_ROOT`, owner-scoped path, SHA-256 ve yetkili download view ile erişilir. `/media/` public değildir.
- Outlook attachment gibi cache-backed private download'larda URL/query credential üretme. Capability authenticated POST body'de taşınmalı; owner-bound, kısa ömürlü, tek kullanımlık olmalı ve payload SHA-256 indirme öncesi yeniden doğrulanmalıdır.
- Job değişikliğinde create endpoint, idempotency key, `automations.catalog` kind/queue/upload/timeout metadata'sı, claim lease/execution token, cancellation, monotonic progress, terminal CAS fencing ve artifact retention birlikte ele alınır. `transaction.atomic`/`select_for_update` ve stale-worker korumasını zayıflatma.
- Windows executor yalnız `windows` queue'dan bridge üzerinden çalışır. Agent'a database/cache/browser credential verilmez; mTLS identity, tek kullanımlık artifact capability ve SHA-256 doğrulaması korunur.
- Compliance import/lifecycle/review/notification değişikliklerinde project scope, optimistic `version`, confirmation token, audit/history ve transaction sınırlarını koru. Model/service'i atlayan bulk update ile türetilmiş alanları bozma.
- Project capability değişikliği backend/frontend contract değişikliğidir: registry, seed/alignment testleri, `frontend/src/features/projects/models/projectRegistry.ts` ve tüketicileri aynı değişiklikte hizala. Internal handler/template/integration metadata'sını API'ye açma.

## Migration, dependency ve üretilmiş dosyalar

- Production sözleşmesi Linux container + fresh PostgreSQL 17 + Redis 7'dir. Önceki database şemasını dönüştüren geçiş migration'ı veya veri-kopyalama komutu ekleme. Shared/production database'i resetleme; backup al, forward-only migration ve forward-fix kullan.
- Normal model değişikliğinde mevcut migration'ı yeniden yazma; yeni migration üret. Migration baseline değişikliği ancak açık repository-wide görevde yapılır ve disposable local database yeniden oluşturulur.
- Proje katalog satırları `orgs` data migration'ıyla seed edilir. `check_project_registry` salt-okunur doğrulamadır; runtime senkronizasyon komutu ekleme.
- Python dependency kaynağı `requirements.in`, üretilen lock `requirements.txt`'dir. Güncelleme komutu `uv pip compile --python-version 3.11 requirements.in -o requirements.txt`; lock'u elle düzenleme. Runtime CPython 3.11'dir.
- Frontend dependency kaynağı `frontend/package.json` ve `frontend/package-lock.json`; kurulum `npm ci` ile yapılır. Kök `package.json` yalnız frontend script proxy'sidir.
- Secret, certificate, private key, endpoint credential veya gerçek kullanıcı verisi commit etme. `backend/.env` local ve git dışıdır; production değerleri process environment/secret manager'dan gelir.
- `frontend/dist/`, `frontend/test-results/`, `frontend/playwright-report/`, `backend/static/`, `backend/staticfiles/`, `__pycache__/`, `.venv/`, `.runtime/`, private/media/model dizinleri, SQLite dosyaları ve release evidence üretilmiş/local state'tir; kaynak gibi düzenleme veya commit etme.
- Container runtime source'u read-only'dir; Django lifecycle'larının numeric non-root kimlik, dropped capabilities ve `no-new-privileges` sınırını koru. Her Compose lifecycle'ına yalnız ihtiyacı olan integration/mail environment'ını ve volume'u ver: notification worker private/model volume'u veya integration credential'ı; cleanup worker mail/integration credential'ı veya model volume'u; backend/local worker mail credential'ı almamalıdır.
- Private artifact volume yalnız backend, local worker ve cleanup worker arasında paylaşılır; model dizini yalnız backend ve local worker'a read-only mount edilir. Windows bridge profile'ı yalnız dedicated mTLS ingress'i yönetir; bu repository harici Windows poller release'inin image, credential veya supervision sahibi değildir.
- Model mount sözleşmesi `/app/models`: DCC/cover-page template'leri `/app/models/templates`, Word modelleri kendi allowlisted alt dizinlerindedir. `CUSTOM_TEMPLATE_DIR` veya model path'lerini source tree'ye ya da writable private artifact alanına yönlendirme.
- İlk production ingress'i yalnız `run_release_smoke --stage core` ve notification-worker içinde `--stage notification` geçtikten sonra açılır. Bu komut mevcut business state üzerinde çalışmayı reddeden first-install gate'idir; upgrade/veri temizleme aracı olarak gevşetme.
- Production image reference'ı mutable tag olamaz. Deploy öncesi `deployment_preflight.py` sonucu, CI release evidence'ı, `verify_release_image.py` ile doğrulanmış frontend ağacı ve Compose'a verilen `repository@sha256:<digest>` aynı release zincirini göstermelidir.
- Dockerfile/Compose base ve infrastructure image digest'lerini veya CI action commit SHA pinlerini yalnız bağımlılık yükseltmesi olarak, deployment contract testleriyle birlikte değiştir; pinleri mutable tag/major referansa gevşetme.
- Redis authentication'ını command argümanına taşıma; restricted config + non-root process ve authenticated healthcheck sözleşmesini koru. Nginx container health'ini hosta açılan bypass route'uyla değil, loopback aggregate readiness listener'ıyla ölç.

## Çalışma ve doğrulama

Repository kökünden temel kapılar:

```bash
python launcher.py check
python launcher.py test
```

Değişiklik kapsamına göre exact kontroller:

```bash
# Backend (backend/ içinden)
../.venv/bin/python manage.py check
../.venv/bin/python manage.py makemigrations --check --dry-run
../.venv/bin/python manage.py migrate --check
../.venv/bin/python manage.py test <app_veya_test_labeli>
../.venv/bin/python manage.py check_project_registry

# Frontend (repository kökünden)
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run test:ci
npm --prefix frontend run test:e2e
npm --prefix frontend run build

# Launcher ve release metadata
.venv/bin/python -m unittest scripts.test_launcher scripts.test_launcher_jobs scripts.test_release_metadata
```

- Model değişikliğinde PostgreSQL üzerinde `migrate --check` ve `makemigrations --check --dry-run` çalıştır.
- Session/route erişimi değişikliğinde backend auth/CSRF testleri ile frontend session, access ve route testlerini birlikte çalıştır.
- Playwright Chromium'u ilk local E2E kullanımından önce `frontend/` içinde `npx playwright install chromium` ile kur. CI browser kurulumunda `npx playwright install --with-deps chromium` kullan; browser binary'sini repository'ye ekleme.
- Frontend artifact/static/container değişikliğinde build sonrası `backend/` içinde `../.venv/bin/python manage.py collectstatic --clear --noinput` ve `../.venv/bin/python manage.py verify_frontend_artifact` çalıştır.
- Deployment değişikliğinde `backend/Dockerfile`, `docker-compose.yml`, iki Nginx config'i, `.github/workflows/ci.yml`, `scripts/deployment_preflight.py`, `scripts/verify_release_image.py`, `backend/awcenter/test_deployment_contract.py` ve release metadata testini birlikte doğrula.
- Çalıştırılmayan veya çevre yüzünden başarısız kalan kontrolü ve kalan riski açıkça raporla.
