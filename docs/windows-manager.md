# AW Center Windows masaüstü yöneticisi

Taşınabilir paket Windows x64 içindir. ZIP'in tamamını kullanıcıya ait yerel bir dizine çıkarın ve `AWCenterManager.exe` dosyasını açın. İlk pencere için kurulu Python, Node, npm, Git veya ağ bağlantısı gerekmez. Python/Tk arayüzü `_internal/` içinde; uygulama kaynakları `source/`, SHA-256 değerleri onaylı Python 3.11, Node ve npm arşivleri `runtimes/` içindedir. Bu dizinleri EXE'den ayırmayın.

Pencerenin açılması uygulamanın hazır olduğu anlamına gelmez. Güncel tam paket,
`dependencies/wheels` ve `dependencies/npm-cache` içerir; yalnız eski
`runtimes/` paketleri bağımlılıkların çevrimdışı kopyası değildir.

## Sade yönetim ekranı

Ana ekran seçili **profilin gerçek durumu**, **ana eylem** ve **işlem ilerlemesi**
üzerine kuruludur. Açılışta ve kaynak/profil değişiminde arka planda salt okunur
inceleme yapılır; eski inceleme yeni seçimi değiştiremez.

| Durum | Ana eylem |
| --- | --- |
| Kurulmamış | Kur ve başlat |
| Hazırlanmış, durmuş | Başlat |
| Tamamlanabilir yarım kurulum | Tamamla ve başlat |
| Çalışıyor ve sağlıklı | Tarayıcıda aç |
| Müdahale gerekiyor | Eksikleri göster |

Kaynaklar ve Rapor düğmeleri ilgili görünümü açar; Ctrl+1/2/3 korunur.
Kaynak testi veya başka bir rapor seçmek çalışan profilin Tarayıcıda aç/Durdur
kontrollerini değiştirmez. Üretimde IPv4, sertifika ve özel anahtar alanları
ana ekranda görünür. Gelişmiş ayarlar isteğe bağlıdır. Açık/koyu tema, sistem
fontu, klavye odağı ve küçük pencerede kaydırma korunur.

İlerleme geçerli aşama, geçen süre ve bekleme nedenini gösterir; tahmini yüzde
üretilmez. Denetim özeti Hazır, Eksiklerle kullanılabilir veya Kurulum engellendi
olur. **Yeniden dene / Ctrl+R**, ilgili görevin kayıtlı ayarlarını kullanır;
formu değiştirmek yeni bir işlem başlatmak içindir. Başlatmada tarayıcı bir kez
açılır. Durdurulan görevin canlı bağlantısı kaldırılır.

Aktif işlem varken **X** görev çubuğuna küçültür. **Çıkış**, mevcut onaylı güvenli
durdurma akışını çalıştırır; süreçler temizlendikten sonra kapanır. Aktif işlem
yokken X doğrudan kapatır. Sistem tepsisi veya Windows servisi kurulmaz.

## Sistem Python ve Node.js seçimi

Manager varsayılan olarak önce sistemdeki uygun Python ve Node.js kurulumlarını arar; bulunan aracı indirmez veya değiştirmez. Python için mevcut CPython, `py -3.11`, PATH'in tüm dizinleri, Windows Python kayıtlarının 32/64 bit görünümleri ve yaygın kurulum dizinleri üzerinden tam **CPython 3.11 x64** aranır. `venv` ve `ensurepip` desteği de doğrulanır. Otomatik aramada uygun Python bulunamazsa seçilen kaynak politikasına göre yönetilen Python hazırlanır. **Her durumda yönetilen Python kurulumunu kullan** kutusu bu otomatik tercihi açıkça geçersiz kılar. Store yürütme alias'ı başlatılmaz; Python launcher'ın otomatik kurulum seçeneği sorguda kapalıdır. [Python Windows launcher ayarları](https://docs.python.org/3/using/windows.html) bu ortam seçeneklerini açıklar.

Otomatik tespit yeterli olmazsa **Gelişmiş ayarlar → Python komutu / yolu (isteğe bağlı)** alanına `python`, `py -3.11`, `C:\Python311\python.exe` veya Python kurulum dizinini girin; **Seç…** düğmesiyle `python.exe` de seçebilirsiniz. Boşluk içeren, tırnakla kopyalanmış dosya yolları desteklenir. Girilen seçim doğrulanır; uyumsuzsa farklı bir Python'a sessizce geçilmez. Shell komutu çalıştırılmaz. Yönetilen Python kutusu seçildiğinde bu alan kullanılmaz. Alan Kur ve başlat ile offline paket hazırlığı içindir; Başlat ve Durumu denetle mevcut profilin kayıtlı Python seçimini korur.

**Node.js komutu / yolu (isteğe bağlı)** alanı `node`, `node.exe` dosyasının tam yolu veya kurulum dizinini kabul eder; **Seç…** düğmesi EXE seçer. Boşsa PATH, Windows kayıtları ve yaygın dizinler taranır. Desteklenen sistem Node, x64 **22.13+ (22.x) veya 24+** sürümüdür; ön sürümler ve uyumsuz mimariler kullanılmaz. Otomatik arama uygun kurulum bulamazsa yalnız eksik yönetilen Node hazırlanır. Elle verilen geçersiz seçim açık hata üretir. İptal, indirmeye geçiş sayılmaz.

Seçilen Node yanındaki kararlı **npm 10.9.4+ (10.x) veya 11.x** CLI da kullanılır. Örneğin Node 26.12.1 ile kurulu npm 11.18.0, yalnız daha yeni olduğu için yeniden kurulmaz. Uygun npm eksikse doğrulanmış yönetilen **npm 10.9.4** arşivi hazırlanır; katalog pini ve dependency lock dosyaları değişmez. npm doğrudan seçilen Node ile çalıştırılır, `.cmd` üzerinden shell komutu yürütülmez. Python ve Node yolları profil bazında kaydedilir; Başlat ve Durumu denetle aynı araçları yeniden doğrular.

Runtime hazırlığı, arşiv edinme/açma, sürüm denetimi ve kayıt yazma aşamalarını ayrı gösterir. Sürüm denetimi de Manager'ın iptal edilebilir süreç yolunu ve ayrı stdin'i kullanır. Başlatma, 30 saniyelik zaman aşımı, süreç çıkışı ve katalog sürüm uyuşmazlığı `runtime_validation_…` kodlarıyla raporlanır; ham stdout/stderr veya dosya yolu gösterilmez. pip/npm alt süreçleri için kullanıcı ve global npm ayarları iki farklı boş geçici dosyayla ayrılır; aynı null dosyasının iki kez yüklenmesi önlenir ve dosyalar işlem sonunda temizlenir.

Python 3.11.3 x64 dahil CPython 3.11 yama sürümleri kabul edilir. Etkileşimli `python` ekranının açılması, `venv` ve `ensurepip` desteğinin hazır olduğunu tek başına göstermez. Manager artık süreç başlatma hatasını (`system_python_start_failed`, varsa `WinError`/`errno`), süreç çıkışını (`system_python_process_failed` ve sayısal çıkış kodu), denetim zaman aşımını (`system_python_timeout`), eksik `venv`/`ensurepip` modülünü ve standart modül yükleme hatasını ayrı raporlar. Ham stderr, dosya yolları veya exception içeriği rapora aktarılmaz. Eski genel “Python bulunamadı” mesajı bu nedenleri ayırt ettirmez.

Python aramasının toplam bütçesi **120 saniye**, tek adayın üst sınırı **60 saniyedir**. Node/npm araması ortak **60 saniyelik** bütçe kullanır; tek denetim en fazla **30 saniye** sürer. Arama başlamadan durum bilgisi gösterilir ve **Durdur** denetim sürerken de kullanılabilir. Aynı dosyaya giden PATH yazımları aynı aramada tekrar denenmez; doğrudan çalıştırılıp bütün kontrolleri geçen Python hemen ikinci kez başlatılmaz. Launcher veya sanal ortam farklı bir temel yorumlayıcı bildirirse temel dosya ayrıca doğrulanır. Zaman aşımı, süreç hatası veya geçersiz yanıt araç yok sayılarak indirmeye dönüştürülmez. Yeniden deneme, açık yol seçimi veya yönetilen araç seçimi gerekir; sistem kurulumu değiştirilmez.

Kurulumda değişiklik yapmadan CMD’de `python -I -S -c "import venv, ensurepip, sysconfig; print(sysconfig.get_platform())"` ile aynı izole modül kontrolünü yapabilirsiniz; Windows x64 için başarılı sonuç `win-amd64` olur. `>>>` etkileşimli Python ekranındaysanız önce `exit()` ile CMD’ye dönün. Başarısızsa hata türünü ve Manager’ın yeni hata kodunu birlikte değerlendirin; yalnız sürüm ekranına bakarak yeniden kurulum kararı vermeyin.

CMD denetimi geçmesine rağmen eski Manager paketleri `system_python_timeout` verebilir: Manager’ın kontrol thread’i iletişim pipe’ında okuma beklerken aynı stdin’i miras alan Python, Windows başlangıcında kilitlenebilir. Manager bağlamındaki komutlar artık bu kanalı miras almaz; özel input verilmediyse stdin kapalı girdiye (`DEVNULL`) yönlendirilir. Açık input akışları, iptal kanalı ve CLI kullanımı korunur. Worker sağlık denetimi de iletişim kanalından ayrılmıştır. Düzeltme paketli Manager koduna aittir; kaynak güncellemesinden sonra Windows ZIP/EXE’si yeniden üretilmelidir.

Kutu seçilirse paketteki veya seçilen kaynaklardaki SHA-256 sabitlenmiş yönetilen Python kullanılır. Bu seçim Node/npm hazırlığından ayrıdır. Her iki durumda da uygulamanın kilitli pip paketleri proje `.venv` dizinine kurulur; sistem Python paketleri değiştirilmez. Sistem modu işletim sistemindeki mevcut Python'a güvenir, onun dosyalarına yönetilen arşivin hash pinini uygulamaz.

Başarılı bağımlılık hazırlığından sonra seçilen sistem yorumlayıcısı dev/prod profil metadata'sına ayrı ayrı kaydedilir; Başlat ve Kontrol et aynı seçimi kullanır. Özel env, anahtarlar ve mevcut hesaplar değişmez. Mevcut `.venv` farklı bir Python'a bağlıysa Manager onu otomatik silmez veya yeniden bağlamaz; ayrı temiz kaynak dizini kullanın ya da mevcut ortamın Python seçimini koruyun. Profil değişimi sonradan sistem Python'unu kaldırmaz veya güncellemez.

Manager üzerinden hazırlanan **tam USB paketi**, üreticide sistem araçları kurulu
olsa da Python/Node/npm arşivlerini içerir. Araçlar ayrı geçici alanda hazırlanır;
canlı uygulamanın runtime veya sanal ortamı değiştirilmez. Kaynak üzerinden
çalıştırmada aynı sürümden önceden derlenmiş Windows Manager dizini seçilmelidir.
Hedefte uyumlu sistem araçları yine önceliklidir. Eski v1/v2 kurulum paketlerinin
okunması ve v2 `host_runtimes` gereksinimlerinin doğrulanması korunur.


## Form değerlerini hatırlama

Manager normal biçimde kapatıldığında son form değerlerini `%LOCALAPPDATA%\AWCenterManager\manager.json` içinde atomik ve yalnız mevcut kullanıcıya açık olarak saklar. Bu alan standart Windows kullanıcısının kendi profilindedir; yönetici olarak çalıştırma veya kurulum klasörünün izinlerini değiştirme gerektirmez. Kurulumun `%LOCALAPPDATA%\AWCenter` dizini yazılabilir veya tam olarak aynı özel ACL biçiminde olmak zorunda değildir. Profil, kaynak modu/adresleri, dizinler, Python/Node seçimleri, portlar, CA/TLS ve `.env` dosya yolları sonraki açılışta geri gelir. `--root` ile verilen kaynak dizini hatırlanan dizinden önceliklidir. İşlem başlatılmadan girilen değerler de kapanışta saklanır; ani süreç sonlandırmada son değişiklikler kaybolabilir.

Yeni kayıt yoksa önceki sürümün `%LOCALAPPDATA%\AWCenter\config\manager.json` dosyası salt okunur olarak kontrol edilir. Sahiplik, özel izinler ve symlink/junction kontrollerinden geçen eski değerler yüklenir ve normal kapanışta yeni alana yazılır. Eski dosya silinmez, içeriği veya izinleri değiştirilmez. Güvensiz ya da bozuk eski kayıt içe alınmaz; yeni alanda form değerlerini kaydetmek yine mümkündür.

Yalnız dosya yolları kaydedilir; `.env`, sertifika ve özel anahtar içerikleri okunmaz. Yönetici kullanıcı adı/parolası ve credential içeren URL'ler kaydedilmez. Migration onayı her işlem için yeniden verilir. Kayıt okunamıyorsa form varsayılanlarla açılır ve durum/rapor mesajı gösterilir; kayıt yazılamıyorsa kapanışta uyarı verilir. Mesaj başarısız aşamayı, kullanıcı adını açığa çıkarmayan sembolik kayıt konumunu, `preferences_…` hata kodunu, varsa sayısal `WinError`/`errno` değerini ve çözüm adımını içerir. Windows ACL kontrolü başarısızsa ilgili güvenli kontrol kimliği de gösterilir; ham exception, SID, form değerleri veya dosya içerikleri gösterilmez. Dosya kilidi, erişim reddi, dolu disk/kota, salt okunur disk ve bozuk kayıt birbirinden ayrılır. Başarısız atomik yazmada önceki kayıt korunur. Bu dosya uygulama profillerinden ayrıdır; mevcut hesapları, anahtarları veya veritabanını değiştirmez.

## .env dosyası seçimi

Çalışma sekmesindeki **.env dosyası (isteğe bağlı)** alanının **Seç…** düğmesiyle kendi dosyanızı seçebilirsiniz. Boş bırakılırsa mevcut profil kullanılır; yeni profilde varsayılan özel yapılandırma üretilir. Seçilen dosyanın yolu görev seçeneklerine alınır; içeriği arayüz veya rapora aktarılmaz.

**Kur ve başlat**, literal `KEY=value` biçimindeki dosyayı doğrular ve ayarlarını `%LOCALAPPDATA%\AWCenter\config\dev.env` veya `prod.env` içindeki owner-only kopyaya aktarır. Kaynak dosyanın içeriği ve izinleri değiştirilmez. Kaynak dosyanızın izinlerini ayrıca koruyun; uygulama yalnız özel profil kopyasını kullanır. UTF-8/BOM desteklenir; yinelenen anahtar, symlink/junction, normal dosya olmayan yol, geçersiz sözdizimi veya 128 KiB üzeri dosya reddedilir. Shell komutu/variable interpolation yapılmaz; süreç başlatma ve başka env dosyasına yönlendirme ayarları kabul edilmez.

Mevcut profilin `SECRET_KEY` / `JIRA_SESSION_ENCRYPTION_KEY` değerleri değiştirilemez. Profilin ayrı veritabanı, özel dosya ve bind/model yollarıyla çelişen ayarlar reddedilir; dosyadan bu alanları çıkarmak mevcut güvenli değerleri korur. İlk kez eski bir geliştirme veritabanı açıkça sahiplenilecekse seçilen dosya her iki özgün anahtarı da içermelidir; veritabanı resetlenmez. Production için seçilen dosya kaynak ağacının dışında olmalıdır. İlk kurulumda eksik anahtarlar yalnız yeni/boş ortam için oluşturulur.

**Durumu denetle** salt okunurdur. **Başlat** paket indirmez veya bağımlılık kurmaz; üretimin deployment, migration durumu, collectstatic ve artifact kontrollerini tekrar çalıştırır. Alan boşken kayıtlı profil kopyasını kullanırlar. Dosya seçiliyse aynı ayarlara karşılık geldiğini doğrularlar; farklı ayarlar varsa bunları önce **Kur ve başlat** ile uygulamanız istenir. Bu seçim, iki profilin aynı state veya anahtarları paylaşmasına izin vermez.

## Geliştirme ve üretim

Varsayılan kaynak dizini EXE'nin yanındaki `source/` dizinidir. Başka bir kaynak için arayüzde dizin seçin veya CMD içinden açıkça belirtin:

```bat
AWCenterManager.exe --root "C:\AWCenter\source"
```

Geliştirme profili `127.0.0.1` üzerinde çalışır; sanal ortam ve frontend paketleri seçilen kaynak dizinine kurulur. Üretim profili ayrı kaynak ve sanal ortam kullanır. Yönetici kaynak envanterini doğrular ve yalnız kaynak dosyalarını şu dizine kopyalar:

```text
%LOCALAPPDATA%\AWCenter\releases\<kaynak-SHA256>\source
```

Kimlik tüm dağıtılabilir kaynak envanterinin SHA-256 değeridir. Aynı kaynak tekrar seçildiğinde mevcut kopya yeniden doğrulanır. Değişmiş bir release dosyası, beklenmeyen kaynak dosyası, symlink veya junction hata verir; yönetici mevcut release'i onarmaz veya üzerine yazmaz. Bilinen üretilmiş sanal ortam, npm paketleri, build çıktıları, Python cache ve geliştirme SQLite dosyaları kaynak karşılaştırmasına girmez.

Dağıtılmış `source/manager-source-manifest.json` dosyasını koruyun. Manifest taşınan kaynağın eksiksizliğini ve bütünlüğünü denetler; dijital imza değildir. ZIP checksum'unu güvenilir bir dağıtım kanalından doğrulayın. Git checkout'undan geliştirme sırasında üretim kopyası hazırlanabilir; manifesti olmayan rastgele çıkarılmış bir kaynak dizini kabul edilmez.

Üretim için makineye atanmış sabit IPv4, kaynak ağacının dışındaki mevcut TLS sertifikası ve özel anahtar gerekir. Profiller ve özel durum `%LOCALAPPDATA%\AWCenter` altında ayrılır. Geliştirme ve üretim aynı veritabanını, özel dosyaları veya anahtarları paylaşmaz. Mevcut üretim veritabanındaki bekleyen migration yalnız açık migration seçimiyle uygulanır; önce yedeği doğrulayın.

## Paket kaynakları

Kaynak modu her işlemde açıkça seçilir:

| Mod | İzin verilen kaynaklar |
| --- | --- |
| Online | Genel HTTPS kaynakları, seçilen kurumsal kaynaklar ve doğrulanmış yerel fallback |
| Kısıtlı internet (`restricted`) | Doğrulanmış yerel içerik → seçilen depolar → genel HTTPS kaynakları |
| Kurumsal | Yalnız seçilen kurumsal HTTPS veya yerel kaynaklar; genel internete fallback yok |
| Çevrimdışı | Yalnız seçilen yerel doğrulanmış paket dizini; ağ indirmesi yok |

Python index adresi, npm registry adresi ve runtime arşiv deposu ayrı alanlardır. Kurumun CA dosyasını gerektiğinde seçin; TLS kontrolü kapatılmaz. URL'ye kullanıcı adı, parola veya token koymayın. Kurumsal proxy yapılandırması işlemin ortamından gelebilir; ham paket yöneticisi çıktıları arayüze veya rapora aktarılmaz.

Runtime arşivi indirme isteği yetki veya erişim nedeniyle reddedilirse Manager `artifact_http_rejected` koduyla Python, Node.js veya npm bileşenini ve sayısal HTTP kodunu gösterir. HTTP 401 depo kimlik doğrulamasını, 403 erişim reddini, 407 proxy kimlik doğrulamasını ayrı açıklar. Eski paketlerde bu durumlar genel `source_unavailable` mesajına dönüşüyordu. Yanıt gövdesi, adres, header ve ham hata metni rapora eklenmez. Kısıtlı modda HTTP 401/403/407, bulunamama ve bağlantı sorunları raporlanarak sıradaki izinli kaynağa geçilir. Diğer modların sınırları korunur. TLS, hash, bozuk manifest ve kurulum hataları fallback yapmadan durur. Her uzak deneme ayrı geçici dizindedir; depolar aynı çözümleme havuzunda karıştırılmaz. Son kurulum Python için `--no-index --find-links`, npm için `npm ci --offline` ile yerelden yapılır.

“Kaynakları dene” seçilen PEM CA dosyasını varsayılan güven deposuna ekler; Windows'un güvenilen CA ve ROOT depoları ile OpenSSL varsayılanları korunur. CA dosyası seçilmediğinde bu varsayılan depolar kullanılır. Dosya okunamıyorsa veya geçerli PEM değilse ağ isteği yapılmadan CA dosyası hatası gösterilir. Her kaynak için sertifika doğrulaması, diğer TLS hataları, proxy bağlantısı/kimlik doğrulaması, HTTP durum kodları, DNS ve zaman aşımı ayrı açıklanır. Proxy bypass ayarları korunur; hata yanıtlarının gövdeleri, ham exception metinleri ve proxy kimlik bilgileri rapora yazılmaz.

Manager'ın pip/npm kurulumu, offline paket hazırlığı ve `launcher.py setup` / `prepare-offline` komutları da sistem güven köklerini korur. İşlem sırasında Windows CA/ROOT ve OpenSSL varsayılanları, pip'in genel CA paketi ve npm için Node'un yerleşik güven kökleri geçici bir PEM paketinde birleştirilir. Seçilen özel CA bu güvene eklenir; seçilmemesi varsayılan güven köklerinin kullanılmasını engellemez. Paket yalnız ilgili alt süreçlere aktarılır, işlem sonunda kaldırılır ve dağıtım/offline paketine eklenmez. TLS ve sunucu adı doğrulaması açık kalır.

Uygulamanın HTTPS entegrasyonları da Windows CA/ROOT, OpenSSL ve Requests'in genel güven köklerini birlikte kullanır. Her entegrasyonun mevcut sertifika ayarı o servisin güvenine eklenir; kurulum kaynakları için seçilen CA dosyası entegrasyon ayarlarını değiştirmez. Özel CA seçilmediğinde mevcut Requests ortam CA ayarları da varsayılan güvene eklenebilir. Bir servise seçilen CA diğer servislerin oturumlarına taşınmaz.

Çevrimdışı kurulum için Windows x64 ve mevcut dependency lock'larıyla hazırlanmış kurulum paketi gerekir. Paket içindeki dependency manifest'i, Python wheel'leri ve npm cache doğrulanır. Yönetici üzerinden paket hazırlama işlemi, erişebilen bir Windows makinede mevcut kurulum bundle akışını kullanır. Yalnız `runtimes/` dizinini seçmek çevrimdışı uygulama kurulumunu tamamlamaz.

Wheel hazırlığı CPython 3.11 yama sürümlerinin koşullu pinlerini birlikte toplar;
örneğin yalnız 3.11.0–3.11.2 için gereken `async-timeout` yeni Python ile hazırlanan
pakette de bulunur. İşletim sistemi koşulları korunur. Bu geçici edinim listesi
lock dosyasını değiştirmez; hedef kurulum özgün lock koşullarını uygular.

## İşlemler ve ilk yönetici

Sıra: ön kontrol → araçlar/bağımlılıklar → tam TLS doğrulaması → özel profil/şema → ilk yönetici → seçilen ekler → build/deployment → web/worker. TLS dosya erişimi ve anahtar eşleşmesi daha ilk ön kontrolde incelenir; tam sertifika/IP kontrolü uygulama ortamındaki cryptography ile profil ve veritabanından önce tamamlanır. Başlat mevcut hazırlanmış profili kullanır. Kontrol et salt okunur tanılama yapar. Kaynak testi seçilen politikanın erişimini veya yerel bağımlılık envanterini inceler; paket kapsamının tamamı kurulum sırasında doğrulanır.

İlk aktif yönetici bulunmadığında kullanıcı adı ve parola ayrı, maskeli parola alanı olan pencerede istenir. Kullanıcı adı bir harf ve beş rakamdır. Bilgiler yalnız worker'ın özel stdin kanalıyla aktarılır; argv, environment, kaynak dosyası veya rapora yazılmaz. Mevcut kullanıcılar değiştirilmez veya yöneticiye yükseltilmez.

Durdur yalnız görev listesindeki seçili işlemi ve onun alt süreçlerini durdurur. Çıkış işlemini onaylamak tüm aktif işlemlere iptal gönderir ve süreç temizliğinin bitmesini bekler. Devam eden migration güvenli komut sınırında durur; tamamlanan kurulum adımları korunur. Hata sonrası gösterilen aşamayı ve çözüm bilgisini inceleyip aynı işlemi tekrar çalıştırın. Özel profili veya veritabanını silmek bir kurtarma adımı değildir. Rapor yalnız temizlenmiş durum bilgisidir.

## Modüller ve bağımsız işlemler

Arayüz (`view.py` / `view_model.py`), görev yönetimi (`controller.py` / `task_policy.py`), özel süreç iletişimi (`transport.py` / `worker.py`) ve işlem yürütme (`operations.py` / `source_checks.py`) ayrıdır. İlk pencerenin kaynak yolu yalnız hafif `paths.py` modülünden gelir; paket hazırlama modülünün yüklenmesi gerekmez. Yeni bir job framework veya bağımlılık eklenmez.

Her işlem ayrı işletim sistemi sürecinde çalışır. Bu, launcher'ın process environment bağlamlarının farklı profillerin anahtarlarını veya araç yollarını karıştırmasını önler. Görev kimliği, seçeneklerin başlangıç anındaki kopyası, olay kutusu, durum, rapor ve iptal kanalı işlem başına ayrıdır. Formu sonradan değiştirmek çalışan görevi değiştirmez. Bir görevin hatası veya iptali diğer görevlere uygulanmaz.

Göreli dosya yolları görev başlarken kaynak çalıştırmada repository kökü, paketli çalıştırmada EXE klasörü esas alınarak mutlak yola çevrilir. Aynı mutlak yollar hem çakışma kontrolüne hem worker'a gönderilir; `~` mevcut kullanıcının home dizinini ifade eder. Böylece aynı çıktı dizininin farklı yazılışları iki ayrı hedef sayılmaz.

| Eşzamanlı işlemler | Davranış |
| --- | --- |
| Çalışan uygulama + kaynak testi / durum kontrolü | Birbirinden bağımsız çalışır. |
| Çalışan uygulama + offline paket hazırlama | Sabitlenmiş araçları ayrı hazırlık alanında kullanır; canlı `.venv` değiştirilmez. |
| Hazır dev + hazır prod başlatma | Ayrı profil ve state ile çalışabilir; mevcut port ve tek DOORS worker kontrolleri korunur. |
| Aynı profilin iki lifecycle işlemi | İkinci işlem açık çakışma mesajıyla reddedilir. |
| Kurulum + çalışan lifecycle / başka kurulum | Kaynak, profil veya paylaşılan runtime yazmalarının çakışması engellenir. Kurulum uygulamayı hazır ilan edince yalnız çalışan sunucu kaynaklarını tutar. |
| İç içe veya aynı çıktı dizinine iki paket | Dosya çakışması açıklanır; bekleme kuyruğuna alınmaz. |

Görev listesinde kısa işlem kimliğini seçerek o işlemin durumunu ve raporunu görüntüleyin. İlk yönetici penceresi modal değildir; açıkken diğer işler izlenebilir, başlatılabilir veya durdurulabilir. Kaynak/alan doğrulamaları yalnız ilgili işlemin kullandığı seçeneklere uygulanır.

Tk iş parçacığında ağ erişimi, süreç bekleme, pipe yazma veya tarayıcı başlatma yapılmaz. Özel pipe yazıcısı ve sınırlı mesaj kuyruğu işlem başınadır. Tk her görevden sınırlı sayıda olay okur; yoğun bir görev diğerlerinin ilerleme veya kapanış olaylarını aç bırakmaz. En fazla 16 aktif işlem ve son 50 tamamlanmış görev tutulur. `done` bildirimi kaynakları erken serbest bırakmaz; sahip olunan süreç temizliği de tamamlanmalıdır.

Kaynak paylaşan işlemlerin güvenlik nedeniyle çakışması ile arayüzün kilitlenmesi farklı durumlardır. Python olmadan migration veya aynı veritabanı üzerinde eşzamanlı kurulum yapılmaz; gerekli sıralama ve transaction sınırları korunur. Profil, kaynak (üst/alt dizinler dahil) ve runtime erişimleri paylaşılan/özel işletim sistemi kilitleriyle Manager ve CLI arasında korunur. Kilitler alt süreç temizliği tamamlanmadan bırakılmaz. Web ve job worker 10 saniyede bir denetlenir; üç başarısız tur sorun, iki başarılı tur tekrar hazır durumu üretir. Otomatik yeniden başlatma yapılmaz.

### Yardımcı süreç hata kodları

Kaynak testi için Windows yönetici yetkisi gerekmez. Kaynaklara HTTPS erişiminin
başarısız olması kontrol satırlarında gösterilir. Yardımcı sürecin kendisi
çalışamıyorsa raporda aşağıdaki ayrı kodlardan biri bulunur:

| Kod | Anlamı |
| --- | --- |
| `worker_start_denied` | İşletim sistemi yardımcı sürecin başlatılmasına izin vermedi. |
| `worker_start_failed` | Yardımcı süreç başlatılamadı; paket ve dosya erişimi kontrol edilmeli. |
| `worker_containment_failed` | Windows süreç izolasyonu kurulamadı; işlem başlatılmadı. |
| `worker_channel_failed` | Özel süreç iletişimi kurulamadı veya kesildi. |
| `worker_protocol_invalid` | Yardımcı sürecin yanıtı beklenen biçimde okunamadı. |
| `worker_exited` | Yardımcı süreç sonuç bildirmeden kapandı. |
| `worker_request_invalid` | Form isteği aktarım için hazırlanamadı. |

Rapor yalnız sabit açıklamalar ve varsa sayısal sistem/süreç çıkış kodlarını
gösterir; ham exception, dosya yolu, worker çıktısı veya credential içermez.
Süreç iletişiminin kodlaması, Windows'un metin kodlamasından bağımsız UTF-8'dir.
Eski paketlerde bunların tamamı `worker_failed` olarak görünür; bu genel mesaj
tek başına internet, yetki veya eksik dosya teşhisi koydurmaz.

## Windows üzerinde paket üretme

Build için native Windows x64 ve Tk içeren CPython 3.11 gerekir. Bu gereksinimler son kullanıcıya ait değildir. Build aracı geçici, ayrı bir sanal ortam oluşturur ve yalnız `packaging/manager-requirements.txt` içindeki `PyInstaller==6.22.3` build bağımlılığını kurar; uygulamanın `requirements.in`, `requirements.txt` veya sanal ortamını değiştirmez. Build paketlerinin transitive sürümleri bu dosyada ayrıca kilitli değildir.

```bat
py -3.11 scripts\build_manager.py --output "C:\AWCenterBuild\AWCenterManager-windows-x64.zip"
```

Çıktı ZIP'i, `.zip.sha256` checksum dosyası ve `.zip.inventory.json` envanteri yeni olmalıdır; mevcut dosyanın üzerine yazılmaz. Envanter ayrıca ZIP içinde `manager-manifest.json` olarak bulunur. ZIP kökü:

```text
AWCenterManager.exe
_internal/
source/
  manager-source-manifest.json
runtimes/
dependencies/
  wheels/
  npm-cache/
  manifest.json
install-manifest.json
manager-manifest.json
```

Kaynak seçimi mevcut `copy_install_source` güvenlik filtresini ve Git tracked envanterini kullanır. Yeni yönetici modülleri ve ilk yönetici servisi yalnız açık dosya allowlist'iyle eklenir. Yerel environment, credential, private state, dependency cache ve bilinmeyen kök dosyalar dağıtılmaz. `runtimes/` yalnız repository'deki onaylı katalogda bulunan Python, Node ve npm arşivlerini içerir; katalogdaki SHA-256 değerleri kopyalamadan sonra yeniden doğrulanır.

Runtime arşivleri için build komutu `--source-mode online|restricted|corporate|offline`, `--repository`, `--offline-dir`, `--ca-file`, `--python-index-url` ve `--npm-registry-url` alır. Bu seçenekler PyInstaller build bağımlılıklarının pip kaynağını değiştirmez; build ortamının paket/proxy/CA yapılandırması ayrıca sağlanmalıdır. [PyInstaller dağıtım dokümantasyonu](https://pyinstaller.org/en/stable/) Windows çıktısının Windows üzerinde üretilmesini gerektirir. PyInstaller build aracıdır; Python, Tcl/Tk ve paket içindeki runtime'ların lisans koşulları dağıtım sürecinde korunmalıdır.

## Doğrulama ve mevcut sınır

`.github/workflows/manager-windows.yml` ilgili kaynak değişiklikleri push edildiğinde, pull request açıldığında veya elle tetiklendiğinde CMD ile Windows üzerinde ZIP üretir ve çıkarılmış EXE'yi çalıştırır. Kaynak worker testi, gerçek kontrol pipe’ı açık ve okuma beklerken sistem Python denetiminin tamamlandığını da doğrular. Native kabul testleri:

- PATH'ten Python, Node, npm ve Git çıkarılmış, ağ proxy'si erişilemez bir ortamda gerçek ilk Tk penceresi;
- paketli worker'ın özel pipe bağlantısı ve açık Kurumsal/Çevrimdışı kaynak seçimleri;
- kurulu araç bulunmadan gerçek Online geliştirme kurulumu, ilk yönetici, HTTP hazır olma ve Durdur sonrası frontend/backend süreçlerinin kapanması.

Online kabul ayrıca aynı özel profili yeniden başlatır; mevcut yönetici korunur, private environment dosyasının SHA-256 değeri değişmez ve yeniden başlatma ağ erişimi kapalıyken tamamlanır. Üretilmiş kaynak durumu asıl taşınabilir paket altında bırakılmaz; test ayrı, doğrulanmış kaynak kopyası kullanır.

```bat
set AWCENTER_RUN_MANAGER_WINDOWS_SMOKE=1
set AWCENTER_MANAGER_EXE=C:\AWCenterBuild\extracted\AWCenterManager.exe
py -3.11 -m unittest scripts.test_manager_package.NativeWindowsPackageTests
```

Tam soğuk çevrimdışı dev/prod kabulü artık workflow'da zorunludur;
`scripts.test_manager_windows_acceptance.NativeOfflineAcceptance` aynı tam
paketi sistem araçlarıyla ve yönetilen araç seçimiyle çalıştırır. Test yalnız
geçici CI Windows makinesinde Windows Firewall ile Manager, sistem/yönetilen
Python ve Node, dev/prod sanal ortamlarının dış IPv4/IPv6 erişimini engeller;
loopback ve uygulamanın kendi IPv4 adresi açık kalır. CI runner'ın ayrı kontrol
bağlantısı engellenmez. Kurallar kurulumdan önce, henüz oluşmamış runtime ve
release yolları dahil tanımlanır. Engelin gerçekten çalıştığı test Python'u ve
kurulan uygulamanın Python/Node süreçlerinde TCP bağlantılarıyla doğrulanır.
Testin geçici kuralları sonunda kaldırılır.
Firewall kurulamazsa test başarısız olur, çevrimdışı kabul atlanmaz.

Paket bir kez üretilir; iki ayrı native kabul işi aynı SHA-256 doğrulanmış ZIP'i
kullanır. ZIP'in artifact olarak bulunması yayın kabulü değildir: workflow'un
iki kabul işi de başarılı olmalıdır.

Gerçek HTTPS, ilk yönetici, session cookie/CSRF, frontend, küçük DOCX karşılaştırma
job'ı, gerçek worker ve yetkili/anonim dosya indirme kontrolleri yapılır. İptalden
sonra yeniden deneme, ikinci Manager/CLI çakışması, süreç çökmesi, portların
kapanması ve yeniden başlatmada hesap/anahtar/eski çıktı korunması kapsanır.
HTTP/API mock kullanılmaz. Eski pencere/proxy smoke testleri bu kapının yerine
geçmez. Network engeli uygulama için bir ürün özelliği değildir.

05.11.2026 uygulaması macOS üzerinde geliştirilmiştir. Windows EXE üretimi,
NTFS/Job Object/Firewall kabulü ve gerçek kurumsal ağ bu ortamda çalıştırılamaz.
Yayın için Windows CI sonucuna ek olarak araçsız **temiz Windows** ve standart
kullanıcı hesabında saha kabulü gerekir; zorlanmış yönetilen araç seçimi temiz
makine kanıtı değildir. Açık/koyu tema, %100/%150/%200 ölçek, küçük pencere,
Tab/Enter/Escape ve küçültüp geri açma gerçek Windows'ta elle kontrol edilir.
Çevrimdışı kurulum JIRA/SMTP gibi uzak servisleri çevrimdışı kullanılabilir yapmaz.

USB yalnız taşıma içindir; tam klasörü hedefte yerel NTFS diske kopyalayın.
Dev kopyalanan kaynakta, prod ayrı yönetilen release alanında çalışır. İlk
başlangıçta tam manifest algılanır, paket yollarıyla çevrimdışı mod seçilir;
açık `--root` önceliklidir ve başka makineden kalmış araç/TLS/env yolları taşınmaz.
Sürüm yükseltme, imzalama, otomatik yayın, servis ve sistem tepsisi kapsam dışıdır.
