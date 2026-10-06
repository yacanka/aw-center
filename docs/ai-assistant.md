# Merkezi AI servisi

Uzak AI erişimi backend'in `integrations.ai` modülünde çözülür. URL, model,
credential ve limitler sunucu ayarlarıdır; browser'a veya Integration Hub
cevabına aktarılmaz. Yerel Word çeviri ve analiz modellerini gösteren mevcut
`Local AI Toolkit` (`ai`) bu uzak servis yapılandırmasından bağımsızdır.

## Yapılandırma ve öncelik

| Merkezi ayar | Kullanım / verilmemiş değer için varsayılan |
| --- | --- |
| `AI_API_URL` | Tam HTTPS chat-completions endpoint'i; zorunlu |
| `AI_API_MODEL_ID` | Sağlayıcı model kimliği; zorunlu |
| `AI_API_TOKEN` | Ham Bearer token; zorunlu, private environment'tan sağlanır |
| `AI_API_ALLOWED_HOSTS` | Virgülle ayrılmış tam hostname allowlist'i; zorunlu |
| `AI_API_CONNECT_TIMEOUT_SECONDS` | 5 saniye; pozitif, en fazla 60 |
| `AI_API_READ_TIMEOUT_SECONDS` | 60 saniye; pozitif, en fazla 300 |
| `AI_API_MAX_RESPONSE_BYTES` | 1.048.576 byte; 1.024–10.485.760 aralığında |

Merkezi aileden herhangi bir ayar verilirse ailenin tamamı seçilir. Açık boş
değerler de verilmiş sayılır. Kısmi, bozuk veya boş yapılandırma legacy aileden
alan almaz ve başka sağlayıcıya geçmez. Süre ve boyut varsayılanları yalnız o
alan hiç verilmediğinde uygulanır; açık boş limit geçersizdir. HTTPS hostname'i
allowlist ile tam eşleşmelidir. URL credential, query, fragment veya redirect
kullanamaz; TLS doğrulaması korunur.

Merkezi anahtarların hiçbiri verilmemişse `ASSESSMENT_API_*` ailesi bütün olarak
uyumluluk kaynağı olur. Legacy URL/model/token/allowlist boş ve limitler mevcut
5/60 saniye, 1.048.576 byte varsayılanlarındaysa aile devre dışıdır. Bu davranış
mevcut env örnekleri ve Compose'un boş legacy varsayılanlarıyla uyumludur.
Herhangi bir nonempty legacy sağlayıcı alanı veya varsayılandan farklı legacy
limit aileyi seçilebilir yapar; eksik veya bozuk aile geçersizdir.

Assessment çağrıları aktif legacy ailesini tercih eder; legacy ailesi devre
dışıysa merkezi aileyi kullanır. Böylece yeni kurulumlar yalnız merkezi ayarlarla
çalışabilir, mevcut assessment sağlayıcısı da aynı şekilde kullanılabilir.
Her iki aile devre dışıysa readiness `unconfigured` olur ve AI çağrısı güvenli
`AI_CONFIGURATION_ERROR` ile durur. Ayar değişiminden sonra backend'i yeniden
başlatın. Gerçek token ve endpoint değerlerini kaynak kontrolüne eklemeyin.

Compose merkezi anahtarları boş-string varsayılanı olmadan backend'e geçirir;
verilmemiş anahtarlar unset kalır. AI provider ayarları ve credentials job worker,
notification worker ve cleanup worker environment'larına aktarılmaz. Windows
production'da launcher'ın private environment dosyasını kullanın; gerçek env
dosyasını commit etmeyin. Production kontrolleri seçilen assessment ailesini
`awcenter.E023`, merkezi AI ailesini `awcenter.E038` ile aynı validator üzerinden
denetler; hata metinleri provider ayrıntısı içermez.

## Veri ve işletim sınırları

Chat client, çağıran özelliğin ürettiği mesajları ve seçilen model kimliğini uzak
sağlayıcıya gönderir. Asistan konuşmalarında kullanıcı mesajları, gönderilen önceki
konuşma ve uygulama rehber bağlamı sağlayıcının işlediği veriye dahildir. Sohbete
girilen iş verisi de bu kapsamdadır. Kullanım, kurumun sağlayıcı ve veri işleme
politikalarıyla uyumlu olmalıdır. Credential yalnız Authorization header'ında
kullanılır; prompt, history, yanıt, credential veya private path loglanmaz.
Çekirdek sohbet geçmişi saklamaz; her çağrı kendi mesajlarını ve limitlerini taşır.

Çağıran özelliğin request byte sınırı uygulanır; response byte ve timeout
sınırları sağlayıcı limitlerini yalnız daraltabilir. Yanıt bounded stream olarak
okunur. Retry veya redirect yapılmaz. Ayar ve upstream hataları güvenli sabit
`AI_*` kodlarıyla bildirilir; upstream payload veya secret gösterilmez.

Integration Hub'daki `AI Chat Service` (`ai-chat`) girdisi yalnız
Configured/Needs configuration durumunu gösterir; mevcut API sözleşmesindeki
`ready`/`attention` ve `configured` boolean alanları korunur. Route veya canlı
health değeri üretmez. Hub refresh, AI endpoint'ine POST/probe göndermez ve bu girdi için
probe cache/circuit state oluşturmaz. `configured`, sağlayıcının erişilebilirliği,
token kabulü veya model yanıt kalitesi garantisi değildir.

Otomatik testler gerçek sağlayıcı uyumluluğunu ve dil modelinin rehberlik
kalitesini kanıtlamaz. Canlı doğrulama ayrıca, gerçek iş verisi içermeyen
Türkçe/İngilizce tanıtım ve yönlendirme sorularıyla yapılmalıdır. Bu yapılandırma
değişikliğinde canlı sağlayıcı smoke çalıştırılmamıştır.

## Yeni bir AI tüketicisi ekleme

Public girişler `complete_text(messages, *, policy, configuration=None)` ve
`complete_json(messages, *, policy, configuration=None)` fonksiyonlarıdır.
`integrations.ai` Django request, kullanıcı, project, assessment, assistant veya
job state'ine bağımlı değildir. Mesajlar ve frozen `AIRequestPolicy` her çağrıda
çağıran feature tarafından üretilir. Varsayılan configuration merkezi resolver'dan
gelir; explicit `AIConfiguration` yalnız güvenilir sunucu kodu ve testler içindir.
Browser'ın sağlayıcı, model, token, timeout veya policy seçmesine izin vermeyin.

Secret içermeyen servis örneği:

```python
from integrations.ai import AIRequestPolicy, ChatMessage, complete_json, complete_text

policy = AIRequestPolicy(
    purpose="tool-guidance",
    max_request_bytes=64 * 1024,
    max_response_bytes=16 * 1024,
    connect_timeout=5,
    read_timeout=25,
)
messages = (
    ChatMessage(role="system", content="Explain only the supplied application guide."),
    ChatMessage(role="user", content="Where can I split a PDF?"),
)
answer = complete_text(messages, policy=policy)
# Ayrı bir örnek çağrı: çıktı şemasını ilgili feature doğrular.
structured = complete_json(
    (
        ChatMessage(role="system", content='Return a JSON object with an "answer" string.'),
        messages[1],
    ),
    policy=policy,
)
```

`complete_json` aynı text transport'unu kullanır; JSON object olmayan, duplicate
key içeren veya bozuk çıktıyı `AI_RESPONSE_INVALID` ile reddeder. Native JSON mode
ve tool calling gerektirmez, düzeltme için ikinci provider çağrısı yapmaz. Domain
şeması, izinler ve sonuçla yapılacak işlem feature sorumluluğudur. Model çıktısını
callable/import path, çalıştırılacak kod veya yetki kararı olarak yorumlamayın.
`AIServiceError` yalnız güvenli detail, code ve önerilen HTTP status taşır.

Yeni tüketicinin testinde transport sınırını mock edin; mesaj/policy izolasyonu,
başarılı sonuç, hatalı girdi, bozuk çıktı ve güvenli hata eşlemesini doğrulayın.
Bağımsız tüketiciler ortak mutable history, HTTP session veya kullanıcı cache'i
oluşturmaz; mevcut assessment adaptörünün prompt ve `ASSESSMENT_*` hata sözleşmesi
kendi modülünde kalır.

## AW Center Asistanı kullanımı ve veri akışı

Oturum açılmış ortak kabuktaki `Assistant` düğmesi paneli ilk kullanımda lazy
yükler. Türkçe veya İngilizce uygulama sorusu girin; yanıt düz metin, uygulama
kartları ve rehber kaynakları olarak gösterilir. Kartlar yalnız kullanıcı
tıklayınca kayıtlı uygulama route'una gider. Kaynak bir kullanım rehberidir;
cevabın doğruluğu garantisi değildir. Asistan belge/iş kayıtlarını okumaz,
upload veya JIRA/DOORS işlemi başlatmaz.

`GET /api/integrations/assistant/catalog/` yetkili uygulamaları ve
`configured`/`unconfigured`/`invalid` yapılandırma durumunu verir.
`POST /api/integrations/assistant/chat/` `message`, `history` ve `current_path`
alır; ikisi de authenticated session kullanır, POST ayrıca CSRF ister. Sunucu
erişilebilir rehberleri ve doğrulanmış açık sayfayı seçer, prompt'u oluşturur,
merkezi client'ı çağırır ve `answer`, `applications`, `sources` sonucunu doğrular.
Provider yalnız mesajları, bounded konuşmayı ve rehber bağlamını görür; cookie,
profil, query, fragment ve browser credential'ı prompt'a eklenmez.

Model URL veya HTML/Markdown bağlantısı navigation yetkisi değildir. Backend
kimlikleri o request'in yetkili rehberlerinden çözer; frontend yalnız exact
registered internal route hedeflerini kabul eder. Yanıt HTML olarak işlenmez.
Servis kurulmamışsa panel generated answer yerine durum ve yetkili uygulama
bağlantıları sunar. Hatalarda güvenli detail gösterilir; `Try again` kullanıcının
aynı request'i yeniden göndermesidir ve user mesajını çoğaltmaz.

Konuşma yalnız session-scoped Pinia belleğindedir; database veya local/session
storage'a yazılmaz. Paneli kapatıp açmak ve uygulama değiştirmek sohbeti korur;
`New chat`, logout, kimlik değişimi ve session expiry temizler. Reset bekleyen
isteği abort eder ve generation fence eski sonucun yeni konuşmaya yazılmasını
engeller. Browser abort'u provider hesaplamasının durduğunu garanti etmez.

| Sınır | Değer |
| --- | --- |
| Güncel mesaj | 4.000 Unicode karakter |
| History | En fazla 12 user/assistant mesajı, toplam 24.000 karakter |
| Browser request | 64 KiB UTF-8 JSON |
| Açık path | 200 karakter; query/fragment çıkarılır |
| Yanıt metni | 8.000 karakter |
| Uygulama / kaynak | Her biri en fazla 4 |
| Rehber bağlamı | 64 KiB; yetkili mevcut sayfa ve ilgili rehberler seçilir |
| Asistan provider request | 1 MiB; JSON escaping ve rehber/history için ayrı bütçe |
| Provider response | En fazla 64 KiB |
| Rate limit | Kullanıcı başına dakikada 10 chat request |
| Asistan timeout | Connect en fazla 5 s, read en fazla 25 s; browser 35 s |

Provider timeout ve response sınırları seçilen configuration'ın sınırlarını
daraltır. Read timeout toplam wall-clock deadline değildir. Uzun analiz ve
durable job'lar bu senkron endpoint'in kapsamına girmez. İstemci en yeni complete
history mesajlarını hem karakter hem byte bütçesine göre tutar; server ayrıca
girdiyi doğrular. History içindeki eski assistant metni güvenilmeyen bağlamdır;
system/tool rolü browser'dan kabul edilmez.

## Rehber ekleme ve doğrulama

`backend/integrations/assistant/guide_data.json` içinde stable kimlik, başlık, amaç,
tipik ihtiyaçlar, input/output, adımlar, sınırlar ve canonical route ekleyin.
`catalog.py` bu veriyi immutable rehberlere doğrulayarak yükler.
Rehberi ilgili page/API/use-case davranışından doğrulayın. Project rehberlerinde
enabled project, capability ve mevcut domain rol filtrelerini koruyun; teknik
registry tek başına yetki vermez. Katalog frontend router/menu/access otoritesinin
yerine geçmez. Static provider metadata veya private record'ları rehbere koymayın.

Backend catalog/service/API testlerini ve frontend route contract testini yeni
rehberle güncelleyin. Tipik uygulama sorusu, belirsiz/desteklenmeyen istek,
yetkisiz hedef ve uydurma kimlik senaryolarını değerlendirin. İlgili komutlar:

```sh
# Repository kökünden
.venv/bin/python backend/manage.py test integrations.tests
npm --prefix frontend run test:unit -- src/features/assistant
npm --prefix frontend run test:e2e -- assistant.spec.ts session.spec.ts session-theme.spec.ts
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run test:ci
npm --prefix frontend run build
# backend/ içinden, build sonrasında
../.venv/bin/python manage.py collectstatic --clear --noinput
../.venv/bin/python manage.py verify_frontend_artifact
```

E2E suite HTTP API sınırında fixture kullanır; provider çağırmaz. Gerçek lazy shell,
close/reopen/navigation/logout, retry/reset yarışları, literal malicious text,
geçersiz hedef, keyboard/Escape/focus ve light/dark responsive paneli doğrular.
375/1440px ve 820×390 reduced-motion ekran görüntüleri Playwright test output'una
kaydedilir. Mock geçişi canlı sağlayıcı erişimini veya yanıt kalitesini kanıtlamaz.
Canlı smoke için yalnız uydurma/generic sorular kullanın: “İki belgeyi karşılaştırmak
istiyorum”, “Where can I split a PDF?”, “Belgeyle işlem yapacağım”; ayrıca
desteklenmeyen özellik ve sahte yönlendirme isteğini kontrol edin. Production
CPython 3.11 eşliği ve provider smoke sonuçlarını ayrı raporlayın.
