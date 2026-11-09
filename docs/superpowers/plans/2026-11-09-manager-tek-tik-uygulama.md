# Manager tek tıkla başlatma uygulama planı

**Hedef** — Sağlam bir ortamı doğrudan başlatmak, kesintiden sonra yalnız eksik aşamayı çalıştırmak ve gerçek Windows kabulünde bu iki kararı ayırt etmek.

**Tasarım** — [Uygulama promptu](../specs/2026-11-09-aw-center-manager-tek-tik-promptu.md). Mevcut Tk arayüzü, Manager worker'ı, `ensure`, launcher kilitleri, SHA-256 doğrulaması ve kurulum kayıtları kullanılacak. Kullanıcının çalışma ağacındaki devam eden paket kaynağı ve Windows izin düzeltmeleri korunacak.

## Uygulama sırası

1. **Yönetilen runtime** — `scripts/launcher/toolchain.py` içinde aynı arşivle iki hazırlığı bir testte çalıştır. İlk kurulumdan sonra yeniden hazırlamada diske çıkarma sayısını sıfıra indir. Arşiv, kurulu dosya veya npm wrapper değiştirilirse doğrulamanın hata verdiğini test et.
2. **Kurulu bağımlılıklar** — `scripts/launcher/installation_dependencies.py`, `scripts/manager/inspection.py` ve `scripts/manager/ensure.py` ile karar veren ve kuran kodu aynı kanıta bağla. Kaynak lock değişimi, silinmiş çıktı, tamamlanmamış kurulum, eski kayıt, iptal ve değiştirilmiş dosya için ayrı test kullan. Doğrulamadan önce kurulum bildirimi veya paket edinimine özgü hazırlık başlatma.
3. **Başlatma ve ayar değişikliği** — Yeni prod profili için eksik IPv4/TLS alanlarını kaynak hazırlığından önce bir arada göster. Kayıtlı bağlantı ayarı değiştiğinde, kilit altında diğer gereksinimleri yeniden değerlendir. Her şey hazırsa paket/üretim build aşamasına girmeden başlat. Yarım kalmış üretim frontend çıktısını tespit et. Zorunlu prod kontrolleri ve otomatik migration yedeği sürsün.
4. **Windows kabulü** — `scripts/test_manager_windows_acceptance.py` ve `.github/workflows/manager-windows.yml` içindeki mevcut paket, TLS, oturum, worker ve yetkili indirme senaryolarını kullan. Her dev/prod profili için aynı kurulumda arka arkaya üç ana eylemin hazır kurulum dalını kullandığını ölç. Kaynak ağacı ilk kurulumu ile tam paket çevrimdışı ilk kurulumunun kanıtlarını ayır.
5. **Doğrulama** — Hedefli regresyonları, tüm Manager/launcher testlerini, `launcher.py check` ve `launcher.py test` kapılarını çalıştır. Üretim frontend build, geçici statik alanda collectstatic/artifact ve Windows'a özel doğrulamaları ayrı kaydet. Çalıştırılacak Windows işlerinin aynı kaynak revizyonunu içermesi gerekir.

## İncelemede özellikle aranacak durumlar

- Kilit öncesi gözlemden sonra başka bir işlem profili değiştirebilir.
- Geçerli bir kurulum kaydı sonradan değiştirilmiş runtime'a güven vermemeli.
- Yalnız port değişikliği yapılırken aynı anda bağımlılık veya şema değişmiş olabilir.
- Kapanma anında profil ve yönetici hazırken frontend build henüz tamamlanmamış olabilir.
- Ağ kısıtlı testlerin sonucunda hangi kaynakların ve hangi giriş noktasının kullanıldığı görünmeli.

## Uygulama ve doğrulama kaydı

| Adım | Sonuç |
| --- | --- |
| Yönetilen runtime | Resmî arşiv SHA-256 değerlerine bağlı kurulu dosya özetleri doğrulandı. Tekrar hazırlıkta Python, Node ve npm için arşiv indirme, diske çıkarma ve arşiv üyelerini yeniden okuma atlanıyor. Kesilen kayıt yazımı doğrulanmış ağacı kullanılabilir bırakıyor. |
| Bağımlılıklar | Kurulum kaydı ve kaynak lock dosyası kararı belirliyor. Gerçek dosyalar doğrulanmadan Django incelemesi çalıştırılmıyor. Eski veya yarım ortam yedekte korunuyor. Aynı lock ve sağlam çıktılarla paket yöneticileri ve paket bağlantısı hazırlığı çağrılmıyor. |
| Manager ana eylemi | Açılış incelemesi sürerken düğmeye basılabiliyor. Bağlantı değişikliği, eşzamanlı durum değişimi ve otomatik port yarışı ayrı ele alınıyor. Yeni üretim profilindeki eksikler tek seferde gösteriliyor. TLS yolları doğrulanmadan kaydedilmiyor. |
| Üretim arayüzü | Başarılı build ve deployment denetimlerinden sonra tüm `dist` dosyaları için atomik kayıt üretiliyor. Eksik lazy chunk ve kayıtsız eski sürüm yeniden derleniyor. Önceki çıktı yedekte kalıyor. İlk kurulum kaydı olmayan üretim ortamında bu bir defalık ek derleme gerektiriyor. |
| Native kabul | Kaynaktan `.pyw` ilk açılışı için bağımsız Windows işi ve paketli dev/prod için üç ardışık Tk düğmesi/EXE worker açılışı kodlandı. Bu çalışma ağacı için Windows sonuçları bekleniyor. |

Gerçek Windows x64 runtime arşivlerinin tek macOS ölçümünde tekrar hazırlık
4,73 saniyeden 0,91 saniyeye düştü. Üç arşivin diske çıkarılması ve üç
arşivin içerik okuması sıfıra indi. Bu ölçümde sürüm sorguları simüle edildi.
İşletim sistemi, kullanıcı hesabı, antivirüs ve disk etkileri için toplam
Windows açılış süresi ayrıca ölçülmeli.

- `launcher.py check`, `launcher.py test` ve `launcher.py prod --help` geçti.
  Tam test kapısı 1.415 Django testini, 62 launcher/release testini ve frontend
  testlerini çalıştırdı.
- Tam launcher keşfinde 548 testin 17’si, Manager keşfindeki 358 testin 9’u
  platform veya isteğe bağlı ortam koşulu nedeniyle atlandı. İki grup da geçti.
  Son küçük profil korumasından sonra 66 ilgili test ayrıca geçti.
- Frontend build/bütçe kontrolü, geçici statik dizinde `collectstatic` ve
  42 giriş varlığıyla `verify_frontend_artifact` geçti. Katalogdaki üç gerçek
  runtime arşivinin envanter özetleri ayrıca doğrulandı.
- Sandbox içindeki ilk genel testler yerel soket ve süreç izinlerine takıldı.
  İlgili tam gruplar bu izinlerin bulunduğu macOS ortamında tekrar çalıştırıldı.
- Windows EXE/ZIP, NTFS, gerçek Windows süreçleri ve standart kullanıcıyla
  saha kabulü açık. Native senaryolar evre sürelerini, kaynak denemelerini,
  başarı sinyalini ve tarayıcıya devir çağrısını kaydedecek. Gerçek HTTP bayt
  sayısı ve masaüstü tarayıcısının görünürlüğü ayrıca ölçüm gerektiriyor.
