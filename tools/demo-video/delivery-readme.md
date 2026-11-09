# AW Center Türkçe tanıtımı

Ana dosya `AW_Center_Tanitim_TR.mp4`. MP4 bölüm işaretleri ve görüntüye işlenmiş altyazı içerir. Haricî altyazı için aynı adlı SRT, bölüm seçimi için `chapters.txt`, tam ses metni için `narration_tr.txt` kullanılabilir. `feature-coverage.csv` görülen işlemleri zaman aralıklarıyla, açık akışları gerekçeleriyle listeler. `scenes.json` kaynak çekimi, kesme aralıklarını ve ses parçalarının zamanlarını saklar.

## Yeniden üretim

Depo kökünde çalıştırın.

```bash
.venv/bin/python tools/demo-video/produce.py
```

Doğrulanmış ortam macOS ARM64, CPython 3.11, Node 22 ve proje kilidindeki Chromium/Playwright sürümüdür. Django bağımlılıkları için projenin `.venv` ortamı, Vue için `npm --prefix frontend ci`, tarayıcı için `frontend` içinde `npx playwright install chromium` gerekir. FFmpeg ve FFprobe komutları PATH üzerinde bulunmalıdır. FFmpeg derlemesi libx264, libass, AAC, ALAC ve loudnorm desteği gerektirir. Kayıt sırasında birden çok ağır video işi çalıştırmak, gerçek zamanlı tarayıcı çekimini yavaşlatır.

Örnek PowerPoint üretimi `python-pptx` kullanır. Bu paket proje ortamında bulunmuyorsa kurulu olduğu ayrı Python yorumlayıcısını `AW_VIDEO_PPTX_PYTHON` ile belirtin. Kullanılan makinede yorumlayıcının yolu yalnız demo çalışma alanındaki `.runtime/aw-center-video/author-python` dosyasında saklandı. İlk ses kurulumu için `uv`, `curl` ve model ağırlıklarına erişim gerekir. Yerel ses önbelleği oluştuğunda kayıt ve montaj çevrimdışı yürüyebilir.

Komut izole Vue derlemesini hazırlar, ses ortamını ve model dosyalarının SHA-256 özetlerini denetler, Django doğrulamasını yapar, demoyu yeniden oluşturur, sunucuyu ve örnek işçiyi başlatır. Pilotun ardından sahneleri çeker, sesi ve altyazıyı yerleştirir, MP4’ü kodlar, oynatır ve doğrular. Açtığı süreçleri çıkışta kapatır. Önceden çalışan kayıt sunucusu varsa komut, sahip olmadığı sürece müdahale etmeden durur.

Saatler ve veri kimlikleri sahne metninden üretilmez. Ses süreleri WAV dosyalarından, işlem ve sonuç zamanları çalışan tarayıcıdan alınır. Montaj, tarayıcı kurulumu ve ekranın hareketsiz beklediği aralıkları kısaltır. Sonuç üzerinde okuma payı bırakır. Kaynaklar `.work/takes`, sesler `.work/speech`, indirilen doğrulama örnekleri `.work/downloads` içindedir. Mevcut önbellekle bir sahne yeniden çekilebilir. Örneğin kayıt sunucusu açıkken aşağıdaki komutları kullanın.

```bash
.venv/bin/python tools/demo-video/audio/tour_audio.py pilot
AW_RESHOOT=1 node tools/demo-video/record.mjs record pilot
.venv/bin/python tools/demo-video/render.py
node tools/demo-video/playback.mjs
.venv/bin/python tools/demo-video/qa.py
```

## Gerçek işlemler ve örnek sağlayıcılar

Ekranlar uygulamanın Vue arayüzüdür. Django oturumu, yetkiler, formlar, veri doğrulama, belge geçmişi, kütük, iş kuyruğu, durum sorgulama, çıktı yetkilendirmesi ve dosya indirmeleri gerçek uygulamada çalışır. Örnek kullanıcı, kişi, durum, görev, belge, revizyon, e-posta ve sunum içerikleri kurgusaldır. Atlas için uygulamanın proje kaydı ve izin sözleşmesi kullanılır. İş durumları gerçek iş tablosundan okunur. Bu sürümde gösterilen iş ekranları HTTP ile periyodik durum sorgular.

JIRA, DOORS, Teamcenter, DocProof ve Numaratör bağlantıları yerel sağlayıcılara yöneltilir. Çeviri, belge analizi, yorum değerlendirmesi, asistan yanıtı ve sunum dönüştürme gibi bağımlı işlemler örnek girdilerden üretilen yerel sonuçlar verir. Sunumun slayt metinleri yüklenen PPTX’ten okunur. Word çevirisi Atlas belgesinin tanımlı paragraflarını çevirir. Örnek belge karşılaştırması, PDF bölme, Outlook MSG ve ekinin okunması, Excel doğrulaması ve medya dönüştürme gerçek dosyalarla yürütülür. Her bölümün alt bandında ilgili durum belirtilir.

`AW_VIDEO_DEMO=1` yalnız üretim komutunun başlattığı demo işlemlerine verilir. Sunucu `127.0.0.1:18765` üzerinde çalışır. Demo her sıfırlamada ayrı bir SQLite veritabanı, cache ve özel dosya alanı oluşturur. Üretim kimlik bilgileri okunmaz. Haricî e-posta taşımacılığı kapalıdır. Parola kurtarma örneğinde gerçek bildirim işçisi iletisini yalnız işlem belleğindeki posta kutusuna teslim eder. Demo Python süreçlerinde dış bağlantı ve DNS engellenir. Tarayıcı yalnız demo origin’ine erişebilir. Hesap parolası çalışma alanında rastgele oluşturulur. Tanıtım, süreleri sistem performansı ölçümü olarak sunmaz.

## Ses ve atıf

**Antalia-2 Mini 1.0.1, Copyright 2026 PatientDesk AI.** Hazır sentetik erkek sesi Türkçe ve yerel olarak üretildi. Model ve çıkarım kodu Apache-2.0 lisanslıdır. Konuşma parçaları 48 kHz mono PCM, son dağıtım sesi AAC’dir. Ekran kaydı ve videoda müzik kullanılmadı. [Resmî model kartı](https://huggingface.co/cloud0day3/antalia-mini) · [Modelin atıfları](https://huggingface.co/cloud0day3/antalia-mini/blob/0965f4a5fb578763be8ca2a2bb39421378471cd1/NOTICE) · [Ses seçimi, lisanslar ve örnek test](../../tools/demo-video/audio/README.md)

Son doğrulamada yerel Whisper Small Q5_1 modeli anlatımdan seçilen Türkçe örnekleri yazıya döker. İlk kurulumda bu model için yaklaşık 181 MiB indirilir. `audio-qa.md` nihai AAC ile kaynak WAV parçalarının eşleşmesini, ölçülen en büyük zaman farkını ve deşifre örneklerini içerir. `qa-report.md` oynatma, görüntü, altyazı, dosya içeriği ve kapsam kontrollerini belgeler.
