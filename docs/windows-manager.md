# AW Center Windows Manager

ZIP’in tamamını aynı klasöre çıkarın ve `AWCenterManager.exe` dosyasını açın. `backend`, `frontend`, `launcher.py` ve `_internal` EXE’nin yanında bulunur. Kaynak checkout’unda giriş noktası `AWCenterManager.pyw` dosyasıdır.

İlk açılışta **Local** veya **Prod** seçin. Seçim profilin formunu açar. **Geri** ile diğer profile geçebilirsiniz. Sonraki açılışta Manager son profili gösterir ve **Çalıştır** düğmesine basmanızı bekler.

## Profil ayarları

Local için başlangıç adresi `127.0.0.1`, backend portu `8000` ve frontend portu `5173` değerleridir. **Canlı yenileme** Django ve Vite’ın kaynak değişikliklerine tepkisini yönetir.

Prod için makineye atanmış IPv4 adresini ve HTTPS portunu kullanın. Varsayılan port `443` değeridir. Sertifika ve özel anahtar dosyalarını seçebilirsiniz. Dosyalar eksikse TLS oluşturma düğmesi seçtiğiniz IP için kendinden imzalı bir sertifika üretir. İstemci cihazların bu sertifikaya güvenmesi gerekir.

Her profil kendi `.env` dosyasını seçebilir. Seçili dosyadaki bağlantı değerleri formda görünür ve o dosya seçiliyken salt okunur olur. Örneğin `IPV4_ADDRESS` adresi, `PORT` Prod portunu, `DEV_FRONTEND_PORT` Local frontend portunu belirler. Dosya seçimini kaldırdığınızda elle girdiğiniz profil değerleri geri gelir. Manager seçilen dosyayı değiştirmez.

## Python ve paketler

Proje klasöründe hazır bir `.venv` varsa varsayılan ortam odur. Listeden kurulu bir CPython da seçebilirsiniz. Hazır ortamdan farklı bir yorumlayıcı seçildiğinde paket kurulumu o profil için ayrı bir sanal ortam hazırlar. Projenin CI’da sınanan Python sürümü 3.11.x’tir.

**Kaynaklar** bölümünde önce kurulu Python ve frontend paketlerini kontrol edebilir, sonra gerekirse kurulum başlatabilirsiniz. Çalıştır günlük kullanımda paket taraması veya kurulumu yapmaz.

| Mod | Gerekli bilgiler |
| --- | --- |
| Online | Genel PyPI ve npm depoları kullanılır. |
| Kurumsal | PyPI indeksinin ve npm registry’nin tam URL’leri, varsa tüm alt yollarıyla girilir. |
| Offline | Wheels klasörünü ve npm cache klasörünü ayrı ayrı seçin. Tam pakette bunlar `dependencies/wheels` ve `dependencies/npm-cache` altındadır. |

## Çalıştırma

Çalıştır ilk kez kullanılacak bir SQLite dosyası için yönetici kullanıcı adı ve parolasını ister, şemayı hazırlar ve sunucuyu başlatır. Mevcut bir veritabanını güncellemek için Local veya Prod profilinde **Sunucu → İsteğe bağlı ayarlar → Bekleyen migration’ları uygula** seçeneğini işaretleyip **Çalıştır** düğmesine basın. Seçenek varsayılan olarak kapalıdır ve her profil için ayrı kaydedilir. Bekleyen migration varsa Manager önce veritabanı ve özel dosyaların yedeğini doğrular. Migration veya son kontrol başarısız olursa sunucu ve worker’lar başlatılmaz.

Prod dağıtımında **Frontend’i derle** düğmesiyle statik arayüzü hazırlayın. **Gelişmiş ayarlar** altında Django dağıtım kontrolü, bekleyen migration kontrolü, statik dosyaları toplama ve frontend çıktısını doğrulama ayrı ayrı seçilebilir. Dördü de ilk kullanımda kapalıdır. Seçtiğiniz adım başarısız olursa başlatma durur ve hata ekranda gösterilir.

Bildirim worker’ı kuyruk tablolarına erişince açılış için hazır sayılır. Bekleyen bildirimler ve SMTP gönderimleri worker’da arka planda işlenir.

**Durdur** Manager’ın başlattığı sunucuyu ve worker süreçlerini kapatır. Terminalde kullanılan `launcher.py prod` kendi dağıtım kontrollerini çalıştırmaya devam eder.

## Windows paketi

Windows x64 üzerinde CPython 3.11 ve Tk ile repository kökünden `python scripts/build_manager.py --output AWCenterManager-windows-x64.zip` komutunu çalıştırın. Derleyici ZIP’i ve arşivin SHA-256 değerini içeren `.sha256` dosyasını üretir. Dosya bazında bütünlük manifesti ZIP’in içinde bulunur. Paketleme ve dağıtım doğrulamaları günlük Manager çalıştırmasından bağımsızdır.
