# AW Center coding agent rehberi

## Değişiklik yapılacak yerler

- Django kaynakları `backend/` altındadır. Proje ayarları ve kök URL sözleşmesi `backend/awcenter/`, yeniden kullanılabilir CompDoc davranışı `backend/common/`, ürün entegrasyonları kendi Django app'leri, proje varyantları ise `backend/projects/<slug>/` içindedir.
- Projeler arası CompDoc model, serializer, view veya workflow davranışını proje app'lerine kopyalama; ortak factory/service'i `backend/common/` içinde değiştir, proje app'lerini ince adapter olarak tut. Gerçekten proje-özel olan davranış ilgili `backend/projects/<slug>/` altında kalmalıdır.
- Teknik proje metadata'sının kaynağı `backend/projects/registry.py` dosyasıdır. `orgs.Project` bunun iş verisi karşılığıdır ve ortak anahtar `slug` değeridir. Route'lar yalnız etkin registry kayıtlarından `backend/projects/routing.py` ile üretilir.
- Vue kaynakları `frontend/src/` altındadır. Route'lar `router/routes.ts`, erişim kararları `services/accessPolicy.ts`, HTTP/CSRF varsayılanları `services/http.ts` içindedir. Yeni entegrasyon state'i ve API kodunu ilgili domain Pinia store/service modülünde tut.
- Kök `launcher.py` yalnız giriş noktasıdır; launcher davranışını `scripts/launcher/` içinde, testlerini `scripts/test_launcher*.py` içinde değiştir.

## Korunacak mimari ve API sözleşmeleri

- DRF varsayılanı `IsAuthenticated` ve browser kimlik doğrulaması HttpOnly token cookie + CSRF'dir. Public endpoint'i yalnız bilinçli olarak `AllowAny` yap; cookie ile gelen unsafe isteklerdeki CSRF kontrolünü veya frontend'deki `withCredentials`/XSRF ayarlarını devre dışı bırakma.
- Frontend route ve navigasyon erişimi aynı `RouteAccessPolicy` kararlarını kullanır; açıkça `public` olmayan route authenticated kabul edilir. Hassas bir ekran eklerken route, `services/accessPolicy.ts`, menü/komut görünürlüğü ve `scripts/test-route-access.mjs` kontrollerini birlikte güncelle.
- Yeni API hata yolları ortak `{ detail, code, ... }` sözleşmesini ve mümkün olduğunda `request_id` değerini korumalıdır. Backend'de `awcenter.api_errors`, frontend'de `services/apiError.ts` üzerinden ilerle; hassas exception veya credential ayrıntısını response'a/loga koyma.
- Upload endpoint'lerinde uzantı, boyut, imza ve arşiv güvenliğini `awcenter.file_security` politikalarıyla uygula; yalnız istemci MIME tipine veya dosya adına güvenme. Job input/output dosyalarını public `MEDIA_ROOT` altına taşıma: `PRIVATE_MEDIA_ROOT`, owner-scoped yollar, hash doğrulaması ve yetkili download view sözleşmesini koru.
- Mevcut durable job akışlarında job kind'ı; create endpoint, `jobs.worker.get_executor` allowlist'i, idempotency key, lease/cancellation, progress ve private artifact yaşam döngüsüyle birlikte ele al. Worker state değişikliklerindeki `transaction.atomic`/`select_for_update` korumalarını kaldırma.
- CompDoc import, lifecycle, review, bulk işlem ve notification akışlarında kullanılan optimistic version/confirmation token, audit/history ve transaction sınırlarını koru. Model save metodunu veya service katmanını atlayan toplu update'lerin türetilmiş `status`, tarih, cover-page ve history alanlarını bozmadığını doğrula.
- Registry capability değişikliği bir backend/frontend contract değişikliğidir. `backend/projects/constants.py`, registry ve invariant/API testleri ile `frontend/src/models/projectRegistry.ts`, fallback/consumer kodunu aynı değişiklikte hizala. Internal app label, template, JIRA veya filesystem metadata'sını registry API'ye açma.

## Kod ve dosya convention'ları

- Backend'de mevcut Django/DRF app organizasyonunu ve yakındaki Python stilini izle. Repository'de Python formatter, linter veya type-checker yapılandırılmamıştır; toplu biçimlendirme yapma.
- Frontend'de yeni kod için TypeScript, Vue SFC'lerde `<script setup lang="ts">`, `@/` alias'ı ve mevcut service/composable/store ayrımını kullan. Entegrasyon state'ini çapraz-domain bir API store facade'ında toplama.
- Frontend biçimi `frontend/.prettierrc` ile tanımlıdır. Naive UI template bileşeni eklenirse `frontend/src/plugins/naiveUi.ts` kaydını ve UI registration testini güncelle; üretim build'inin bundle budget kontrolünü koru.
- Backend testleri ilgili app yanında `test*.py`/`tests/` altında Django `TestCase` ailesiyle; frontend regresyon testleri `frontend/scripts/test-*.mjs` altında Node test runner ile tutulur. Değişen contract'a en yakın testi güncelle veya ekle.
- Model değişikliklerinde mevcut numaralı migration'ları yeniden yazma; yeni migration üret. `CompDocBase` gibi ortak abstract modellerde değişiklik her concrete proje app'inde migration gerektirebilir; tüm proje app'lerini migration kontrolüne dahil et.

## Bağımlılıklar, config ve üretilmiş dosyalar

- Python bağımlılığını `requirements.in` içinde değiştir, ardından `pip-compile requirements.in` ile üretilen `requirements.txt` dosyasını yenile; lock dosyasını elle düzenleme. Launcher ve dependency manifest'i CPython 3.11+ kabul eder ve backend kodu 3.11 uyumunu korumalıdır.
- Frontend bağımlılıklarının kaynağı `frontend/package.json` ve `frontend/package-lock.json` dosyalarıdır; kurulumu `npm ci` ile yap. Kök `package.json` yalnız frontend komutlarını proxy eder. Fresh checkout kurulumu için kökten `python launcher.py setup` kullan; tek taraflı kurulumda `--skip-backend`/`--skip-frontend` seçenekleri vardır.
- Gerçek secret/credential, yerel endpoint, sertifika, database veya kullanıcı verisi commit etme. Yerel seçim dosyası `backend/.env` git dışıdır; yoksa `backend/.env.example` dosyasından oluştur, mevcut yerel dosyanın üzerine yazma. Güvenli varsayımlar `backend/.env.development`, production şablonları `backend/.env.production` ve kök `.env.example` dosyasında tutulur.
- `frontend/dist/`, `backend/core/assets/`, `backend/static/`, `backend/staticfiles/`, `backend/templates/index.html`, `.runtime/`, media/private-media/model dizinleri ve SQLite dosyaları üretilmiş veya yerel state'tir; kaynak gibi elle düzenleme veya commit etme. SPA shell kaynağı `frontend/src/`, Django shell-serving kodu `backend/core/` kökündeki Python dosyalarıdır.
- Migration veya veri senkronizasyonu otomatik değildir. `python launcher.py check`, `dev` ve `prod` veritabanını değiştirmez; migration ancak açık `--migrate` veya doğrudan `manage.py migrate` ile uygulanır. `sync_projects` veri yazar; agent doğrulamasında varsayılan olarak `sync_projects --dry-run` kullan.

## Doğrulama komutları

Repository kökünden temel kapılar:

```bash
python launcher.py check
python launcher.py test
```

Değişiklik kapsamına göre daha dar veya ek kontroller:

```bash
# Backend (backend/ içinden)
../.venv/bin/python manage.py test <app_veya_test_labeli>
../.venv/bin/python manage.py check
../.venv/bin/python manage.py makemigrations --check --dry-run
../.venv/bin/python manage.py migrate --check

# Frontend (repository kökünden)
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run test:ci
npm --prefix frontend run build

# Launcher
.venv/bin/python -m unittest scripts.test_launcher scripts.test_launcher_jobs
```

- Model/registry değişikliğinde backend tam testine ek olarak `manage.py check_project_registry` ve `manage.py sync_projects --dry-run` çalıştır.
- Frontend artifact serving, Vite base/chunking, static ayarları veya container değişikliğinde frontend build'den sonra `backend/` içinde `../.venv/bin/python manage.py collectstatic --noinput` ve `../.venv/bin/python manage.py verify_frontend_artifact` çalıştır. Container/deployment değişikliğinde ayrıca kök `backend/Dockerfile`, `docker-compose.yml`, `deploy/nginx/awcenter.conf` ve `.github/workflows/ci.yml` sözleşmelerini birlikte kontrol et.
