# AW Center Git Geçmişi Temizliği Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aynı GitHub deposunda hassas geçmiş içeriğini temizlemek; güncel sürümün işlevlerini ve uygulama kayıtlarını korumak.

**Architecture:** Yenileme, kaynak checkout yerine repo dışındaki erişimi sınırlı bağımsız mirror üzerinde yapılır. Eski dallar adları korunarak yalnız tarihsel referans olur; güncel sürüm dosya ağacı birebir korunur. Onaylanan dal/tag güncellemeleri beklenen eski SHA kontrolüyle yayımlanır; GitHub PR referansları ve yerel kurtarma nesneleri ayrıca ele alınır.

**Tech Stack:** Git, izole git-filter-repo >= 2.47, Python standart kütüphanesi; mevcut Django/Vue/launcher testleri. Uygulamaya bağımlılık eklenmez.

**Spec:** Bu konuşmada alınan kararlar: aynı depo korunacak; eski dallar yalnız tarihsel olacak; güncel sürüm çalışacak; uygulama kayıtları korunacak. Bu belge plan onayı içindir, gerçek silme/force push yetkisi değildir.

## Global Constraints

- Hassas değerler kaynak, rapor, komut argümanı veya loga yazılmaz. Özel dönüşüm kuralları repo dışında owner-only tutulur.
- Teknik slug/capability/API, migration geçmişi ve güncel uygulama dosyaları korunur.
- Veritabanı, özel dosyalar, dış JSON/env/TLS dosyaları Git dönüşümünün hedefi değildir.
- Eski dalların deploy edilebilirliği desteklenmez; otomatik dağıtımları engellenir. İsimleri silinmez veya kendiliğinden değiştirilmez.
- Bu aşamada merge, reset, force push, branch silme ve gerçek nesne temizliği yapılmaz.
- Eski kirli geçmiş geri push edilmez; sorun halinde temiz geçmiş üzerinde forward-fix uygulanır.

## İnceleme kanıtı — 29.10.2026

- Kaynak branch: `codex/architecture-consolidation`; inceleme başlangıcı HEAD: `72cfdf8`. Başlangıçta çalışma ağacı temizdi.
- Önceki prova HEAD'i `849f3c8` idi. Sonrasında 157 dosya değişti; önceki 204 test sonucu güncel sürüm testi olarak kabul edilmez.
- Önceki geçici prova dosyalarının çoğu artık mevcut değil. Eski prova scriptleri/manifestleri çalıştırılabilir teslimat sayılmaz; yeni mirror ve dönüşüm manifesti oluşturulacak.
- Yerel tüm ref/reflog erişimindeki 21 benzersiz medya blob'u incelendi: 16 ekran görüntüsü, 3 PNG ikon, 1 ICO ve 1 video. Tüm yerel nesne deposunda dosya imzası taraması ek PNG/JPEG/GIF/ICO/MP4 nesnesi bulmadı.
- 20 sabit görsel/ikon görsel olarak incelendi ve yerel Vision OCR ile işlendi; OCR hatası yok. Kişi bilgisi, credential, iç endpoint veya gerçek iş belgesi içeriği saptanmadı. DOORS görüntülerinde örnek test alanları; compliance görüntülerinde mock test kullanıcıları ve korunması kararlaştırılan teknik proje etiketi var. Compliance içeriği `frontend/e2e/compdoc-settings.spec.ts` fixture'larıyla karşılaştırıldı.
- 19 PNG'de tEXt/iTXt/zTXt/eXIf chunk veya IEND sonrası ek veri bulunmadı. ICO görsel olarak kontrol edildi.
- Video 16 saniye / 400 kare / tek H.264 görüntü akışı içeriyor; ses, altyazı veya ayrı veri akışı yok. Tüm 400 kare OCR kontrolünden geçti, metin bulunmadı. Saniyelik görsel örnekler dekoratif dünya animasyonunu gösteriyor; container metadata'sında encoder bilgisi dışında hassas bulgu yok.
- Bu kontrol görünür içerik, OCR ve belirtilen metadata kapsamındadır; steganografi yokluğu garantisi değildir. Güncel uzak ref'ler bu aşamada yeniden indirilmedi; yeni mirror'da farklı medya hash'i çıkarsa tekrar incelenecek.
- Medya kaldırılması gerektiren doğrulanmış gizlilik bulgusu yok; dosyalar korunacak. Ham inceleme çıktıları repo dışındadır, paylaşılmayacak.

## Review Focus

1. Eşzamanlı push yeni işi kaybettirebilir: ref manifesti değişirse yayın durur.
2. Doğrudan tree ref, reflog veya unreachable blob kirli içeriği tutabilir: commit dışı nesneler ayrıca taranır.
3. Aynı hassas metnin farklı kaçış/kodlama biçimi kalabilir: exact/JSON-escaped/Base64 kuralları ve bağımsız son tarama gerekir.
4. Eski klon/PR/cache geçmişi yeniden erişilebilir kılabilir: klon yenileme ve sunucu kalıntıları ayrı kapanış kapısıdır.
5. Güncel dosyaya yanlış replacement işlev kaybı yaratabilir: öncesi/sonrası tree ve dosya SHA-256 eşitliği zorunludur; beklenmeyen farkta durulur.

## Görev 1 — Geçiş önkoşulları ve geri dönüş sınırı

**Dosyalar:** Repo dışı `source-manifest.json`, `remote-refs-before.json`, `recovery-inventory.json`; uygulama dosyaları değişmez.

- [ ] Diğer makinede yeni, bağımsız Django/JIRA anahtarlarının etkin olduğunu değerleri göstermeden doğrula. Eski ortak anahtar kullanımını ve fallback'i reddet. Gerekirse ayrı kontrollü rotasyon yap; yeniden giriş kabul edilmiş durumda.
- [ ] AW Center/JIRA yeniden girişini ve parola sıfırlama outbox davranışını doğrula; kullanıcı/iş kayıtlarının korunduğunu kontrol et.
- [ ] Kullanıcıyla yazma duraklatma zamanını ve geçici kurtarma kopyasının saklama süresini kararlaştır. Onaylandı: başarılı geçişin kabulünden sonra 7 gün, erişimi sınırlı ve şifreli repo dışı saklama; süresi dolunca ayrı silme onayı. Yazma duraklatma zamanı henüz belirlenmedi.
- [ ] Aktif sürüm olarak güncel Codex branch'inin tam SHA'sını sabitle. `main`e taşıma veya default branch değişikliği bu plana dahil değildir; gerekirse ayrı karar al.
- [ ] Çalışma ağacı, tüm refs/tags, açık PR'lar, branch korumaları, imzalı tag/commitler, release/artifact/LFS ve bilinen klonları envanterle. Ham hassas içerik çıkarmadan eski/yeni nesne eşlemesi hazırla.
- [ ] Uygulama DB/private-media yedek ve restore prosedürünü doğrula; Git kurtarma arşivinden ayrı tut. Canlı DB üzerinde temizlik veya test çalıştırma.

**Kapı:** Anahtar doğrulaması ve kurtarma/saklama kararı tamamlanmadan gerçek geçişe başlama.

## Görev 2 — Güncel prova ve incelemeye hazır sonuç

**Dosyalar:** Repo dışı `repository.git`, `private-rules.json`, `rewrite.py`, `verification.json`, `changed-refs.json`; sürümlenen kod değişmez.

- [ ] Güncel uzak dallar/tag'ler/PR head'leri ve yerel kurtarma ref'lerinden bağımsız, hardlink kullanmayan mirror oluştur. Kopyanın push hedefini hazırlık boyunca kapalı tut.
- [ ] Önceki 43 kuralı özel yapılandırmalardan yeniden oluştur ve kapsamını gözden geçir; eski sayıyı sabit doğruluk ölçütü sayma. Yeni hassas örüntüleri envanterle. Teknik slug'ları koru.
- [ ] Blob içerikleri yanında commit/tag mesajları ve dosya yollarını tara. Yeni bilinmeyen hassas içerikte kapsam kararını kullanıcıya getir.
- [ ] İzole mirror'da commit grafiğini ve ref adlarını koruyarak hassas değerleri nötr örneklerle değiştir. Doğrudan tree ref'lerini de dönüştür; kaynak Codex checkpoint'lerine dokunma.
- [ ] Mirror'a özel reflog/nesne temizliği sonrası tüm object store'u tara. Bilinen hassas değerler için sıfır eşleşme; `git fsck --full --strict` için başarı bekle.
- [ ] Güncel sürümün tree ve dosya hash'lerini karşılaştır: fark sıfır olmalı. Fark varsa yayına geçme. Tüm ref adlarını ve eski/yeni SHA eşlemesini raporla.
- [ ] Bu rapordaki medya manifestiyle yeni mirror'ı karşılaştır; yeni hash'leri yeniden incele.

**Kapı:** Yeni prova sonucu, güncel etkilenen dal/PR sayısı ve yayımlanacak ref listesi kullanıcıya sunulur. Önceki 10 dal/104 PR sayısı yalnız eski prova bulgusudur.

## Görev 3 — Güncel sürüm regresyon doğrulaması

**Dosyalar:** Yalnız izole checkout ve repo dışı test sonuçları.

- [ ] CPython 3.11 ile `python launcher.py check`, `python launcher.py test`, `python launcher.py prod --help` çalıştır; tüm zorunlu kapılar başarılı olmalı.
- [ ] Backend auth/CSRF, password reset/outbox, JIRA sessions, DDF authorization/CAS, AI yapılandırma, project JSON, DCC belge/mail, TLS ve job testlerinin kapsamda olduğunu doğrula. Sentetik env ve disposable DB kullan; gerçek AI/JIRA/mail çağrısı yapma.
- [ ] `npm --prefix frontend run format:check`, `typecheck`, `test:ci`, `test:e2e`, `build` çalıştır.
- [ ] İzole backend'de `manage.py collectstatic --clear --noinput` ve `manage.py verify_frontend_artifact` çalıştır. Kaynak checkout'ın generated dosyalarını değiştirme.
- [ ] Windows hedefinde launcher/worker/DOORS ve yerel SQLite kontrollerini doğrula. Çalıştırılamayan kapıyı açık bırak; test başarısı varsayma.

**Kapı:** Güncel sürümün test kanıtı olmadan gerçek yayın yok; eski tarihsel dallar için runtime testi şart değil.

## Görev 4 — Ayrı onaydan sonra gerçek yayın

- [ ] Tam ref/SHA manifesti, test sonuçları, PR diff/imza etkileri ve saklama kararını göstererek gerçek geçmiş yeniden yazımı için açık onay al.
- [ ] Yazma duraklatmasını uygula; açık PR işlerini koruyarak merge/kapatma kararlarını ayrı doğrula. Başkalarına bildirim gönderme ancak açık talimatla yapılır.
- [ ] Uzak SHA'ları tekrar oku; manifestten farklıysa DUR ve provayı yenile.
- [ ] Yalnız onaylı heads/tags için exact refspec ve `--force-with-lease=<ref>:<old-sha>` kullan; destekleniyorsa atomik push yap. Kör `--mirror` ile yerel Codex/rehearsal ref'lerini yayımlama veya bilinmeyen uzak ref'leri silme.
- [ ] Gerekli branch korumalarını en dar kapsamda geçici değiştir; hemen geri yükle. Tarihsel dallardan dağıtım yapılmasını engelle; mevcut repo kimliği ve issue numaraları korunur.
- [ ] Temiz uzak depodan fresh clone al; refs, hash, hassas içerik ve fsck kontrollerini tekrar yap. Güncel sürüm smoke testini çalıştır.

## Görev 5 — Sunucu ve yerel kalıntıların kapanışı

- [ ] GitHub `refs/pull` doğrudan yazılamaz. Etkilenen PR'ları ve first-changed commitleri belgeleyerek gerekirse Support talebini kullanıcı onayına hazırla. Destek kabulü garanti değildir; PR diff'leri/cache temizlenmesi bağlantı ve inceleme görünümünü etkileyebilir.
- [ ] Release asset, Actions artifact/cache, LFS ve fork/klon envanterinde hassas kopya varsa her biri için kapsamlı ayrı işlem uygula. Git rewrite bunları kendiliğinden temizlemez.
- [ ] Tüm yetkili makinelerde yeni klon kullan; eski geçmişi merge/push etme. Kaynak checkout değiştirilmeden önce uncommitted dosyaları ve repo dışı konfigürasyonu koru.
- [ ] Eski yerel `.git`, reflog, Codex tree/checkpoint, eski prova klasörleri ve kurtarma kopyalarının saklama/silme planını uygula. Eski ham veriler dururken bulguyu tamamen kapatma.
- [ ] Kabul kanıtını kaydet; geçici hassas kopyaları kararlaştırılan süre ve onayla kaldır. SSD üzerinde fiziksel güvenli silme garantisi verme.

## Kaynak

[GitHub: Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) — 29.10.2026 tarihinde kontrol edildi. Force push tek başına PR/cache/diğer klonları temizlemez; Support yalnız uygun hassas veri taleplerini değerlendirir.

## Geçiş öncesi kullanıcı doğrulaması — 29.10.2026

Kullanıcı bağımsız Django/JIRA anahtarlarını ve Windows ortamında güncel sürüm, giriş ve temel belge üretimini doğruladığını bildirdi. Bu makineden bağımsız host testi yapılmış sayılmıyor; kanıt kullanıcı doğrulamasıdır. Uzak dört dalın SHA değerleri başarılı provayla aynı; açık PR yok. Yerel doğrulanmış Codex sürümü uzak dalın bir commit önünde olduğundan, gerçek yayın önerisi bu commit’in temizlenmiş karşılığını da içerir. Gerçek yeniden yazım/push onayı henüz alınmadı. Şifreli kurtarma arşivi ilk yıkıcı işlemden önce hazırlanmalıdır.
