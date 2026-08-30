# Production deployment ve operasyon runbook'u

Bu belge AW Center'ın desteklenen tek production topolojisini tanımlar: Linux container runtime, same-origin HTTPS, immutable combined image, PostgreSQL 17, Redis 7 ve private artifact volume. Local launcher production'da kullanılmaz.

## Servis topolojisi

| Compose service | Sorumluluk | State |
|---|---|---|
| `ingress` | Public TLS, `/app`, `/api`, `/health` proxy | TLS files read-only |
| `backend` | Gunicorn/Django, built Vue shell ve API | Source/image read-only |
| `worker` | `local` queue durable executors ve heartbeat | PostgreSQL + private volume |
| `notification-worker` | Password-reset outbox ve compliance notification scan/send | PostgreSQL + Redis |
| `cleanup-worker` | Expired preview ve terminal job/artifact retention | PostgreSQL + private volume |
| `database` | PostgreSQL 17 | `postgres-data` volume |
| `redis` | Shared Redis 7 cache/capability state, AOF | `redis-data` volume |
| `windows-bridge-ingress` | Opsiyonel mTLS agent ingress | CA/server TLS read-only |

Backend host portuna publish edilmez. Public ingress `/media/` ve `/internal/bridge/` yollarını kapatır. Bridge ingress ayrı `windows-bridge` profile'ındadır ve yalnız internal bridge API'yi geçirir.

`windows-bridge` profile'ı bir Windows poller başlatmaz. Poller binary/service'i ayrı release, sertifika lifecycle'ı ve Windows service supervisor'u olan harici bir deployment bileşenidir; Compose yalnız onun bağlandığı mTLS ingress'in sahibidir.

## Process least-privilege sözleşmesi

Compose ortak runtime ayarlarını paylaşır, fakat feature secret ve volume'ları lifecycle bazında sınırlar:

| Service | İzinli ek secret/config | Filesystem capability |
|---|---|---|
| `backend` | Browser/API integration'ları | `private-artifacts:rw`, `models:ro` |
| `worker` | Yalnız local executor JIRA/Teamcenter ayarları | `private-artifacts:rw`, `models:ro` |
| `notification-worker` | Yalnız password-reset/compliance mail transport | Ek volume yok |
| `cleanup-worker` | Yalnız artifact retention | `private-artifacts:rw` |
| `windows-bridge-ingress` | Bridge enable gate'i ve hostname | Nginx config + public/server/CA TLS dosyaları `ro` |

Notification worker'a integration/session credential'ı veya private/model volume; cleanup worker'a integration/mail credential'ı veya model volume; backend/local worker'a mail credential'ı vermeyin. Password-reset API yalnız durable outbox'a yazar; SMTP teslimi notification worker'dadır. Bir yeni executor bu matrisi genişletmek zorundaysa değişikliği Compose contract testi ve threat-boundary gerekçesiyle birlikte yapın.

## Immutable image contract'ı

`backend/Dockerfile` üç aşamalıdır:

1. Node 22 + `npm ci` ile frontend build ve bundle budget.
2. Python 3.11 venv + locked `requirements.txt` + `pip check`.
3. Runtime native araçları, non-root user, frontend artifact copy, `collectstatic`, `verify_frontend_artifact` ve Gunicorn.

Runtime image Node veya compiler içermez. Django lifecycle'ları numeric `10001:10001` kimliği, drop edilmiş tüm Linux capability'leri ve `no-new-privileges` ile çalışır. `/app` source tree build sonunda write bit'lerini kaybeder. Yalnız `/app/private_media` named volume ve `/app/models:ro` deployment mount'ıdır. Source/static volume ile image içeriğini maskelemeyin.

AW Center image'ı release evidence digest'iyle; Dockerfile Node/Python base image'ları ile bundled Nginx, PostgreSQL ve Redis image'ları da doğrudan SHA-256 digest'leriyle pinlidir. CI action referansları commit SHA kullanır. Base/altyapı/action pin güncellemesini sürüm yükseltmesi gibi review/test edin; görünen tag/major sürümü koruyup pin'i sessizce değiştirmeyin.

Redis container'ı image'ın `redis` kullanıcısıyla çalışır; entrypoint password'ü `0600` geçici config'e yazar, kendi environment'ından kaldırır ve server'ı bu config ile `exec` eder. Password yine Compose/container secret yüzeyidir; loga veya komut argümanına taşımayın. Redis healthcheck authentication kullanmalı, unauthenticated `PING` reddedilmelidir.

## Zorunlu deployment environment

Kök `.env.example` yalnız isim/shape şablonudur; gerçek değerleri secret manager veya orchestrator environment'ından sağlayın.

| Değişken | Sözleşme |
|---|---|
| `AWCENTER_RELEASE` | Tek kullanımlık release kimliği; commit SHA veya release ID |
| `AWCENTER_IMAGE` | Registry'deki immutable full reference; zorunlu `repository@sha256:<64-hex>` biçimi |
| `AWCENTER_HOST` | Public same-origin hostname |
| `SECRET_KEY` | Güçlü, placeholder olmayan secret |
| `DATABASE_URL` | PostgreSQL URL; Compose `database` servisine yönelir |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Database bootstrap; secret dışarıda tutulur |
| `REDIS_PASSWORD` | URL-safe, güçlü Redis authentication secret'ı; Compose cache URL'sine kapalı biçimde aktarılır |
| `MODEL_DIRECTORY` | Host model dizini; container'a read-only mount edilir |
| `TLS_CERTIFICATE_FILE`, `TLS_PRIVATE_KEY_FILE` | Public ingress TLS dosyaları |

Production default'ları:

- `DEBUG=False`
- authenticated `CACHE_URL=redis://:<REDIS_PASSWORD>@redis:6379/1`, Compose tarafından process environment'ında oluşturulur
- secure session/CSRF cookie, `SameSite=Lax`
- `TRUST_PROXY_HEADERS=True`, `TRUSTED_PROXY_COUNT=1`
- `SECURE_SSL_REDIRECT=True`, HSTS
- `PRIVATE_MEDIA_ROOT=/app/private_media`
- `AWCENTER_MAIL_TRANSPORT=django` veya `disabled`

Bir integration yalnız explicit `*_ENABLED=true` ile açılır. JIRA session encryption key ve upstream credential'lar secret'tır. ECR review state'i PostgreSQL'de durable'dır fakat publish/resume yalnız kullanıcıya bağlı ephemeral JIRA session ve `Idempotency-Key` ile yeni, server-owned fenced job başlatır; credential job payload'ına yazılmaz. `DOORS_ENABLED=true` yalnız tam yapılandırılmış Windows bridge ile geçerlidir. Production system checks HTTP integration URL'lerinde HTTPS, PostgreSQL, Redis, proxy trust, cookie ve bridge zorunluluklarını fail-closed doğrular.

Preflight `DATABASE_URL` değerini bundled topology'ye bağlar: host `database`, port varsayılan PostgreSQL portu, kullanıcı/veritabanı da `POSTGRES_USER`/`POSTGRES_DB` ile aynı olmalıdır. Ayrıca TLS certificate/private-key dosyaları ile model dizininin var, regular/non-symlink ve beklenen türde olmasını ister. Private key group/other permission bit'i taşıyamaz ve certificate ile aynı dosya olamaz. Bridge enabled ise ayrıca `COMPOSE_PROFILES=windows-bridge`, placeholder olmayan bridge hostname, trusted-proxy flag'i, CA dosyası ve listedeki her client fingerprint için geçerli SHA-256 biçimi zorunludur. Bridge disabled iken profile'ın açık kalması da reddedilir. `deployment_preflight.py` env dosyasını okuduktan sonra process environment değerlerini üstün kabul eder; operator, doğruladığı env dosyasını daha sonra fark edilmeyen shell override'larıyla değiştirmemelidir.

## Release evidence

CI aşağıdaki evidence'ı üretir ve release artifact olarak saklar:

- `release-manifest.json`: tracked source ve built frontend dosyaları için path, size, SHA-256; ayrıca reviewed frontend root/tree digest/file count;
- `sbom.cdx.json`: locked Python ve npm dependency'lerinden CycloneDX 1.5 SBOM;
- `image-build-metadata.json`: BuildKit resolved image digest ve build-result metadata'sı;
- `image-verification.json`: resolved image digest ve image içindeki frontend tree'nin reviewed artifact ile tam eşliği.

Local evidence üretimi clean Git worktree ister:

```bash
npm --prefix frontend ci
cd frontend
npx playwright install chromium
cd ..
npm --prefix frontend run test:e2e
npm --prefix frontend run build
export AWCENTER_RELEASE_EVIDENCE_ROOT=/srv/awcenter-release-evidence
printf '%s' "$AWCENTER_RELEASE" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
install -d -m 0750 "$AWCENTER_RELEASE_EVIDENCE_ROOT/$AWCENTER_RELEASE"
python scripts/build_release_metadata.py \
  --release "$AWCENTER_RELEASE" \
  --output "$AWCENTER_RELEASE_EVIDENCE_ROOT/$AWCENTER_RELEASE"
```

Playwright browser kurulumu host başına bir kez yeterlidir; CI `frontend/` içinde `npx playwright install --with-deps chromium` kullanır. Browser gate login/session akışına ek olarak `/app/task/ecr` üzerindeki explicit reconciliation resume davranışını da doğrular; build/container smoke'unun yerine geçmez.

Evidence output repository checkout'u dışında, erişim kontrollü operator storage'ında tutulur. Manifest, SBOM ve image-verification dosyaları mevcut bir evidence dosyasının üzerine yazmaz; aynı release kimliğini yeniden üretmek yerine yeni bir release kimliği kullanın. Deploy yalnız review edilmiş commit, başarılı frontend/browser kapıları, eşleşen manifest/SBOM, başarılı `image-verification.json` ve aynı digest'i taşıyan `AWCENTER_IMAGE` ile yapılır. Mutable tag production Compose contract'ında kabul edilmez. Dirty worktree için `--allow-dirty` production release sürecinde kullanılmaz.

`AWCENTER_IMAGE`, onaylı registry repository adı ile `image-verification.json.image_digest` değerinin `repository@sha256:...` biçiminde birleştirilmiş tam karşılığıdır. `verify_release_image.py`, BuildKit metadata'sındaki resolved digest'i kabul etmeden önce image içinden çıkarılan frontend ağacını hem review edilmiş `frontend/dist` hem schema-2 release manifest girdileriyle path/size/SHA-256 düzeyinde eşitler. Üretilen verification kaydı release, commit, manifest SHA-256, frontend tree/count ve image digest'i birlikte taşır:

```bash
python scripts/verify_release_image.py \
  --image-metadata image-build-metadata.json \
  --release-manifest release-metadata/release-manifest.json \
  --expected-dist frontend/dist \
  --image-dist image-frontend-dist \
  --output release-metadata/image-verification.json
```

Başka bir digest'e çözümlenen image deploy edilmez. Environment preflight yalnız biçim kontrolü yapmaz; kendisine verilen release manifest ile image verification dosyasının release/commit/manifest hash/frontend tree/count değerlerini ve `AWCENTER_IMAGE` digest'ini fail-closed eşleştirir.

## Fresh kurulum: ingress son gate

Operator-owned env dosyasını repository dışında tutun. Aynı shell boyunca preflight'tan geçmiş tek dosyayı Compose'a veren yardımcıyı kullanın; template placeholder'ları, mutable image reference'ı, bundled database topology'sinden sapan URL ve database password uyuşmazlığı fail-closed reddedilir:

```bash
export AWCENTER_DEPLOY_ENV_FILE=/etc/awcenter/production.env
export AWCENTER_RELEASE_EVIDENCE_DIRECTORY=/srv/awcenter-release-evidence/REPLACE_WITH_RELEASE_ID
python scripts/deployment_preflight.py \
  --env-file "$AWCENTER_DEPLOY_ENV_FILE" \
  --release-manifest "$AWCENTER_RELEASE_EVIDENCE_DIRECTORY/release-manifest.json" \
  --image-verification "$AWCENTER_RELEASE_EVIDENCE_DIRECTORY/image-verification.json"
awcenter_compose() {
  docker compose --env-file "$AWCENTER_DEPLOY_ENV_FILE" "$@"
}
awcenter_compose config --quiet
awcenter_compose config --services
awcenter_compose pull
```

State servislerini başlatın, fakat ingress'i açmayın:

```bash
awcenter_compose up -d --wait --wait-timeout 180 database redis
awcenter_compose ps database redis
```

Fresh PostgreSQL schema'yı one-shot container ile kurun ve salt-okunur deploy kontrollerini çalıştırın:

```bash
awcenter_compose run --rm --no-deps backend python manage.py migrate --noinput
awcenter_compose run --rm --no-deps backend python manage.py migrate --check
awcenter_compose run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING
awcenter_compose run --rm --no-deps backend python manage.py check_project_registry
awcenter_compose run --rm --no-deps backend python manage.py verify_frontend_artifact
```

İlk operator hesabını image'a veya migration'a seed etmeyin. İnteraktif one-shot command ile oluşturun; parola shell history'ye girmez:

```bash
awcenter_compose run --rm --no-deps backend python manage.py createsuperuser
```

Ingress kapalıyken ephemeral, exact-cleanup release smoke'larını çalıştırın. Core aşaması
session/CSRF, role-filtered proje kataloğu, CompDoc preview/confirm+lifecycle, gerçek DCC
DOCX executor'u ve owner-scoped private download sözleşmesini doğrular. Bu aşama
`MODEL_DIRECTORY/templates/<project>_dcc_template.docx` dosyasını gerçek worker ile
render eder; template eksik veya bozuksa yayın durur. Notification aşaması yalnız mail
secret'larına sahip notification-worker lifecycle'ı ile bir canary mesajı gönderir:

```bash
test -n "$AWCENTER_OPERATOR_USERNAME"
test -n "$AWCENTER_SMOKE_NOTIFICATION_RECIPIENT"
awcenter_compose run --rm --no-deps backend python manage.py run_release_smoke \
  --stage core \
  --project hys \
  --operator-username "$AWCENTER_OPERATOR_USERNAME" \
  --confirm-fresh-install
awcenter_compose run --rm --no-deps notification-worker python manage.py run_release_smoke \
  --stage notification \
  --operator-username "$AWCENTER_OPERATOR_USERNAME" \
  --notification-recipient "$AWCENTER_SMOKE_NOTIFICATION_RECIPIENT" \
  --confirm-fresh-install
```

Komut, canonical business tablolarda veri varsa çalışmayı reddeder; mevcut production'a
karşı bir sentetik-data temizleme aracı değildir. Canary alıcısı kontrollü bir operasyon
mailbox'ı olmalıdır. Her iki aşama geçmeden internal servisleri veya ingress'i başlatmayın.

Internal process'leri başlatıp health contract'larını doğrulayın:

```bash
awcenter_compose up -d --wait --wait-timeout 180 \
  backend worker notification-worker cleanup-worker
awcenter_compose exec -T backend curl -fsS \
  -H 'Host: backend' \
  -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8000/health/ready/
awcenter_compose exec -T worker python manage.py check_job_worker_health \
  --worker-id-file /tmp/awcenter-job-worker.id
awcenter_compose ps backend worker notification-worker cleanup-worker
```

Yalnız tüm komutlar başarılı ve lifecycle'lar healthy ise public ingress'i açın:

```bash
awcenter_compose up -d --wait --wait-timeout 180 ingress
curl -fsS "https://$AWCENTER_HOST/health/ready/"
curl -fsS "https://$AWCENTER_HOST/app/" >/dev/null
```

Windows bridge etkinse public gate'ten bağımsız olarak [windows-bridge.md](windows-bridge.md) kontrollerini tamamladıktan sonra açın:

```bash
awcenter_compose --profile windows-bridge up -d --wait --wait-timeout 180 \
  windows-bridge-ingress
```

`docker compose up -d` komutunu service adı vermeden ilk bootstrap adımı olarak kullanmayın; ingress migration/readiness'ten önce açılmamalıdır.

## Upgrade: backup, migration ve atomic ingress gate

Yeni image ve evidence'ı trafik açıkken hazırlayın. Operator env dosyasında `AWCENTER_RELEASE` ve evidence ile eşleşen digest-pinned `AWCENTER_IMAGE` değerlerini güncelleyin; maintenance window'dan önce preflight ve pull'u tamamlayın:

```bash
export AWCENTER_DEPLOY_ENV_FILE=/etc/awcenter/production.env
export AWCENTER_RELEASE_EVIDENCE_DIRECTORY=/srv/awcenter-release-evidence/REPLACE_WITH_RELEASE_ID
python scripts/deployment_preflight.py \
  --env-file "$AWCENTER_DEPLOY_ENV_FILE" \
  --release-manifest "$AWCENTER_RELEASE_EVIDENCE_DIRECTORY/release-manifest.json" \
  --image-verification "$AWCENTER_RELEASE_EVIDENCE_DIRECTORY/image-verification.json"
awcenter_compose() {
  docker compose --env-file "$AWCENTER_DEPLOY_ENV_FILE" "$@"
}
awcenter_compose pull
```

Schema geçişine başlamadan önce maintenance window açın. Önce public ingress'i kapatıp yeni browser/API job create isteklerini kesin; retention ve notification lifecycle'larını durdurun, fakat mevcut local/Windows claim'lerinin tamamlanabilmesi için backend, job worker ve bridge ingress'i çalışır bırakın:

```bash
awcenter_compose stop ingress
awcenter_compose stop notification-worker cleanup-worker
```

Bu noktada yeni browser password-reset request'i gelemez; henüz gönderilmemiş `PasswordResetDelivery` satırları PostgreSQL'de durable kalır ve yeni notification worker tarafından lease ile devam ettirilir. Token/link üretimini elle tekrarlamayın veya outbox satırını doğrudan terminal duruma çekmeyin.

Queued/running/cancel-requested işler sıfırlanana kadar drain edin. Belirsiz bir external-write sonucu otomatik retry edilmez. DOORS write ve `automations.publish_ecr_jira` reconciliation kayıtlarının sayısını maintenance kaydına alın; dış sistem sonucu doğrulanmadan aynı write'ı yeniden göndermeyin. Terminal reconciliation kaydı tek başına schema migration'ı bloke etmez:

```bash
awcenter_compose exec -T backend python manage.py shell -c \
  "from jobs.models import Job, JobStatus; active=Job.objects.filter(status__in=[JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED]); uncertain=Job.objects.filter(kind__in=['automations.publish_ecr_jira','doors.update_object','doors.create_object'], status=JobStatus.RECONCILIATION_REQUIRED); counts={'active': active.count(), 'external_reconciliation': uncertain.count()}; print(counts); assert counts['active'] == 0"
```

ECR reconciliation kaydı yeni image'da da otomatik alınmaz. Operator/provider marker durumunu doğruladıktan ve kullanıcı JIRA session'ını yeniden bağladıktan sonra owner `/api/workflows/ecr/<uuid>/resume/` üzerinden yeni `Idempotency-Key` ile explicit attempt başlatır.

Gate sıfır döndüğünde artık yeni claim alınamaz; bridge ingress, worker ve backend'i sırasıyla durdurun:

```bash
awcenter_compose --profile windows-bridge stop windows-bridge-ingress
awcenter_compose stop worker backend
```

PostgreSQL dump ve private artifact snapshot aynı write-free window'dan alınmalıdır. Örnek Linux operator akışı:

```bash
export AWCENTER_BACKUP_ROOT=/srv/awcenter-backups
test "${AWCENTER_BACKUP_ROOT#/}" != "$AWCENTER_BACKUP_ROOT"
export AWCENTER_BACKUP_ID=REPLACE_WITH_CURRENT_RELEASE-pre-REPLACE_WITH_TARGET_RELEASE
printf '%s' "$AWCENTER_BACKUP_ID" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
AWCENTER_BACKUP_DIRECTORY="$AWCENTER_BACKUP_ROOT/$AWCENTER_BACKUP_ID"
install -d -m 0700 "$AWCENTER_BACKUP_DIRECTORY"
awcenter_compose exec -T database sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "$AWCENTER_BACKUP_DIRECTORY/postgresql.dump"
awcenter_compose run --rm --no-deps -T --entrypoint python backend -c \
  'import sys,tarfile; archive=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); archive.add("/app/private_media",arcname="private_media"); archive.close()' \
  > "$AWCENTER_BACKUP_DIRECTORY/private-media.tar.gz"
sha256sum "$AWCENTER_BACKUP_DIRECTORY/postgresql.dump" \
  "$AWCENTER_BACKUP_DIRECTORY/private-media.tar.gz" \
  > "$AWCENTER_BACKUP_DIRECTORY/SHA256SUMS"
```

`AWCENTER_BACKUP_ROOT` repository checkout'u veya launcher package alanı dışında, yalnız operator tarafından okunabilen absolute bir dizin olmalıdır. Backup dosyalarını ayrıca host dışında şifreli ve erişim kontrollü storage'a kopyalayın; restore drill ile periyodik olarak doğrulayın. Database ve private artifact snapshot'ı bir çifttir.

Redis authoritative business/job/ECR review state'i değildir ve bu restore çiftinin parçası olarak geri yüklenmez. JIRA oturumları, probe cache'i ve tek kullanımlık bridge capability'leri upgrade/DR sonrasında kaybolabilir; ECR publish/resume öncesi kullanıcı JIRA'yı yeniden bağlar ve agent yeni claim alır. Drain tamamlanmadan Redis'i silmeyin veya değiştirmeyin.

Yeni image ile one-shot migration ve gate'leri çalıştırın:

```bash
awcenter_compose run --rm --no-deps backend python manage.py migrate --noinput
awcenter_compose run --rm --no-deps backend python manage.py migrate --check
awcenter_compose run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING
awcenter_compose run --rm --no-deps backend python manage.py check_project_registry
awcenter_compose run --rm --no-deps backend python manage.py verify_frontend_artifact
```

Ardından internal process'leri başlatın ve health gate'lerini bekleyin:

```bash
awcenter_compose up -d --wait --wait-timeout 180 \
  backend worker notification-worker cleanup-worker
awcenter_compose exec -T backend curl -fsS \
  -H 'Host: backend' \
  -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8000/health/ready/
awcenter_compose exec -T worker python manage.py check_job_worker_health \
  --worker-id-file /tmp/awcenter-job-worker.id
```

Readiness/worker gate'leri başarılı olduktan sonra ve en son ingress'i açıp external smoke'u çalıştırın:

```bash
awcenter_compose up -d --wait --wait-timeout 180 ingress
curl -fsS "https://$AWCENTER_HOST/health/ready/"
curl -fsS "https://$AWCENTER_HOST/app/" >/dev/null
```

Bridge etkin deployment'ta dedicated ingress'i ayrıca yeniden başlatın ve onaylı external agent release'inin mTLS status/claim smoke'unu tamamlayın:

```bash
awcenter_compose --profile windows-bridge up -d --wait --wait-timeout 180 \
  windows-bridge-ingress
```

Herhangi bir gate başarısızsa ilgili ingress kapalı kalır.

## Forward-fix ve restore politikası

- Migration'lar forward-only'dir. Uygulama write kabul ettikten sonra eski image/schema'ya dönmeyin.
- Hata migration veya startup gate sırasında, write açılmadan oluştuysa ingress'i kapalı tutun; root cause'u düzeltip yeni corrective image/migration üretin.
- Hata trafik açıldıktan sonra görülürse write'ı tekrar durdurun, yeni backup alın ve forward-fix deploy edin.
- Database restore yalnız disaster recovery kararıyla, tüm writer'lar durmuşken ve eşleşen private artifact snapshot'ıyla yapılır. Tek taraflı DB veya file restore owner/hash referanslarını bozabilir.
- Restore edilen çift yeni bir release sayılmaz: aynı digest-pinned image/evidence, deploy checks, readiness, worker health ve smoke gate'leri yeniden geçmeden ingress açılmaz.
- Migration history'yi elle değiştirmeyin, migration'ı fake etmeyin ve production database'i local reset prosedürüyle sıfırlamayın.

## Health ve gözlemlenebilirlik

- `/health/live/`: Django request process'i cevaplıyor mu; dependency ayrıntısı vermez.
- `/health/ready/`: database, Redis cache ve frontend artifact hazır mı; herhangi biri başarısızsa 503.
- Job worker: database heartbeat + container-local worker identity file.
- Notification worker: password-reset ve compliance kuyruklarının başarılı pass'i sonrası heartbeat file; cleanup da kendi başarılı pass'i sonrası heartbeat file yazar. Compose stale threshold ile health verir.
- Public ve bridge Nginx container healthcheck'i yalnız loopback `127.0.0.1:8080/nginx-ready` üzerinden backend readiness'i proxy eder; bu listener hosta publish edilmez ve public TLS/mTLS doğrulamasını gevşetmez.
- Loglar JSON stdout'dur ve `request_id`, seviye, logger ve bounded operational alanlar taşır.

Readiness upstream URL, credential veya private path döndürmez. Integration health kullanıcı-authenticated catalog/probe üzerinden ve timeout/circuit-breaker ile değerlendirilir.

## Retention ve private state

`cleanup-worker` varsayılan beş dakikalık aralıkla:

- expired unconfirmed preview'ları;
- `JOB_ARTIFACT_RETENTION_DAYS` süresini aşmış succeeded, failed, cancelled veya reconciliation-required job kayıtlarını ve bağlı private artifact'ları temizler.

Backend, worker ve cleanup aynı `private-artifacts:/app/private_media` volume'unu mount eder. Volume'u Nginx, CDN veya object listing ile yayınlamayın. Retention değerini en az bir gün tutan code contract'ını operasyonel ihtiyaçla hizalayın.

## Production validation özeti

```bash
export AWCENTER_DEPLOY_ENV_FILE=/etc/awcenter/production.env
export AWCENTER_RELEASE_EVIDENCE_DIRECTORY=/srv/awcenter-release-evidence/REPLACE_WITH_RELEASE_ID
python scripts/deployment_preflight.py \
  --env-file "$AWCENTER_DEPLOY_ENV_FILE" \
  --release-manifest "$AWCENTER_RELEASE_EVIDENCE_DIRECTORY/release-manifest.json" \
  --image-verification "$AWCENTER_RELEASE_EVIDENCE_DIRECTORY/image-verification.json"
awcenter_compose() {
  docker compose --env-file "$AWCENTER_DEPLOY_ENV_FILE" "$@"
}
awcenter_compose run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING
awcenter_compose run --rm --no-deps backend python manage.py migrate --check
awcenter_compose run --rm --no-deps backend python manage.py check_project_registry
awcenter_compose run --rm --no-deps backend python manage.py verify_frontend_artifact
awcenter_compose exec -T worker python manage.py check_job_worker_health \
  --worker-id-file /tmp/awcenter-job-worker.id
curl -fsS "https://$AWCENTER_HOST/health/ready/"
```
