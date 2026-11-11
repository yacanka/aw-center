# Django + Vue launcher

Kök `launcher.py`, local setup/quality/development/offline packaging akışlarının ve
güncel Windows-native production lifecycle'ının tek girişidir. macOS'ta yalnız
development desteklenir; `prod` komutu fail-closed biçimde yalnız Windows'ta çalışır.

Windows'ta sıfırdan kurulumun yönlendirmeli girişi `AWCenter.cmd` dosyasıdır.
`wizard`, `provision`, `doctor`, `start` ve `prepare-install-bundle` komutları
aynı launcher çekirdeğine bağlıdır. Ayrıntılar [Windows kurulum yardımcısı](windows-install-helper.md)
içindedir. Aşağıdaki düşük seviyeli `setup/dev/prod` sözleşmeleri korunur;
yalnız açık `provision` yeni private profil/anahtar ve repository dışı kurulum
state'i oluşturur. `doctor` bunları oluşturmaz veya düzeltmez.

## Sözleşme

- CPython 3.11.x ister ve `.venv` minor sürümünü doğrular; 3.11 yama sürümleri kabul edilir.
- Launcher giriş noktası yalnız standart kütüphane kullanır; ilk `setup` için
  uygulama paketlerinin global Python'a kurulması gerekmez. Production TLS
  doğrulaması proje `.venv` interpreter'ında çalışır.
- `.env`, `.env.local`, PID veya kalıcı runtime state yazmaz.
- Geliştirmede de açık `SECRET_KEY`, JIRA etkinse bağımsız Fernet anahtarı gerekir.
  [Özel ortam kurulumu](private-environment.md) bir kez operatör tarafından yapılır;
  `setup`, `dev`, web ve worker süreçleri anahtar üretmez veya yenilemez.
- Child process'ler mevcut shell environment'ını miras alır; host/port ve `VITE_API_URL` yalnız process-local override'dır.
- Migration örtülü uygulanmaz. Yalnız `dev --migrate` açıkça verilirse startup öncesi `migrate --noinput` çalışır.
- `prod`, migration'ı yalnız `--migrate` verildiğinde uygular; her başlangıçta
  migration drift, deploy check ve frontend artifact kontrollerini çalıştırır.
- Dolu veya geçersiz portta başka port seçmez; fail-fast durur.
- `dev`, seçilen scope'a göre Django/Vite ile mevcut durable job, password-reset/compliance notification ve cleanup command'larını foreground child process olarak supervise eder. `DOORS_ENABLED=True` olduğunda durable worker DOORS queue'sunu varsayılan olarak tüketir; `--exclude-doors` bu davranışı kapatır.
- `prod`, Windows'ta static IPv4 üzerinde doğrudan TLS sunan tek Uvicorn process'i
  ile job, notification ve cleanup worker'larını aynı terminal lifecycle'ında supervise eder.
- `prod` environment, TLS certificate ve private key girdilerini repository dışından
  ister. Sertifika seçilen IPv4 adresini SAN olarak içermeli ve private key ile eşleşmelidir.
- Açık production profilinde `DEBUG=True` engelleyici hatadır. Başlangıçta bir
  child açılamazsa veya başlangıç kesilirse daha önce açılmış child'lar kapatılır.
- Offline dependency bundle OS, architecture, Python, lock digest ve artifact SHA-256 manifest'ine bağlıdır; başka target veya değiştirilmiş bundle fail-closed reddedilir.
- Packaging yalnız izinli Git kaynaklarını alır; secret env, key/certificate, database, media, virtualenv, dependency tree ve generated build state'ini dışarıda bırakır. Symlink ve path escape reddedilir.

## Komutlar

```bash
python launcher.py setup
python launcher.py setup --skip-backend
python launcher.py setup --skip-frontend

python launcher.py check
python launcher.py test

python launcher.py dev --backend-port 8000 --frontend-port 5173
python launcher.py dev --migrate
python launcher.py dev --exclude-doors

python launcher.py prod --help

python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
python launcher.py package-changes
```

Launcher'ın yazdırdığı frontend URL'sini hostname dahil aynen kullanın. Örneğin çıktı
`http://127.0.0.1:5173` ise sayfayı `http://localhost:5173` ile açmak güvenlik
kontrolünden geçmez; browser hostname'i (`localhost`) process-local `VITE_API_URL`
hostname'iyle (`127.0.0.1`) aynı değildir. `localhost` kullanmak istiyorsanız iki
child process'i de aynı adla başlatın:

```bash
python launcher.py dev --host localhost
```

Başka bir cihazdan erişim için wildcard bind adresini browser adresi olarak
kullanmayın; erişilebilir somut host/IP ile başlatıp yazdırılan URL'yi açın (örneğin
`python launcher.py dev --host 192.0.2.10`). Bu same-host kontrolünü gevşetmek yerine
frontend ile session-cookie kullanan API'nin hostlarını hizalar.

`check` backend için Django system check, isolated in-memory migration drift/plan; frontend için format ve typecheck çalıştırır. `test` full Django, launcher/release metadata unittest'leri ve frontend `test:ci` çalıştırır.

Playwright browser cache'i launcher tarafından örtülü kurulmaz. İlk kullanımda `frontend/` içinde `npx playwright install chromium`, ardından repository kökünde `npm --prefix frontend run test:e2e` çalıştırın; release gate bu browser smoke'u ayrıca ister.

Her komutun parametreleri için:

```bash
python launcher.py --help
python launcher.py dev --help
python launcher.py package-offline --help
```

## Offline akış

Yalnız repository kaynaklarını taşımak için (önceden `prepare-offline` gerekmez):

```bash
python launcher.py package-offline --ignore-packages --offline-zip project-source.zip
```

Bu komut varsayılan olarak backend, frontend, migration'lar, testler, dokümanlar,
deploy/packaging/tools, launcher ve kök yapılandırma/lock dosyaları dahil tüm
Git'te takip edilen güvenli kaynak dosyalarının mevcut çalışma kopyasını ZIP'e
koyar. Yeni kaynak dosyasını önce `git add` ile takibe alın; commit zorunlu
değildir. Takip edilmeyen veya silinmiş dosyalar eklenmez. `--skip-backend` veya
`--skip-frontend` açıkça verilirse ilgili taraf hariç tutulur.

`--ignore-packages`, wheel/npm cache dosyalarını ve offline manifest'i dışlar;
paket indirme, doğrulama veya kurulum çalıştırmaz. Yanlışlıkla Git'e eklenmiş
paket önbellekleri ve `--offline-dir` ile seçilen özel önbellek dizini de kaynak
olarak arşive sızmaz. Requirements ve npm lock dosyaları bağımlılık **tanımları**
olduğu için ZIP'te kalır. Çıktıda kaynak ve bağımlılık dosya sayısı gösterilir.

Bu kaynak arşivi tek başına internetsiz bağımlılık kurulumu için yeterli değildir.
`.git`, `.venv`, `node_modules`, build/test çıktıları, database/media, özel `.env`
profilleri (takip edilen `.env.development`/`.env.production` dahil), registry
kimlik bilgileri ve key/certificate dosyaları güvenlik gereği eklenmez. Güvenli
`.env.example`/`.env.sample` şablonları korunur. Git metadata'sı olmayan çıkarılmış
klasörler paketleme kaynağı olamaz; komutu Git checkout'unda çalıştırın.

İnternet erişimli, hedefle aynı OS/architecture/Python ortamında:

```bash
python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
```

Offline hedefte ZIP açıldıktan sonra:

```bash
python launcher.py setup --mode offline --offline-dir offline
```

`prepare-offline`, wheelhouse'un hedef platformdaki tüm lock girdilerini yalnız yerel
wheel'lerle çözebildiğini doğrular. Bu kontrol Windows'a koşullu `uvicorn`, `pywin32`
ve `WMI` paketlerinin bundle dışında kalmasını önler. Offline `setup`, kuruluma
başlamadan önce manifestteki OS, architecture, Python ve lock bilgilerini hedef
makineyle tekrar karşılaştırır. Manifest eşleşmiyorsa internet erişimli, hedefle
aynı Windows/architecture/Python ortamında yeni bundle hazırlayın; doğrulamayı
atlamayın.

## Windows production

Frontend değişikliklerini başlangıçta derlemek için `prod` komutuna
`--build-frontend` eklenir. Bu seçenek `frontend/` içinde `npm run build`
çalıştırır; build başarısızsa static dosyalar toplanmaz ve server/worker başlatılmaz.
Seçenek verilmezse mevcut build kullanılır. İlk kurulumda veya bağımlılıklar
değiştiğinde önce repository kökünde `npm --prefix frontend ci` çalıştırılmalıdır;
`--build-frontend` bağımlılık kurulumu yapmaz. Node.js/npm build için gereklidir.

Güncel production komutu örneği:

```powershell
python launcher.py prod `
  --env-file "$env:LOCALAPPDATA\AWCenter\config\production.env" `
  --host 192.0.2.10 `
  --tls-cert-file "$env:LOCALAPPDATA\AWCenter\certificates\server.crt" `
  --tls-key-file "$env:LOCALAPPDATA\AWCenter\certificates\server.key"
```

İlk kurulumda veya yeni migration içeren kontrollü bir release geçişinde aynı
komuta `--migrate` eklenir. Normal yeniden başlatmada eklenmez. Production SQLite,
private artifact, AI ağırlığı, DOCX şablonu, env ve certificate dosyalarının tamamı
repository dışında `%LOCALAPPDATA%\AWCenter\` altında tutulur.

`DOORS_ENABLED=True` ise production worker DOORS queue'sunu varsayılan olarak
tüketir. Yalnız local queue'ları çalıştırmak için komuta `--exclude-doors` eklenir.

`backend/Dockerfile`, `docker-compose.yml`, Nginx, PostgreSQL ve Redis sözleşmesi
sonraki olgunluk aşaması için korunur; bugünkü `launcher.py prod` akışının parçası
değildir. Ayrıntılar [deployment.md](deployment.md) içindedir.

Launcher kapanışı yalnız doğrudan child PID'lerini değil, sahip olduğu süreç ağacını
sonlandırır. POSIX'te her servis ayrı process group içinde başlar; worker'a kendi
izole executor ağacını kapatması için toplam 30 saniyelik süre tanınır, kalan grup
zorla durdurulur. Windows'ta komut, kill-on-close Job Object ataması tamamlanana
kadar bir başlangıç kapısında bekler; başlangıç hatası veya launcher kapanışı aynı
Job Object içindeki alt süreçleri de durdurur. Job Object atanamazsa komut
çalıştırılmaz. Bu yol launcher kurulumundan önce de kullanılabildiği için yalnız
Python standart kütüphanesine bağlıdır.

POSIX worker'ın kontrollü kapanışında yarım kalan yerel işler
`JOB_WORKER_STOPPED` ile yeniden denenebilir duruma geçer; dış sistem yazımı
olabilecek işler `reconciliation_required` olarak korunur. Windows'ta zorunlu
kapanıştan kalan claim'ler mevcut lease/reconciliation kurallarıyla toparlanır.
