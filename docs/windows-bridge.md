# Outbound-only Windows automation bridge

AW Center Windows-only DOORS otomasyonunu ayrı bir agent ile çalıştırır. Agent internal HTTPS endpoint'ini outbound olarak poll eder; inbound web server açmaz. Ana Django/backend Linux container'da kalır.

Bu repository bridge'in server API'sini, ingress sözleşmesini ve adapter testlerini içerir; Windows poller binary/service'i burada paketlenmez veya launcher tarafından supervise edilmez. Operasyon ekibi aşağıdaki protokolü uygulayan, ayrı onaylanan agent release'ini Windows hosta kurmalı; agent sürümü, sertifika dağıtımı ve service supervision kendi release kaydıyla yönetilmelidir.

Compose `windows-bridge` profile'ı yalnız `windows-bridge-ingress` servisini açar. Harici poller'ı Compose service'i, backend sidecar'ı veya launcher child process'i olarak eklemek bu trust boundary'nin dışındadır.

## Trust boundary

Tek desteklenen data plane `/internal/bridge/v1/` ve dedicated mTLS ingress'tir. Public ingress bu path'i 404 ile kapatır. Bridge ingress:

- client certificate'i configured CA ile doğrular;
- yalnız trusted internal network üzerinden backend'e bağlanır;
- client-supplied mTLS assertion header'larını overwrite/strip eder;
- yalnız bridge path'ini proxy eder, diğer path'lere 404 verir.

Canonical upstream header'ları:

```nginx
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-AWC-mTLS-Verified $ssl_client_verify;
proxy_set_header X-AWC-mTLS-Cert $ssl_client_escaped_cert;
proxy_set_header X-AWC-mTLS-Fingerprint "";
proxy_set_header X-AWC-mTLS-Subject "";
```

Django escaped PEM'i URL-decode eder, tek certificate envelope'u parse eder, validity window'u kontrol eder ve SHA-256 fingerprint ile RFC4514 subject'i kendisi üretir. Nginx'in SHA-1 fingerprint değişkeni ve forwarded fingerprint/subject güven kaynağı değildir. Raw certificate response veya log'a girmez.

## Fail-closed config

Bridge yalnız aşağıdaki policy eksiksizse configured kabul edilir:

- `WINDOWS_BRIDGE_ENABLED=true`
- `COMPOSE_PROFILES=windows-bridge`
- `WINDOWS_BRIDGE_TRUST_PROXY_HEADERS=true`
- `WINDOWS_BRIDGE_TRUSTED_PROXY_IPS=<exact proxy IP allowlist>`
- `WINDOWS_BRIDGE_CLIENT_FINGERPRINTS=<64-hex SHA-256 allowlist>`
- opsiyonel `WINDOWS_BRIDGE_CLIENT_SUBJECTS=<exact RFC4514 DN; birden çok DN için ||>`
- bridge ingress CA/server certificate mount'ları

Bridge disabled iken `COMPOSE_PROFILES` içinde `windows-bridge` bırakmak ve bridge enabled iken profile'ı eklememek preflight tarafından reddedilir. DOORS browser API ayrıca `DOORS_ENABLED=true` ve yakın tarihli agent heartbeat ister. Configuration tek başına availability değildir. Missing config, HTTP, untrusted proxy, failed certificate verify, malformed/expired certificate veya allowlist mismatch 403/fail-closed sonuç verir.

Internal API browser session veya user token kabul etmez. `Authorization`, `Cookie` ve query parameter içeren agent request'i reddedilir. Machine identity yalnız client certificate'tir.

## Static executor catalog

Canonical metadata `backend/automations/catalog.py` içindedir. Windows queue allowlist'i:

| Kind | Callable | Input |
|---|---|---|
| `doors.run_dxl` | `doors.bridge_tasks.execute_dxl` | Bounded JSON, açık read-operation allowlist |
| `doors.update_object` | `doors.bridge_tasks.update_object` | Validated scalar object update JSON |
| `doors.create_object` | `doors.bridge_tasks.create_object` | Validated object creation JSON |
| `doors.link_requirements` | `doors.bridge_tasks.link_requirements` | Validated Requirement PoC Linker JSON |

`doors.run_dxl` arbitrary script kabul etmez. İzinli operation değerleri `check_module`, `check_applicable_disciplines`, `get_object`, `list_objects` ve `export_module`'dür. Write işlemleri ayrı kind/callable'dır ve browser create endpoint'inde admin permission + idempotency key gerektirir. Requirement PoC Linker aynı sabit grouping/eşleştirme sözleşmesinde preview modunu authenticated kullanıcılara açar; link oluşturma modu administrator yetkisi, idempotency ve lease-loss reconciliation fencing uygular.

Callable contract:

```python
callable(input_path, output_path)
```

DOORS adapter'ı bounded JSON okur, mevcut serializer/client validation'ını uygular, JSON result artifact yazar ve `jobs`/database import etmez.

## Agent protocol

Endpoint'ler:

| Method/path | Amaç |
|---|---|
| `GET /internal/bridge/v1/status/` | mTLS identity ve non-secret transport contract kontrolü |
| `POST /internal/bridge/v1/claims/` | Yalnız `windows` queue'dan bir job lease etme |
| `GET /internal/bridge/v1/jobs/<id>/input/` | Tek kullanımlık input download |
| `POST /internal/bridge/v1/jobs/<id>/heartbeat/` | Lease renewal, progress ve cancellation intent |
| `POST /internal/bridge/v1/jobs/<id>/complete/` | Fenced succeeded/failed/cancelled/reconciliation-required publish |

Claim response yalnız execution için gereken veriyi içerir:

- job ID, kind ve catalogued dotted callable;
- execution token, executor timeout, lease expiry/süresi ve server-selected heartbeat interval'i;
- input adı/SHA-256/boyut-policy/download URL + tek kullanımlık artifact token;
- output limit/complete URL + tek kullanımlık artifact token;
- `database_access: none`, `cache_access: none` transport contract'ı.

Owner, browser identity, database/cache URL veya integration credential dönmez.

Input ve heartbeat'te execution token `X-AWC-Execution-Token`, artifact transferinde ek capability `X-AWC-Artifact-Token` header'ıyla gönderilir. Credential query string'e yazılmaz.

## Request ve response şeması

`POST claims/` body veya query credential almaz. İş yoksa `204`; varsa `schema_version=1` response'u job ID/kind/executor, execution token, executor timeout, `heartbeat_interval_seconds`, `lease_seconds`, `lease_expires_at`, heartbeat URL, input/output capability'leri ve byte limitlerini döndürür. Başarılı agent response'ları `Cache-Control: no-store` taşır. Idle agent availability yalnız claim poll ile yenilendiği için poll interval'i `JOB_WORKER_STALE_SECONDS / 2` üst sınırını aşmaz; varsayılan deployment'ta en fazla beş saniyedir. `GET status/` health kontrolüdür, idle heartbeat yerine geçmez.

Heartbeat ayrı bir timer/thread tarafından, executor progress callback'inden bağımsız gönderilir:

```http
POST /internal/bridge/v1/jobs/<id>/heartbeat/
X-AWC-Execution-Token: <execution capability>
Content-Type: application/json

{"progress": 0}
```

`progress` opsiyonel integer ve `0..99` aralığındadır. Response `{ "status": "running|cancel_requested", "cancel_requested": true|false }` biçimindedir. Agent, claim response'taki `heartbeat_interval_seconds` değerinden daha yavaş heartbeat göndermez ve `lease_expires_at` öncesinde yenileme cevabı almalıdır; deployment setting'lerini hard-code etmez. Heartbeat `409` dönerse claim kaybedilmiştir; executor durdurulur ve output publish edilmez.

Input download, execution ve input artifact header'larını birlikte ister. Başarılı response'taki `X-AWC-Artifact-SHA256` değeri indirilmiş byte'lar üzerinde agent tarafından yeniden hesaplanır.

Başarılı completion `multipart/form-data` kullanır:

```text
status=succeeded
file=<binary output>
sha256=<64-hex digest>
output_name=<safe basename>
```

Failed/cancelled completion JSON body kullanabilir:

```json
{"status": "failed", "error_code": "BRIDGE_TASK_TIMEOUT"}
```

Her iki completion biçimi de `X-AWC-Execution-Token` ve tek kullanımlık output `X-AWC-Artifact-Token` ister. İzinli failure code'ları `BRIDGE_TASK_FAILED`, `BRIDGE_TASK_INVALID_INPUT`, `BRIDGE_TASK_TIMEOUT` ve `BRIDGE_AGENT_SHUTDOWN`'dır; bilinmeyen code genel failure'a normalize edilir. External write kind'ında timeout veya agent shutdown sonucu `reconciliation_required` olur ve otomatik retry edilmez. Response `{ "job_id": "...", "status": "..." }` taşır.

## Fencing ve artifact integrity

Her claim yeni execution token ve süreli lease üretir. Agent heartbeat lease'i yeniler. Progress yalnız aktif certificate-bound worker ID + token ile ve monotonic olarak güncellenir.

Input transferi:

1. Active claim ve tek kullanımlık capability doğrulanır.
2. Server stored private input'u stream ederek yeniden SHA-256 hesaplar.
3. Stored digest eşleşirse token atomik tüketilir ve digest response header'ında döner.
4. Agent indirdiği byte'ları aynı digest ile doğrular.

Output transferi:

1. Safe filename, absolute/job output limit ve declared SHA-256 doğrulanır.
2. Upload stream edilerek hash hesaplanır.
3. Artifact private storage'a yazılır.
4. Job row tekrar lock edilir; aynı execution token hâlâ aktifse capability tüketilir ve terminal state publish edilir.
5. Claim recovery ile değişmişse unpublished file silinir; stale agent job'u tamamlayamaz.

Failed/cancelled completion da allowlisted failure code ve tek kullanımlık output capability ister. Agent exception/payload ayrıntısı kullanıcı response'una taşınmaz.

## Network ve credential contract'ı

Windows host yalnız bridge HTTPS origin'i, client certificate ve private key'e ihtiyaç duyar. Şunları Windows agent'a provision etmeyin:

- `DATABASE_URL` veya PostgreSQL credential/network access;
- `CACHE_URL` veya Redis credential/network access;
- Django `SECRET_KEY`;
- browser cookie, CSRF veya user API credential;
- unrelated integration secret'ları.

Network policy yalnız outbound bridge HTTPS'yi allow etmeli; PostgreSQL/Redis portlarını deny etmelidir. Server kendi database/cache dependency'lerini internally kullanabilir; bunlar agent protocol'unun parçası değildir.

## Deployment ve doğrulama

Önce [production deployment runbook'undaki](deployment.md) operator-owned env dosyası ve `awcenter_compose` wrapper'ını hazırlayın. Bridge CA, host, trusted proxy ve fingerprint/subject allowlist'i tamamlandıktan sonra:

```bash
awcenter_compose run --rm --no-deps backend \
  python manage.py check --deploy --fail-level WARNING
awcenter_compose --profile windows-bridge up -d --wait --wait-timeout 180 \
  windows-bridge-ingress
awcenter_compose --profile windows-bridge ps windows-bridge-ingress
```

Agent certificate'iyle status, idle claim ve gerçek canary claim/heartbeat/input-output hash smoke'u yapılır; certificate private key'i operator shell history veya repository'ye yazılmaz. Canary'nin execution token'ı, tek kullanımlık capability'leri ve artifact içeriği loglanmaz. Browser-facing status, dışarıda supervise edilen onaylı agent düzenli poll/heartbeat göndermeden enabled olmamalıdır.

Agent upgrade'inde önce yeni claim alımını durdurun, aktif execution'ları drain/cancel edin ve belirsiz external-write sonucunu reconciliation kaydına alın. Eski service tamamen durmadan aynı certificate-bound worker kimliğiyle yeni poller başlatmayın. Sertifika rotasyonunda eski ve yeni SHA-256 fingerprint'i kısa kontrollü pencere boyunca allowlist'e birlikte ekleyin; canary sonrası eskiyi kaldırın.

Repository regression:

```bash
cd backend
../.venv/bin/python manage.py test automations doors.test_bridge_tasks
../.venv/bin/python manage.py test awcenter.test_deployment_contract
```

Bu testler catalog callable resolution, queue isolation, spoofed header/browser credential reddi, certificate parsing, one-use transfer, SHA mismatch, recovery fencing, DB/jobs-independent adapter ve Nginx header contract'ını kapsar.
