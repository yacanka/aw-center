# Host-local Windows DOORS runner

AW Center ve IBM Rational DOORS aynı Windows cihazda çalışır. Django/Vue,
PostgreSQL, Redis ve genel worker lifecycle'ları Linux container'larında kalır;
OLE/COM gerektiren DOORS executor ise DOORS'un açık olduğu Windows kullanıcı
oturumunda native process olarak çalışır.

Runner ayrı bir uzak sunucu veya inbound agent değildir. Yalnız host
loopback'ine publish edilen `http://127.0.0.1:8765/internal/doors-runner/v1/`
data plane'ini poll eder. Public HTTPS ingress bütün `/internal/` yollarını 404
ile kapatır.

## Neden ayrı process korunuyor?

HTTP request process'i uzun süren COM çağrısı çalıştırmaz. Native runner:

- `pythoncom` ile Windows COM apartment'ını başlatır;
- açık ve authenticated `DOORS.Application` OLE nesnesine bağlanır;
- her işi disposable `spawn` subprocess'inde çalıştırır;
- server-selected heartbeat aralığıyla lease'i yeniler;
- timeout, cancellation ve stale claim sonucunda subprocess'i sonlandırır;
- sonucu SHA-256 ile doğrulayıp fenced completion olarak yayımlar.

Runner'a PostgreSQL/Redis credential'ı, Django `SECRET_KEY`, browser cookie'si
veya private artifact volume'u verilmez.

## Kimlik ve network sınırı

`DOORS_RUNNER_TOKEN` kurulumda `secrets.token_urlsafe(32)` ile üretilen en az
256-bit shared secret'tır. URL, query string, browser response veya log'a
yazılmaz. Runner her istekte `X-AWC-Runner-Token` header'ını gönderir; backend
constant-time comparison uygular.

Bu token yalnız runner process'ini tanıtır. Claim sonrasında verilen execution
token ile tek kullanımlık input/output artifact token'ları ayrıca zorunludur.

Compose yalnız şu host binding'ini yayınlar:

```text
127.0.0.1:${DOORS_RUNNER_PORT:-8765}:8765
```

LAN veya internet adresine binding eklemeyin. Main Nginx local listener'ı yalnız
runner path'ini proxy eder, `Authorization` ve `Cookie` header'larını temizler,
diğer yolları 404 döndürür.

## Token provisioning

Token'ı secret içermeyen bir komutla üretin:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

1. Değeri backend deployment secret manager'ında `DOORS_RUNNER_TOKEN` olarak
   saklayın. Repository veya tracked `.env` dosyasına yazmayın.
2. Windows Credential Manager arayüzünde, DOORS'u çalıştıran kullanıcı için bir
   Generic Credential oluşturun. Target adı varsayılan olarak
   `AWCenter/DOORSRunner`, password alanı token değeridir.
3. Farklı target kullanılırsa runner ortamında
   `DOORS_RUNNER_CREDENTIAL_TARGET` ayarlayın.

Native runner önce process environment'daki `DOORS_RUNNER_TOKEN` değerini,
sonra current-user Windows Credential Manager kaydını kullanır. Production'da
Credential Manager tercih edilir. Token'ı CLI argument olarak geçiren seçenek
yoktur.

Rotasyondan önce yeni claim alımını durdurun, aktif işleri drain/cancel edin,
backend ve Credential Manager değerlerini aynı maintenance penceresinde
değiştirin, backend ve runner'ı yeniden başlatın. Belirsiz DOORS write sonucunu
tekrar göndermeden önce reconciliation kaydını doğrulayın.

## Runner kurulumu ve çalışma

Runner backend release'iyle aynı source/release sürümünden çalışmalıdır. Windows
Python ortamında locked bağımlılıkları kurun; platform marker'ları `pywin32` ve
`WMI` paketlerini getirir. DOORS bağlantı ayarlarını runner process environment'ı
veya ignored `backend/.env` içinde yapılandırın:

```text
DOORS_ENABLED=True
DOORS_EXECUTABLE=C:\IBM\DOORS\doors.exe
DOORS_DATABASE=36677@doors-server
DOORS_PREFER_ACTIVE_INSTANCE=True
DOORS_AUTO_START_CLIENT=False
DOORS_RUNNER_URL=http://127.0.0.1:8765
DOORS_RUNNER_CREDENTIAL_TARGET=AWCenter/DOORSRunner
```

`backend/` dizininden foreground canary:

```powershell
..\.venv\Scripts\python.exe manage.py run_doors_runner --once
```

Sürekli çalışma:

```powershell
..\.venv\Scripts\python.exe manage.py run_doors_runner
```

Task Scheduler kaydı DOORS ile aynı kullanıcıya ait olmalı ve **Run only when
the user is logged on** seçeneğini kullanmalıdır. Session 0 altında ayrı service
account ile çalıştırmak, aktif desktop OLE nesnesine erişimi garanti etmez.
Runner aynı anda tek DOORS işi yürütür.

Task Scheduler action'ında program olarak repository kökündeki
`.venv\Scripts\python.exe`, argument olarak `manage.py run_doors_runner` ve
**Start in** olarak release'in `backend` dizinini kullanın. Böylece runner,
server ile aynı source sürümünü ve doğru Django settings yükleme kökünü kullanır.

## Statik executor allowlist'i

Canonical metadata `backend/automations/catalog.py` içindedir. `doors` queue
yalnız şu kind'ları kabul eder:

| Kind | Callable | Input |
|---|---|---|
| `doors.run_dxl` | `integrations.doors.runner_tasks.execute_dxl` | Bounded JSON ve sabit read-operation allowlist |
| `doors.update_object` | `integrations.doors.runner_tasks.update_object` | Validated scalar update JSON |
| `doors.create_object` | `integrations.doors.runner_tasks.create_object` | Validated object creation JSON |
| `doors.link_requirements` | `integrations.doors.runner_tasks.link_requirements` | Validated Requirement PoC Linker JSON |

Server claim içinde callable yolu döndürse de runner bu yolu kendi local
catalog'uyla yeniden doğrular. Arbitrary DXL veya server-selected Python callable
çalıştırılmaz.

## Data plane

| Method/path | Amaç |
|---|---|
| `GET /internal/doors-runner/v1/status/` | Token ve transport contract kontrolü |
| `POST /internal/doors-runner/v1/claims/` | Yalnız `doors` queue'dan job lease etme |
| `GET /internal/doors-runner/v1/jobs/<id>/input/` | Tek kullanımlık, SHA-256 doğrulanan input |
| `POST /internal/doors-runner/v1/jobs/<id>/heartbeat/` | Lease renewal, progress ve cancellation intent |
| `POST /internal/doors-runner/v1/jobs/<id>/complete/` | Fenced terminal publish |

Internal API browser session veya user token kabul etmez. `Authorization`,
`Cookie` veya query parameter içeren istek reddedilir. Başarılı ve hatalı bütün
runner response'ları `Cache-Control: no-store` taşır.

DOORS write işinde timeout, runner shutdown, cancellation veya lease loss sonucu
`reconciliation_required` olur; dış sistem sonucu doğrulanmadan otomatik retry
yapılmaz.

## Doğrulama

```bash
cd backend
../.venv/bin/python manage.py test automations integrations.tests.test_doors_runner
../.venv/bin/python manage.py test integrations.tests.test_doors_api \
  integrations.tests.test_doors_runner_tasks
../.venv/bin/python manage.py test awcenter.test_deployment_contract
```

Gerçek OLE canary'si Windows kullanıcı oturumunda, test DOORS modülü üzerinde
ayrıca yapılmalıdır. Canary sırasında runner token, execution token, artifact
capability veya payload loglanmamalıdır.
