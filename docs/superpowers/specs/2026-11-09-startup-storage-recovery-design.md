# Başlangıçta özel kurulum alanını güvenle hazırlama

Kullanıcı, Windows'ta `.pyw` ile açılışı engelleyen izin kalıtımını elle
düzeltti; aynı sınıftaki sorunların başlangıçta güvenle giderilmesini istiyor.
Bu istek mevcut kullanıcıya ait yönetilen kurulum klasörlerinin izinlerini
sıkılaştırmayı yetkilendirir. Salt okunur inceleme ve kullanıcı verisi aynı
otomatik düzeltme kapsamına girmez.

## Yaklaşım

Yalnız daha açıklayıcı hata vermek manuel müdahaleyi sürdürür. Bütün izin
hatalarını onarmak ise sahiplik ve erişim politikası sınırını bozar. Seçilen
dar çözüm, yalnız mevcut token kullanıcısına ait ve kalıtımı açık nesnelerin
DACL'ini mevcut tek-kullanıcı sözleşmesine sıkılaştırmaktır. Korunmuş ama
beklenmeyen ACL, başka sahip, bağlantı/reparse, çoklu hard link ve API hatası
otomatik geçilmez. Sahiplik değiştirilmez; okuma/onarım/doğrulama aynı Windows
dosya handle'ına bağlıdır. Sonraki `require_private` kontrolleri sürer.

İzin yazmadan önce handle'ın gerçek yolu, DOS uzun yol karşılığıyla eşleştirilir;
ata klasörün junction ile değiştirilmesi de reddedilir. Yeni işlem kilidi
`x+b` ile atomik oluşturulur; izin handle'ının volume/file ID'si açık kilit
descriptor'ıyla eşleşmelidir. Mevcut kilitler sahiplik yazmadan hazırlanır.
Yeni nesne oluşturmanın önceki token-sahiplik sözleşmesi korunur: elevated token'ın
varsayılan owner grubundan kullanıcı SID'sine geçiş yalnız initialization'da
kabul edilir; kalıtım kurtarması bu istisnayı kullanmaz.

Manager'ın açık başlatma/hazırlama eylemi, kayıtlı profil okunmadan önce ana
klasörü ve mevcut config/locks klasörlerini hazırlar; özel geçici alanda gerçek
yazma, fsync ve mevcut dosyayı atomik değiştirmeyi sınar. Dizin oluşturma her
yeni ara klasörü güvenli hale getirir ve eşzamanlı oluşturmayı yeniden doğrular.
Yalnız inert işlem kilidi dosyaları da kalıtım düzeltmesine uygundur.
Bilinen yönetilen kök altındaki mevcut ara klasörler de doğrulanır; kök dışındaki
mevcut LOCALAPPDATA/sistem klasörlerinin izinleri değiştirilmez.

Profil/env/veritabanı içeriği, çalışma zamanı hash doğrulaması, migration,
iptal ve gerçek kilit çakışması korunur. Doctor/inspect/sadece pencere açma
kurulum alanını değiştirmez. Ağ kaynak sınırları ve açık araç seçimleri korunur.
Yeni bağımlılık veya genel amaçlı bir kurtarma altyapısı eklenmez.

Windows FFI politikası portable API çiftleriyle, gerçek NTFS davranışı native
Windows testleriyle doğrulanır. macOS sonucu native Windows kabulü sayılmaz.
