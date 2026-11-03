# AW Center Windows masaüstü yöneticisi

Taşınabilir paket Windows x64 içindir. ZIP'in tamamını kullanıcıya ait yerel bir dizine çıkarın ve `AWCenterManager.exe` dosyasını açın. İlk pencere için kurulu Python, Node, npm, Git veya ağ bağlantısı gerekmez. Python/Tk arayüzü `_internal/` içinde; uygulama kaynakları `source/`, SHA-256 değerleri onaylı Python 3.11, Node ve npm arşivleri `runtimes/` içindedir. Bu dizinleri EXE'den ayırmayın.

Pencerenin açılması uygulamanın kurulduğu veya servisin hazır olduğu anlamına gelmez. Durum ve ilerleme gerçek kurulum, HTTP ve worker kontrollerinden gelir. İlk kurulumun Python ve frontend bağımlılıkları için erişilebilir paket kaynakları gerekir. Runtime arşivleri, uygulamanın tüm bağımlılıklarının çevrimdışı kopyası değildir.

## Sade yönetim ekranı

**Çalışma (Ctrl+1)** sekmesi seçili işlemin durum özetini, çalışma profilini,
kaynak dizinini, host ve backend portunu gösterir. **Başlat**, **Kur ve başlat**
ve **Durumu denetle** burada bulunur. **Gelişmiş ayarları göster** ile frontend
portu, TLS dosyaları, isteğe bağlı Python kurulumu, `.env` seçimi ve migration
seçeneği açılır. Bu bölümü kapatmak girilen değerleri silmez. Üretim profili
seçildiğinde veya kapalı bölümdeki bir alan doğrulama hatası verdiğinde bölüm
otomatik açılır.

**Paket kaynakları (Ctrl+2)** kaynak politikasını, ilgili dizin ve depoları,
**Kaynakları dene** ve **Çevrimdışı paket hazırla** işlemlerini içerir.
**Durum ve rapor (Ctrl+3)** seçili işlemin temizlenmiş raporunu gösterir.
Sekmelerin altındaki işlem listesi ve **Seçili işlemi durdur** düğmesi tüm
sekmelerde erişilebilir. Bir işlemi seçip **Raporu incele**, Enter veya çift
tıklama ile raporuna geçebilirsiniz.

Küçük pencerede, büyük sistem fontunda veya hata gösterildiğinde işlem listesi
başlık satırına küçülür; **Listeyi göster** ile tekrar açılabilir. Görevler ve
seçim korunur. Hata kartı kısa özet gösterir; **Çözümü incele** tam hata, çözüm
ve hata kodunu içeren raporu açar. Yeniden deneme kısayolu **Ctrl+R** olarak kalır.

Durum özeti formdaki profil seçiminden bağımsızdır; yalnız seçili görevin
kayıtlı profilini ve controller tarafından bildirilen durumunu gösterir.
Henüz işlem yokken uygulama çalışıyor gibi gösterilmez. Arayüz mevcut
Tkinter/ttk üzerinde onaylanan Sade yönetim örneğinin açık/koyu paletini,
yuvarlatılmış kartlarını, çizgi sekmelerini ve yan yana bağlantı alanlarını
kullanır. İlk görünüm sistemin açık/koyu yüzeyinden çözülür; kontroller standart
ttk bileşenleri olarak kalır. Windows'un yerel düğme çizimi özel renkleri
yok sayabildiğinden paint edilebilir standart Clam elemanları kullanılır;
ek GUI bağımlılığı gerekmez. Sistem fontu, görev seçimi ve klavye kısayolları korunur.

## İsteğe bağlı Python kurulumu

Çalışma sekmesindeki **Python çalışma zamanını kur (isteğe bağlı)** kutusu varsayılan olarak seçili değildir. Seçilmezse Manager mevcut CPython, `py -3.11`, PATH ve Windows Python kayıtları üzerinden tam **CPython 3.11 x64** arar. `venv` ve `ensurepip` desteği de doğrulanır. Uygun Python bulunmazsa açık uyarı verir; kendi kendine Python kurulumuna geçmez. Store yürütme alias'ı başlatılmaz; Python launcher'ın otomatik kurulum seçeneği de sorgu sürecinde kapatılır. [Python Windows launcher ayarları](https://docs.python.org/3/using/windows.html) bu davranışın ortam seçeneklerini açıklar.

Kutu seçilirse paketteki veya seçilen kaynaklardaki SHA-256 sabitlenmiş yönetilen Python kullanılır. Bu seçim Node/npm hazırlığından ayrıdır. Her iki durumda da uygulamanın kilitli pip paketleri proje `.venv` dizinine kurulur; sistem Python paketleri değiştirilmez. Sistem modu işletim sistemindeki mevcut Python'a güvenir, onun dosyalarına yönetilen arşivin hash pinini uygulamaz.

Başarılı bağımlılık hazırlığından sonra seçilen sistem yorumlayıcısı dev/prod profil metadata'sına ayrı ayrı kaydedilir; Başlat ve Kontrol et aynı seçimi kullanır. Özel env, anahtarlar ve mevcut hesaplar değişmez. Mevcut `.venv` farklı bir Python'a bağlıysa Manager onu otomatik silmez veya yeniden bağlamaz; ayrı temiz kaynak dizini kullanın ya da mevcut ortamın Python seçimini koruyun. Profil değişimi sonradan sistem Python'unu kaldırmaz veya güncellemez.

Offline paket üretiminde üreticinin seçtiği Python kullanılabilir; taşınabilir çıktı, başka bilgisayarda isteğe bağlı yönetilen kurulum için Python arşivini içermeye devam eder. Kaynak `.pyw` dosyasını çalıştırmak için Python/Tk gerekir; paketli EXE'nin ilk penceresi kendi gömülü Python/Tk'sini kullanır. Mevcut düşük seviyeli CLI akışının yönetilen Python varsayılanı korunur; kayıtlı sistem profiliyle Başlat sistem yorumlayıcısını kullanır.

## .env dosyası seçimi

Çalışma sekmesindeki **.env dosyası (isteğe bağlı)** alanının **Seç…** düğmesiyle kendi dosyanızı seçebilirsiniz. Boş bırakılırsa mevcut profil kullanılır; yeni profilde varsayılan özel yapılandırma üretilir. Seçilen dosyanın yolu görev seçeneklerine alınır; içeriği arayüz veya rapora aktarılmaz.

**Kur ve başlat**, literal `KEY=value` biçimindeki dosyayı doğrular ve ayarlarını `%LOCALAPPDATA%\AWCenter\config\dev.env` veya `prod.env` içindeki owner-only kopyaya aktarır. Kaynak dosyanın içeriği ve izinleri değiştirilmez. Kaynak dosyanızın izinlerini ayrıca koruyun; uygulama yalnız özel profil kopyasını kullanır. UTF-8/BOM desteklenir; yinelenen anahtar, symlink/junction, normal dosya olmayan yol, geçersiz sözdizimi veya 128 KiB üzeri dosya reddedilir. Shell komutu/variable interpolation yapılmaz; süreç başlatma ve başka env dosyasına yönlendirme ayarları kabul edilmez.

Mevcut profilin `SECRET_KEY` / `JIRA_SESSION_ENCRYPTION_KEY` değerleri değiştirilemez. Profilin ayrı veritabanı, özel dosya ve bind/model yollarıyla çelişen ayarlar reddedilir; dosyadan bu alanları çıkarmak mevcut güvenli değerleri korur. İlk kez eski bir geliştirme veritabanı açıkça sahiplenilecekse seçilen dosya her iki özgün anahtarı da içermelidir; veritabanı resetlenmez. Production için seçilen dosya kaynak ağacının dışında olmalıdır. İlk kurulumda eksik anahtarlar yalnız yeni/boş ortam için oluşturulur.

**Başlat** ve **Durumu denetle** salt okunur davranır. Alan boşken kayıtlı profil kopyasını kullanırlar. Dosya seçiliyse aynı ayarlara karşılık geldiğini doğrularlar; farklı ayarlar varsa bunları önce **Kur ve başlat** ile uygulamanız istenir. Bu seçim, iki profilin aynı state veya anahtarları paylaşmasına izin vermez.

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
| Kurumsal | Yalnız seçilen kurumsal HTTPS veya yerel kaynaklar; genel internete fallback yok |
| Çevrimdışı | Yalnız seçilen yerel doğrulanmış paket dizini; ağ indirmesi yok |

Python index adresi, npm registry adresi ve runtime arşiv deposu ayrı alanlardır. Kurumun CA dosyasını gerektiğinde seçin; TLS kontrolü kapatılmaz. URL'ye kullanıcı adı, parola veya token koymayın. Kurumsal proxy yapılandırması işlemin ortamından gelebilir; ham paket yöneticisi çıktıları arayüze veya rapora aktarılmaz.

Çevrimdışı kurulum için Windows x64 ve mevcut dependency lock'larıyla hazırlanmış kurulum paketi gerekir. Paket içindeki dependency manifest'i, Python wheel'leri ve npm cache doğrulanır. Yönetici üzerinden paket hazırlama işlemi, erişebilen bir Windows makinede mevcut kurulum bundle akışını kullanır. Yalnız `runtimes/` dizinini seçmek çevrimdışı uygulama kurulumunu tamamlamaz.

## İşlemler ve ilk yönetici

Hazırlama işlemi özel profili oluşturur, onaylı runtime'ları açar, kilitli bağımlılıkları kurar, şemayı ve ilgili build/deployment kapılarını doğrular, ardından uygulamayı başlatır. Başlat mevcut hazırlanmış profili kullanır. Kontrol et salt okunur tanılama yapar. Kaynak testi seçilen politikanın erişimini veya yerel bağımlılık envanterini inceler; paket kapsamının tamamı kurulum sırasında doğrulanır.

İlk aktif yönetici bulunmadığında kullanıcı adı ve parola ayrı, maskeli parola alanı olan pencerede istenir. Kullanıcı adı bir harf ve beş rakamdır. Bilgiler yalnız worker'ın özel stdin kanalıyla aktarılır; argv, environment, kaynak dosyası veya rapora yazılmaz. Mevcut kullanıcılar değiştirilmez veya yöneticiye yükseltilmez.

Durdur yalnız görev listesindeki seçili işlemi ve onun alt süreçlerini durdurur. Pencereyi kapatmayı onaylamak tüm aktif işlemlere iptal gönderir ve süreç temizliğinin bitmesini bekler. Devam eden migration güvenli komut sınırında durur; tamamlanan kurulum adımları korunur. Hata sonrası gösterilen aşamayı ve çözüm bilgisini inceleyip aynı işlemi tekrar çalıştırın. Özel profili veya veritabanını silmek bir kurtarma adımı değildir. Rapor yalnız temizlenmiş durum bilgisidir.

## Modüller ve bağımsız işlemler

Arayüz (`view.py` / `view_model.py`), görev yönetimi (`controller.py` / `task_policy.py`), özel süreç iletişimi (`transport.py` / `worker.py`) ve işlem yürütme (`operations.py` / `source_checks.py`) ayrıdır. İlk pencerenin kaynak yolu yalnız hafif `paths.py` modülünden gelir; paket hazırlama modülünün yüklenmesi gerekmez. Yeni bir job framework veya bağımlılık eklenmez.

Her işlem ayrı işletim sistemi sürecinde çalışır. Bu, launcher'ın process environment bağlamlarının farklı profillerin anahtarlarını veya araç yollarını karıştırmasını önler. Görev kimliği, seçeneklerin başlangıç anındaki kopyası, olay kutusu, durum, rapor ve iptal kanalı işlem başına ayrıdır. Formu sonradan değiştirmek çalışan görevi değiştirmez. Bir görevin hatası veya iptali diğer görevlere uygulanmaz.

Göreli dosya yolları görev başlarken kaynak çalıştırmada repository kökü, paketli çalıştırmada EXE klasörü esas alınarak mutlak yola çevrilir. Aynı mutlak yollar hem çakışma kontrolüne hem worker'a gönderilir; `~` mevcut kullanıcının home dizinini ifade eder. Böylece aynı çıktı dizininin farklı yazılışları iki ayrı hedef sayılmaz.

| Eşzamanlı işlemler | Davranış |
| --- | --- |
| Çalışan uygulama + kaynak testi / durum kontrolü | Birbirinden bağımsız çalışır. |
| Çalışan uygulama + offline paket hazırlama | Doğrulanmış mevcut araçları okuyarak, ayrı staging/cache/çıktı alanında çalışır; canlı `.venv` değiştirilmez. |
| Hazır dev + hazır prod başlatma | Ayrı profil ve state ile çalışabilir; mevcut port ve tek DOORS worker kontrolleri korunur. |
| Aynı profilin iki lifecycle işlemi | İkinci işlem açık çakışma mesajıyla reddedilir. |
| Kurulum + çalışan lifecycle / başka kurulum | Kaynak, profil veya paylaşılan runtime yazmalarının çakışması engellenir. Kurulum uygulamayı hazır ilan edince yalnız çalışan sunucu kaynaklarını tutar. |
| İç içe veya aynı çıktı dizinine iki paket | Dosya çakışması açıklanır; bekleme kuyruğuna alınmaz. |

Görev listesinde kısa işlem kimliğini seçerek o işlemin durumunu ve raporunu görüntüleyin. İlk yönetici penceresi modal değildir; açıkken diğer işler izlenebilir, başlatılabilir veya durdurulabilir. Kaynak/alan doğrulamaları yalnız ilgili işlemin kullandığı seçeneklere uygulanır.

Tk iş parçacığında ağ erişimi, süreç bekleme, pipe yazma veya tarayıcı başlatma yapılmaz. Özel pipe yazıcısı ve sınırlı mesaj kuyruğu işlem başınadır. Tk her görevden sınırlı sayıda olay okur; yoğun bir görev diğerlerinin ilerleme veya kapanış olaylarını aç bırakmaz. En fazla 16 aktif işlem ve son 50 tamamlanmış görev tutulur. `done` bildirimi kaynakları erken serbest bırakmaz; sahip olunan süreç temizliği de tamamlanmalıdır.

Kaynak paylaşan işlemlerin güvenlik nedeniyle çakışması ile arayüzün kilitlenmesi farklı durumlardır. Python olmadan migration veya aynı veritabanı üzerinde eşzamanlı kurulum yapılmaz; gerekli sıralama ve transaction sınırları korunur. Ayrı Manager pencereleri arasındaki mevcut işletim sistemi kurulum kilidi de geçerlidir.

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
manager-manifest.json
```

Kaynak seçimi mevcut `copy_install_source` güvenlik filtresini ve Git tracked envanterini kullanır. Yeni yönetici modülleri ve ilk yönetici servisi yalnız açık dosya allowlist'iyle eklenir. Yerel environment, credential, private state, dependency cache ve bilinmeyen kök dosyalar dağıtılmaz. `runtimes/` yalnız repository'deki onaylı katalogda bulunan Python, Node ve npm arşivlerini içerir; katalogdaki SHA-256 değerleri kopyalamadan sonra yeniden doğrulanır.

Runtime arşivleri için build komutu `--source-mode online|corporate|offline`, `--repository`, `--offline-dir` ve `--ca-file` alır. Bu seçenekler PyInstaller build bağımlılıklarının pip kaynağını değiştirmez; build ortamının paket/proxy/CA yapılandırması ayrıca sağlanmalıdır. [PyInstaller dağıtım dokümantasyonu](https://pyinstaller.org/en/stable/) Windows çıktısının Windows üzerinde üretilmesini gerektirir. PyInstaller build aracıdır; Python, Tcl/Tk ve paket içindeki runtime'ların lisans koşulları dağıtım sürecinde korunmalıdır.

## Doğrulama ve mevcut sınır

`.github/workflows/manager-windows.yml` CMD ile Windows üzerinde ZIP üretir ve çıkarılmış EXE'yi çalıştırır. Native kabul testleri:

- PATH'ten Python, Node, npm ve Git çıkarılmış, ağ proxy'si erişilemez bir ortamda gerçek ilk Tk penceresi;
- paketli worker'ın özel pipe bağlantısı ve açık Kurumsal/Çevrimdışı kaynak seçimleri;
- kurulu araç bulunmadan gerçek Online geliştirme kurulumu, ilk yönetici, HTTP hazır olma ve Durdur sonrası frontend/backend süreçlerinin kapanması.

Online kabul ayrıca aynı özel profili yeniden başlatır; mevcut yönetici korunur, private environment dosyasının SHA-256 değeri değişmez ve yeniden başlatma ağ erişimi kapalıyken tamamlanır. Üretilmiş kaynak durumu asıl taşınabilir paket altında bırakılmaz; test ayrı, doğrulanmış kaynak kopyası kullanır.

```bat
set AWCENTER_RUN_MANAGER_WINDOWS_SMOKE=1
set AWCENTER_MANAGER_EXE=C:\AWCenterBuild\extracted\AWCenterManager.exe
py -3.11 -m unittest scripts.test_manager_package.NativeWindowsPackageTests
```

Tam soğuk çevrimdışı kurulum kabulü ayrıca hazırlanmış, onaylı bir bundle gerektirir. `AWCENTER_RUN_MANAGER_OFFLINE_SMOKE=1` ve `AWCENTER_MANAGER_OFFLINE_BUNDLE=<bundle dizini>` tanımlanınca aynı native test sınıfı erişilemeyen proxy'lerle bu akışı da çalıştırır. Varsayılan workflow bu ek offline bundle'ı üretmez; bu kabul açıkça skip edilir.

Bu testler runtime ve bağımlılık indirebilir, geçici doğrulanmış kaynak kopyasında geliştirme ortamı oluşturabilir ve yalnız testin geçici uygulama-data dizininde profil oluşturur. Gerçek kullanıcı profiliyle çalıştırmayın. Normal unittest çalışmasında native testler açıkça skip edilir.

02.11.2026 tarihinde macOS üzerindeki kaynak ve paket kontratı testleri çalıştırılabilir; bu ortam Windows EXE üretemez ve Windows/Tk/NTFS/native worker kabulünü kanıtlayamaz. İlk yayın için Windows workflow sonucunu ve üretilen ZIP üzerindeki kabul sonuçlarını inceleyin. Native smoke, üretim TLS kurulumu veya elle yapılan görsel/erişilebilirlik kabulünün yerine geçmez. Bu değişiklik otomatik yayın veya imzalama yapmaz.
