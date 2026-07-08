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

- **DCC / ECD yönetimi:** JIRA tabanlı Design Change Control kayıtlarını izleme, oluşturma, güncelleme, değerlendirme, e-posta gönderimi ve belge üretimi.
- **DDF ve CompDoc takibi:** Proje bazlı compliance document listeleri, Excel içe aktarma, önizleme/onay akışı, alan keşfi, dinamik kolon ayarları, grafikler ve durum takibi.
- **JIRA otomasyonları:** JIRA issue arama, issue detay okuma, subtask üretimi, Excel tabanlı toplu subtask üretimi ve akış durumlarının SSE ile canlı izlenmesi.
- **DOORS otomasyonları:** Excel verisinden DXL script üretimi, DOORS çalıştırma entegrasyonu ve PoC linkleme ekranları.
- **Doküman karşılaştırma:** Excel, Word ve PDF karşılaştırma araçları.
- **Word işleme:** Word compare, analyze ve translate kuyrukları.
- **PDF işleme:** PDF bölme ve PDF karşılaştırma.
- **Outlook `.msg` işlemleri:** E-posta parse etme, ekleri indirme ve ECR/task ekranları.
- **PowerPoint gallery:** Sunum ve slayt yükleme, listeleme, görsel önizleme ve dış dönüşüm araçlarıyla galeri oluşturma.
- **Medya dönüştürme:** FFmpeg tabanlı görüntü/ses/video dönüştürme, önizleme ve çıktı boyutu tahmini.
- **Organizasyon yönetimi:** Proje, panel, sorumlu ve kişi kayıtlarının CRUD yönetimi ve kişi Excel yükleme.
- **Kullanıcı ve yetki yönetimi:** Login/logout, HttpOnly token cookie, CSRF koruması, parola değiştirme, parola sıfırlama, kullanıcı tercihleri ve izin listesi.
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
- **Varsayılan yetki:** DRF için global `IsAuthenticated`.
- **Veritabanı:** Varsayılan olarak SQLite (`backend/db.sqlite3`) ve eski veri için ikinci SQLite bağlantısı (`backend/db_old.sqlite3`).
- **Statik dosyalar:** `/core/` URL kökü ve WhiteNoise `CompressedManifestStaticFilesStorage`.
- **Medya dosyaları:** `backend/media`.
- **Production güvenliği:** `DEBUG=False` iken HTTPS redirect, secure cookie, HSTS, content-type nosniff, same-origin referrer policy ve `X_FRAME_OPTIONS="DENY"` aktif olur.

### Frontend

- **Framework:** Vue 3 + Vite + TypeScript.
- **UI:** Naive UI.
- **State:** Pinia.
- **Router:** Vue Router, browser history kökü `/app/`.
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
- DCC dokümanı oluşturma ve indirme bağlantısı üretme.
- ECD dosyası yükleme ve assessment işlemleri.
- DCC reminder/e-posta gönderimi.
- Uzun süren DCC, subtask ve Excel subtask operasyonları için SSE progress stream.
- JIRA dynamic field metadata okuma.
- JIRA session kontrolü ve attachment ekleme.
- Proje registry üzerinden JIRA component -> proje eşleştirme.
- DCC template dosyalarının güvenli path resolver ile çözülmesi.

Önemli endpoint örnekleri:

- `GET/POST /dcc/api/`
- `GET/PUT/DELETE /dcc/api/<id>/`
- `GET /dcc/issues/`
- `POST /dcc/create_issue/`
- `POST /dcc/send_mail/`
- `POST /dcc/upload/`
- `GET /dcc/create_dcc_stream/<uuid>/`
- `GET /dcc/create_subtask_stream/<uuid>/`
- `GET /dcc/create_subtask_excel_stream/<uuid>/`
- `GET /dcc/subtask_fields/`

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
- Excel import önizleme ve kullanıcı onayı sonrası kayıt.
- Eksik kolon, unmapped kolon ve satır validation uyarılarını gösterme.
- Server-side pagination ve filtreleme.
- DocProof arama entegrasyonu.
- Durum akışı ve gecikme göstergeleri.
- Cover page üretimi.
- Doküman analiz ekranı.

Proje bazlı CompDoc route'ları registry ile etkin projeler için bağlanır: `ozgur`, `piku`, `aesa`, `havasoj`, `hys`, `blok30`.

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
- `POST /excel/create_queue/`
- `GET /excel/excel_to_cover_pages_stream/<uuid>/`

### 7. Word Araçları

Backend route kökü: `/word/`
Frontend ekranları: `/app/compare/word`, `/app/translator`

Özellikler:

- Word doküman karşılaştırma.
- Word analiz kuyruğu.
- Word çeviri kuyruğu.
- Uzun süren analyze/translate akışlarını UUID üzerinden takip etme.
- Opsiyonel NLP paketleri varsayılan güvenli kurulumdan çıkarılmıştır; ilgili özellik çağrıldığında runtime bağımlılık ihtiyacı kontrollü hata mesajıyla bildirilir.

Endpointler:

- `POST /word/compare/`
- `POST /word/create_queue/`
- `GET /word/translate/<uuid>/`
- `GET /word/analyze/<uuid>/`

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

- Outlook `.msg` dosyasını parse etme.
- E-posta eklerini indirme.
- ECR task ekranı.
- ECR upload popup bileşenleri.

Endpointler:

- `POST /outlook/msg/parse/`
- `POST /outlook/msg/download/`

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
Frontend ekranları: `/app/login`, `/app/users`, `/app/profile`, `/app/settings`

Özellikler:

- Token tabanlı login.
- HttpOnly auth cookie.
- CSRF token cookie ve unsafe method'lar için `X-CSRFToken` gönderimi.
- Logout sırasında server token silme ve cookie temizleme.
- Stale cookie recovery.
- `/auth/me/` ile oturum bootstrap.
- Kullanıcı CRUD.
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

Kök dizindeki `launcher.py`, projenin önerilen ana komut yüzeyidir. Amaç; farklı işletim sistemlerinde tek komutla bağımlılık kurmak, offline paket hazırlamak, backend/frontend kontrollerini çalıştırmak, geliştirme sunucularını başlatmak ve değişiklik/offline paketleri ZIP olarak taşınabilir hale getirmektir.

### Neden Launcher Var?

- Backend ve frontend komutlarını tek yerde standartlaştırır.
- `.venv` Python sürümünü kontrol eder.
- Shell string kullanmadan subprocess çalıştırır; komut enjeksiyonu riskini azaltır.
- `.venv` içinden yanlış working directory ile komut çalıştırmayı engeller.
- Online/offline kurulum akışını aynı arayüzden yönetir.
- Geliştirme sunucuları için port çakışmalarını algılar ve boş port seçer.
- Frontend `.env.local` dosyasına seçilen backend URL'lerini yazar.

### Gereksinimler

- Python **3.11+**.
- Node.js ve npm.
- Backend için `requirements.txt`.
- Frontend için `frontend/package-lock.json` bulunduğundan launcher `npm ci` kullanır.

Windows örneği:

```powershell
py -3.11 launcher.py all
```

Linux/macOS örneği:

```bash
python3.11 launcher.py all
```

### Komut Özeti

| Komut | Amaç |
|---|---|
| `prepare-offline` | Python wheel'larını indirir ve npm cache'i ısıtır. |
| `package-offline` | Offline kurulum için gerekli proje dosyalarını ve paketleri ZIP'e koyar. |
| `package-changes` | Git değişikliklerini ZIP olarak paketler. |
| `install` | Backend ve frontend bağımlılıklarını kurar. |
| `check` | Backend ve frontend doğrulamalarını çalıştırır. |
| `all` | Önce install, sonra check çalıştırır. |
| `run` | Varsayılan olarak backend ve frontend geliştirme sunucularını; `--profile production` ile Cheroot tabanlı production HTTPS serverını başlatır. |

### En Sık Kullanılan Akışlar

İlk kurulum ve doğrulama:

```bash
python launcher.py all --mode online
```

Otomatik online/offline tespiti:

```bash
python launcher.py all --mode auto
```

Sadece bağımlılık kurulumu:

```bash
python launcher.py install
```

Sadece kontroller:

```bash
python launcher.py check
```

Backend ve frontend geliştirme sunucularını başlatma:

```bash
python launcher.py run
```

Port seçerek çalıştırma:

```bash
python launcher.py run --host 127.0.0.1 --backend-port 8000 --frontend-port 5173
```

Production profiliyle çalıştırma:

```bash
python launcher.py run --profile production --host 0.0.0.0 --backend-port 8443
```

Production profili geliştirme serverı kullanmaz. Launcher `backend/.env` dosyasında `DEBUG=False`, `IPV4_ADDRESS` ve `PORT` değerlerini günceller; `manage.py check --deploy`, `manage.py migrate --check` ve `collectstatic --noinput` kontrollerini çalıştırır; ardından `backend/run_cheroot.py` üzerinden HTTPS Cheroot WSGI serverını başlatır. Bu profil başlamadan önce `backend/AWCenter.crt`, `backend/AWCenter.key` ve `frontend/dist` build çıktılarının varlığını doğrular.

Sadece backend:

```bash
python launcher.py install --skip-frontend
python launcher.py check --skip-frontend
python launcher.py run --skip-frontend
```

Sadece frontend:

```bash
python launcher.py install --skip-backend
python launcher.py check --skip-backend
python launcher.py run --skip-backend
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
python launcher.py install --mode offline --offline-dir offline
```

Offline modda backend kurulumu şu şekilde yapılır:

```bash
pip install --no-index --find-links offline/wheels -r requirements.txt
```

Frontend kurulumu şu mantığı kullanır:

```bash
npm ci --offline --cache offline/npm-cache
```

### Migration Fix Seçeneği

Varsayılan `check`, migration üretmez veya uygulamaz. Model değişikliği varsa fail eder.

Eksik migration dosyalarını oluşturup unapplied migration'ları uygulamak için:

```bash
python launcher.py check --fix-migrations
python launcher.py all --fix-migrations
```

> Production veritabanlarında otomatik migration uygulama kararını dikkatli verin. CI/local geliştirme için yararlı olsa da canlı sistemlerde migration planı ayrıca gözden geçirilmelidir.

### Interactive Mod

Komut ve seçenekleri menüden seçmek için:

```bash
python launcher.py --interactive
python launcher.py -i
```

### Launcher'ın Yazdığı Dosyalar

`run` sırasında backend runtime adresi için `backend/.env` güncellenir veya yoksa development placeholder değerlerle oluşturulur.

Frontend için `frontend/.env.local` dosyasına aşağıdaki değerler yazılır:

```env
VITE_API_BASE_URL=http://127.0.0.1:<backend-port>
VITE_BACKEND_URL=http://127.0.0.1:<backend-port>
VITE_API_URL=http://127.0.0.1:<backend-port>
VITE_SERVER_URL=http://127.0.0.1:<backend-port>
```

Uygulamada aktif kullanılan ana değişken `VITE_API_URL` değeridir. Diğer adlar backward compatibility için yazılır.

### Launcher Seçenekleri

| Seçenek | Açıklama |
|---|---|
| `--mode auto|online|offline` | Paket kurulum modunu seçer. |
| `--offline-dir <path>` | Offline wheel/cache dizini. Varsayılan `offline`. |
| `--offline-zip <path>` | `package-offline` çıktısı. |
| `--changes-zip <path>` | `package-changes` çıktısı. |
| `--skip-frontend` | Frontend adımlarını atlar. |
| `--skip-backend` | Backend adımlarını atlar. |
| `--fix-migrations` | Eksik migration üretme ve migration uygulama davranışını açar. |
| `--host <host>` | Development server host. Varsayılan `127.0.0.1`. |
| `--backend-port <port>` | Tercih edilen Django portu. Varsayılan `8000`. |
| `--frontend-port <port>` | Tercih edilen Vite portu. Varsayılan `5173`. |
| `--no-backend-reload` | Django autoreload kapatılır. |
| `--ignore-packages` | Paket ilişkili operasyonları paketleme senaryolarında atlamak için kullanılır. |

### Launcher Trade-off'ları

- `auto` mod sadece PyPI/npm registry bağlantısını kısa probe ile ölçer; kurumsal proxy veya internal registry varsa sonuç yanıltıcı olabilir.
- Offline npm kurulumu cache'in eksiksiz olmasına bağlıdır. Eksik tarball/metadata varsa online makinede `prepare-offline` tekrar çalıştırılmalıdır.
- `--fix-migrations` local hız kazandırır; fakat production migration yönetimi kontrollü release planıyla yapılmalıdır.
- Launcher development `.env` placeholder'ları üretir; bu dosya production secrets dosyası değildir.

---

## Environment Değişkenleri

Backend `.env` dosyası `backend/.env` konumundan okunur. Gerçek secret, token, parola, sertifika veya production endpoint bilgileri commit edilmemelidir.

### Minimum Local Development Örneği

```env
DEBUG=True
SECRET_KEY=dev-insecure-secret-key-change-me
IPV4_ADDRESS=127.0.0.1
PORT=8000
DOCPROOF_URL=http://localhost/docproof
DOORS_EXECUTABLE=doors
JIRA_LEGACY_URL=http://localhost/jira-legacy
JIRA_BTB_URL=http://localhost/jira
AW_USERNAME=
AW_PASSWORD=
ALLOWED_HOSTS=127.0.0.1,localhost
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
| `JIRA_LEGACY_URL` | Zorunlu | Legacy JIRA URL'i. |
| `JIRA_BTB_URL` | Zorunlu | Ana JIRA URL'i. |
| `AW_USERNAME` | Varsayılan boş | DocProof/DOORS gibi entegrasyonlarda kullanılır; hassas kabul edilmelidir. |
| `AW_PASSWORD` | Varsayılan boş | DocProof/DOORS gibi entegrasyonlarda kullanılır; hassas kabul edilmelidir. |
| `FFMPEG_EXECUTABLE` | Varsayılan `ffmpeg` | Media Converter için FFmpeg binary adı/path'i. |
| `DATABASE_URL` | Varsayılan `backend/db.sqlite3` | Primary database URL'i. Production için PostgreSQL önerilir. |
| `DB_OLD_URL` | Varsayılan `backend/db_old.sqlite3` | Legacy database bağlantısı. |
| `DATABASE_CONN_MAX_AGE` | Varsayılan `60` | Persistent database connection süresi. |
| `CACHE_URL` | Varsayılan local memory cache | Redis gibi production cache backend URL'i. |
| `LOG_LEVEL` | Varsayılan `INFO` | Django ve uygulama console log seviyesi. |
| `FRONTEND_DIST_DIR` | Varsayılan `frontend/dist` | Django'nun SPA shell ve Vite asset çıktısını aradığı dizin. |
| `FRONTEND_RESET_URL` | Ortama göre hesaplanır | Parola reset linklerinde kullanılan frontend login URL'i. |
| `ALLOWED_HOSTS` | `IPV4_ADDRESS`, `127.0.0.1`, `localhost` | Django allowed hosts listesi. |
| `CORS_ALLOWED_ORIGINS` | `DEBUG=False` iken zorunlu | Production CORS origin allowlist. |
| `CSRF_TRUSTED_ORIGINS` | Varsayılan boş liste | Cross-site POST/PUT/PATCH/DELETE için trusted origin listesi. |
| `SECURE_SSL_REDIRECT` | `DEBUG=False` iken varsayılan `True` | HTTP isteklerini HTTPS'e yönlendirir. TLS proxy arkasında topolojiye göre ayarlanmalıdır. |
| `USE_X_FORWARDED_HOST` | `DEBUG=False` iken varsayılan `True` | Reverse proxy host header'ını kullanır. |
| `AUTH_COOKIE_NAME` | Varsayılan `auth_token` | DRF token cookie adı. |
| `AUTH_COOKIE_MAX_AGE` | Varsayılan 14 gün | Auth cookie ömrü, saniye cinsinden. |
| `AUTH_COOKIE_SAMESITE` | `DEBUG=True`: `Lax`, `DEBUG=False`: `None` | Browser cookie SameSite politikası. |
| `AUTH_COOKIE_SECURE` | `DEBUG=True`: `False`, `DEBUG=False`: `True` | Auth cookie için Secure bayrağı. |
| `AUTH_TOKEN_RESPONSE_ENABLED` | Varsayılan `DEBUG` | Local fallback için token'ın response body'de dönülmesine izin verir. Production'da kapalı kalmalıdır. |
| `SECURE_HSTS_SECONDS` | `DEBUG=False` iken varsayılan `31536000` | HSTS süresi. |
| `SOFFICE_BIN` | Varsayılan `soffice` | PPT/PDF dönüşümünde LibreOffice binary. |
| `PDFTOPPM_BIN` | Varsayılan `pdftoppm` | Poppler PDF-to-image binary. |

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
npm run typecheck
npm run typecheck:ci
npm run build
```

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

CI workflow'u `.github/workflows/ci.yml` altında backend ve frontend kalite kapıları için temel bir GitHub Actions akışı içerir.

---

## Güvenlik Notları

- `.env`, SQLite database, media upload, node_modules, build artifact, sertifika ve private key dosyaları commit edilmemelidir.
- `AW_USERNAME`, `AW_PASSWORD`, DRF token, `auth_token` cookie ve JIRA/DocProof credential değerleri secret kabul edilmelidir.
- Global DRF permission `IsAuthenticated` olduğu için public endpoint açarken `AllowAny` bilinçli ve testli kullanılmalıdır.
- Cookie-backed token auth unsafe method'lar için CSRF kontrolü uygular.
- Production'da `DEBUG=False`, güçlü `SECRET_KEY`, explicit `CORS_ALLOWED_ORIGINS` ve doğru `CSRF_TRUSTED_ORIGINS` kullanılmalıdır.
- File upload endpointlerinde dosya türü, boyut, path traversal ve temporary file cleanup riskleri dikkate alınmalıdır.
- DOORS, LibreOffice, Poppler ve FFmpeg gibi dış binary entegrasyonlarında shell fragment kullanılmamalı; argüman listesiyle çalıştırma korunmalıdır.
- `AUTH_TOKEN_RESPONSE_ENABLED=True` production için önerilmez; HttpOnly cookie-only model daha güvenlidir.

---

## Deployment Temelleri

Repository aşağıdaki deployment yapı taşlarını içerir:

- `backend/Dockerfile`: Django backend image temeli.
- `frontend/Dockerfile`: Vite build + statik servis image temeli.
- `docker-compose.yml`: Backend, frontend static serving, PostgreSQL ve Redis içeren local production-like orchestration.
- `.env.example`: Production environment sözleşmesi için secrets içermeyen örnek.
- `deploy/nginx/awcenter.conf`: TLS terminasyonu önündeki reverse proxy için başlangıç Nginx örneği.
- `.github/workflows/ci.yml`: Backend/frontend check, build ve audit adımları.
- `docs/deployment.md`: Deployment detayları.

Önemli deployment kararları:

- Mevcut Django settings local varsayılan olarak SQLite kullanır; production `DATABASE_URL` ile PostgreSQL'e geçirilmelidir.
- Frontend build çıktısı immutable artifact olarak `frontend/dist` altında tutulmalı veya `FRONTEND_DIST_DIR` ile mount edilmelidir.
- Production secret yönetimi environment/secret manager üzerinden yapılmalıdır.
- HTTPS, HSTS, secure cookie ve CORS/CSRF listeleri deployment topolojisine göre doğrulanmalıdır.

### Production İlk Kurulum Akışı

```bash
docker compose build
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py collectstatic --noinput
docker compose up -d
curl -fsS http://localhost:8000/health/ready/
```

`docker-compose.yml` içindeki örnek secret ve parolalar sadece local doğrulama içindir. Production'da bunlar secret manager veya platform environment ayarlarıyla değiştirilmelidir.

---

## Sık Karşılaşılan Sorunlar

### `SECRET_KEY must be defined when DEBUG is False`

`DEBUG=False` ise `SECRET_KEY` zorunludur. Local development için `DEBUG=True` kullanın veya `.env` içine güçlü bir `SECRET_KEY` ekleyin.

### Backend check `.env` değişkenleri yüzünden başlamıyor

`IPV4_ADDRESS`, `PORT`, `DOCPROOF_URL`, `DOORS_EXECUTABLE`, `JIRA_LEGACY_URL`, `JIRA_BTB_URL` zorunlu okunur. Local placeholder üretmek için:

```bash
python launcher.py install
python launcher.py run --skip-frontend
```

### Login sonrası auth cookie gönderilmiyor

- Local HTTP geliştirmede `AUTH_COOKIE_SAMESITE=Lax` ve `AUTH_COOKIE_SECURE=False` kullanın.
- Cross-site HTTPS deployment'ta `AUTH_COOKIE_SAMESITE=None`, `AUTH_COOKIE_SECURE=True`, `CORS_ALLOWED_ORIGINS` ve `CSRF_TRUSTED_ORIGINS` değerlerini birlikte ayarlayın.

### Frontend API çağrıları yanlış backend'e gidiyor

`frontend/.env.local` içindeki `VITE_API_URL` değerini kontrol edin veya launcher ile frontend env'i tekrar yazdırın:

```bash
python launcher.py run
```

### DOORS işlemleri çalışmıyor

`DOORS_EXECUTABLE` doğru path'i göstermeli ve ortam Windows/DOORS automation gereksinimlerini sağlamalıdır.

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
