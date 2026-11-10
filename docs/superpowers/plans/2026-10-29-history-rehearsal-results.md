# AW Center güncel geçmiş temizliği provası — 29.10.2026

## Sonuç ve kapsam

Gerçek geçmiş temizliği veya push yapılmadı. Kaynak uygulama dosyaları, HEAD ve referansları korundu; uygulama veritabanı yerine izole test veritabanı kullanıldı. Eski dallar yalnız tarihsel referans olarak değerlendirildi.

Başlangıç sürümü: `codex/architecture-consolidation`, `72cfdf80b363396f2024f726f746d162c42d557e`.

## Geçmiş doğrulaması

| Kontrol | Sonuç |
| --- | --- |
| Commit sayısı | 395 → 395 |
| Parent ilişkileri | 395/395 doğru eşlendi |
| Referans adları | 130/130 korundu |
| Kimliği değişen referanslar | 126 |
| Etkilenen güncel uzak dal | 4 |
| Etkilenen PR head | 104 |
| Güncel sürümün dosya ağacı | Birebir aynı |
| Kaynak envanteri | 1.132 dosyanın hash'i korundu |
| Test checkout'ı | Tracked dosyalar temiz; gerçek dosya byte'ları temiz tree blob'larıyla aynı |
| Bilinen hassas değer taraması | 20 mantıksal kural / 51 exact ve kodlanmış örüntü; sıfır kalan eşleşme |
| Commit/tag metadata ve tüm ham tree giriş adları | Sıfır bilinen eşleşme |
| Git bütünlüğü | `git fsck --full --strict` başarılı; bağımsız incelemede unreachable nesne yok |
| Medya | Önceden incelenen 21 nesne değişmedi; yeni medya yok |

Etkilenen uzak dallar: `aw-center-v2`, `codex/architecture-consolidation`, `initial-aw-center-backup`, `main`. Bunlar bu provada indirilen güncel uzak dallardır; önceki provanın 10 dal sayısı kullanılmadı. PR sayısı, her PR'da ayrı hassas veri bulunduğu anlamına gelmez; ortak ataların değişmesi de PR head kimliğini değiştirir.

Sıfır eşleşme yalnız bilinen değerler ve taranan kodlama biçimleri için geçerlidir. Bilinmeyen değerler, parçalı kodlamalar veya steganografi için mutlak gizlilik garantisi değildir. Güncel kaynakta yeni maskeleme yapılmadı; dönüşüm tarihsel içeriğe uygulandı. Doğrudan tree referanslarından biri ayrıca temizlendi.

## Regresyonlar

- CPython 3.11.15: 1.378 backend testi başarılı.
- Launcher/release metadata: 54 test başarılı.
- Frontend test:ci: 579 test başarılı (477 + 29 Vitest; 73 Node test).
- Tarayıcı testleri: 130/130 başarılı; tek worker, retriesiz, 9,2 dakika.
- `launcher.py check`, `launcher.py prod --help`: başarılı.
- Frontend format, typecheck, build ve bundle budget: başarılı.
- `collectstatic --clear --noinput`, `verify_frontend_artifact`: başarılı.
- Prova doğrulama kapısı: 3 test başarılı; kaynak/ref/tree korunumu, commit sayısı, içerik/path ve medya ihlallerinin reddi doğrulandı.

Testler kaynakla ve temizlenmiş güncel sürümle byte eşitliği doğrulanan izole checkout üzerinde çalıştı. Gerçek AI/JIRA/mail yapılandırması aktarılmadı; sentetik process environment ve geçici DB kullanıldı. Canlı sistemdeki kullanıcı/veri kayıtları üzerinde işlem yapılmadı.

### İlk koşularda karşılaşılan ortam sorunları

İlk tam backend koşusu disk doluluğuyla kesildi; ilk tarayıcı koşusu da disk/tarayıcı sorunları nedeniyle geçersiz kaldı (122 geçiş, 5 başarısız, 3 flaky). Bunlar başarı kanıtı sayılmadı. Kullanıcı disk alanı açtı; yalnız yeniden üretilebilir paket indirme önbelleği ve OCR kareleri kaldırıldı. Asıl video, OCR sonucu ve geçmiş nesneleri korundu.

İkinci `launcher.py test` koşusunda 1.378 backend testi geçti; ardından iki launcher testi geçici uv ortamında pip metadata'sı eksik olduğu için hata verdi. Python'un `ensurepip` adımıyla yalnız geçici ortam düzeltildi; 54 launcher testi tekrar başarılı oldu. Wrapper bu hatada frontend aşamasına geçmediğinden frontend kapısı ayrıca çalıştırılan başarılı `test:ci` sonucuyla doğrulandı. Uygulama veya test assertion'ları değiştirilmedi.

İlk koşudaki erken JavaScript/yükleme hatalarının tekil kök nedeni ayrıca kanıtlanmadı; 130 senaryoluk retriesiz tekrar koşusunda yeniden ortaya çıkmadı.

Tarayıcı tekrarında Chromium yalnız prova klasörüne yeniden kuruldu; tek worker ve `--retries=0` kullanıldı. İlk koşunun kayıtları ayrı tutuldu; tekrar sonucu ilk hataların üstünü örtmez.

## Bağımsız inceleme

İzole prova için kritik kaynak/izolasyon ihlali bulunmadı. İnceleme sonrası tarama aracı bütün ham tree adlarını kapsayacak, doğrulama aracı test checkout'ının gerçek byte'larını kontrol edecek ve başarısız kapılarda nonzero dönecek biçimde güçlendirildi. Kaynak frontend dependency dosyalarıyla ortak inode bulunmadı; mirror alternates/object symlink kullanmıyor ve push hedefi kapalı.

## Gerçek geçiş öncesi açık kapılar

- Başka makinede bağımsız Django/JIRA anahtarlarının etkinliği, yeniden giriş ve parola sıfırlama davranışı doğrulanmalı.
- Windows-native çalışma ve gerçek Windows/DOORS ortamı bu macOS provasında doğrulanmadı; ilgili host kontrolleri gerekli.
- Uzak refs, açık PR'lar, korumalar, release/artifact/cache/LFS ve diğer klon envanteri gerçek geçiş anında yenilenmeli. Bu prova sunucu kalıntılarını kaldırmaz.
- Güncel SHA/ref manifesti kullanıcıya gösterilerek gerçek geçmiş yazımı için ayrı onay alınmalı; eşzamanlı ref değişiminde işlem durmalı.
- Aynı GitHub deposu korunacak; PR/cache temizliğinin destek uygunluğu ve PR diff etkileri ayrıca ele alınacak.

Kurtarma kopyasının başarılı gerçek geçişin kabulünden sonra **7 gün** saklanması onaylandı; kaldırılması ayrıca onay gerektiriyor. Süre henüz başlamadı. Repo dışı prova klasörleri erişimi sınırlı çalışma alanlarıdır; şifreli gerçek kurtarma arşivi yerine geçmez ve ham içeriği paylaşılmamalıdır.
