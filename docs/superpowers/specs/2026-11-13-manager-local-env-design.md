# Yerel Manager ve .env davranışı

13.11.2026 tarihinde kullanıcıyla soru-cevapla netleştirilen hedef.

## Amaç

Manager yalnız kullanıcının kendi bilgisayarındaki yerel SQLite kurulumunu
kolayca açıp yönetsin. Tek ana eylem **AW Center’ı aç** olsun. Mevcut Manager ve
launcher geliştirilecek; yeni bir yönetim uygulaması veya framework kurulmayacak.

## Kararlaştırılan davranış

1. Etkili ayar önceliği **dolu/açıkça seçilmiş Manager değeri > seçilen .env
   değeri > uygulama varsayılanı** olacak. Otomatik bulunan veya ekranda gösterilen
   değerler kullanıcı tarafından verilmiş override sayılmayacak.
2. Kaynak `.env` hiçbir zaman değiştirilmeyecek. Gerekirse birleştirilmiş çalışma
   yapılandırması ayrı, kullanıcıya özel bir kopyaya yazılacak. Bu kopya sonraki
   açılışta seçilmiş `.env` dosyasından daha yüksek öncelikli girdi olmayacak.
3. Manager'da açıkça verilen, gizli olmayan seçimler ortak hatırlanacak. `.env`
   değişse de aynı Manager seçimleri geçerli kalacak. Alanı temizlemek override'ı
   kaldırıp `.env` değerine dönmek anlamına gelecek.
4. `.env` içindeki veritabanı ve uygulama dosya/model yolları da boş Manager
   alanlarının yerine geçerli olacak. Dev ayarları Manager'ın sabit ürettiği
   değerlerle birebir eşit olmak zorunda olmayacak. Gerçek biçim/erişim hatası
   ilgili ayarla ve çözümüyle gösterilecek; değerler ve sırlar raporlanmayacak.
5. Eksik Python/frontend bileşenleri izinli kaynaklardan otomatik hazırlanacak;
   aynı ana eylem sunucuyu açmaya devam edecek. Günlük açılış tüm paket
   dosyalarının SHA-256 taramasına bağlı olmayacak. Kapsamlı denetim ayrı kalacak.
6. Var olan SQLite veritabanı sıfırlanmayacak. Gereken güvenli migration önce
   doğrulanmış yedek alınarak otomatik uygulanacak. Yarım veya tanınmayan geçiş
   otomatik veri değiştirme gerekçesi sayılmayacak.
7. Manager ve hazırlık işlemleri terminal açmayacak. İlk sunucu süreci
   başlatılırken tek terminal açılacak; sunucu/frontend/worker çıktıları orada
   görülebilecek. Terminali kapatmak sunucuyu ve ona ait worker'ları durduracak,
   Manager açık kalacak. İkinci kez açmak mükerrer sunucu oluşturmayacak.

## Uygulayıcının kararları

- Kaynak `.env` her açılışta yeniden okunacak; global override'ların kaynağı
  birleştirilmiş sonuçtan ayrı tutulacak. Secret içerik tercihlerde saklanmayacak.
- Takvim/tarih, oturum, CSRF ve worker sahipliği mevcut uygulama sözleşmesini
  koruyacak. Yerel varsayılan adres loopback olacak; dosyada açıkça verilen
  bağlantı değerleri birleşimin parçası olacak.
- Göreli database/artifact/model yolları mevcut Django davranışıyla uyumlu
  olarak `backend/` çalışma dizinine göre çözülecek; env dosyasının konumuna göre
  sessizce farklı veriye yönlendirilmeyecek.
- Yerel bağlantı için gereken originler etkili host/port ile uyumlu üretilecek;
  kullanıcının ek originleri korunacak. Diğer açıkça verilmiş uygulama URL'leri
  genel bir profil eşitliği kontrolüyle reddedilmeyecek.
- Dosyadaki anahtarlar esas alınacak. Manager kendi başına mevcut anahtarları
  yenilemeyecek; eksik anahtarların üretimi ve yeniden kullanımı doğru
  veritabanı/ortam kimliğiyle ilişkilendirilecek. Başka bir `.env`/veritabanının
  anahtarları yeni seçime yanlışlıkla taşınmayacak.
- PostgreSQL yönetimi bu yerel akışın kapsamında olmayacak. Production profilinin
  TLS, ayrı state ve deployment sözleşmeleri bu yerel sadeleştirmeyle değişmeyecek.

## Yaklaşım

Mevcut Manager'da tek bir ayar çözümleme adımı kullanılacak. Form girdileri,
dosyadan gelen değerler ve çalışma çıktısı birbirine karıştırılmayacak. Yeni
profil katmanları veya bağımsız bir başlatıcı yerine mevcut lifecycle, yedekleme
ve süreç sahipliği kullanılacak. Kayıtlı profili her ayarın otoritesi olarak
tutmak kullanıcının seçtiği öncelikle çeliştiği için sürdürülmeyecek.

## Kabul

- Manager alanı dolu/boş/temizlenmiş durumları ve değişen `.env` dosyaları doğru
  önceliği üretmeli; kaynak dosyanın byte içeriği değişmemeli.
- Eski üretilmiş çalışma kopyası yeni `.env` değerlerini bastırmamalı.
- Var olan SQLite ve anahtarlar korunmalı; migration öncesi yedek doğrulanmalı.
- Eksik bağımlılık, ilk kurulum, yeniden açılış ve dolu port gerçek yerel
  kullanıcı akışından sınanmalı; gereksiz hash veya kurulum tekrarı olmamalı.
- Windows'ta terminal çıktısı, Türkçe karakterler, terminalin kapatılması,
  Manager'ın açık kalması ve tüm sahipli süreçlerin bitmesi doğrudan sınanmalı.

## Mevcut ilerleme ve sınırlar

Yerel ayar önceliği, global açık Manager girdileri, kaynak dosyanın korunması,
SQLite anahtar kimliği, journal kurtarması ve paketli yeniden açılış çalışma
ağacında uygulanmıştır. 14.11.2026 yeniden denetiminde güncel repodaki açık
`managed`/`developer` politikasıyla birleştirilmiştir: hafif günlük açılış açık
kaynak seçimine bağlı geliştirici modundadır; yönetilen kullanım ve production
kapsamlı bütünlük kontrolünü korur. İkinci örtük bir hızlı yol kullanılmaz.

Geliştirici modunun korunması, kullanıcının değerlendirme yetkisi doğrultusunda
verilen uygulama kararıdır; kaynak üzerinde çalışma ile paketli kullanımın
birbirine karışmasını önler. Her iki politikada env önceliği aynıdır.

Son scripts doğrulaması: 1.183 test; 1.156 başarılı, 27 atlandı, hata yok.
Native Windows terminal görünürlüğü/kapatma ve NTFS kabulü bu macOS ortamında
yapılmadı. Commit veya push yapılmadı.
