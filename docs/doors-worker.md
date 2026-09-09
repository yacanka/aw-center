# Windows DOORS execution

Güncel production'da AW Center ve IBM Rational DOORS aynı Windows cihazda, aynı
logged-in kullanıcı oturumunda çalışır. `DOORS_ENABLED=True` olduğunda
`launcher.py prod`, genel job worker'ına varsayılan olarak hem `local` hem `doors`
queue allowlist'ini verir. Ayrı Task Scheduler
kaydı, Windows Credential Manager token'ı, loopback HTTP servisi veya ikinci Python
process'i elle başlatılmaz.

Development'ta `DOORS_ENABLED=True` ise `launcher.py dev` aynı allowlist'i
varsayılan olarak açar. Yalnız local queue'ları çalıştırmak için
`launcher.py dev --exclude-doors` kullanılır. Gerekiyorsa migration startup'tan önce
`launcher.py dev --migrate` ile açıkça uygulanır.

## Güncel çalışma şekli

```text
Browser → HTTPS Uvicorn/Django → SQLite durable job
                                  │
                                  ▼
                     launcher-owned general worker
                         ├── local executor'lar
                         └── DOORS adapter → aç / hazır olmasını bekle → OLE/COM → DXL
```

HTTP request process'i COM çağrısı çalıştırmaz; yalnız durable job oluşturur. Worker:

- `doors` job kind'larını açık allowlist üzerinden çözer;
- her executor'ı Windows'ta disposable `spawn` subprocess'inde izole eder;
- input'u private artifact alanından kontrollü geçici dosyaya materialize eder;
- timeout/cancellation ve stale execution token sınırlarını korur;
- sonucu hash'li private artifact olarak fenced completion ile yayımlar;
- sonucu belirsiz bir DOORS write işleminde otomatik retry yerine
  `reconciliation_required` üretir.

Her iş, önce aynı Windows oturumundaki açık istemciye bağlanır. İstemci kapalıysa
`DOORS_AUTO_START_CLIENT=True` ile masaüstü uygulamasını başlatır; yalnız COM
nesnesinin bulunması yeterli değildir, küçük bir DXL/Result kontrolünün başarıyla
dönmesini bekler. İş bittikten veya executor sonlandıktan sonra DOORS'a `Quit`
gönderilmez; başlatılan masaüstü process'i sonraki işler için açık kalır.
Otomatik başlatma batch veya COM `/automation` yaşam döngüsünü kullanmaz.

`DOORS_WORKER_LOCK_FILE`, aynı Windows kullanıcı profilinde aynı anda yalnız bir
DOORS-capable worker bulunmasını sağlar. Kilit dosyasını silmek çalışan process'i
durdurmaz ve ikinci worker açmak için kullanılmamalıdır.

## Production ayarları

Repository dışındaki production env dosyasında:

```text
DOORS_ENABLED=True
DOORS_OLE_PROG_ID=DOORS.Application
DOORS_EXECUTABLE=
DOORS_DATABASE=36677@doors-server
DOORS_USERNAME=
DOORS_PASSWORD=
DOORS_PREFER_ACTIVE_INSTANCE=True
DOORS_AUTO_START_CLIENT=True
DOORS_STARTUP_TIMEOUT_SECONDS=90
DOORS_RUN_TIMEOUT_SECONDS=120
DOORS_MAX_RESULT_BYTES=10485760
DOORS_RESULT_MODE=file
DOORS_WORKER_LOCK_FILE=C:/Users/<user>/AppData/Local/AWCenter/state/doors-worker.lock
```

Gerçek DOORS kullanıcı adı/parolası yalnız seçilen, erişimi kısıtlı env dosyasına
veya process environment'a girilir. `DOORS_EXECUTABLE` boşsa executable,
`DOORS_OLE_PROG_ID` için Windows COM kaydının 64/32 bit görünümlerinden bulunur.
Birden fazla DOORS sürümü varsa ProgID ile uyumlu EXE yolu açıkça verilebilir.
`DOORS_DATABASE` boşsa kurulu istemcinin varsayılan veritabanı kullanılır.

Windows'a interaktif giriş yapılmış olmalıdır. Kullanıcı adı tanımlıysa yeni
istemci IBM'in `-user` / `-password` seçenekleriyle giriş yapar; parola tanımlıysa
kullanıcı adı da zorunludur. İkisi de boşsa mevcut istemci/sistem giriş politikası
geçerlidir; bir login ekranı açılırsa verilen süre içinde giriş tamamlanmalıdır.
Açık bir istemci yeniden kullanılırken mevcut DOORS kullanıcısı ve veritabanı
korunur; kimlik değiştirmek için istemciyi kapatıp yeniden iş başlatın.

`DOORS_AUTO_START_CLIENT=False` açık tercihi korunur; bu ayarda kullanıcı DOORS'u
önceden açmalıdır. Eski env dosyaları otomatik değiştirilmez; özelliği kullanmak
için bu değeri `True` yapıp AW Center'ı yeniden başlatın.

Production başlatılırken:

```powershell
python launcher.py prod `
  --env-file "$env:LOCALAPPDATA\AWCenter\config\production.env" `
  --host 192.0.2.10 `
  --tls-cert-file "$env:LOCALAPPDATA\AWCenter\certificates\server.crt" `
  --tls-key-file "$env:LOCALAPPDATA\AWCenter\certificates\server.key"
```

DOORS queue'sunu tüketmeden production çalıştırmak için `--exclude-doors` verilir;
integration status bunu unavailable olarak bildirir. `DOORS_ENABLED` yanlışlıkla
açık bırakılıp worker Windows dışında başlatılırsa production check fail-closed durur.

## Güvenlik sınırı

- DOORS credential'ı job payload, database, browser response veya log'a yazılmaz.
- IBM'in otomatik GUI giriş seçeneği parolayı yerel process argümanında taşır.
  AW Center bu komutu veya alt process çıktısını loglamaz; Windows process
  argümanlarını okuyabilen yetkili yerel araçlar parolayı görebilir. Bunu istemeyen
  kurulumlar önceden giriş yapılmış istemciyi kullanıp otomatik başlatmayı kapatabilir.
- Kullanıcıdan gelen DXL dosya yolu doğrudan açılmaz; artifact servisi ve allowlisted
  task sözleşmesi kullanılır.
- Temporary input/output dosyaları iş sonunda temizlenir.
- DOORS output'u bounded size ve SHA-256 doğrulamasıyla yayımlanır.
- Browser session/CSRF sınırı worker execution identity'si yerine geçmez.
- Okuma işi önceden açık modülleri kapatmaz. Yazma/link kaynağı modülü masaüstünde
  açıksa iş yazmaya başlamaz; modülü önce kaydedip kapatın. Böylece kullanıcının
  kaydedilmemiş değişiklikleri otomatik `save`/`close(false)` akışına karışmaz.

## Durum ve hata teşhisi

`configured`: DOORS etkin, platform Windows ve temel adapter ayarları geçerli.
`available`: buna ek olarak DOORS-capable worker heartbeat'i güncel. Bu alanlar
DOORS login/lisans/veritabanı veya belirli bir modüle erişim testi değildir;
web process'i COM çalıştırmaz. Gerçek bağlantı ilk kuyruk işi sırasında yapılır.

| İş hata kodu | Kontrol |
| --- | --- |
| `DOORS_CONFIG_INVALID` | ProgID, timeout, result mode/size ve kullanıcı adı/parola ayarları |
| `DOORS_EXECUTABLE_UNAVAILABLE` | DOORS kurulumu, ProgID COM kaydı veya EXE yolu |
| `DOORS_CONNECTION_FAILED` | Aynı Windows kullanıcı oturumu, pywin32/WMI, COM kaydı ve giriş |
| `DOORS_STARTUP_TIMEOUT` | Login ekranı, yanlış giriş bilgisi, lisans, veritabanı veya modal pencere |
| `DOORS_MULTIPLE_CLIENTS` | Aynı oturumda yalnız bir DOORS istemcisi bırakın |
| `DOORS_OPEN_MODULE` / `DOORS_ATTRIBUTE_NOT_FOUND` | Modül yolu, okuma izni ve attribute isimleri |
| `DOORS_DXL_FAILED` | DXL çalışması veya tamamlanma/sonuç protokolü başarısız |
| `RECONCILIATION_REQUIRED` | Yazma gönderildikten sonra sonuç belirsiz; DOORS durumunu incelemeden tekrar göndermeyin |

DXL öncesi bağlantı hataları yazma işi için de normal failure olur. DXL gönderildikten
sonraki belirsizliklerde mevcut reconciliation sınırı korunur. Worker'ın toplam
iş süresi başlangıç + DXL süreleri + 15 saniye yayınlama payını kapsar. Disiplin
kontrolü üç DXL çalıştırdığından read kuyruğu için üç çalışma payı ayrılır;
başlangıç ve run timeout üst sınırları sırasıyla 300 ve 600 saniyedir.

Dosya sonucu yalnız doğru dosyaya ait tamamlanma işareti geldikten sonra UTF-8
olarak okunur. Dosyanın oluşması veya kısmi içerik başarı sayılmaz.
`application_result` modunda her çağrı ayrı sonuç token'ı kullanır.

## Doğrulama

Platformdan bağımsız contract testleri:

```bash
cd backend
../.venv/bin/python manage.py test automations \
  integrations.tests.test_doors_api \
  integrations.tests.test_doors_worker_tasks \
  integrations.tests.test_doors_lifecycle \
  integrations.tests.test_doors_execution \
  jobs.tests.test_isolated_worker
```

Gerçek OLE canary'si Windows kullanıcı oturumunda ve test DOORS modülü üzerinde
ayrıca yapılmalıdır. Canary sırasında payload, private path veya credential
loglanmamalıdır.

Windows canary sırası: DOORS kapalıyken modül kontrolü; aynı istemcide ikinci kontrol;
liste/detail/export ve disiplin kontrolü; Linker preview; disposable modülde
create/update/link; yanlış login, kapalı veritabanı, modal pencere, timeout ve
cancellation. Başarılı işlemlerden sonra DOORS process'inin açık kaldığını,
önceden açık okuma modüllerinin kapanmadığını ve hash'li sonuç indirmesini doğrulayın.

IBM sözleşmeleri: [istemci başlangıç seçenekleri](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors/9.7.2?topic=client-command-line-switches-doors-interoperation-server)
ve [DXL Reference Manual](https://www.ibm.com/docs/en/SSYQBZ_9.6.0/com.ibm.doors.requirements.doc/topics/dxl_reference_manual.pdf).
