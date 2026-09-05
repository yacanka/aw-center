# Local database reset

Bu runbook yalnız disposable local development state'i içindir. Shared, staging veya production database/volume üzerinde kullanmayın. Production'da [deployment.md](deployment.md) backup ve forward-fix prosedürü uygulanır.

Migration baseline fresh database contract'ıdır; önceki local schema'yı dönüştüren bir geçiş hattı yoktur. Korunması gereken yerel veri varsa reset yerine export/backup ihtiyacını ayrıca değerlendirin.

## Reset öncesi kontrol

Hangi environment'ın aktif olduğunu, credential değerlerini terminale dökmeden doğrulayın:

```bash
.venv/bin/python backend/manage.py shell -c \
  "from django.conf import settings; db=settings.DATABASES['default']; print({'debug': settings.DEBUG, 'db_engine': db['ENGINE'], 'db_host_configured': bool(db.get('HOST')), 'cache_backend': settings.CACHES['default']['BACKEND'], 'private_media_is_repo_local': settings.PRIVATE_MEDIA_ROOT.resolve().is_relative_to(settings.BASE_DIR.resolve())})"
```

Bu çıktı yalnız güvenli sınıflandırma sinyalleridir; verinin disposable olduğunu kanıtlamaz. Aktif deployment bağlamını, Compose project adını ve volume sahipliğini ayrıca doğrulayın. Production/shared olma ihtimali veya tanımadığınız volume varsa durun. Reset aynı anda database, Redis cache ve private artifact referanslarını etkileyebilir.

## Compose ile fresh PostgreSQL + Redis

Bu yol local container topolojisini tamamen sıfırlar. Aşağıdaki `down --volumes` komutu Compose projesine ait PostgreSQL, Redis ve private artifact named volume'larını geri dönüşsüz siler.

Repository kökünde, yalnız bu disposable instance için kullanılan env dosyası ve explicit Compose project adıyla ilerleyin. Production preflight burada da placeholder secret, mutable image ve database password uyuşmazlığını reddeder:

```bash
export AWCENTER_LOCAL_COMPOSE_ENV_FILE=/absolute/path/awcenter-local.env
export AWCENTER_LOCAL_COMPOSE_PROJECT=awcenter-local
export AWCENTER_LOCAL_RELEASE_EVIDENCE_DIRECTORY=/absolute/path/release-evidence/REPLACE_WITH_RELEASE_ID
python scripts/deployment_preflight.py \
  --env-file "$AWCENTER_LOCAL_COMPOSE_ENV_FILE" \
  --release-manifest "$AWCENTER_LOCAL_RELEASE_EVIDENCE_DIRECTORY/release-manifest.json" \
  --image-verification "$AWCENTER_LOCAL_RELEASE_EVIDENCE_DIRECTORY/image-verification.json"
awcenter_local_compose() {
  docker compose \
    --project-name "$AWCENTER_LOCAL_COMPOSE_PROJECT" \
    --env-file "$AWCENTER_LOCAL_COMPOSE_ENV_FILE" \
    "$@"
}
```

Bu production-benzeri Compose reset'i için local env gerçek ve eşleşen digest evidence'ı, non-placeholder hostname, regular TLS certificate, group/other permission bit'i olmayan private key ile mevcut AI model ve document template dizinlerini göstermelidir. Bu girdileri atlamak için preflight'ı bypass etmeyin; daha hafif host geliştirme ihtiyacında aşağıdaki SQLite convenience yolunu kullanın.

Önce hedefi görün:

```bash
awcenter_local_compose config --services
awcenter_local_compose ps -a
docker volume ls \
  --filter "label=com.docker.compose.project=$AWCENTER_LOCAL_COMPOSE_PROJECT"
```

Verinin disposable olduğundan emin olduktan sonra:

```bash
awcenter_local_compose down --volumes --remove-orphans
awcenter_local_compose up -d --wait --wait-timeout 180 database redis
awcenter_local_compose run --rm --no-deps backend python manage.py migrate --noinput
awcenter_local_compose run --rm --no-deps backend python manage.py migrate --check
awcenter_local_compose run --rm --no-deps backend python manage.py check_project_registry
awcenter_local_compose run --rm --no-deps backend python manage.py check --deploy --fail-level WARNING
```

Local operator hesabını one-shot oluşturun:

```bash
awcenter_local_compose run --rm --no-deps backend python manage.py createsuperuser
```

Internal service'leri ve son olarak ingress'i başlatın:

```bash
awcenter_local_compose up -d --wait --wait-timeout 180 \
  backend worker notification-worker cleanup-worker
awcenter_local_compose exec -T backend curl -fsS \
  -H 'Host: backend' \
  -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8000/health/ready/
awcenter_local_compose exec -T worker python manage.py check_job_worker_health \
  --worker-id-file /tmp/awcenter-job-worker.id
awcenter_local_compose up -d --wait --wait-timeout 180 ingress
```

Compose database'ini yine container environment'ı üzerinden doğrulayın; host `backend/.env` profili farklı bir database'e işaret edebilir:

```bash
awcenter_local_compose exec -T backend python manage.py check
awcenter_local_compose exec -T backend python manage.py migrate --check
awcenter_local_compose exec -T backend python manage.py check_project_registry
awcenter_local_compose exec -T backend python manage.py shell -c \
  "from orgs.models import Project; assert Project.objects.count() == 8"
```

## Local SQLite convenience profile

`backend/.env.development` SQLite kullanıyorsa dosyayı silmek yerine recoverable bir adla taşıyın. Django/worker process'leri önce durdurun:

```bash
cd backend
mv db.sqlite3 "db.sqlite3.pre-reset.$(date +%Y%m%d-%H%M%S)"
mv private_media "private_media.pre-reset.$(date +%Y%m%d-%H%M%S)"
mkdir -p private_media
../.venv/bin/python manage.py migrate --noinput
../.venv/bin/python manage.py migrate --check
../.venv/bin/python manage.py check_project_registry
../.venv/bin/python manage.py createsuperuser
```

`db.sqlite3` veya `private_media` yoksa ilgili `mv` komutunu atlayın. Eski DB ile yeni private directory'yi ya da yeni DB ile eski private directory'yi karıştırmayın; job file referansları tutarsız olur.

Rollback gerekirse tüm local process'leri durdurun, yeni oluşturulan DB/private directory'yi ayrı bir yere taşıyın ve aynı timestamp'e ait eski çifti birlikte geri adlandırın.

## SQLite reset sonrası doğrulama

Bu komutlar yalnız yukarıdaki host SQLite yolunu doğrular; Compose PostgreSQL doğrulaması için container komutlarını kullanın.

```bash
cd backend
../.venv/bin/python manage.py check
../.venv/bin/python manage.py migrate --check
../.venv/bin/python manage.py check_project_registry
../.venv/bin/python manage.py shell -c \
  "from orgs.models import Project; assert Project.objects.count() == 8"
cd ..
python launcher.py check
```

Fresh migration canonical project satırlarını seed eder. Ayrı bir runtime project-sync adımı yoktur.

## Yapılmaması gerekenler

- Shared/production PostgreSQL volume'unu `down --volumes` ile silmek.
- Migration table'ını elle düzenlemek veya migration'ı fake etmek.
- Eski schema dump'ını fresh baseline üstüne kısmi import etmek.
- Database backup ile private artifact snapshot'ını farklı zamanlardan eşleştirmek.
- Reset'i data migration/upgrade mekanizması olarak sunmak.
