# Windows DOORS execution

Güncel production'da AW Center ve IBM Rational DOORS aynı Windows cihazda, aynı
logged-in kullanıcı oturumunda çalışır. `launcher.py prod --include-doors`, genel
job worker'ına hem `local` hem `doors` queue allowlist'ini verir. Ayrı Task Scheduler
kaydı, Windows Credential Manager token'ı, loopback HTTP runner veya ikinci Python
process'i elle başlatılmaz.

## Güncel çalışma şekli

```text
Browser → HTTPS Uvicorn/Django → SQLite durable job
                                  │
                                  ▼
                     launcher-owned general worker
                         ├── local executor'lar
                         └── DOORS adapter → OLE/COM → açık DOORS oturumu
```

HTTP request process'i COM çağrısı çalıştırmaz; yalnız durable job oluşturur. Worker:

- `doors` job kind'larını açık allowlist üzerinden çözer;
- her executor'ı Windows'ta disposable `spawn` subprocess'inde izole eder;
- input'u private artifact alanından kontrollü geçici dosyaya materialize eder;
- timeout/cancellation ve stale execution token sınırlarını korur;
- sonucu hash'li private artifact olarak fenced completion ile yayımlar;
- sonucu belirsiz bir DOORS write işleminde otomatik retry yerine
  `reconciliation_required` üretir.

`DOORS_WORKER_LOCK_FILE`, aynı Windows kullanıcı profilinde aynı anda yalnız bir
DOORS-capable worker bulunmasını sağlar. Kilit dosyasını silmek çalışan process'i
durdurmaz ve ikinci worker açmak için kullanılmamalıdır.

## Production ayarları

Repository dışındaki production env dosyasında:

```text
DOORS_ENABLED=True
DOORS_EXECUTION_MODE=worker
DOORS_EXECUTABLE=C:\IBM\DOORS\doors.exe
DOORS_DATABASE=36677@doors-server
DOORS_PREFER_ACTIVE_INSTANCE=True
DOORS_AUTO_START_CLIENT=False
DOORS_STARTUP_TIMEOUT_SECONDS=30
DOORS_RUN_TIMEOUT_SECONDS=120
DOORS_MAX_RESULT_BYTES=10485760
DOORS_RESULT_MODE=file
DOORS_WORKER_LOCK_FILE=C:/Users/<user>/AppData/Local/AWCenter/state/doors-worker.lock
```

DOORS kullanıcısı önce Windows'a ve DOORS istemcisine interaktif olarak giriş
yapmalıdır. Production başlatılırken:

```powershell
python launcher.py prod `
  --env-file "$env:LOCALAPPDATA\AWCenter\config\production.env" `
  --host 192.0.2.10 `
  --tls-cert-file "$env:LOCALAPPDATA\AWCenter\certificates\server.crt" `
  --tls-key-file "$env:LOCALAPPDATA\AWCenter\certificates\server.key" `
  --include-doors
```

`--include-doors` verilmezse web uygulaması çalışır fakat DOORS queue'sunu tüketen
worker olmaz; integration status bunu unavailable olarak bildirir. `DOORS_ENABLED`
yanlışlıkla açık bırakılıp worker Windows dışında başlatılırsa production check
fail-closed durur.

## Güvenlik sınırı

- DOORS credential'ı job payload, database, browser response veya log'a yazılmaz.
- Kullanıcıdan gelen DXL dosya yolu doğrudan açılmaz; artifact servisi ve allowlisted
  task sözleşmesi kullanılır.
- Temporary input/output dosyaları iş sonunda temizlenir.
- DOORS output'u bounded size ve SHA-256 doğrulamasıyla yayımlanır.
- Browser session/CSRF sınırı worker execution identity'si yerine geçmez.

## Gelecekteki container profili

Backend Docker/PostgreSQL/Redis'e taşındığında mevcut host-local runner protokolü
kullanılacaktır. O profilde native runner database, Redis ve private-media volume'una
erişmez; yalnız `127.0.0.1` loopback API'sini dedicated `DOORS_RUNNER_TOKEN`, execution
token ve tek kullanımlık artifact capability'leriyle kullanır. Credential Manager ve
Task Scheduler yönergeleri ancak o profile geçiş planı onaylandığında devreye alınır.

## Doğrulama

Platformdan bağımsız contract testleri:

```bash
cd backend
../.venv/bin/python manage.py test automations \
  integrations.tests.test_doors_api \
  integrations.tests.test_doors_runner_tasks \
  jobs.tests.test_isolated_worker
```

Gerçek OLE canary'si Windows kullanıcı oturumunda ve test DOORS modülü üzerinde
ayrıca yapılmalıdır. Canary sırasında payload, private path veya credential
loglanmamalıdır.
