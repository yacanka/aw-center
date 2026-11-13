# AW Center Manager geliştirici çalışma biçimi tasarımı

Tarih: 13.11.2026

Durum: Kullanıcı tarafından uygulama için onaylandı; uygulama ve doğrulama kaydı ilgili plandadır. Gerçek Windows kabulü ve toplam açılış süresi ölçümü Linux ortamında çalıştırılmadı.

## Amaç ve kapsam

Kaynak kod üzerinde çalışan kişi Manager'ın mevcut aç, durdur ve tarayıcıda aç akışını kullanarak uygulamayı hızlıca başlatabilsin. İlk kurulum ve açık doğrulama işlemleri bütünlük incelemesini yapmaya devam etsin. Paketli yerel kullanım ve production mevcut güvence düzeyini korusun.

Bu iş yeni bir sunucu, servis yöneticisi, kurulum sistemi veya uygulama profili oluşturmaz. Mevcut Tk arayüzü, Manager worker protokolü, `ensure`, `dev` launcher'ı, profil dosyaları ve süreç kilitleri kullanılır. İlk teslim geliştirici doğrulama politikasıdır. Mermaid renderer'ın tekrar derlenmesini önleme aynı hedefe hizmet eden, bunun ardından bağımsız doğrulanabilen ikinci iyileştirmedir.

## İncelemede görülen davranış

- `scripts/manager/controller.py` pencere açıldığında seçili profili inceler. `inspection.py` üzerinden runtime ve `_core_checks` çağrılır.
- `scripts/launcher/installation_dependencies.py::_package_inventory`, `.venv` ve `frontend/node_modules` içindeki normal dosyaların SHA-256 değerlerini hesaplar. Otomatik inceleme tamamlandıysa hazır ortamın açılışında bu işlem önce incelemede, sonra `ensure` kilidi altında tekrar yapılabilir. Kilit öncesi hazırlık kararı zaten `verify=False` kullanır; o aşamayı tam tarama olarak saymamak gerekir.
- Yönetilen runtime incelemesi ve `toolchain_environment` kurulu runtime dosyalarının bütünlüğünü ayrıca denetler. Paket kaynaklarının doğrulanması da kaynak seçimine göre tekrarlanabilir.
- `launcher.py dev`, kalite/test komutlarını çağırmayan mevcut çalışma çekirdeğidir. `check`, `test` ve kaynak bağlantısı sınamaları ayrı işlemlerdir.
- `frontend/package.json` içindeki `predev`, `build-mermaid-renderer.mjs` üzerinden her frontend başlangıcında renderer'ı yeniden derler.

Bu bulgular tekrar eden işi gösterir. Windows'ta aşama süreleri henüz ölçülmedi; darboğazların süre içindeki payı ve kazanım yüzdesi ölçümle belirlenecek.

## Değerlendirilen yaklaşımlar

1. **Terminalden mevcut `launcher.py dev` kullanımı.** Daha az değişiklik gerektirir. Manager'ın kayıtlı private dev ortamı terminalde kendiliğinden seçilmez; kullanıcının ortam eşleştirmesini yönetmesi gerekir.
2. **Manager içinde açık geliştirici çalışma biçimi.** Kullanıcı bunu seçti. Mevcut tek arayüz korunur; kapsamlı dosya doğrulaması ile günlük başlatma ayrı davranışlar olur. Arayüz, istek protokolü ve launcher'ın ilgili kontrollerinde sınırlı değişiklik gerekir.

## Çalışma biçimi ve varsayılanlar

İki doğrulama politikası kullanılır: `managed` ve `developer`. Bunlar `dev` ve `prod` uygulama profillerinden ayrıdır. Mevcut `dev`, paketli uygulamanın yerel kullanımını da kapsadığı için tek başına geliştirici davranışı seçmez.

- Varsayılan her zaman `managed` olur. Eski kayıtlarda alanın bulunmaması mevcut davranışı korur.
- `developer` yalnız kullanıcının açık seçimiyle, `dev` profili ve açıkça seçilmiş düzenlenebilir kaynak dizini için kullanılabilir. `.git` varlığı veya Manager'ın EXE/`.pyw` olması tek başına bu seçimi yapmaz. Paket içindeki yönetilen kaynak varsayılan olarak yönetilen kullanımda kalır; EXE üzerinden ayrı bir çalışma dizini seçilerek geliştirilebilir.
- Tercih kaynak dizini bağlamına bağlı hatırlanır. Yeni kaynak veya paket bağlamında açık seçim gerekir. Production'a geçiş geliştirici tercihini etkin bırakmaz.
- Worker doğrulaması `prod` + `developer` isteğini başlangıçtan önce reddeder. Bilinmeyen politika değerleri reddedilir; yalnız eksik alan `managed` sayılır. UI tek uygulama noktası değildir.
- Çalışan görev kendi başlatıldığı politikayı kullanır. Politika değişikliği çalışan süreci sessizce dönüştürmez; mevcut durdur/uygula/aç akışından geçer.
- Politika değişikliği aynı dev profilinin veritabanını, anahtarlarını, private dosyalarını veya kayıtlı araç seçimini değiştirmez. Dev ve prod state ayrılığı korunur.

## Günlük kullanım

Geliştirici seçimi mevcut gelişmiş ayarlar içinden yapılır; etkinliği ana durum bilgisinde görünür. Ana **AW Center'ı aç** eylemi korunur. Kullanıcı hangi çalışma biçiminin etkin olduğunu anlayabilmelidir.

Geliştirici modunda pencere açılışı profil ve kurulum metadata'sını sınırlı olarak okur. Kaynak, bağımlılık veya runtime dizinlerini bütünüyle taramaz; Django'yu veya paket yöneticilerini yalnız durum etiketi üretmek için başlatmaz. Bu gözlem başlatma yetkisi veya tam bütünlük kanıtı değildir. Durum metni **Geliştirici modu — hızlı kontrol** gibi yapılan işi doğru anlatır; tamamlanmamış kapsamlı incelemeyi başarılı göstermez.

Ana eylemde hazırlık/başlatma kararı mevcut kilit modeliyle alınır. Kilit altındaki güncel profil, lock ve şema bilgileri yeniden değerlendirilir. Pencere açılışındaki sonuç başka bir işlemden sonra geçerli kabul edilmez.

Mevcut salt okunur `doctor` işlemi **Tam doğrula** eyleminin temelidir. Bu eylem geliştirici seçiliyken de kapsamlı runtime/bağımlılık kontrollerini çalıştırır. Kaynak bağlantısı sınaması ve test paketleri ayrı işlemler olarak kalır; tam doğrulamaya ağ testi veya tam test paketi örtülü eklenmez.

## Kontrollerin sınırı

| Kontrol | Geliştirici günlük açılış | Hazırlama / Tam doğrula | Yönetilen kullanım ve prod |
| --- | --- | --- | --- |
| Kaynak yerleşimi, profil/state ayrılığı, env sahipliği ve yol bağları | Korunur | Korunur | Mevcut davranış |
| Seçili CPython 3.11.x ve Node/npm kimliği/sürümü | Sınırlı mevcut süreç kontrolleri | Mevcut kapsamlı kontroller | Mevcut davranış |
| Bağımlılık lock özeti ve tamamlanmış aşama kaydı | Hafif güncellik kontrolü | Gerçek dosya envanteri de doğrulanır | Mevcut dosya doğrulaması |
| `.venv`, `node_modules`, runtime ve isteğe bağlı kurulu araçların tam dosya envanteri | Başlatma için taranmaz | İlgili mevcut bütünlük kontrolleri | Mevcut davranış |
| Düzenlenebilir geliştirme kaynağını release manifestiyle karşılaştırma | Kaynak değişikliği beklenen davranıştır | Release üretimi/ithali mevcut sözleşmeye uyar | Mevcut kaynak doğrulaması |
| Yeni edinilen arşiv/paket bütünlüğü ve kaynak politikası | Edinim gerekiyorsa korunur | Korunur | Mevcut davranış |
| Şema durumu, mevcut `migrate --check`, ilk yönetici gereksinimi | Korunur | Korunur | Mevcut davranış |
| Port, süreç sahipliği/kilitleri, iptal ve süreç ağacı temizliği | Korunur | Korunur | Mevcut davranış |
| HTTP/Vite ve gerekli worker hazırlığı | Tarayıcı açılmadan doğrulanır | Başlatılıyorsa doğrulanır | Mevcut davranış |
| Production TLS, deploy, migration, collectstatic ve frontend artifact kapıları | Bu çalışma biçiminde prod çalıştırılmaz | Prod sözleşmesi korunur | Mevcut davranış |

Geliştirici modu, kullanıcının değiştirebildiği yerel dosyaları her başlangıçta release bütünlüğüyle onaylama iddiasında bulunmaz. Lock dosyası aynı kalırken yapılan yerel bağımlılık değişikliği, tam dosya karşılaştırması olmadığı için günlük açılışı tek başına engellemez. Hızlı kontrol, kapsamlı doğrulama kaydını güncellemez veya yeni bütünlük kanıtı üretmez. Sonradan yönetilen kullanıma dönmek gerçek dosya kontrollerini yeniden çalıştırır.

Hafif bağımlılık kontrolü mevcut büyük dosya envanteri JSON'unu her seferinde ayrıştırmak zorunda kalmamalıdır. Uygulama kararı olarak başarılı hazırlığın kaynak/araç/lock kimliklerini içeren küçük, sınırlı bir geliştirici güncellik özeti üretilebilir. Bu özet atomik yayımlanır, yalnız geliştirici hazırlık kararına yardımcı olur ve kapsamlı doğrulama yerine kullanılamaz. Böyle bir özet eksikse bir defalık mevcut kayıt okumasıyla oluşturulabilir; hızlı yol dosyaların o anda kapsamlı doğrulandığını iddia etmez. Tam hazırlık kaydı bulunmayan ortam için bir defalık hazırlama gereksinimi devam eder.

İlk sürüm genel bir kontrol-atlama bayrağı sağlamaz. Politika yalnız ilgili kontrollerin çağrıldığı sınırlarda uygulanır. Tam doğrulama, indirme/kurulum ve production yolları varsayılan olarak kapsamlı kalır.

## Hazırlık, değişiklik ve hata davranışı

- **Hazır ve aynı lock dosyaları:** Günlük başlatma paket kaynağına başvurmaz; pip kurulumu, `npm ci`, runtime çıkarma veya tam bağımlılık envanteri çalıştırmaz.
- **Lock dosyası değişmiş:** Yalnız ilgili bağımlılık aşaması güncel değildir. Mevcut hazırlama akışı etkilenen tarafı günceller; diğer taraf yeniden kurulmaz. Hazırlık ve edinimin bütünlük kontrolleri korunur.
- **Manager aşama kaydı yok:** Klasörün varlığı yeterli sayılmaz. Mevcut hazırlama akışı bir defalık tamamlanır. Elle kurulmuş ortamları yeni bir sahiplenme protokolüyle otomatik kabul etmek bu işin kapsamı dışındadır.
- **Migration gerekli:** Mevcut migration politikası, gerekiyorsa kullanıcı kararı, yedek ve kurtarma sınırları uygulanır. Hızlandırma şema değişikliğini atlama yetkisi vermez.
- **Eksik executable veya zorunlu çıktı:** Hafif kontrol ya da süreç başlangıcı ilgili bileşen için hata verir. Tüm ortamı silme veya sessizce yeniden kurma yapılmaz. Yarım/eksik bağımlılık için mevcut hazırlama yolu kullanılır; tam envanter eksikliği sonraki süreç hatasını başarı gibi göstermez.
- **Tam doğrulama uyuşmazlığı:** Sonuç raporda korunur ve hangi doğrulamanın başarısız olduğu gösterilir. Yönetilen açılış engellemeye devam eder. Geliştirici seçimi yerel değişikliklere izin verir; buna dayanarak tam doğrulama sonucu başarılıya çevrilmez. Yeni edinimde hash/TLS hatası her iki çalışma biçiminde engelleyicidir.
- **İptal veya kapanma:** Başarılı aşama kaydı yalnız aşama tamamlanınca yayımlanır. Mevcut iptal, kilit ve süreç sahipliği davranışları korunur.

## Mermaid renderer'ın tekrar kullanım sınırı

Bu ikinci teslim yalnız geliştirme başlangıcındaki tekrar derlemeyi önler. Production build ve test davranışları ilk sürümde mevcut kapsamlı derlemeyi korur.

Geliştirme önbelleğinin kimliği renderer'ın yerel kaynak/import girdilerini ve dosya kümesini, build scriptini/seçeneklerini, frontend lock dosyasını ve seçili Node ile build araçlarının sürüm kimliklerini kapsar. Girdi ekleme, silme veya içerik değişimi, eksik/bozuk çıktı ve önceki yarım build yeniden derlemeye neden olur. Yeniden kullanılan `renderer.js` kendi kayıtlı içerik özetiyle ve mevcut tek klasik-script/importsuz çıktı koşuluyla kontrol edilir; kontrol bütün `node_modules` ağacını taramaz.

Çıktı ve küçük önbellek kaydı yalnız başarılı build ardından atomik yayımlanır; eşzamanlı dev/build/test çağrıları yarım çıktı görmez. Geçersiz kayıt yeniden derlemeye yönlendirir. Mevcut `publishRenderer` atomik çıktı davranışı korunur. Zorla yeniden derleme yolu sağlanır. Lock/sürüm metadata'sı değişmeden doğrudan `node_modules` içeriğini düzenleyen geliştirici bu yolu kullanır. Renderer kaynağını açık sunucu sırasında izleyen yeni bir watch sistemi bu işin kapsamı dışındadır; mevcut renderer hazırlama noktası başlangıçtır.

Önbellek kaydı aynı build'in girdi görüntüsüne ve ürettiği baytların özetine bağlanır. Derleme sırasında girdiler değişmişse güncel başarı kaydı yayımlanmaz. Eşzamanlı başka bir build'in yayımladığı çıktı yanlış girdi anahtarının altına kaydedilmez; okuyucu kayıt/çıktı eşleşmesini doğrular veya yeniden derler.

## Uygulama sınırları

- **Politika ve istek taşıma:** `scripts/manager/view_model.py`, `view.py`, `preferences.py`, `paths.py`, `operations.py` ve mevcut worker/transport istek yolu. Yeni değer UI ve worker'da doğrulanır; kaynak bağlamı ve çalışan görevin sabit istek görüntüsü korunur.
- **İnceleme ve açılış:** `scripts/manager/inspection.py`, `ensure.py`, `scripts/launcher/installation.py`. Otomatik gözlem ve kilit altındaki karar ayrılır; mevcut `ensure` dalları kullanılır.
- **Runtime ve bağımlılık sınırı:** `scripts/launcher/toolchain.py`, `installation_dependencies.py`, `installation_features.py`. Geliştirici başlatması için sınırlı doğrulama sağlanır; kurulum ve kapsamlı doğrulamanın varsayılanları gevşetilmez.
- **Renderer:** `frontend/scripts/build-mermaid-renderer.mjs` ve `frontend/package.json` içindeki dev hazırlama çağrısı. Build/test çağrıları kapsamlı kalır.
- **Ölçüm/kabul:** Mevcut Manager/launcher testleri ve Windows kabul akışı kullanılır. Yeni telemetri servisi, bağımlılık veya genel doğrulama framework'ü eklenmez.

Kesin fonksiyon imzaları, politika yardımcısının dosya yeri, test dosyası gruplaması ve kullanıcı arayüzündeki kısa metinler uygulama planının sorumluluğudur. Bu tasarımın davranış sınırları değişmez.

## Teslim sırası

1. Aynı Windows makinesinde mevcut hazır `dev` ve yönetilen/prod başlangıçlarını ölç; aşama süresi ve tekrar sayaçlarını kaydet.
2. Açık geliştirici tercihini, worker doğrulamasını ve kaynak bağlamına bağlı kaydetmeyi ekle.
3. Geliştirici otomatik incelemesi ve kilit altındaki hafif başlatmayı mevcut çalışma çekirdeğine bağla; ayrı tam doğrulama davranışını koru.
4. Bu ilk teslimin regresyon ve Windows kabulünü tamamla.
5. Dev-only renderer önbelleğini ayrı doğrula ve önce/sonra toplam süreleri tekrar ölç.

## Kabul ölçütleri

| Senaryo | Beklenen davranış |
| --- | --- |
| Eski ayarlar / yeni paket | Açık geliştirici seçimi olmadan mevcut yönetilen davranış sürer. |
| Geliştirici pencere açılışı | Tam kaynak/runtime/bağımlılık taraması, Django inceleme süreci ve paket kaynağı isteği sıfırdır. |
| Hazır geliştirici ortamında üç durdur/aç | Başlatmaya kadar tam bağımlılık/runtime envanteri, paket edinimi, pip kurulumu, `npm ci` ve runtime çıkarma sıfırdır; gerçek HTTP/worker hazırlığından sonra tarayıcı açılır. |
| Geliştirici modunda Tam doğrula | Dosya değişiklikleri mevcut kapsamlı kontrollerle raporlanır. Hızlı kontrol sonucu bunun yerine geçmez. |
| Kaynak/çalışma biçimi değiştirme ve eski worker isteği | Tercih başka kaynağa/prod'a sızmaz; `prod` + `developer` worker tarafından reddedilir; çalışan görevin politikası sessizce değişmez. |
| Yalnız frontend/Python lock değişimi | Yalnız ilgili hazırlık aşaması güncellenir; diğer bağımlılıklar korunur. |
| Dolu port, pending migration, eksik araç veya worker hatası | Uygun başlangıç engeli görülür; sahte başarı, erken tarayıcı açma veya yetim süreç oluşmaz. |
| Kilit öncesi gözlemden sonra kaynak/profil/lock/şema değişimi | Kilit altında güncel durum yeniden değerlendirilir; eski hazır bilgisiyle başlatılmaz. |
| Yönetilen dev/prod, bozulmuş bağımlılık veya kaynak | Mevcut engelleme ve production kapıları korunur; geliştirici politikası bu yolları etkilemez. |
| Renderer girdileri aynı / girdi değişmiş / çıktı eksik | Dev'de sırasıyla sıfır build / yeni build / yeni build; production ve test hazırlığı mevcut kapsamlı davranışı korur. |
| İptal ve eşzamanlı başlatma/build | Başarı kayıtları ve renderer çıktısı yarım yayımlanmaz; ikinci sunucu/worker veya yarım çıktı üretilmez. |

Windows ölçümü aynı kaynak sürümü, seçili araçlar ve disk üzerinde ilk kurulum ile hazır ortam başlangıcını ayırır. En az üç hazır başlangıç için toplam süre ve aşama süreleri, tam tarama/build/kurulum sayıları raporlanır. Sayısal hızlanma hedefi baseline görülünce belirlenir; ölçülmemiş hız kazancı vaat edilmez. Kaynak üzerinden `.pyw` ile paketli EXE kabulü ayrı kaydedilir. Testler birim/mock kanıtı ile gerçek Windows süreç/ACL/NTFS/HTTP kanıtını birbirine karıştırmaz.

## Sınırlar ve başarısız sayılacak sonuçlar

Geliştirici modu web uygulamasının session/CSRF, yetkilendirme, artifact erişimi veya job fencing sözleşmelerini değiştirmez. Production veritabanı/private-media alanı geliştirmede kullanılmaz. Kaynak dosyası değişikliklerini tam release hash eşitliğiyle durdurmak, her yeniden başlatmada bütün bağımlılık ağacını taramak, tüm profillere yayılan bir kontrol-atlama bayrağı eklemek veya tam doğrulama yapmadan yapılmış gibi raporlamak bu tasarımın başarısız sonucudur.
