# AW Center Manager için tek tıkla başlatma

## Uygulama hedefi

Windows kullanıcısı Manager’da **AW Center’ı aç** düğmesine bir kez bastığında seçili profilin sunucusu ve gerekli worker’lar hazır olsun, tarayıcı uygulamayı bir kez açsın. İlk kurulum yalnız eksik bileşenleri hazırlasın. Aynı kurulumun sonraki açılışı paket kaynaklarına başvurmadan, runtime arşivi açmadan, paket kurmadan ve frontend’i yeniden derlemeden tamamlansın. Kesintiden sonra doğrulanmış iş korunsun ve kullanıcı aynı düğmeyle devam edebilsin.

## Uygulayıcıya verilecek prompt

AW Center Manager ve launcher üzerinde çalışan kıdemli yazılım mühendisi olarak bu hedefi tasarla, uygula ve Windows’ta doğrula. Günlük kullanıcı Python ortamı, paket önbelleği, port veya worker yönetmek zorunda kalmadan uygulamasını açabilmeli. İlk kullanım, günlük açılış ve hatadan dönüş aynı ana eylemden geçmeli.

### 1. Bugünkü davranışı ölç

Önce `AGENTS.md`, `docs/windows-manager.md`, `AWCenterManager.pyw`, `scripts/manager/`, `scripts/launcher/` ve ilgili testleri oku. Commit edilmemiş düzenlemeleri de incele. Ana düğmeden tarayıcının açılmasına kadar çağrıları takip et. Doğrulanmış tam Windows paketi ile kaynak ağacından çalışan `.pyw` için ölçümleri ayrı tut. Paketli EXE kurulu Python olmadan açılabilir. Kaynaktan çalışan `.pyw` için arayüzü açacak uyumlu Python/Tk gerekir.

Aynı makine ve sürümde ilk açılışı, durdurup tekrar açmayı ve bağımlılık aşamasından sonra kesilen kurulumu kaydet. Her aşamanın süresini, paket kaynağına istekleri, indirilen baytı, arşiv çıkarma sayısını, `pip wheel/install`, `npm ci` ve frontend build çağrılarını say. Kullanıcıya gösterilen aşamayla gerçekten çalışan komutu karşılaştır. Her gecikmeyi veya duruşu karar veren kod ve tekrarlanabilir bir senaryoyla ilişkilendir.

İlk incelemede izlenecek üç somut yol var.

- `scripts/launcher/toolchain.py` içindeki `_install`, hazırlık sırasında yönetilen runtime arşivini geçici dizine açtıktan sonra mevcut hedefi denetliyor. Ayrıca `_trusted_inventory`, hazır ortamı doğrularken arşiv üyelerini okuyup SHA-256 hesaplıyor. Diske çıkarma ile sıkıştırılmış içeriği bellekte tekrar açma maliyetini ayrı ölç. İyileştirme sabitlenmiş katalogdan gelen bütünlük kanıtını korusun. Yerelde değiştirilebilir bir kurulum kaydını tek güven kaynağı yapma.
- `scripts/launcher/installation_dependencies.py` içindeki `install_dependencies`, tamamlanmış aşama kaydına bakmadan önce “bağımlılıklar hazırlanıyor” bildiriyor. Kurulan, doğrulanan ve yeniden kullanılan içeriğin ekranda doğru fiille gösterildiğini sına.
- `scripts/manager/ensure.py` içindeki `needs_preparation` ve `scripts/launcher/installation.py` içindeki `_core_checks` başlatma kararını veriyor. Geliştirme profilindeki frontend kontrolü `node_modules/.package-lock.json` varlığına bakıyor. Kaynak lock dosyası değiştiğinde veya kurulu çıktı eksildiğinde kararın doğru aşamaya yöneldiğini doğrula. Kilit alınmadan önceki gözlemle kilit altında yeniden doğrulamanın ayrı amaçlarını koru.

### 2. Her açılışta gereken işi seç

Mevcut `ensure` akışını, süreç kilitlerini, kurulum kayıtlarını ve paket önbelleğini kullan. Her aşama için girdileri, başarı kanıtını, hangi değişikliğin onu geçersiz kıldığını ve kesilirse nereden devam edileceğini tanımla. Bu kararlar hem uygulamayı hem kullanıcıya gösterilen durumu beslesin.

| Gözlenen durum | Ana düğmenin sonucu |
| --- | --- |
| İlk yerel kurulum | Uyumlu araçları bul, eksikleri izinli kaynaktan edin, kilitli bağımlılıkları kur, profili ve veritabanını hazırla. İlk aktif yönetici eksikse bilgileri bir kez al ve aynı işlemde açılışa devam et. |
| Kurulu ve durmuş | Kurulumun seçili sürümle uyumunu ve zorunlu başlangıç koşullarını doğrula. Doğrudan sunucu ve worker’ları başlat. |
| Zaten sağlıklı | Seçili profile ait adresi aç. Tekrarlanan tıklama ve aynı anda başlayan ikinci işlem ikinci bir kurulum, sunucu veya worker oluşturmasın. |
| Önceki işlem kesildi | Tam ve doğrulanmış adımları kullan. Sonuçları belirsiz adımı denetle ve güvenle devam edilebilen ilk noktadan sürdür. |
| Bir girdi değişti | Girdiyle ilişkili adımları yeniden değerlendir. Örneğin yalnız port değiştiğinde bağımlılıklar hazır kalmalı, yalnız frontend lock dosyası değiştiğinde Python kurulumu hazır kalmalı. |
| Kullanıcı müdahalesi gerekli | Hangi bileşenin neden durduğunu, kullanıcının yapacağı tek düzeltmeyi ve devam eylemini aynı yerde göster. Geçerli ayarları ve tamamlanmış işi koru. |

İndirilmiş dosya, kurulmuş bağımlılık ve çalışır servis için ayrı kanıt kullan. Önbellek kimliğinde kilit dosyası, hedef runtime/platform ve izinli kaynak politikası dikkate alınmalı. Yarım indirmeleri tamamlanmış olarak yayımlama. Uygun bütünlük kanıtı varsa tamamlanmış indirmeleri sonraki denemeye taşı. Eski kurulumda kayıt eksikse güvenle doğrulanabilen çıktıdan yararlan. Bozulmuş veya kaynağı belirsiz içeriğin üzerine sessizce yazma. Kurulu bileşenin güvenilir olduğunu yalnız klasörün varlığından veya önceki başarılı açılıştan çıkarma.

### 3. Varsayılanları, ayarları ve hata anını tasarla

- Varsayılan deneyim mevcut yerel `dev` profili ve loopback erişimi olsun. Manager penceresi açıldığında salt okunur durum incelemesi yapılsın. Kurulum ve başlatmayı **AW Center’ı aç** başlatsın. Otomatik araç seçiminde kullanılabilir sistem Python ve Node kurulumlarını tercih et. Elle seçilmiş araç yolu geçersizse o alanı göster. Eksik bileşenlerin ediniminde tam dağıtım paketindeki doğrulanmış yerel içerik öncelikli olsun. Paket bulunmayan kaynak kurulumunda yalnız seçili modun izin verdiği kaynaklardan eksikler edinilsin.
- İlk ekranda seçili profil, temel eylem, mevcut aşama ve sonuç görünsün. Profil, kaynak, Python/Node yolu, port, kurumsal CA, TLS ve ortam dosyası gelişmiş ayarlardan yönetilebilsin. Kurumsal proxy için mevcut ortam yapılandırmasını kullan. Açık bir seçimi uygula, kaydet ve aynı kurulum bağlamında bir sonraki açılışta kullan. Eksik alan gerekiyorsa doğrudan o alanı göster.
- Yeni üretim profilinde makineye atanmış sabit IPv4 ve kaynak ağacı dışında geçerli TLS sertifikası/anahtarı gerekir. Kullanıcıdan edinilmesi gereken eksikleri pahalı işlemlerden önce birlikte göster. Kayıtlı geçerli profil bu bilgileri tekrar istemeden açılsın. Yerel profilin otomatik portu doluysa boş port seç. Elle seçilmiş veya üretim portundaki çakışmayı ilgili ayarda göster.
- Geçici erişim hatalarında süre ve deneme sayısı sınırlı olsun. İzin verilen alternatif başarılı olursa normal akış sürsün. Kalıcı bir engelde örneğin “Üretim sertifikası kayıtlı konumda bulunamadı. Sertifika seç” gibi nedeni ve eylemi birlikte bildir. Gerçek ilerlemeyi “yerel kopya doğrulanıyor”, “indiriliyor”, “kuruluyor” veya “worker bekleniyor” olarak ayırt et. Tekrarlanan uyarı pencerelerini kaldır. Rapora yalnız güvenle paylaşılabilen hata kodunu, süreyi ve işlem bilgisini yaz.
- Güvenli kurtarma mevcut sahiplik ve kilit sınırları içinde çalışsın. İptal veya çökmede yalnız Manager’ın sahip olduğu süreçleri kapat. Veritabanı, hesaplar, özel dosyalar, anahtarlar ve önceki iş çıktıları korunsun. Mevcut tanınan veritabanına migration öncesi doğrulanmış yedek al. Yarım veya bilinmeyen migration’ı yeniden çalıştırmadan önce mevcut durum için güvenli kararı ver.
- Üretimde TLS, `check --deploy`, bekleyen migration kontrolü, `collectstatic`, `verify_frontend_artifact` ve worker sağlık kapılarını koru. Paket kaynağı için kurumsal ve çevrimdışı sınırları uygula. İsteğe bağlı bir entegrasyonun eksikliği yalnız o özelliği etkiliyorsa ana uygulamayı aç. Tarayıcıyı ancak profilin gerçek HTTP/HTTPS hazır olma kontrolü ve gerekli worker kontrolleri geçince aç.

### 4. Kabulü gerçek kullanıcı yolundan kanıtla

| Senaryo | Başarılı sayılma ölçütü |
| --- | --- |
| Temiz Windows x64, standart kullanıcı, tam EXE/ZIP, dış ağ kapalı | Kurulu geliştirici araçları olmadan tek ana eylemle yerel uygulama açılır. İlk yönetici dışında teknik alan veya yeniden deneme istenmez. |
| Kaynak ağacı, çalışan Python/Tk, boş önbellek, tam offline paket yok | Varsayılan otomatik seçimle izinli kaynaktan gerekli edinimler gerçekleşir. Aynı sürümde sonraki açılış dış ağ kapalıyken başarılı olur. |
| Hazır dev ve önceden yapılandırılmış prod, durdur/aç | Her profilde art arda üç açılışta **0 paket kaynağı isteği, 0 paket indirme, 0 runtime arşivi çıkarma, 0 pip kurulumu, 0 npm ci, 0 frontend build ve 0 teknik istem**. Tarayıcı her başlatmada hazır olduktan sonra bir kez açılır. |
| Edinimden sonra iptal, kurulum ortasında kapanma, worker başlangıcında hata | Her kesintiyi ayrı üret. Tekrar açınca tamamlanmış edinimler korunur, doğrulanmış aşamalar yeniden kurulmaz, yetim süreç veya ikinci worker kalmaz. |
| Tek girdide değişiklik, eksik çıktı, eski kayıt, bozuk paket | Yalnız etkilenen aşama yeniden çalışır veya bütünlük sorunu doğru bileşende açıkça bildirilir. Önbellekteki bozuk dosya çalıştırılmaz. |
| Çevrimdışı pakette eksik dosya veya erişilemeyen kurumsal depo | Eksik bileşen ve gerekli düzeltme görünür. Sayaçlar çevrimdışı modda dış paket kaynağına sıfır istek, kurumsal modda izin verilmeyen genel kaynaklara sıfır istek gösterir. |
| Dolu port, eksik TLS, disk dolu, geçici ağ kesintisi ve eşzamanlı ikinci açılış | Güvenli otomatik çözüm varsa aynı işlem tamamlanır. Müdahale gereken senaryoda tek bir somut düzeltme gösterilir. Düzeltildikten sonra doğrulanmış aşamalar korunur. |
| Uygulama kullanılabilirliği | Gerçek kullanıcı oturumu açılır, frontend yüklenir, küçük bir iş worker’da tamamlanır ve yetkili kullanıcı çıktıyı indirir. Yeniden başlatınca hesap ve çıktı korunur. |

Önce doğruladığın her sorun için davranışı yakalayan regresyon testi yaz. İlgili Manager/launcher testlerini, repository kapılarını ve `.github/workflows/manager-windows.yml` içindeki paketli Windows kabulünü çalıştır. Tam paketteki yerel wheel ve npm içeriği kullanılmış bir testi, kaynaktan ağ üzerinden ilk kurulum kanıtı olarak raporlama. Sonuçta aynı Windows sürümü ve paket kimliği için önce/sonra sürelerini, işlem sayaçlarını, kullanıcı istemlerini ve kalan engelleri paylaş. Windows’ta çalıştırılamayan senaryolar kabul tablosunda açık kalsın.
