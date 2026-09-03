# AW Center test stratejisi

Test stratejisinin amacı yalnız assertion sayısı değil; architecture, security, migration, artifact ve deployment contract'larını release öncesi executable evidence olarak doğrulamaktır.

## Test katmanları

| Katman | Araç/konum | Korunan sözleşme |
|---|---|---|
| Backend unit/domain | Django `SimpleTestCase`, `TestCase`; app yanındaki `test*.py`/`tests/` | Service, serializer, permission, transaction, error yolları |
| Backend API/contract | DRF `APIClient` | Session/CSRF, status/body/error, project scope, idempotency |
| Architecture fitness | `backend/awcenter/test_architecture.py`, `backend/automations/tests.py` | Import DAG, removed packages, canonical URLs, queue/catalog boundaries |
| Deployment contract | `backend/awcenter/test_deployment_contract.py`, `test_environment.py` | Digest-pinned image, process env/volume capability'si, Nginx, CI, production settings |
| Frontend unit | Vitest, `frontend/src/**/*.test.ts` | Session/project/API normalization ve typed services |
| Frontend contract | `frontend/scripts/test-*.mjs` | Route/access/menu, store boundaries, upload/jobs/UI registration |
| Browser smoke | Playwright Chromium, `frontend/e2e/` | Login+CSRF, protected deep-link ve explicit ECR reconciliation resume |
| Launcher/release | Python unittest `scripts/test_*.py` | CLI, worker lifecycle, safe packaging, manifest/SBOM |
| Container smoke | GitHub Actions | Fresh PostgreSQL/Redis, session+role+CompDoc+DCC/private-artifact release smoke, notification canary, readiness, worker heartbeat, read-only source |

## Ana local kapılar

Repository kökünden:

```bash
python launcher.py check
python launcher.py test
```

`check`:

- Django system check;
- isolated in-memory database üzerinde migration drift ve migration plan;
- frontend read-only format check ve strict TypeScript.

`test`:

- full Django suite;
- launcher, worker lifecycle ve release metadata unittest'leri;
- frontend `test:ci` zinciri.

Bu komutlar source formatlamaz, migration üretmez ve mevcut database'e migration uygulamaz.

## Explicit doğrulama komutları

Backend, `backend/` dizininden:

```bash
../.venv/bin/python manage.py check
../.venv/bin/python manage.py makemigrations --check --dry-run
../.venv/bin/python manage.py migrate --check
../.venv/bin/python manage.py test
../.venv/bin/python manage.py check_project_registry
```

Dar backend örnekleri:

```bash
../.venv/bin/python manage.py test users.test_auth_csrf
../.venv/bin/python manage.py test compliance
../.venv/bin/python manage.py test jobs
../.venv/bin/python manage.py test automations integrations.tests.test_doors_runner \
  integrations.tests.test_doors_runner_tasks
../.venv/bin/python manage.py test awcenter.test_architecture awcenter.test_deployment_contract
```

Frontend, repository kökünden:

```bash
npm --prefix frontend ci
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run test:ci
npm --prefix frontend run build
```

İlk local browser smoke kurulumunda:

```bash
cd frontend
npx playwright install chromium
cd ..
npm --prefix frontend run test:e2e
```

CI, `frontend/` çalışma dizininde `npx playwright install --with-deps chromium` kullanır ve ardından aynı `npm run test:e2e` gate'ini çalıştırır. Browser binary/cache'i source veya release manifestine eklenmez.

Launcher/release:

```bash
.venv/bin/python -m unittest \
  scripts.test_launcher \
  scripts.test_launcher_jobs \
  scripts.test_release_metadata
```

Frontend artifact-serving değişikliğinde build sonrasında, `backend/` içinden:

```bash
../.venv/bin/python manage.py collectstatic --clear --noinput
../.venv/bin/python manage.py verify_frontend_artifact
```

## Değişiklik → zorunlu evidence matrisi

| Değişiklik | Minimum ek kontroller |
|---|---|
| Model/migration | Target app tests, `makemigrations --check --dry-run`, fresh PostgreSQL `migrate`, `migrate --check` |
| Project registry/roles | `projects`, `orgs`, `check_project_registry`, frontend project registry tests |
| Compliance lifecycle/import | Compliance unit/API, optimistic version/confirmation, audit/history ve concurrency testleri |
| Session/authorization | Backend auth/CSRF/permission + password-reset outbox/lease; frontend session, route access, menu/command tests |
| Upload/private artifact | File security, path traversal/signature/size, authorization, SHA ve cleanup testleri |
| Job/executor | Catalog resolution, queue allowlist, idempotency, lease/token fencing, heartbeat, cancellation, recovery, retention |
| ECR workflow | Owner scope, bounded PDF/immutable review create replay'i, versioned approve/reject, ephemeral JIRA session, publish/resume idempotency, job fencing ve no-auto-retry reconciliation |
| JIRA subtask | Operator/project scope, credential-free manual/Excel plan, live field contract, marker idempotency, uncertain write ve explicit resume |
| DCC reminder | Record/version/role scope, recipient sınırı, idempotency/cooldown, outbox lease, stable Message-ID ve SMTP'siz web enqueue |
| DOORS runner | Loopback-only ingress, runner-token rejection, one-use input/output, stale completion, local catalog allowlist ve DOORS adapter tests |
| Frontend service/store | Vitest + ilgili script contract + typecheck |
| Session/router/browser shell | Backend auth/CSRF + frontend unit/route contracts + `test:e2e` |
| Static/Vite/Docker/Nginx | Frontend build, collectstatic, artifact verify, deployment contract, container build/smoke |
| Launcher/offline/release | Üç launcher/release unittest modülü, checksum/target mismatch ve secret-exclusion cases |
| Compose/env/release gate | Preflight placeholder/path/password/evidence reddi, resolved digest, reviewed/image frontend tree eşliği, base/action pinleri ve per-process secret/volume assertions |

## Güvenlik senaryoları

Değişen yüzeyle orantılı olarak en az şunları değerlendirin:

- anonymous, authenticated fakat yetkisiz ve doğru role sahip kullanıcı;
- missing/invalid CSRF ve session invalidation;
- known/unknown account için aynı password-reset response, SMTP'siz web enqueue, raw-token persistence reddi, stale mail lease ve fragment capability'nin hemen scrub edilmesi;
- cross-project object ID ve disabled/unknown project;
- unsafe filename, traversal, yanlış signature, oversized upload, archive expansion;
- Outlook attachment capability'sinde cross-user kullanım, query/URL sızıntısı, replay ve cached SHA-256 mismatch;
- idempotency key replay: aynı input ve farklı input;
- ECR'de cross-owner erişim, stale approve/reject version, credential payload reddi, missing/expired JIRA session, stale publication fence ve explicit resume öncesi reconciliation doğrulaması;
- subtask create/resume'da legacy credential reddi, unknown/required field kontrolü, marker reuse ve uncertain provider write sonrası otomatik retry olmaması;
- Watcher reminder'da record/project scope, stale version, aynı idempotency replay'i, saatlik cooldown, alıcıların response'ta gizlenmesi ve stale mail lease;
- expired/recovered lease ve stale worker publish;
- browser cookie/authorization ile internal runner erişimi;
- untrusted proxy, missing/invalid/expired certificate ve fingerprint mismatch;
- Redis authenticated health + unauthenticated command rejection ve Nginx loopback-only readiness;
- response/log içinde secret, path, certificate veya upstream exception sızıntısı.

Test kolaylığı için production guard kaldırılmaz, exception yutulmaz, assertion gevşetilmez ve expected failure skip'e çevrilmez.

## Database ve concurrency

SQLite yalnız hızlı local convenience olabilir; release evidence PostgreSQL ve process-shared Redis üzerinde üretilir. Transaction/locking davranışı içeren testler fresh PostgreSQL'de çalışmalıdır. CI:

1. PostgreSQL ve Redis servislerini health-check ile başlatır.
2. Fresh schema'ya `migrate --noinput` uygular.
3. Project seed sayısını ve `migrate --check` sonucunu doğrular.
4. Full backend suite'i çalıştırır.

Job claim/recovery, compliance/ECR version transition ve notification lease testleri row lock/token değişimini assertion ile kanıtlar; yalnız happy-path status kontrolü yeterli değildir. ECR external write timeout/lease loss `reconciliation_required` üretmeli, otomatik yeni job yaratmamalı ve resume yeni `Idempotency-Key` olmadan ilerlememelidir.

## Frontend kalite zinciri

`frontend/package.json` içindeki `test:ci` sırasıyla Vitest unit testleri ve repository-owned Node contract testlerini çalıştırır. `test:e2e` ayrı Playwright gate'idir; mevcut smoke session API'nin CSRF cookie/header contract'ını, anonymous protected deep-link redirect'ini ve `/app/task/ecr` ekranında `reconciliation_required` publication'ın version + yeni `Idempotency-Key` ile queued durable attempt'e resume edilmesini gerçek Chromium navigation'ıyla doğrular. Bu mocked browser contract smoke'u canlı Django/container smoke'unun yerine geçmez. Route görünürlüğü, navigation guard ve backend permission aynı policy niyetini paylaşmalıdır; UI gizleme authorization yerine geçmez.

Frontend lock dosyasının canonical üreticisi `frontend/package.json` içindeki npm sürümüdür. Rolldown'ın optional WASI zincirindeki `@emnapi/core` ve `@emnapi/runtime` peer'ları doğrudan dev dependency olarak sabitlenir; böylece npm 10 ve npm 11 aynı lock dosyasını `npm ci` ile kabul eder. Dependency güncellemesinden sonra iki npm major'ünde de clean install doğrulanmalıdır.

`format:check` read-only'dir. CI source'u otomatik formatlamaz. Bundle build, `check-bundle-budget.mjs` ve postbuild artifact existence kontrolüyle tamamlanır.

## CI ve release gate

GitHub Actions jobs:

- Backend: Python 3.11, PostgreSQL/Redis, fresh migration, checks/tests, dependency audit, integrated frontend/static smoke.
- Frontend: Node 22, `npm ci`, format/type/unit-contract test, Playwright Chromium E2E, build, npm audit ve immutable artifact upload.
- Compatibility: Python 3.14 üzerinde backend check/test.
- Container: digest-pinned base/infra image'lar, commit-SHA-pinned actions, combined image, resolved digest/frontend tree verification, release manifest/CycloneDX SBOM, fresh-schema migration, `run_release_smoke` core+notification kapıları, deploy checks, readiness, worker heartbeat ve source read-only assertion.

`verify_release_image.py`, BuildKit digest'i ve image frontend ağacını schema-2 release manifestine bağlar. `deployment_preflight.py` environment/runtime-path sözleşmesinin yanında manifest ve verification kaydındaki release, commit, manifest SHA-256, frontend tree/count ve `AWCENTER_IMAGE` digest eşliğini yeniden doğrular. Testler hem image-verification üretimindeki değiştirilmiş dist/manifest reddini hem deploy-time değiştirilmiş evidence/env reddini ayrı kapsamalıdır.

Required job başarısızken release deploy edilmez. Audit bulgusu gizlenmez; dependency exception gerekiyorsa risk, owner ve expiry ile ayrı karar kaydı gerekir.

## Test verisi ve artifact hijyeni

- Test credential'ları yalnız test scope'unda sentetik değerlerdir; gerçek secret/PII kullanılmaz.
- Temporary file/directory context veya teardown ile temizlenir.
- Generated `frontend/dist`, `frontend/test-results`, `frontend/playwright-report`, collected static, SQLite, private media ve release evidence commit edilmez.
- Testler external JIRA/DOORS/Teamcenter servisine güvenmez; bounded adapter/transport mock'ları kullanır.
- Windows-only callable contract'ları platformdan bağımsız artifact adapter testleriyle, gerçek OLE smoke'u kontrollü agent ortamında ayrıca doğrulanır.

## Sonuç raporlama

Teslim özetinde komut, test sayısı/sonuç, skip ve çalıştırılamayan kontrol açıkça yazılır. Bir kontrol environment nedeniyle çalışmadıysa yapılan alternatif doğrulama ve kalan risk belirtilir.
