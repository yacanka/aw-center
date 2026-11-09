# AW Center Windows masaüstü yöneticisi

Taşınabilir paket Windows x64 içindir. ZIP'in tamamını kullanıcıya ait yerel bir dizine çıkarın ve `AWCenterManager.exe` dosyasını açın. İlk pencere için kurulu Python, Node, npm, Git veya ağ bağlantısı gerekmez. Python/Tk arayüzü `_internal/` içinde; uygulama kaynakları `source/`, SHA-256 değerleri onaylı Python 3.11, Node ve npm arşivleri `runtimes/` içindedir. Bu dizinleri EXE'den ayırmayın.

Pencerenin açılması uygulamanın hazır olduğu anlamına gelmez. Güncel tam paket,
`dependencies/wheels` ve `dependencies/npm-cache` içerir; yalnız eski
`runtimes/` paketleri bağımlılıkların çevrimdışı kopyası değildir.

## Sade yönetim ekranı

Yeni kullanıcı için varsayılan yerel geliştirme profilidir. **AW Center’ı aç**,
teknik alan doldurmadan eksik kurulumu hazırlar ve uygulamayı başlatır. Gerekli
Python/Node, kilitli bağımlılıklar, özel yapılandırma, veritabanı ve worker aynı
akışta ele alınır. İlk aktif yönetici yoksa kullanıcı adı ve parola sorulur.
Hazır ortam yeniden kurulmadan açılır. Pencerenin açılması tek başına kurulum,
migration veya sunucu başlatmaz.

Profil, kaynak, bağlantı, araç ve `.env` alanları **Gelişmiş ayarları göster**
altındadır; kayıtlı değerler olsa da bu panel başlangıçta kapalıdır. Kaynaklar ve
Rapor görünümleri isteğe bağlıdır. Ana eylem, gelişmiş değişiklikleri uygular veya
ilgili engeli açıklar. Çalışan profilin ayarları değişirse **Durdur, uygula ve aç**
yalnız sahip olunan süreçleri temizledikten sonra yeni ayarlarla devam eder.

Ana ekran seçili **profilin gerçek durumu**, **ana eylem** ve **işlem ilerlemesi**
üzerine kuruludur. Açılışta ve kaynak/profil değişiminde arka planda salt okunur
inceleme yapılır; eski inceleme yeni seçimi değiştiremez.

| Durum | Ana eylem |
| --- | --- |
| Kurulmamış | AW Center’ı aç |
| Hazırlanmış, durmuş | AW Center’ı aç |
| Tamamlanabilir yarım kurulum | Tamamla ve aç |
| Çalışıyor ve sağlıklı | Tarayıcıda aç |
| Müdahale gerekiyor | Eksikleri göster |

Kaynaklar ve Rapor düğmeleri ilgili görünümü açar; Ctrl+1/2/3 korunur.
Kaynak testi veya başka bir rapor seçmek çalışan profilin Tarayıcıda aç/Durdur
kontrollerini değiştirmez. Üretimde eksik IPv4, sertifika ve özel anahtar alanları
gerektiğinde gelişmiş panelde gösterilir. Açık/koyu tema, sistem
fontu, klavye odağı ve küçük pencerede kaydırma korunur.

İlerleme geçerli aşama, geçen süre ve bekleme nedenini gösterir; tahmini yüzde
üretilmez. Denetim özeti Hazır, Eksiklerle kullanılabilir veya Kurulum engellendi
olur. **Yeniden dene / Ctrl+R**, ilgili görevin kayıtlı ayarlarını kullanır;
formu değiştirmek yeni bir işlem başlatmak içindir. Başlatmada tarayıcı bir kez
açılır. Durdurulan görevin canlı bağlantısı kaldırılır.

Aktif işlem varken **X** görev çubuğuna küçültür. **Çıkış**, mevcut onaylı güvenli
durdurma akışını çalıştırır; süreçler temizlendikten sonra kapanır. Aktif işlem
yokken X doğrudan kapatır. Sistem tepsisi veya Windows servisi kurulmaz.

`AWCenterManager.pyw` ve paketlenmiş EXE üzerinden çalıştırılan kurulum,
pip/npm, Git sorguları ve uygulama süreçleri siyah konsol penceresi açmaz.
Komut kapısı, konsolu olmayan Manager altında gizli bir konsol oluşturur;
ensurepip ve npm'in kendi alt süreçleri de bu konsolu miras alır.
Yalnız ilk sürece `CREATE_NO_WINDOW` vermek bu mirası sağlamaz;
[Windows süreç oluşturma bayrakları](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)
ve `STARTUPINFO` pencere ayarı birlikte kullanılır. Terminalden çalıştırılan
launcher'ın mevcut konsolu korunur. İşlem iptali ve Job Object sınırı değişmez.

## Sistem Python ve Node.js seçimi

Manager varsayılan olarak önce sistemdeki uygun Python ve Node.js kurulumlarını arar; bulunan aracı indirmez veya değiştirmez. Python için mevcut CPython, `py -3.11`, PATH'in tüm dizinleri, Windows Python kayıtlarının 32/64 bit görünümleri ve yaygın kurulum dizinleri üzerinden tam **CPython 3.11 x64** aranır. `venv` ve `ensurepip` desteği de doğrulanır. Otomatik aramada uygun Python bulunamazsa seçilen kaynak politikasına göre yönetilen Python hazırlanır. **Her durumda yönetilen Python kurulumunu kullan** kutusu bu otomatik tercihi açıkça geçersiz kılar. Store yürütme alias'ı başlatılmaz; Python launcher'ın otomatik kurulum seçeneği sorguda kapalıdır. [Python Windows launcher ayarları](https://docs.python.org/3/using/windows.html) bu ortam seçeneklerini açıklar.

Otomatik tespit yeterli olmazsa **Gelişmiş ayarlar → Python komutu / yolu (isteğe bağlı)** alanına `python`, `py -3.11`, `C:\Python311\python.exe` veya Python kurulum dizinini girin; **Seç…** düğmesiyle `python.exe` de seçebilirsiniz. Boşluk içeren, tırnakla kopyalanmış dosya yolları desteklenir. Girilen seçim doğrulanır; uyumsuzsa farklı bir Python'a sessizce geçilmez. Shell komutu çalıştırılmaz. Yönetilen Python kutusu seçildiğinde bu alan kullanılmaz. Alan Kur ve başlat ile offline paket hazırlığı içindir; Başlat ve Durumu denetle mevcut profilin kayıtlı Python seçimini korur.

**Node.js komutu / yolu (isteğe bağlı)** alanı `node`, `node.exe` dosyasının tam yolu veya kurulum dizinini kabul eder; **Seç…** düğmesi EXE seçer. Boşsa PATH, Windows kayıtları ve yaygın dizinler taranır. Desteklenen sistem Node, x64 **22.13+ (22.x) veya 24+** sürümüdür; ön sürümler ve uyumsuz mimariler kullanılmaz. Otomatik arama uygun kurulum bulamazsa yalnız eksik yönetilen Node hazırlanır. Elle verilen geçersiz seçim açık hata üretir. İptal, indirmeye geçiş sayılmaz.

Seçilen Node yanındaki kararlı **npm 10.9.4+ (10.x) veya 11.x** CLI da kullanılır. Örneğin Node 26.12.1 ile kurulu npm 11.18.0, yalnız daha yeni olduğu için yeniden kurulmaz. Uygun npm eksikse doğrulanmış yönetilen **npm 10.9.4** arşivi hazırlanır; katalog pini ve dependency lock dosyaları değişmez. npm doğrudan seçilen Node ile çalıştırılır, `.cmd` üzerinden shell komutu yürütülmez. Python ve Node yolları profil bazında kaydedilir; Başlat ve Durumu denetle aynı araçları yeniden doğrular.

Runtime hazırlığı, arşiv edinme/açma, sürüm denetimi ve kayıt yazma aşamalarını ayrı gösterir. Sürüm denetimi de Manager'ın iptal edilebilir süreç yolunu ve ayrı stdin'i kullanır. Başlatma, 30 saniyelik zaman aşımı, süreç çıkışı ve katalog sürüm uyuşmazlığı `runtime_validation_…` kodlarıyla raporlanır; ham stdout/stderr veya dosya yolu gösterilmez. pip/npm alt süreçleri için kullanıcı ve global npm ayarları iki farklı boş geçici dosyayla ayrılır; aynı null dosyasının iki kez yüklenmesi önlenir ve dosyalar işlem sonunda temizlenir.

Paket komutlarının Python çıktısı ve Manager okuması açıkça UTF-8 kullanır;
Windows'un yerel ANSI kod sayfasına veya devralınan `PYTHONIOENCODING` değerine
bağlı değildir. Eski kod sayfasıyla yazan yerel araçların tanılama baytları
kaçış biçiminde korunur; çıktı çözümlemesi başarılı komutu hataya çevirmez veya
başarısız komutun çıkış kodunu gizlemez. Ham araç çıktısı rapora aktarılmaz.
Bağımlılık aşaması sanal ortam, güven deposu, Python paketleri ve frontend
paketleri olarak ayrı ilerleme bildirir. Dosya erişimi, disk doluluğu, eksik
yol ve uzun yol hataları güvenli kategori ve varsa `WinError`/`errno` ile
raporlanır; dosya adları, komut satırları ve kimlik bilgileri gösterilmez.

`truststore` veya onu başlangıçta etkinleştiren `pip-system-certs` bulunan
Python kurulumlarında, HTTPS doğrulaması çalışsa da `get_ca_certs()` sertifika
listeleme çağrısı desteklenmeyebilir. Önceki Manager bu `NotImplementedError`
hatasını genel `operation_failed` olarak gösteriyordu.
Sertifika aktarımı artık bu durumda CPython'un yerel OpenSSL bağlamını yalnız
listeleme için kullanır: Windows `CA` ve `ROOT` depolarından sunucu doğrulamasına
izinli sertifikalar, varsayılan OpenSSL kökleri, pip/Node kökleri ve seçilen ek
CA dosyaları birleştirilir. Kurulu SSL sağlayıcısı değiştirilmez; kurum paketi
kaldırılmaz ve TLS doğrulaması kapatılmaz. Aynı yardımcı hem Manager içinde
hem hedef Python'da, kurulum ve çevrimdışı paket hazırlığında kullanılır.
[Truststore'un SSL sağlayıcısı](https://github.com/sethmlarson/truststore/blob/main/src/truststore/_api.py)
bu listeleme metodunun desteklenmediğini açıkça belirtir.

Güven deposu hazırlığı sistem, ek CA, Python/pip, Node.js ve birleşik dosya
adımlarını ayrı raporlar. Başarısızlıkta `package_trust_<aşama>` kodu ve
güvenli hata türü (örneğin `NotImplementedError`, `SSLError`) gösterilir;
ham hata metni, sertifika içeriği veya özel dosya yolu gösterilmez.
Bu tanı ayrımı, farklı bir makinedeki arızayı yalnız genel hata mesajından
tahmin etmeye ihtiyaç bırakmaz.

Python 3.11.3 x64 dahil CPython 3.11 yama sürümleri kabul edilir. Etkileşimli `python` ekranının açılması, `venv` ve `ensurepip` desteğinin hazır olduğunu tek başına göstermez. Manager artık süreç başlatma hatasını (`system_python_start_failed`, varsa `WinError`/`errno`), süreç çıkışını (`system_python_process_failed` ve sayısal çıkış kodu), denetim zaman aşımını (`system_python_timeout`), eksik `venv`/`ensurepip` modülünü ve standart modül yükleme hatasını ayrı raporlar. Ham stderr, dosya yolları veya exception içeriği rapora aktarılmaz. Eski genel “Python bulunamadı” mesajı bu nedenleri ayırt ettirmez.

Python aramasının toplam bütçesi **120 saniye**, tek adayın üst sınırı **60 saniyedir**. Node/npm araması ortak **60 saniyelik** bütçe kullanır; tek denetim en fazla **30 saniye** sürer. Arama başlamadan durum bilgisi gösterilir ve **Durdur** denetim sürerken de kullanılabilir. Aynı dosyaya giden PATH yazımları aynı aramada tekrar denenmez; doğrudan çalıştırılıp bütün kontrolleri geçen Python hemen ikinci kez başlatılmaz. Launcher veya sanal ortam farklı bir temel yorumlayıcı bildirirse temel dosya ayrıca doğrulanır. Zaman aşımı, süreç hatası veya geçersiz yanıt araç yok sayılarak indirmeye dönüştürülmez. Yeniden deneme, açık yol seçimi veya yönetilen araç seçimi gerekir; sistem kurulumu değiştirilmez.

Kurulumda değişiklik yapmadan CMD’de `python -I -S -c "import venv, ensurepip, sysconfig; print(sysconfig.get_platform())"` ile aynı izole modül kontrolünü yapabilirsiniz; Windows x64 için başarılı sonuç `win-amd64` olur. `>>>` etkileşimli Python ekranındaysanız önce `exit()` ile CMD’ye dönün. Başarısızsa hata türünü ve Manager’ın yeni hata kodunu birlikte değerlendirin; yalnız sürüm ekranına bakarak yeniden kurulum kararı vermeyin.

CMD denetimi geçmesine rağmen eski Manager paketleri `system_python_timeout` verebilir: Manager’ın kontrol thread’i iletişim pipe’ında okuma beklerken aynı stdin’i miras alan Python, Windows başlangıcında kilitlenebilir. Manager bağlamındaki komutlar artık bu kanalı miras almaz; özel input verilmediyse stdin kapalı girdiye (`DEVNULL`) yönlendirilir. Açık input akışları, iptal kanalı ve CLI kullanımı korunur. Worker sağlık denetimi de iletişim kanalından ayrılmıştır. Düzeltme paketli Manager koduna aittir; kaynak güncellemesinden sonra Windows ZIP/EXE’si yeniden üretilmelidir.

Kutu seçilirse paketteki veya seçilen kaynaklardaki SHA-256 sabitlenmiş yönetilen Python kullanılır. Bu seçim Node/npm hazırlığından ayrıdır. Her iki durumda da uygulamanın kilitli pip paketleri proje `.venv` dizinine kurulur; sistem Python paketleri değiştirilmez. Sistem modu işletim sistemindeki mevcut Python'a güvenir, onun dosyalarına yönetilen arşivin hash pinini uygulamaz.

Başarılı bağımlılık hazırlığından sonra seçilen sistem yorumlayıcısı dev/prod profil metadata'sına ayrı ayrı kaydedilir; Başlat ve Kontrol et aynı seçimi kullanır. Özel env, anahtarlar ve mevcut hesaplar değişmez. Mevcut `.venv` farklı bir Python'a bağlıysa veya yarım kalmışsa hazırlık işlemi eski ortamı kaynak dizininin `.runtime/venv-backups/` alanında korur, seçilen Python ile yeni ortamı oluşturur ve kilitli bağımlılıkları kurarak devam eder. Ayrı kaynak dizini seçmek gerekmez. İşlem kesilirse yeniden açma işlemi hazırlığı sürdürür; eski ortam yedekleri otomatik silinmez. Profil değişimi sonradan sistem Python'unu kaldırmaz veya güncellemez.

Windows CPython **3.11.9 x64** desteklenir. `.pyw` üzerinden açılışta bulunan
`pythonw.exe`, aynı kurulumdaki `python.exe` doğrulanarak kullanılır; eski profil
seçimleri ve yarım kalmış oluşturma kayıtları da bu eşleştirmeyle okunur.
[CPython 3.11.9 venv](https://github.com/python/cpython/blob/v3.11.9/Lib/venv/__init__.py#L299-L306)
iki EXE'yi de oluşturur; konsol ortamının temel yorumlayıcısı pencere kipindeki
EXE'den farklı adla bildirilebilir. Yorumlayıcı yolu ASCII JSON olarak taşınır;
Türkçe karakterli dizinlerde farklı Windows kod sayfaları karşılaştırmayı bozmaz.
Yeni oluşturulan ortam doğrulanamazsa aynı oluşturma kaydı korunur ve sonraki
denemelerde yeniden yedeklenmez. Önceki sürümlerin oluşturduğu yedekler silinmez.

Manager üzerinden hazırlanan **tam USB paketi**, üreticide sistem araçları kurulu
olsa da Python/Node/npm arşivlerini içerir. Araçlar ayrı geçici alanda hazırlanır;
canlı uygulamanın runtime veya sanal ortamı değiştirilmez. Kaynak üzerinden
çalıştırmada hazır Windows Manager dağıtımı bulunamazsa aynı kaynak sürümünün
EXE'si ayrı geçici ortamda otomatik üretilir ve tam pakete eklenir. Hazır Manager
dizini seçmek gelişmiş kullanıcılar için isteğe bağlıdır. Derleme araçları da
seçilen kaynak modu, paket indeksi ve CA ayarlarına uyar; ilk hazırlıkta bu
paketlerin izin verilen kaynaklarda bulunması gerekir.
Hedefte uyumlu sistem araçları yine önceliklidir. Eski v1/v2 kurulum paketlerinin
okunması ve v2 `host_runtimes` gereksinimlerinin doğrulanması korunur.


## Form değerlerini hatırlama

Manager normal biçimde kapatıldığında son form değerlerini `%LOCALAPPDATA%\AWCenterManager\manager.json` içinde atomik ve yalnız mevcut kullanıcıya açık olarak saklar. Bu alan standart Windows kullanıcısının kendi profilindedir; yönetici olarak çalıştırma veya kurulum klasörünün izinlerini değiştirme gerektirmez. Kurulumun `%LOCALAPPDATA%\AWCenter` dizini yazılabilir veya tam olarak aynı özel ACL biçiminde olmak zorunda değildir. Profil, kaynak modu/adresleri, dizinler, Python/Node seçimleri, portlar, CA/TLS ve `.env` dosya yolları sonraki açılışta geri gelir. `--root` ile verilen kaynak dizini hatırlanan dizinden önceliklidir. İşlem başlatılmadan girilen değerler de kapanışta saklanır; ani süreç sonlandırmada son değişiklikler kaybolabilir.

Yeni kayıt yoksa önceki sürümün `%LOCALAPPDATA%\AWCenter\config\manager.json` dosyası salt okunur olarak kontrol edilir. Sahiplik, özel izinler ve symlink/junction kontrollerinden geçen eski değerler yüklenir ve normal kapanışta yeni alana yazılır. Eski dosya silinmez, içeriği veya izinleri değiştirilmez. Güvensiz ya da bozuk eski kayıt içe alınmaz; yeni alanda form değerlerini kaydetmek yine mümkündür.

Yalnız dosya yolları kaydedilir; `.env`, sertifika ve özel anahtar içerikleri okunmaz. Yönetici kullanıcı adı/parolası ve credential içeren URL'ler kaydedilmez. Migration onayı her işlem için yeniden verilir. Kayıt okunamıyorsa form varsayılanlarla açılır ve durum/rapor mesajı gösterilir; kayıt yazılamıyorsa kapanışta uyarı verilir. Mesaj başarısız aşamayı, kullanıcı adını açığa çıkarmayan sembolik kayıt konumunu, `preferences_…` hata kodunu, varsa sayısal `WinError`/`errno` değerini ve çözüm adımını içerir. Windows ACL kontrolü başarısızsa ilgili güvenli kontrol kimliği de gösterilir; ham exception, SID, form değerleri veya dosya içerikleri gösterilmez. Dosya kilidi, erişim reddi, dolu disk/kota, salt okunur disk ve bozuk kayıt birbirinden ayrılır. Başarısız atomik yazmada önceki kayıt korunur. Bu dosya uygulama profillerinden ayrıdır; mevcut hesapları, anahtarları veya veritabanını değiştirmez.

## .env dosyası seçimi

Ana **AW Center’ı aç** eylemi seçilen ayarları kayıtlı profille karşılaştırır;
değişiklik varsa hazırlama yolunu, yoksa normal başlatmayı kullanır. Gelişmiş
paneldeki eski **Kur ve başlat** ve salt okunur denetim işlemleri de korunur.

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
%LOCALAPPDATA%\AWCenter\r\<12-karakter-kaynak-kimliği>
```

Manifest kimliği tüm dağıtılabilir kaynak envanterinin tam SHA-256 değeridir. Klasör adında ilk 12 karakter kullanılarak Windows paket yolları kısa tutulur; aynı kısa kimlik farklı tam manifest ile çakışırsa mevcut kaynak değiştirilmez. Eski `releases/<tam-SHA256>/source` kurulumları taşınmadan okunmaya devam eder. Aynı kaynak tekrar seçildiğinde mevcut kopya yeniden doğrulanır. Değişmiş bir release dosyası, beklenmeyen kaynak dosyası, symlink veya junction hata verir; yönetici mevcut release'i onarmaz veya üzerine yazmaz. Bilinen üretilmiş sanal ortam, npm paketleri, build çıktıları, Python cache ve geliştirme SQLite dosyaları kaynak karşılaştırmasına girmez.

Dağıtılmış `source/manager-source-manifest.json` dosyasını koruyun. Manifest taşınan kaynağın eksiksizliğini ve bütünlüğünü denetler; dijital imza değildir. ZIP checksum'unu güvenilir bir dağıtım kanalından doğrulayın. Git checkout'undan geliştirme sırasında üretim kopyası hazırlanabilir; manifesti olmayan rastgele çıkarılmış bir kaynak dizini kabul edilmez.

Otomatik kaynak seçiminde **AW Center’ı aç**, **Başlat** ve **Kontrol et** kayıtlı
profilin kaynak dizinini kullanır. Manager veya dağıtım paketi güncellense de
mevcut prod kurulumu yeni sürüme kendiliğinden bağlanmaz. Kontrol et mevcut
prod'un manifestini ve profilini salt okunur doğrular; paket indirmez, yeni
release oluşturmaz, veritabanını veya anahtarları değiştirmez.

Gelişmiş ayarlarda açıkça seçilen kaynak bu otomatik seçimi geçersiz kılar.
Seçilen sürüm için hazırlanmış prod kopyası yoksa `production_source_not_prepared`
gösterilir. Mevcut prod'u denetlemek veya başlatmak için Proje kaynak dizini
alanını boş bırakarak otomatik seçime dönün. Eksik release, kaynak ZIP'in bozuk
olduğu anlamına gelmez; bütünlük veya izin hataları ayrıca denetlenmeye devam eder.

Üretim için makineye atanmış sabit IPv4, kaynak ağacının dışındaki mevcut TLS sertifikası ve özel anahtar gerekir. Profiller ve özel durum `%LOCALAPPDATA%\AWCenter` altında ayrılır. Geliştirme ve üretim aynı veritabanını, özel dosyaları veya anahtarları paylaşmaz. CLI ve gelişmiş eski kurulum işleminin migration onayı değişmez; ana otomatik akış aşağıdaki yedek politikasını kullanır.

Kayıtlı TLS sertifikası veya özel anahtar taşınmışsa, gelişmiş ayarlardan mevcut
dosyayı seçip **AW Center’ı aç** işlemini çalıştırın. Manager eski dosyanın hâlâ
var olmasını şart koşmadan seçilen yeni yolları değerlendirir. Profilin sahipliği,
kaynak kimliği, `.env`, anahtarlar ve ayrı veri yolları doğrulanmaya devam eder.
Yeni sertifika/anahtar eşleşmesi, geçerlilik süresi ve IPv4 kimliği doğrulanmadan
yollar kaydedilmez. Güncelleme mevcut kesintiye dayanıklı profil kaydı üzerinden
yapılır; veritabanı ve uygulama anahtarları korunur. Başlat/Kontrol et işlemleri
dosya yollarını kendiliğinden onarmaz.

Dosya yolu hatalarında rapor hangi alanın eksik, bulunamayan, göreli veya prod
kaynağı içinde olduğunu belirtir (`tls_file_*`); ham dosya yolları gösterilmez.
Bu kontrol HTTPS bağlantı testinden ayrıdır. Kullanılabilir bir sertifika/anahtar
yoksa Manager güvenilir bir kurumsal sertifika üretemez; uygun dosyalar seçilmelidir.

### Otomatik portlar ve migration

Yeni yerel kurulumda portlar boş bırakılabilir. Önce backend için 8000, frontend
için 5173 denenir; doluysa farklı boş loopback portları seçilir. Otomatik seçilmiş
portlar sonraki açılışta uygunsa korunur. Elle seçilmiş ve önceki sürümden kalmış
portlar sabittir; yerel port alanına `auto` yazarak otomatik seçim açılabilir.
Üretim portu sabit kalır. Port değiştiğinde otomatik üretilmiş CSRF/origin ve
reset/invitation adresleri birlikte güncellenir; özel `.env` adresleri çelişiyorsa
işlem açıklamayla durur. Başka uygulamalar kapatılmaz; doğrulanmış port
çakışmasında en fazla üç seçim denenir.

Ana akışta mevcut ve tanınan veritabanının bekleyen migration'ları, uygulama
durmuşken SQLite ve özel dosya yedeği doğrulandıktan sonra otomatik uygulanır.
Gelişmiş panelde yedek sonrası ayrıca onay isteme seçilebilir. Yedekler
`%LOCALAPPDATA%\AWCenter\backups\<profil>\<kimlik>` altında owner-only tutulur;
eski yedekler silinmez veya üzerlerine yazılmaz. Manifest içerik yerine hash ve
işlem kimliklerini taşır; mevcut anahtarlar özel environment dosyasında korunur.
Bu yerel migration yedeği, ayrı ortamda saklanan felaket kurtarma yedeğinin yerini
almaz.

Bozuk/bilinmeyen şema, aktif SQLite WAL/yazıcı, değişen dosyalar, disk/izin veya
yedek doğrulama hatası migration'ı engeller. Yarım kalan migration otomatik tekrar
edilmez; tüm migration'lar uygulanmışsa yalnız eşleşen işlem kaydı ve son
kontrollerle tamamlanabilir. Reset, fake migration ve otomatik geri yükleme yoktur.

Aynı paket yeniden açıldığında gelişmiş tercihler korunur. Paket yolu veya kaynak
kimliği değiştiğinde eski makine yolları otomatik uygulanmaz; önceki tercihler
filtrelenmiş bağlam geçmişinde saklanır. Kurumsal/çevrimdışı sınır otomatik olarak
genel internete açılmaz. Açık kaynak seçimi yoksa doğrulanmış kayıtlı kurulum
kullanılır; yeni paket açmak mevcut release'i yükseltmez.

## Paket kaynakları

Kaynak modu her işlemde açıkça seçilir:

| Mod | İzin verilen kaynaklar |
| --- | --- |
| Online | Doğrulanmış yerel içerik → genel HTTPS kaynakları → seçilen kurumsal kaynaklar |
| Otomatik (`restricted`, yeni masaüstü varsayılanı) | Doğrulanmış yerel içerik → seçilen depolar → genel HTTPS kaynakları |
| Kurumsal | Yalnız seçilen kurumsal HTTPS veya yerel kaynaklar; genel internete fallback yok |
| Çevrimdışı | Yalnız seçilen yerel doğrulanmış paket dizini; ağ indirmesi yok |

Python index adresi, npm registry adresi ve runtime arşiv deposu ayrı alanlardır. Kurumun CA dosyasını gerektiğinde seçin; TLS kontrolü kapatılmaz. URL'ye kullanıcı adı, parola veya token koymayın. Kurumsal proxy yapılandırması işlemin ortamından gelebilir; ham paket yöneticisi çıktıları arayüze veya rapora aktarılmaz.

Kur ve başlat ve Çevrimdışı paket hazırla, EXE yanındaki doğrulanmış arşiv ve
bağımlılık paketlerini otomatik değerlendirir. Çevrimdışı modda dizin alanını boş
bırakabilirsiniz; gerekli içerik otomatik bulunan yerel pakette yoksa eksik bildirilir.
Kayıtlı kaynak modu ve CLI'nin online varsayılanı korunur. Ağ kullanılan modlarda
seçilen modun izin verdiği kaynaklar sırayla denenir. Kesilen runtime transferleri
en fazla üç kez denenir; geçici HTTP/npm hataları diğer izinli kaynakları engellemez.
Tam uzunluktaki bozuk hash, TLS, izin, disk veya kurulum hatası otomatik fallback
ile gizlenmez. Kaynak numarası ve gerçek aşama raporda gösterilir.
Python bağımlılıkları hazırlanırken paket çözümleme, indirilen dosya (pip bildirirse
boyutuyla), önbellekten alma, wheel derleme ve kurulum adımları komutun bitmesi
beklenmeden durum alanına ve rapora yansır. Bu gösterim paket/dosya bazındadır;
indirme yüzdesi veya hız ölçümü değildir. Depo URL'leri, yerel yollar ve ham hata
çıktıları gösterilmez. Aynı canlı gösterim çevrimdışı paket hazırlığında da kullanılır.

Paket çıktı alanı boşsa her görev için yeni bir
`%LOCALAPPDATA%\AWCenter\exports\AWCenter-offline-…` dizini seçilir. Mevcut bir
çıktı klasörü seçildiğinde içinde yeni bir alt klasör oluşturulur; mevcut içerik
korunur. Hedef kaynak, Manager dağıtımı, asset veya bağımlılık girdilerinin
içindeyse Manager araç hazırlığından önce otomatik exports konumuna yönlendirir
ve bunu raporda belirtir. Diğer yeni hedefler aynen kullanılır. CLI çakışan
hedefleri yazma yapmadan reddeder; mevcut/yeni hedef sözleşmesi değişmez.
Tam paket hazırlığı araçlar için indirdiği doğrulanmış arşivleri tekrar
kullanır; canlı runtime veya uygulama bağımlılıklarını değiştirmez.

Kullanıcı müdahalesi gereken örnekler: ilk yönetici bilgileri, yeni production
profilinin IPv4/TLS dosyaları, seçilmişse yedek sonrası migration onayı, güvenilen kurum
CA'sı/proxy erişimi, bozuk medya veya tüm izinli kaynaklarda bulunmayan paket.
Paket komutu hataları `package_tls_failed`, `package_integrity_failed`,
`package_disk_full`, `package_access_denied` veya `package_command_failed` ile
güvenli neden ve yapılacak işlem olarak bildirilir. Kaynak ve kilit doğrulaması
ilk progress olayından önce sessizce çalışmaz; “Hazırlık” tek başına ağ hatası
teşhisi değildir.

İzole `npm ci --ignore-scripts` paket edinimi zaman aşımında diğer izinli depolar
denenir. Son çevrimdışı kurulum/build ve Python wheel derlemesi zaman aşımları
yeniden çalıştırılmaz; güvenli `package_timeout` bildirimi üretir. İptal hiçbir
kaynak denemesini veya otomatik yeniden başlatmayı tetiklemez.

Runtime arşivi indirme isteği yetki veya erişim nedeniyle reddedilirse Manager `artifact_http_rejected` koduyla Python, Node.js veya npm bileşenini ve sayısal HTTP kodunu gösterir. HTTP 401 depo kimlik doğrulamasını, 403 erişim reddini, 407 proxy kimlik doğrulamasını ayrı açıklar. Eski paketlerde bu durumlar genel `source_unavailable` mesajına dönüşüyordu. Yanıt gövdesi, adres, header ve ham hata metni rapora eklenmez. HTTP 401/403/407, bulunamama ve geçici bağlantı sorunları raporlanarak sıradaki izinli kaynağa geçilir. Kurumsal ve çevrimdışı modların sınırları korunur. TLS, hash, bozuk manifest ve kurulum hataları fallback yapmadan durur. Her uzak deneme ayrı geçici dizindedir; depolar aynı çözümleme havuzunda karıştırılmaz. Son kurulum Python için `--no-index --find-links`, npm için `npm ci --offline` ile yerelden yapılır.

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

### Kurulum alanı ve işlem kilidi hataları

**AW Center’ı aç**, Başlat, hazırlama ve paket oluşturma eylemleri, kayıtlı
profil okunmadan önce özel kurulum alanını denetler. Mevcut Windows hesabının
sahibi olduğu yönetilen klasörlerde üst klasörden izin kalıtımı açıksa, izinler
yalnız bu kullanıcıya açık hale getirilir ve sonuç yeniden doğrulanır. Yapılan
düzeltme ilerlemede gösterilir. İnert işlem kilidi dosyalarında aynı kurtarma
uygulanır; çalışan bir işlemin gerçek kilidi kaldırılmaz.

Ana klasör ve mevcut config klasöründe özel, geçici dosyalarla yazma, diske
aktarma ve atomik değiştirme sınanır. Böylece erişim, disk veya güvenlik yazılımı
engelleri paket hazırlığına geçmeden görünür. Her yeni ara klasör ayrı güvenli
oluşturulur; başka bir Manager aynı klasörü eşzamanlı oluşturduysa sahiplik ve
izinleri yeniden doğrulanarak kullanılır. Deneme dosyaları işlem sonunda silinir.

Bu kurtarma sahiplik almaz, alt dosyaların izinlerini topluca değiştirmez ve
mevcut profil/env/veritabanı içeriğini düzeltmez. Başka sahip, bağlantı/reparse,
çoklu hard link, değişmiş dosya kimliği/yolu veya kalıtımı zaten kapalı fakat beklenmeyen ACL hata olarak
kalır. Yalnız pencereyi açmak, **Durumu denetle / doctor / inspect** işlemleri
kurulum alanını değiştirmez. Yönetici yetkisi veya ağ erişimi gerekmez.

`Hazırlık` aşamasında özel kurulum alanına veya işlem kilidine erişim
reddedilebilir; bu aşama henüz paket kaynaklarının çalışmadığını göstermez.
İzin raporu başarısız kontrolün sabit adını ve varsa sayısal `WinError` kodunu
korur. Ham Windows hata metni, kullanıcı kimliği ve gerçek dosya yolu rapora
eklenmez.

| Kod | Anlamı / yapılacak kontrol |
| --- | --- |
| `storage_owner_mismatch`, `storage_ace_owner` | Sahiplik mevcut Windows hesabıyla eşleşmiyor. Kurulumu oluşturan hesapla açın ve sahipliği BT ile kontrol edin. |
| `storage_acl_read`, `storage_acl_apply` | İzinleri okuma veya uygulama başarısız. Windows hata koduyla kullanıcı profili erişimini ve kurum politikasını kontrol edin. |
| `storage_acl_inheritance` | Başlatmada yönetilen klasör/kilit kalıtımı otomatik sıkılaştırılır. Hata sürüyorsa düzeltme doğrulanamamıştır veya hata otomatik onarılmayan bir veri dosyasındadır; rapordaki aşamayı kontrol edin. |
| `storage_path_open`, `storage_path_information` | Windows dosya handle'ı veya tür/izin bilgisi okunamadı; sayısal Windows koduyla erişim ve güvenlik politikasını kontrol edin. |
| `storage_directory_type`, `storage_path_reparse`, `storage_path_links`, `storage_path_type_changed`, `storage_path_scope`, `storage_path_identity` | Beklenen yerel klasör/dosya türü, kimliği veya güvenli yol doğrulanamadı; dosyaları silmeden yolu ve bağlantıları kontrol edin. |
| Diğer `storage_*` izin kodları | Raporda belirtilen sahiplik / yalnız kullanıcıya açık izin kontrolü başarısız. |
| `storage_lock_failed` | İşlem kilidi alanının hazırlanması, dosyanın açılması veya kilit API'si başarısız; sayısal sistem koduyla erişim, disk ve güvenlik politikasını kontrol edin. |
| `resource_busy` | Başka bir işlem çakışan kilidi tutuyor; ilgili Manager / launcher görevini durdurun veya tamamlanmasını bekleyin. |

Önceki paketlerde bu durumlar `storage_unavailable` olarak birleştirilir.
Bu genel kod tek başına erişim reddini, sahiplik uyuşmazlığını veya gerçek
kilit çakışmasını ayırt etmez. Yeni tanılama için güncel kaynaklardan üretilmiş
Windows Manager paketi gerekir. Mevcut profil, anahtar veya veritabanını silmek
ve izinleri herkese açmak bir kurtarma adımı değildir.

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

Paket bir kez üretilir; paket yaşam döngüsü ve dört dev/prod × sistem/yönetilen
araç senaryosu ayrı native kabul işlerinde aynı SHA-256 doğrulanmış ZIP'i kullanır.
ZIP'in artifact olarak bulunması yayın kabulü değildir: workflow'un bütün kabul
işleri başarılı olmalıdır. Test sınıfı elle çalıştırıldığında dört senaryoyu da
çalıştırır; CI'nin seçtiği tek senaryo eksik veya geçersizse test hata verir.

Gerçek HTTPS, ilk yönetici, session cookie/CSRF, frontend, küçük DOCX karşılaştırma
job'ı, gerçek worker ve yetkili/anonim dosya indirme kontrolleri yapılır. İptalden
sonra yeniden deneme, ikinci Manager/CLI çakışması, süreç çökmesi, portların
kapanması ve yeniden başlatmada hesap/anahtar/eski çıktı korunması kapsanır.
HTTP/API mock kullanılmaz. Eski pencere/proxy smoke testleri bu kapının yerine
geçmez. Network engeli uygulama için bir ürün özelliği değildir.

05.11.2026 saat 07:36 (Europe/Istanbul) itibarıyla
[Windows CI koşusu 41961724839](https://github.com/yacanka/aw-center/actions/runs/41961724839)
`5ef3e184095f8e3741dc7e4be3744f9b2ff0bc96` üzerinde başarılıdır:
Windows EXE/ZIP build'i, beş paket yaşam döngüsü testi ve dört bağımsız
çevrimdışı dev/prod × sistem/yönetilen araç senaryosu geçti. NTFS, Job Object
ve gerçek Firewall kabulü Windows runner üzerinde çalıştı.
[Tam Windows paketi](https://github.com/yacanka/aw-center/actions/runs/41961724839/artifacts/13386701085)
ZIP, checksum ve envanteri içerir; GitHub artifact saklama süresi geçerlidir.

Geliştirme macOS üzerinde yapılmıştır; gerçek kurumsal ağ doğrulanmamıştır.
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

Yukarıdaki CI kanıtı önceki pakete aittir. Tek tuşlu `ensure` akışını, boş yerel
portları ve aynı akışla yeniden başlatmayı kapsayan yeni native kabul testleri
Windows üzerinde yeniden çalıştırılmadan bu değişiklik için Windows yayın kabulü
iddia edilmez. Snapshot write-through ve güç kesintisi dayanıklılığı da native
Windows kabulünün parçasıdır.

### Başlatma ve worker sağlık denetimi

Manager başlatırken Python/Node doğrulaması, profil okuma, şema kontrolü ve
web/worker hazırlığı ayrı aşamalar olarak raporlanır. Hazır olma süresi dolarsa
backend HTTP, frontend HTTP, bildirim/temizlik worker veya iş worker heartbeat
kontrollerinden hangisinin tamamlanmadığı gösterilir (`startup_not_ready`).

İş worker sağlık denetimi Django'yu her kontrolde yeniden açmaz. Launcher'ın
sahip olduğu tek `check_job_worker_health --watch` süreci aynı veritabanındaki
bu başlatmaya ait worker kimliğini ve heartbeat güncelliğini denetler. Manager,
özel runtime oturumundaki atomik sağlık kaydını okur; beş saniyeden eski,
süresi dolmuş veya başka worker'a ait kayıt hazır kabul edilmez. Durdurma ve
başlatma hatalarında sağlık süreci diğer alt süreçlerle birlikte kapatılır.
PowerShell, yönetici yetkisi veya güvenlik doğrulamasını kapatma gerekmez.

### Paket indirmelerini tekrar kullanma

Kurulum yardımcısı tamamlanan Python wheel ve npm paket edinimlerini
`%LOCALAPPDATA%\AWCenter\cache\packages` altında kullanıcıya özel saklar.
Dev ve prod sanal ortamları ayrıdır; aynı kilit dosyaları, hedef runtime ve
kaynak politikası için doğrulanmış indirmeler paylaşılır. Paket kurulumu veya
sonraki bir aşama başarısız olursa tamamlanmış indirmeler kaybolmaz. Başarılı
kurulumun aşama kaydı da aynı kilit ve dosyalar için tekrar kurulumu atlar.

Önbellek okunmadan SHA-256 envanteri doğrulanır. Yarım edinimler yayımlanmaz;
bozulmuş içerik, değişen hedef runtime veya farklı kaynak politikasına ait bir
önbellek sessizce kullanılmaz. Açıkça seçilen doğrulanmış çevrimdışı paket
önceliklidir. npm kurulumları önbelleğin geçici kopyası üzerinde çalışır;
paylaşılan edinim sonradan değiştirilemez. Kaynak adresleri bizim önbellek
manifestimize yazılmaz; npm'in çevrimdışı çözümleme için gereken özel indeks
metadatası kullanıcıya özel cache içinde kalır.

İndirilmiş Python paketleri `cache\packages\python\<kimlik>\data`, npm paketleri
`cache\packages\npm\<kimlik>\data\_cacache` altındadır. Bunlar kurulu paketlerden
ayrıdır: prod Python paketleri `r\<sürüm-kimliği>\.venv\Lib\site-packages`,
frontend paketleri `r\<sürüm-kimliği>\frontend\node_modules` altında bulunur.
Bu yollar `%LOCALAPPDATA%\AWCenter` tabanına göredir; eski prod kaynakları
`releases\<tam-kimlik>\source` altında kalabilir. Dev paketleri seçilen proje
dizinindeki `.venv` ve `frontend\node_modules` içindedir. Python/Node/npm
arşivleri `cache\runtimes`, kurulu yönetilen araçlar `runtimes\<ad>-<sürüm>`
altındadır. Hazır kurulumu açma işlemi paket hazırlığını çağırmaz.

Manager aynı hazırlık kararı içinde veritabanı incelemesini tekrar başlatmaz.
Hazır kurulum açılışındaki bu incelemeler dört süreçten ikiye indirilmiştir;
işlem kilidi alındıktan sonraki yeniden kontrol korunur. Kaynak/runtime hash
doğrulamaları sürer; ilk kurulum süresi ile hazır kurulumun açılış süresi ayrıdır.

Yeni prod kaynakları kısa `r/<12-karakter-kaynak-kimliği>` yolunu kullanır.
Bu, özellikle Torch'un derin paket dosyalarında Windows uzun yol politikasını
veya yönetici yetkisini değiştirmeden varsayılan kurulum yolunu kısaltır.
Paket hatalarında tanınan uzun yol, dosya kullanımda, erişim ve disk sorunları,
kurulum aşaması ve sayısal WinError ayrı gösterilir; özel yollar veya ham araç
çıktıları rapora eklenmez.

### Prod başlangıcında backend HTTPS hazır değil

Prod ASGI sunucusu sertifika ve özel anahtarla HTTPS açar; Manager
`https://<IPv4>:<port>/health/ready/` adresini aynı sertifikayla doğrular.
Eski raporlardaki `backend HTTP` etiketi protokol seçimi değildi; yeni
raporlarda prod için `backend HTTPS` yazılır.

Windows'un `2148204809` (`CERT_E_UNTRUSTEDROOT`) hatası, yerel sağlık kontrolünde
normal bir `CA:false` sunucu sertifikasının native TLS sağlayıcısının CA
listesinden düşmesiyle oluşabilir. Bu kontrol artık yalnız profilde seçilen ilk
PEM sunucu sertifikasına bağlı bir CPython/OpenSSL bağlamı kullanır. Süre ve IP
doğrulamasının ardından sunulan sertifika seçilen sertifikayla birebir eşleşmeden
HTTP isteği gönderilmez. CA tarafından imzalanmış yaprak sertifika da kökünü
Windows'a kurmadan bu yerel kontrol için kullanılabilir. Genel SSL sağlayıcısı,
paket indirme güveni ve Windows sertifika depoları değiştirilmez. Tarayıcıların
ve başka istemcilerin sertifika zincirine güvenmesi ayrı bir gerekliliktir.

Başlatma raporu TLS sertifika doğrulama kodunu, bağlantı reddini, bağlantı/yanıt
zaman aşımını (tek istek için 1 saniye) ve HTTP durumunu ayrı belirtir. HTTP 503
yanıtında yalnız bilinen veritabanı, önbellek ve frontend hazır olma sonuçları
aktarılır. Ham yanıt, sertifika ayrıntısı, özel adres/yol veya yönlendirme hedefi
rapora eklenmez. Proxy kullanmama, yönlendirmeyi izlememe ve TLS doğrulaması
korunur. Bu ayrıntı görülmeden aynı genel hatayı sertifika veya yavaş başlangıç
sorunu olarak varsaymayın.
