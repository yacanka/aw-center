# Merkezi AI erişimi ve AW Center Asistanı

Bu tasarım, mevcut AI servis erişimini farklı özelliklerin bağımsız kullanabildiği
ortak fonksiyonlara ayırır ve bunları kullanan AW Center yardımcı asistanını ekler.
Kullanıcı asistanın rehberlik, sohbet ve uygulama bağlantıları sunması kapsamını
onayladı; ortak altyapının `assessment.py` genişletilerek kurulmasını istemedi.
Bu belge bu kararı somutlaştırır. Uygulama kodu henüz değiştirilmemiştir.

## Amaç ve başarı ölçütleri

Asistan kullanıcının yapmak istediği işi anlayarak uygun AW Center uygulamasını
önerir, doğrulanmış kullanım adımlarını açıklar ve erişilebilir sayfalara bağlantı
sunar. Belirsiz isteklerde açıklama ister; Türkçe ve İngilizce sorulara sorunun
dilinde yanıt verir. Açık sayfa ve sınırlı konuşma geçmişi bağlama katılır.

Merkezi AI fonksiyonları Django HTTP request nesnesine, belirli bir feature'a,
konuşma deposuna veya kullanıcı modeline bağımlı olmaz. Assessment ve asistan aynı
transport uygulamasını kullanırken prompt, yanıt doğrulaması, yetki ve durumlarını
birbirinden bağımsız yönetir. Ayrı kullanıcıların, konuşmaların veya kullanım
amaçlarının verileri ortak mutable state üzerinden birbirine geçmez.

İlk sürüm rehberlik ve yönlendirmedir. Canlı belge/iş kayıtları okunmaz; kayıt
oluşturma, dosya yükleme, JIRA/DOORS işlemi başlatma veya kendiliğinden gezinme
yapılmaz. Yerel çeviri ve embedding modellerinin mevcut çalışma biçimi bu görevde
değişmez. Uzak sohbet servisi ortak fonksiyonlarla merkezileştirilir.

## Mevcut koddan doğrulanan durum

- `integrations/assessment.py`, HTTPS host allowlist, yönlendirme engeli, süre ve
  yanıt boyutu sınırı ile `messages` tabanlı senkron chat endpoint'ine erişiyor.
- `ddf/views.py` ve `dcc/watcher_assessment.py` bu adaptörü kullanıyor; prompt ve
  sonuç işleme kuralları ilgili feature içinde bulunuyor.
- Frontend route'ları `app/router/routes.ts`, menü görünürlüğü
  `app/services/mainMenu.ts` ve `features/session/services/accessPolicy.ts` içinde.
  Tarayıcı route tabanı `/app/`.
- Proje görünürlüğünün backend otoritesi `orgs.access_policy`; teknik capability
  kataloğu `projects.registry`. Teknik registry tek başına erişim yetkisi değildir.
- Mevcut `Local AI Toolkit`, uzak assessment servisini değil yerel model
  dosyalarını temsil ediyor. Asistan bu ikisini birbirine karıştırmamalıdır.
- Sağlayıcının native function calling veya JSON schema mode desteği koddan
  doğrulanmıyor. İlk sürüm bunları zorunlu tutmaz.

## Seçilen yaklaşım ve alternatifler

Seçilen yaklaşım, `integrations/ai/` altında küçük bir ortak Python paketi ve
ondan bağımsız bir asistan kullanım senaryosudur. Yeni Django app, model,
migration, bağımlılık veya genel amaçlı agent framework gerekmez.

`assessment.py` içine sohbet ve araç mantığı eklemek merkezileşmeyi bir feature'a
bağlayacağı için seçilmedi. Ayrı AI mikroservisi veya dinamik plugin/tool runtime'ı
ise mevcut ihtiyaca göre ek deployment ve güvenlik yükü getirir. Bağımsız tüketim,
açık fonksiyon sözleşmeleri ve bağımlılık sınırlarıyla sağlanır.

## Modül sınırları

| Konum | Sorumluluk |
| --- | --- |
| `backend/integrations/ai/contracts.py` | Immutable mesaj, istek politikası ve sonuç tipleri; güvenli ortak hata |
| `backend/integrations/ai/config.py` | Sunucu ayarlarından doğrulanmış sağlayıcı yapılandırması |
| `backend/integrations/ai/client.py` | Ortak metin ve JSON sorgu fonksiyonları; girdi ve çıktı sınırları |
| `backend/integrations/ai/transport.py` | Mevcut chat protokolü, HTTPS/allowlist, bounded okuma ve güvenli hatalar |
| `backend/integrations/assessment.py` | Mevcut fonksiyon ve `ASSESSMENT_*` hata sözleşmesine uyarlama |
| `backend/integrations/assistant/` | Rehber kataloğu, yetki filtresi, bağlam, prompt, sonuç doğrulaması ve HTTP yüzeyi |
| `frontend/src/features/assistant/` | API, session-scoped sohbet durumu, panel ve yönlendirme kartları |
| `frontend/src/app/layouts/ProtectedLayout.vue` | Asistanın ortak kabuğa bağlanması |

Bağımlılık yönü `feature → AI client → transport` olur. AI çekirdeği assessment,
assistant, DDF, DCC, kullanıcı/proje modelleri veya jobs modüllerini import etmez.
Asistan kendi erişim kararları için mevcut feature policy'lerini kullanabilir.
Composition root yalnız ayar ve URL bağlantısını yapar.

## Yeniden kullanılabilir fonksiyon sözleşmesi

Merkezi girişler `complete_text(messages, *, policy, configuration=None)` ve
`complete_json(messages, *, policy, configuration=None)` olacaktır. `messages`
açık roller ve metinlerden, `policy` sunucuya ait immutable limitlerden oluşur.
Varsayılan configuration merkezi ayarlardan çözülür; testler transport sınırını
mock edebilir. Browser endpoint, token, model veya policy seçemez.

`complete_text` doğrulanmış metin döndürür. `complete_json` aynı transport üzerinden
gelen metni bounded JSON object olarak ayrıştırır; feature şemasının doğrulanması
tüketicinin sorumluluğudur. Hatalı JSON için ikinci bir model çağrısı yapılmaz.
Native JSON mode veya tool calling parametreleri gönderilmez.

Sistem mesajı, feature prompt'u ve chat geçmişi her çağrıda açıkça oluşturulur.
Ortak client geçmiş biriktirmez, prompt saklamaz, global mutable HTTP session veya
kullanıcıya ait cache kullanmaz. Otomatik retry yoktur. Network ve protokol
hataları configuration, unavailable, rejected, invalid-response ve invalid-input
kategorilerine normalize edilir; upstream response body dışarı verilmez.

AI kullanan diğer araçlar bu fonksiyonları doğrudan kendi servislerinden çağırır.
Prompt üretimi, domain doğrulaması ve varsa işlem yürütme ilgili aracın servisinde
kalır. Model çıktısı callable adı, Python import path veya çalıştırılacak kod olarak
yorumlanmaz. Bu sürüm genel amaçlı araç çalıştırma API'si açmaz.

## Yapılandırma ve mevcut assessment uyumluluğu

Merkezi sağlayıcı ailesi `AI_API_URL`, `AI_API_MODEL_ID`, `AI_API_TOKEN`,
`AI_API_ALLOWED_HOSTS`, `AI_API_CONNECT_TIMEOUT_SECONDS`,
`AI_API_READ_TIMEOUT_SECONDS` ve `AI_API_MAX_RESPONSE_BYTES` olur.

Merkezi aileden herhangi bir ayar açıkça verilmişse bu aile kullanılır; eksik veya
geçersiz credentials/URL/allowlist eski ayarlarla alan alan tamamlanmaz. Aile hiç
tanımlanmamışsa mevcut `ASSESSMENT_API_*` ailesi bütün olarak merkezi client için
uyumluluk kaynağı olur. Süre ve boyut alanlarının dokümante varsayılanları korunur.

Assessment uyarlayıcısı, açık legacy sağlayıcı yapılandırması varsa onu kullanır;
yoksa merkezi aileyi kullanır. Böylece mevcut deployment davranışı korunurken yeni
kurulumlar yalnız merkezi ayarlarla çalışabilir. Açık fakat hatalı yapılandırma
başka sağlayıcıya sessiz fallback yapmaz. Assessment'ın mevcut `request_assessment`
fonksiyonu, prompt biçimi ve dış hata kodları korunur; taşıma kodu çekirdeğe taşınır.

Production check'leri gerçekten seçilen yapılandırmayı aynı validator ile denetler.
Örnek env dosyaları ve deployment environment aktarımı yeni ayarları belgeler.
Gerçek env dosyaları, token'lar ve endpoint değerleri belgeye veya commit'e girmez.

## Asistan bilgisi ve bağlantı güvenilirliği

Backend rehber kataloğu stable uygulama kimliği, ad, amaç, tipik ihtiyaçlar,
girdiler, çıktılar, kullanım adımları, sınırlamalar ve route hedefi içerir. Metinler
ilgili page/API/use-case kodu incelenerek yazılır. Salt uygulama adından kabiliyet
tahmin edilmez. Menüdeki kullanıcıya açık araçlar kapsanır; developer/admin araçları
aynı erişim kurallarıyla filtrelenir. Proje hedefleri mevcut enabled project,
capability ve domain role'lerinden üretilir.

Katalog sistemin route otoritesinin yerine geçmez. Backend katalog hedeflerinin
gerçek frontend route'lara ve menü/access kararlarına uyumu contract testleriyle
korunur. Entegrasyon kataloğundaki route'lar doğrulanmadan yeniden kullanılmaz.

İstek başında kullanıcının erişebildiği rehber bölümleri oluşturulur. Model yalnız
bu bilgiyi, doğrulanmış açık sayfa kimliğini ve sınırlandırılmış sohbeti görür.
Cookie, token, kullanıcı profili, gerçek belge içeriği, sorgu parametresi ve URL
fragment'ı modele gönderilmez. Sohbet mesajlarının yapılandırılmış AI servisine
gönderildiği panelde kısa bir bilgilendirmeyle belirtilir.

Model `answer`, `application_ids` ve `source_ids` alanları olan JSON üretir.
Sunucu şemayı, uzunlukları ve kimliklerin o istek için izin verilen katalogda
bulunmasını doğrular. Geçersiz şema güvenli hata döndürür; bilinmeyen/yetkisiz
kimliklerden kart üretilmez. En fazla dört uygulama kartı ve dört kaynak gösterilir.
Modelin verdiği URL, HTML, Markdown bağlantısı veya yönlendirme talimatı uygulanmaz.
Yanıt düz metin olarak render edilir; bağlantılar yalnız server-resolved kartlardır.

Kaynak kartları uygulama rehberi dayanağını gösterir; yanıtın doğruluğuna dair
garanti anlamına gelmez. Prompt, belgelenmeyen özellikleri uydurmamayı ve eksik
bilgide soru sormayı ister. Testler tipik ve yanıltıcı taleplerde davranışı ölçer.
Prompt injection'ın yalnız sistem mesajıyla tamamen önlendiği iddia edilmez;
yetki ve yönlendirme sınırları deterministik kodla uygulanır.

## HTTP ve sohbet yaşam döngüsü

`POST /api/integrations/assistant/chat/`, SessionAuthentication, IsAuthenticated
ve CSRF ile korunur. İstek `message`, `history` ve opsiyonel `current_path` içerir.
History yalnız `user`/`assistant` rollerini kabul eder; browser'dan `system` veya
`tool` rolü alınmaz. İstemciden gelen eski assistant mesajları da güvenilmeyen
konuşma bağlamıdır; erişim, kaynak veya URL otoritesi sayılmaz.

İlk limitler: güncel mesaj 4.000 karakter, geçmiş en fazla 12 mesaj ve toplam
24.000 karakter, yol 200 karakter, yanıt metni 8.000 karakter. İstek UTF-8 boyutu
ayrıca 64 KiB ile sınırlanır. Rehber bağlamı 64 KiB içinde tutulur; sınır aşımında
önce statik genel yardım ve geçerli mevcut sayfa, ardından soruyla eşleşen araçlar
seçilir. Proje bağlantıları yalnız seçili yetkili proje bağlamında eklenir.

Asistan için kullanıcı başına dakikada 10 istek sınırı uygulanır. Merkezi transport
asistan çağrılarında connect en fazla 5, read en fazla 25 saniye ve response en
fazla 64 KiB kullanır; upstream daha uzun çalışıyorsa kontrollü hata gösterilir.
Read timeout toplam wall-clock deadline garantisi değildir. Provider thread'i
arkada bırakacak sahte timeout kullanılmaz. Uzun iş, belge analizi ve durable job
mantığı bu senkron sohbet endpoint'ine taşınmaz.

Başarılı yanıt `answer`, doğrulanmış `applications` ve `sources` içerir. Hatalar
ortak `{detail, code, request_id}` sözleşmesini kullanır. Servis kurulmamışsa panel
açıklayıcı durum ve yetkili rehber bağlantıları gösterir; model yanıtı varmış gibi
yerel metin üretmez. Bu fallback için salt-okunur, authenticated
`GET /api/integrations/assistant/catalog/` kullanılır.

Konuşma frontend belleğinde session-scoped store'da tutulur; local/session storage
ve database'e kaydedilmez. Sayfa değişiminde korunur. Yeni sohbet, logout, kullanıcı
değişimi ve session expiry durumu sıfırlar. Bekleyen istek iptal edilir; generation
kimliğiyle eski yanıtın yeni sohbete veya kullanıcıya yazılması engellenir. İstemci
iptali uzak sağlayıcıdaki hesaplamanın durduğunu garanti etmez.

## Arayüz ve işletim

Protected shell içinde erişilebilir isimli sabit asistan düğmesi, desktop yan panel
ve mobil geniş panel bulunur. Mevcut NConfigProvider ve useThemeVars kullanılır.
Klavye/focus yönetimi, Escape, yükleniyor, tekrar dene ve yeni sohbet durumları
uygulanır. Sayfa değişimi yalnız kullanıcı kart bağlantısına bastığında olur.

Loglarda yalnız istek kimliği, sabit kullanım amacı, süre, sonuç ve güvenli hata
kodu yer alabilir; prompt, yanıt, history, credentials veya private path yazılmaz.
Yeni AI servisi için probe yapılmadan yalnız yapılandırma durumunu gösteren bir
Integration Hub girdisi eklenir; Local AI Toolkit girdisi korunur. Yapılandırılmış
olmak canlı sağlık veya model kalite garantisi olarak sunulmaz.

## Doğrulama ve kabul

- Ortak client: roller, bozuk girdi, boyut limitleri, Unicode, JSON şeması, boş veya
  bozuk sağlayıcı yanıtı, timeout, redirect, allowlist ve secret redaction.
- İzolasyon: ardışık/eşzamanlı farklı amaç ve kullanıcı çağrılarında mesaj/policy
  paylaşılmaması; çekirdeğin feature modüllerine bağımlı olmaması.
- Uyumluluk: mevcut DDF, Watcher ve assessment testleri; eski/yeni ayar ailelerinin
  seçimi, kısmi hatalı yapılandırma ve hata kodu eşlemesi.
- Asistan API: auth/CSRF, rate limit, enabled/capability/role filtreleri, yetkisiz
  path, bilinmeyen kimlik, dış URL, sahte system mesajı ve bozuk JSON.
- Frontend: route sözleşmesi, doğru kart hedefi, güvenli metin render, reset ve eski
  yanıt yarışı; mobil/desktop ve light/dark panel E2E kontrolleri.
- Mevcut architecture testleri, ilgili backend suite'leri, frontend test:ci,
  format:check, typecheck, build, collectstatic ve verify_frontend_artifact.
- Merkezi ayarların production aktarımı değişirse launcher/production checks ve
  ilgili deployment contract testleri de çalıştırılır.

Mock testler canlı sağlayıcı uyumluluğunu veya dil modelinin rehberlik kalitesini
kanıtlamaz. Canlı servis erişimi mümkünse gerçek iş verisi içermeyen Türkçe/İngilizce
tanıtım ve yönlendirme sorularıyla ayrıca smoke yapılır; çalıştırılmadıysa açıkça
raporlanır. Veritabanı şeması değişmez. Mevcut çalışma ağacındaki ilgisiz değişiklikler
korunur; yalnız bu görevle ilgili diff ve doğrulamalar teslim edilir.
