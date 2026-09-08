# Windows production ve operasyon

## Desteklenen güncel topoloji

AW Center production, uygulama ve IBM Rational DOORS ile aynı Windows kullanıcı
oturumunda çalışır. Public giriş doğrudan TLS kullanan tek Uvicorn/Django ASGI
process'idir. `launcher.py prod` ayrıca bir genel job worker, notification worker ve
cleanup worker başlatır. Production database'i SQLite'tır.

Docker, Nginx, PostgreSQL ve Redis dosyaları gelecekteki container migration'ı için
korunur; güncel production başlangıcının bağımlılığı değildir.

```text
Kurumsal LAN → https://<statik-ip>:443
                 └─ Uvicorn → Django + built Vue
                              ├─ production db.sqlite3
                              ├─ production private-media
                              ├─ local/doors job worker
                              ├─ notification worker
                              └─ cleanup worker
```

Uygulama kullanıcı oturumu kapatıldığında çalışmayı durdurur. Oturumdan bağımsız
7/24 servis gereksinimi doğarsa Windows Service veya container aşaması ayrıca
tasarlanmalıdır.

## Windows dizinleri

Production state'i repository'nin ve OneDrive'ın dışında tutulur:

```text
%LOCALAPPDATA%\AWCenter\
├─ config\production.env
├─ state\
│  ├─ production\
│  │  ├─ db.sqlite3
│  │  ├─ private-media\
│  │  ├─ media\
│  │  ├─ static\
│  │  └─ cache\
│  └─ doors-worker.lock
├─ assets\sets\<asset-set-id>\
│  ├─ ai-models\
│  └─ document-templates\
├─ releases\<release-id>\source\
├─ tls\application\
│  ├─ tls.crt
│  └─ tls.key
└─ backups\
```

Development kendi checkout'u, `backend/db.sqlite3` ve `backend/private_media`
yollarını kullanır. İki ortam yalnız açıkça seçilen read-only asset setini
paylaşabilir; database, private-media, port, secret veya worker kilidi paylaşmaz.
Production file cache'i web ve worker process'leri arasında kısa ömürlü, şifrelenmiş
JIRA session state'ini paylaşır; erişimi yalnız aynı Windows kullanıcısıyla sınırlandırın.
Launcher logları foreground PowerShell oturumunun stdout/stderr akışındadır. Kalıcı
log gerekiyorsa bu akış erişim kontrollü, repository dışındaki bir hedefe operasyon
katmanında yönlendirilmelidir.

AI dizini yalnız şu ağırlık alt dizinlerini barındırır:

```text
ai-models\
├─ opus-mt-tr-en\
├─ opus-mt-en-tr\
├─ paraphrase-multilingual\
└─ ms-marco-cross-encoder\
```

DOCX şablonları `document-templates\` altında tutulur. Mail HTML gövdeleri runtime
asset değildir; ilgili Django app'inin tracked `templates/` dizininde kalır.

## İlk kurulum

1. CPython 3.11, Node.js 22, npm ve gerekli native Office/PDF araçlarını kurun.
2. Review edilmiş release'i
   `%LOCALAPPDATA%\AWCenter\releases\<release-id>\source` altında temiz bir kopya
   olarak hazırlayın. Development `.venv`, `.env`, SQLite, `.runtime`, private-media
   veya generated static state'i kopyalamayın.
3. PowerShell'de bu release'in `source` dizinine geçip bağımlılıkları kurun:

   ```powershell
   python launcher.py setup
   ```

4. `%LOCALAPPDATA%\AWCenter` dizin ağacını oluşturun.
5. `backend/.env.production` dosyasını
   `%LOCALAPPDATA%\AWCenter\config\production.env` konumuna kopyalayın.
6. `REPLACE_ME`, statik IP, release ve asset-set placeholder'larını değiştirin.
   En az 50 karakterlik rastgele `SECRET_KEY` kullanın. Dosyayı repository'ye
   kopyalamayın veya commit etmeyin.
7. SQLite URL'sini local NTFS üzerindeki production dosyasına yöneltin.
   Network share, junction, symlink ve OneDrive desteklenmez.
8. Self-signed veya kurum CA tarafından imzalı sertifikanın IP Address SAN alanına
   production statik IPv4 adresini ekleyin. Sertifika ve private key eşleşmelidir.
   Self-signed sertifikayı yalnız yetkili LAN istemcilerinin Trusted Root store'una
   kurun.
9. Windows Firewall'da yalnız kurumsal ağ profili/subnet'i için TCP 443 inbound
   kuralı açın. Development 8000/5173 portlarını LAN'a açmayın.
10. Frontend artifact'ını üretin:

   ```powershell
   npm --prefix frontend ci
   npm --prefix frontend run build
   ```

11. İlk schema kurulumu ile production'ı başlatın:

    ```powershell
    python launcher.py prod `
      --env-file "$env:LOCALAPPDATA\AWCenter\config\production.env" `
      --host 192.0.2.10 `
      --tls-cert-file "$env:LOCALAPPDATA\AWCenter\tls\application\tls.crt" `
      --tls-key-file "$env:LOCALAPPDATA\AWCenter\tls\application\tls.key" `
      --migrate
    ```

Launcher sırasıyla Windows/statik-IP/path/TLS kontrollerini, Django deploy
check'ini, migration durumunu, `collectstatic` ve frontend artifact doğrulamasını
çalıştırır. Bir kapı başarısızsa web veya worker process'i açılmaz.

Normal yeniden başlatmada aynı komutu `--migrate` olmadan kullanın. Pending migration
varsa başlangıç fail-closed durur.

İlk kurulumda ikinci bir PowerShell açıp aynı release dizininden ilk yöneticiyi
oluşturun; bu komut yalnız process environment'ında production profilini seçer:

```powershell
$env:AWCENTER_ENV_FILE="$env:LOCALAPPDATA\AWCenter\config\production.env"
$env:AWCENTER_DEPLOYMENT_MODE="windows-native"
python backend/manage.py createsuperuser
Remove-Item Env:AWCENTER_ENV_FILE
Remove-Item Env:AWCENTER_DEPLOYMENT_MODE
```

## DOORS

Production environment'ında:

```text
DOORS_ENABLED=True
DOORS_EXECUTABLE=C:/IBM/DOORS/bin/doors.exe
DOORS_DATABASE=36677@doors-server
```

Production worker'ı DOORS etkin olduğunda `doors` queue'sunu varsayılan olarak
tüketir; yalnız local queue'lar için komuta `--exclude-doors` ekleyin. Worker yalnız
catalog'daki `doors` kind'larını kabul eder, her executor'ü child process'te çalıştırır
ve belirsiz write sonucunu `reconciliation_required` yapar. Aynı lock dosyasını
kullanan Windows process'leri arasında alınan kilit, ikinci DOORS-capable worker'ı reddeder.

Development worker'ı `DOORS_ENABLED=True` olduğunda DOORS queue'sunu varsayılan
olarak tüketir. Yalnız local queue'ları çalıştırmak için
`launcher.py dev --exclude-doors` kullanın. Aynı masaüstü DOORS instance'ına iki ortamın eşzamanlı
yazmasına izin vermeyin; development başlatmadan önce production worker'ını durdurun.

Credential Manager, Task Scheduler ve ayrı bir loopback servisi kullanılmaz.

## Release ve güncelleme

- Production yalnız clean ve review edilmiş bir release kopyasından çalıştırılır;
  development checkout'undaki dirty dosyalar doğrudan production'a verilmez.
- Yeni release ayrı `%LOCALAPPDATA%\AWCenter\releases\<release-id>\source` dizinine
  hazırlanır ve kendi `.venv` ortamını kullanır.
- Upgrade öncesi production durdurulur ve eşlenmiş SQLite/private-media yedeği
  alınır.
- Yeni release'te `launcher.py check`, backend/frontend testleri ve frontend build
  tamamlandıktan sonra `launcher.py prod --migrate` çalıştırılır.
- Migration sonrası write alınmışsa eski schema'ya dönülmez; forward-fix uygulanır
  veya doğrulanmış eşlenmiş yedek geri yüklenir.

## Yedekleme ve geri yükleme

SQLite ve private-media aynı business state'in parçalarıdır; ayrı zamanlarda alınan
kopyalar tam yedek sayılmaz.

1. Public erişimi kesin ve launcher'ı durdurun.
2. `db.sqlite3`, `private-media\` ve kullanılan production env'in secretsiz
   envanterini aynı backup kimliği altında kopyalayın.
3. Her dosyanın relative path, byte size ve SHA-256 değerini manifestte saklayın.
4. Kopyayı BitLocker korumalı harici disk veya erişim kontrollü kurumsal UNC
   paylaşımında ikinci kez saklayın.
5. Periyodik olarak boş bir dizine restore edin; `manage.py check`, `migrate --check`,
   login, private artifact download ve örnek document job canary'sini çalıştırın.

Canlı SQLite dosyasını Explorer ile kopyalamak desteklenmez. Online yedekleme
gerekiyorsa Python `sqlite3.Connection.backup` API'sini kullanan, ardından artifact
state'ini quiesce eden repository-owned araç ayrıca eklenmelidir.

## Gelecekteki container aşaması

`docker-compose.yml`, `backend/Dockerfile`, Nginx, deployment preflight, immutable
image evidence ve PostgreSQL/Redis testleri gelecekteki hedef sözleşmedir. Bu profile
geçiş ayrı bir repository-wide migration olarak ele alınacaktır:

- fresh PostgreSQL 17 schema;
- authenticated Redis 7;
- digest-pinned immutable image;
- private artifact volume ve read-only AI/template mount'ları;
- DOORS entegrasyonu için ayrıca tasarlanacak Windows execution sınırı;
- SQLite verisinin taşınması gerekiyorsa ayrıca review edilmiş, one-shot ve
  geri-dönüş kapılı veri migration'ı.

Bu container belgeleri veya `.env.example` bugünkü `launcher.py prod` komutuna input
olarak verilmez.
