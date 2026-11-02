# Git geçmişi temizliği — uygulama sonucu (29.10.2026)

## Tamamlanan kapsam

Kullanıcının açık onayıyla dört GitHub dalı exact eski SHA koşullarıyla tek atomik force-push işleminde güncellendi. Aynı özel depo ve dal adları korundu. Varsayılan dal değiştirilmedi; dal veya tag silinmedi. Codex dalına yerelde doğrulanmış son commit'in temizlenmiş karşılığı da dahil edildi.

| Dal | Eski uzak SHA | Yeni SHA |
| --- | --- | --- |
| aw-center-v2 | `c6a0ef25ea36` | `7a409c532d50` |
| codex/architecture-consolidation | `24396f18739f` | `c45c93b3c72c` |
| initial-aw-center-backup | `b91129fcb557` | `0ee9b60f35ba` |
| main | `9b29f555ba97` | `87ce06f6dfe8` |

Yerel checkout aynı temiz geçmişe taşındı. Yerel dal/remote-tracking referansları ve gerekli Codex tree kayıtları korundu; ORIG_HEAD/FETCH_HEAD kimlikleri eşlendi; eski yerel reflog/erişilemeyen nesneler temizlendi. Çalışma ağacındaki uygulama dosyaları ve `.venv` değişmedi.

## Kurtarma kopyası

İlk yıkıcı işlemden önce AES-256-GCM ile doğrulamalı şifreli arşiv oluşturuldu. Kaynak Git deposu, eski uzak/PR geçmişini içeren denetim deposu, 1.133 kaynak/dokümantasyon dosyası ve 188 yapılandırma/veri dosyası arşive alındı. Geri açma ve dosya hash kontrolleri; geçici geri açılan iki Git deposunda `git fsck --full --strict` başarılı.

Arşiv: `/Users/ysrcn/Library/Application Support/AWCenter/recovery/history-cutover-20261029-bcc12bbf/recovery.tar.gz.aesgcm`

Anahtar ayrı `~/Library/Application Support/AWCenter/recovery-keys/` altında tutuluyor. Dizinler 0700, arşiv ve anahtar dosyaları 0600 izinli. Anahtar değeri konuşmaya veya loga yazılmadı. Anahtar ve arşiv aynı kullanıcı hesabı altında olduğundan bu kontrol, hesabın bütünüyle ele geçirilmesine karşı bağımsız bir güvenlik sınırı değildir.

Kabulden sonra 7 gün saklama ve kaldırmadan önce ayrı kullanıcı onayı kuralı korunuyor. Kullanıcı kabul tarihi henüz kaydedilmedi; otomatik silme yapılmayacak.

## İşlem sonrası doğrulama

- Dört uzak dalın SHA değerleri son salt-okunur kontrolde beklenen yeni değerlerle aynı.
- GitHub'dan bağımsız yeni checkout indirildi; güncel sürümün tree'si işlem öncesi sürümle birebir aynı.
- Yeni uzak kopyanın ve yerel `.git` deposunun tüm nesneleri, commit/tag metadata'sı ve ham tree dosya adları tarandı: bilinen 20 kuralın exact/kodlanmış biçimlerinde sıfır eşleşme. Her iki Git bütünlük kontrolü başarılı.
- 1.133 mevcut kaynak dosyası ve 188 yapılandırma/veri dosyasının SHA-256 değerleri korundu. Veritabanında migration veya veri temizliği yapılmadı.
- Python 3.11 ortamında gerçek yapılandırmayla system check ve sentetik ayar/geçici DB ile launcher check başarılı.
- İşlem sonrası 1.378 backend + 54 launcher/release metadata testi başarılı.
- Frontend dosyaları değişmedi; önceki aynı-tree provasında geçen 579 frontend ve 130 E2E testi bu işlemde tekrar çalıştırılmadı.
- Tek CI artifact'ının 140 dosyasında bilinen hassas değer eşleşmesi yok. Yedi medya dosyası daha önce incelenen nesnelerle aynı. Cache, release ve fork envanterleri boş. Artifact silinmedi.

## Açık kalan kalıntılar

Bu sonuç tüm kopyaların küresel olarak silindiği anlamına gelmez:

1. GitHub'daki 104 salt-okunur PR head hâlâ eski SHA'lara bağlı. Açık PR yok, ancak eski PR referansları/cached view'lar için GitHub Support değerlendirmesi gerekiyor. Destek taslağı `.runtime/history-cutover/github-support-draft.txt` içinde hazır; gönderilmedi. Uygunluk ve temizlemenin PR diff etkileri GitHub tarafından belirlenir.
2. Diğer makinedeki eski klon temiz uzak geçmişten yenilenmeli. Eski geçmiş merge/push edilmemeli; özel config/JSON/DB/media dosyaları yeni klona aktarılırken korunmalı.
3. Repo dışındaki eski denetim/prova kopyaları eski geçmişi barındırabilir. Özellikle `/private/tmp/aw-rehearsal-20261029-quemokam/original-audit.git` halen erişimi sınırlı geçici alanda duruyor. Bu kopyanın içeriği şifreli kurtarma arşivinde de mevcut; açık kopyaların kaldırılması ayrıca takip edilmeli. Şifreli kurtarma arşivi silinmedi.
4. Bilinen örüntü taraması, bilinmeyen/başka biçimde kodlanmış hassas verilerin yokluğunu garanti etmez. Genel güvenlik bulgusu bu kalan kopyalar nedeniyle tamamen kapatılmadı.

Windows ve bağımsız Django/JIRA anahtarlarının doğrulandığı kullanıcı tarafından bildirildi; bu makinede gerçek Windows host doğrulaması yapılmış sayılmıyor.
