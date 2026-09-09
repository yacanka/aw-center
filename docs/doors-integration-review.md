# DOORS entegrasyonu incelemesi — 2026-09-09

İnceleme kapsamı: frontend DOORS API/ekranları, HTTP izin ve serializer sınırları,
durable job/artifact akışı, executor kataloğu ve Windows spawn worker'ı, COM
başlatma/bağlanma, bütün read/write/link DXL builder'ları, sonuç ayrıştırma,
Compliance DOORS import tüketicisi ve Excel → DXL üretimi.

Kullanıcının Windows hata kaydı ve IBM DOORS kurulumu bu ortamda bulunmadığından,
üretimde bütün işlerin hata vermesinin tek ve kesin nedeni doğrulanamadı. Aşağıdaki
kusurlar koddan tespit edilip düzeltildi. Sahte masaüstü sınırıyla başarılı testler,
IBM DXL derleyicisi veya gerçek Windows COM kabul testi yerine geçmez.

## Bulunan ve düzeltilen sorunlar

| Alan | Önceki kusur | Düzeltme |
| --- | --- | --- |
| Başlatma/giriş | Otomatik başlatma varsayılan kapalıydı; DOORS kullanıcı adı/parolası settings/config/startup akışında yoktu. | Açık istemciyi kullan; kapalıysa env ayarlarıyla normal GUI process'i başlat. İş sonunda DOORS'u kapatma. Açıkça verilen `False` tercihi korunur. |
| Executable bulma | Yalnız EXE yoluna dayanılıyordu; ProgID tek başına başlangıç için yeterli değildi. | EXE boşsa ProgID → CLSID → LocalServer32 üzerinden 64/32 bit registry görünümünde kurulum bulma. |
| Hazır olma | COM nesnesinin varlığı giriş tamamlanmış gibi kabul ediliyordu. | İş DXL'inden önce benzersiz işaret döndüren küçük DXL readiness kontrolü; süre sınırlı bekleme. |
| Windows oturumları | Process taraması bütün Windows oturumlarını kapsıyordu. Başka oturumdaki DOORS yeni istemci başlangıcını engelleyebilirdi. | Worker'ın SessionId'siyle tarama; aynı oturumda birden fazla istemciyi reddetme. |
| Timeout | Job katalog süresi DXL için 120 saniye iken istemci başlangıcı ve üç çağrılı disiplin kontrolü aynı süreyi tüketiyordu. | Parent timeout'a startup, gereken DXL çağrıları ve yayınlama payını dahil etme; mevcut subprocess fencing korunur. |
| Sonuç dosyası | DXL başında açılan dosyanın varlığı tamamlanma sayılıyordu; kısmi/boş sonuç başarıya dönüşebilirdi. | Tam dosya yoluna ait footer işareti zorunlu; UTF-8 sink, boyut kontrolü ve boş/bozuk sonuç reddi. |
| OLE Result | Sabit sonuç prefix'i farklı çağrıları ayırmıyordu. | Her Application.Result çağrısına ayrı correlation token. |
| Attribute okuma | Attribute değerleri DXL string fonksiyonuna açık string dönüşümü olmadan veriliyordu. | `object.attribute ""` dönüşümü. Satır/sayı/attribute sayısı ayrıştırmasını doğrulama. |
| Attribute arama | Arama metni kaçırılmıyor, sayaç durumu başlatılmıyor, AttrDef modül kapatıldıktan sonra kullanılıyordu. | Güvenli DXL quoting; object attribute filtresi; adı kapanıştan önce kopyalama; eksik/çoklu eşleşmeyi açık hata yapma. |
| Modül yaşam döngüsü | Okuma/yazma sonunda koşulsuz `close(module, false)` kullanıcının açık modülünü ve kaydedilmemiş değişikliklerini kapatabilirdi. | Önceden açık okuma modülünü kapatma. Önceden açık yazma kaynağını değiştirmeden reddet; önce kaydet/kapat yönlendirmesi. |
| Yazma hataları | Update/create `save` hatasını yakalamıyordu. Her bağlantı hatası yazma belirsizliği sayılıyordu. | Save hatasını yakala; DXL öncesi bağlantı ve bilinen yazma öncesi reddi normal failure yap. Yazma sonrası belirsizliği reconciliation olarak koru. |
| Disiplin kontrolü | Kullanılmayan checklist builder'ı bozuk format alanları/brace'ler içeriyordu; aktif yol ilk 20 objeyi filtrelemeden döndürüyordu. | Geçerli builder'ı aktif yola bağla; uygulanabilir olup disiplin değeri boş olan en fazla 20 objeyi döndür. |
| Linker | Aynı requirement metnine sahip farklı kaynak objeler tek adayda birleşiyordu; boş PoC anahtarları ve birden fazla hedefin aynı anahtarı taşıması yanlış linke yol açabilirdi. | Kaynak kimliğiyle tekilleştirme; boş anahtarı atlama; belirsiz hedefi yazma öncesi reddetme. |
| Excel → DXL | Üretilen script repository dışındaki `addins/user/yck.dxl` dosyasına bağımlıydı. | Arama helper'ını üretilen script içine dahil et; ekstra kurulum gereksinimini kaldır. |
| Input/hata sınırı | Obje olmayan JSON ve hashlenemeyen operation alanı genel hata oluşturabiliyordu. DXL int taşması/NUL değerleri kontrol edilmiyordu. | 400/worker validation; 32 bit object number sınırı ve NUL reddi. Raw upstream metin yerine allowlisted hata kodları. |

## Değişen kaynaklar

- `backend/awcenter/settings.py`, `.env.example`, `.env.development`, `.env.production`:
  dedicated DOORS credential ayarları ve otomatik başlangıç örnekleri.
- `backend/integrations/doors/config.py`, `services.py`, `startup.py`, `transport.py`:
  doğrulama, ProgID çözümleme, oturum/giriş/readiness, COM proxy temizliği ve sonuç protokolü.
- `backend/integrations/doors/builder_common.py`, `builder_read.py`, `builder_write.py`,
  `builder_link.py`, `checklist.py`, `client.py`: DXL ve ayrıştırma düzeltmeleri.
- `backend/integrations/doors/api_views.py`, `serializers.py`, `worker_tasks.py`,
  `job_executor.py`, `exceptions.py`: input doğrulama ve güvenli hata sınıflandırması.
- `backend/awcenter/job_executors.py`, `error_guidance.py`: toplam timeout ve kurtarma mesajları.
- `backend/integrations/doors/views.py`: bağımsız Excel → DXL script üretimi.
- `backend/integrations/tests/test_doors_api.py`, `test_doors_worker_tasks.py`,
  `test_doors_result_transport.py`, `test_doors_lifecycle.py`, `test_doors_execution.py`:
  regression ve API → artifact testleri.
- `docs/doors-worker.md`: kurulum, hata kodları, güvenlik sınırı ve Windows canary adımları.

Yeni uygulama bağımlılığı veya migration eklenmedi. Kullanıcının gerçek env dosyası,
production veritabanı ve private artifact state'i değiştirilmedi.

## Doğrulama

Python 3.11.15 için geçici ayrı virtualenv kuruldu; gerekli paketler mevcut
`requirements.txt` ile sınırlandı. Repository'nin mevcut `.venv`'i 3.14.6 olduğu
için değiştirilmedi. Test veritabanları disposable SQLite'tı.

| Kontrol | Sonuç |
| --- | --- |
| Python 3.11: `integrations`, production/environment/database/error-guidance checks, `compliance.test_doors_imports` | **176 test geçti** |
| Python 3.11: launcher/job launcher/release metadata | **38 test geçti** |
| Bağımsız dosya SQLite + gerçek spawned executor + sahte DOORS masaüstü | **Geçti**; kuyruktan başarılı terminal duruma, owner artifact ve SHA-256 doğrulamasına ulaştı |
| Frontend `test:ci` | **173 test geçti** (108 Vitest, 65 Node test) |
| Frontend typecheck ve build/bundle bütçesi | **Geçti** |
| Django `collectstatic --clear --noinput`, `verify_frontend_artifact` | **Geçti**; 37 frontend asset doğrulandı |
| Django `check`, `makemigrations --check --dry-run`, Python 3.11 compile, `git diff --check`, `launcher.py prod --help` | **Geçti**; migration değişikliği yok |
| Geniş backend grubu: integrations/automations/worker/isolated worker/production/SQLite/compliance | 217 testte 4 mevcut failure, 1 FFmpeg eksikliği nedeniyle skip; aşağıda açıklanmıştır |
| `format:check`, dolayısıyla `launcher.py check` tamamı | Mevcut `frontend/src/features/organization/api/organizationProjects.test.ts` biçim hatasında durdu; dosyaya dokunulmadı |

Geniş gruptaki dört failure, değişiklik öncesi `HEAD` içeriği `/tmp` altında ayrı
bir kopyaya çıkarılarak Python 3.11 ile yeniden üretildi:

1. `automations.test_architecture...test_jobs_internal_import_graph_is_acyclic`:
   mevcut `process_bootstrap → worker → process_bootstrap` import döngüsü.
2. `jobs.tests.test_isolated_worker...test_isolated_executor_publishes_only_through_parent_fencing`.
3. `jobs.tests.test_isolated_worker...test_parent_terminates_non_write_executor_on_timeout`.
4. `jobs.tests.test_isolated_worker...test_external_write_success_wins_cancellation_race`.

Son üç test, macOS spawn'ın Django test runner'ın process-local test veritabanı
ayarını miras almamasıyla ilişkili mevcut test ortamı sorununu gösteriyor.
Dosya tabanlı SQLite ve iki process'in aynı environment'ı kullandığı bağımsız
spawn smoke'u başarılıdır. Bu görevde generic job kernel'i veya test beklentileri
bu mevcut hataları gizlemek amacıyla değiştirilmedi.

## Operasyonel sınırlar ve kabul adımı

- Windows + IBM DOORS üzerinde gerçek login, license/database, GUI/COM ömrü ve DXL
  derleme/çalıştırma henüz doğrulanmadı. Frontend browser E2E çalıştırılmadı.
- IBM OLE arayüzü `runStr`, `runFile` ve `Result` sunar; bir login metodu varsayılmadı.
  Başlangıç ve DXL davranışları IBM kılavuzuyla karşılaştırıldı.
- Otomatik GUI girişi IBM'in `-user`/`-password` argümanlarını kullanır. Bunlar
  log/artifact/browser'a taşınmaz; yerel process argümanlarını okuyabilen Windows
  kullanıcı/araçları parolayı görebilir. Önceden giriş yapılmış istemci kullanımı
  otomatik başlatma kapalıyken korunur.
- Açık istemcinin mevcut DOORS kullanıcısı/veritabanı değiştirilmez. Kaynak modül
  masaüstünde açıksa otomatik yazma reddedilir; kullanıcı önce kaydedip kapatmalıdır.
- Eski production env dosyasında `DOORS_AUTO_START_CLIENT=False` varsa değer açıkça
  `True` yapılmalı ve dedicated username/password ayarları girilmelidir.
- Kabul için [Windows canary adımlarını](doors-worker.md#doğrulama) disposable
  test modülünde uygulayın. Timeout/cancellation sonrası belirsiz yazmayı otomatik
  yeniden göndermeyin; önce DOORS'taki sonucu doğrulayın.

Kaynaklar: [IBM istemci başlangıç seçenekleri](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors/9.7.2?topic=client-command-line-switches-doors-interoperation-server),
[IBM DXL Reference Manual](https://www.ibm.com/docs/en/SSYQBZ_9.6.0/com.ibm.doors.requirements.doc/topics/dxl_reference_manual.pdf).
