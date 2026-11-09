# Türkçe ses üretimi

Videoda PatientDesk AI’nin **Antalia-2 Mini 1.0.1** motoru ve modelin hazır sentetik erkek sesi kullanılır. Ses, metin veya kullanıcı verisi dışarı gönderilmeden ana işlemcide üretilir. Kişisel ses kaydı kullanılmaz. Model kartı 48 kHz doğal çıkışı, Türkçeye özel metin normalleştiriciyi ve tek sesli yapıyı açıklar. Çıkarım kodu ile ağırlıkların lisansı Apache-2.0’dır. [Resmî model kartı](https://huggingface.co/cloud0day3/antalia-mini) · [Lisans](https://huggingface.co/cloud0day3/antalia-mini/blob/0965f4a5fb578763be8ca2a2bb39421378471cd1/LICENSE) · [Atıflar](https://huggingface.co/cloud0day3/antalia-mini/blob/0965f4a5fb578763be8ca2a2bb39421378471cd1/NOTICE)

Ses kaynağının atfı **Antalia-2 Mini, Copyright 2026 PatientDesk AI**. Modelin resmî NOTICE dosyası, eğitim sesini OpenBMB VoxCPM2’ye ve İngilizce özel ad sözlüğünü CMU Pronouncing Dictionary’ye atfeder. Telaffuz sözlüğünün Python sarmalayıcısı ve sözlük verisi bağımsız lisanslara sahiptir. Motor, bağımlılıklar ve ağırlıklar yeniden dağıtılan MP4 içine paketlenmez. [CMU sözlüğü](https://github.com/cmusphinx/cmudict) · [Python paketi](https://pypi.org/project/cmudict/)

AW Center’ın mevcut Python 3.11 sanal ortamı, kayıtlı `torch`, `numpy`, `safetensors` sürümleri, `uv`, `curl`, `node` ve FFmpeg gerekir. İlk kurulum, yalnız video aracına ait bağımlılıkları `.work/audio/packages` ve 30,5 MB ağırlığı `.work/audio/models` içine alır. Üç model dosyasında SHA-256 denetimi uygulanır. Sentez ve tekrar kullanım için internet gerekmez. Bu araç AW Center'ın `requirements.txt` dosyasını veya sanal ortamını değiştirmez.

```bash
.venv/bin/python tools/demo-video/audio/setup.py
.venv/bin/python tools/demo-video/audio/tour_audio.py
.venv/bin/python tools/demo-video/audio/tour_audio.py pilot
.venv/bin/python tools/demo-video/audio/synthesize.py --sample
```

`tour_audio.py` sahneleri kayıt motorunun güncel `list` çıktısından alır. `synthesize.py --batch FILE.json` ayrıca `text`, isteğe bağlı `pronunciation` ve `output` alanlarını taşıyan JSON listesi kabul eder. Sözlük konumu `synthesize.py` içindeki `WORDS` değeridir. Alt yazı metninin özgün yazımı korunur. Model sürümü, hız, sabit rastgelelik tohumu ve telaffuz metni klip anahtarını belirler. Aynı klip yeniden kullanılabilir. WAV uzunluğu, gerçek örnek sayısı ve örnekleme hızından hesaplanır. Çıktı 48.000 Hz, mono, 16 bit PCM’dir. Motor hızı `0.94`, tohum `11`, CPU iş parçacığı sayısı `2` olarak kaydedilmiştir.

## Ses seçeneklerinin değerlendirilmesi

- Edge Read Aloud bir çevrimiçi tarayıcı hizmetidir. İstemcinin açık kaynak lisansı sunucu hizmetinin ses çıktısını kapsamaz. İncelenen Microsoft tüketici hizmeti metninde bu yol üzerinden üretilen sesin kurumsal tanıtım videosunda tekrar dağıtımı için açık izin doğrulanamadı. Bu nedenle dış ses kataloğu ya da Emel/Ahmet sentezi çağrılmadı. Yerel motor seçildi. [Microsoft hizmet sözleşmesi](https://www.microsoft.com/en-us/servicesagreement) · [edge-tts kaynak deposu](https://github.com/rany2/edge-tts)
- Piper `tr_TR-dfki-medium` kartı ses eğitim kaynağında CC BY-NC-SA 4.0 gösterir. Bu sesi kurumsal gösterim için seçmedik. [Sesin kendi model kartı](https://huggingface.co/rhasspy/piper-voices/blob/main/tr/tr_TR/dfki/medium/MODEL_CARD)
- Chatterbox Multilingual V3, Türkçe (`tr`) destekleyen MIT lisanslı, yaklaşık 500 milyon parametreli bir modeldir. Resmî depo V3’ü önerir. PyPI `chatterbox-tts==0.1.7` için ayrı ARM64 ortam çözümlemesi 109 paket ve PyTorch 2.6.0 gerektirdi. Gerekli metin ve ses üretim ağırlıkları toplam yaklaşık 3,2 GB’tır. [Resmî depo](https://github.com/resemble-ai/chatterbox) · [Model kartı](https://huggingface.co/ResembleAI/chatterbox) · [Sürüm ve bağımlılıklar](https://pypi.org/project/chatterbox-tts/0.1.7/)

## Ölçülen örnek

`--sample`, modelin ürün adlarını, Türkçe karakterleri ve 101 sayısını telaffuz ettiği bir **23,224 saniyelik** WAV üretir. Montaj öncesi FFmpeg EBU R128 ölçümü −21,7 LUFS, azami gerçek tepe −2,7 dBTP ve LRA 2,1 LU verdi. Bağımsız yerel Whisper Small Q5_1 çözümlemesi altı cümleyi geri aldı. Yazım farklarının yanında `kurgusal`, `liste`, `açıp` kelimelerini sırasıyla `kurbusal`, `listi`, `açık` olarak çözdü. Özel adları ve sayıyı tanıdı. ASR hatası ile telaffuz kusuru bu ölçümden tek başına ayırt edilemiyor. Ses dalgasını bu oturumda dinleme olanağı yoktu. Son miksin ses ve zaman ölçümleri ana kalite raporundadır. [Whisper](https://github.com/openai/whisper)

Chatterbox denemesi için geçici kuruluma 109 paket çözümlendi. Ana uygulamanın Python bağımlılıkları korundu. Yayımlanmış 0.1.7 paketinde Türkçe sınıfın `from_local` metodu V2 ağırlık adını kullanıyor, güncel GitHub kaynağında V3 de destekleniyor. V3 dosyası için 400 saniyede 294.733.908 / 2.143.989.928 bayt, ortak S3Gen için 206.788.606 / 1.057.165.844 bayt alınabildi. İki indirme zaman aşımına uğradı. Chatterbox’ın yerel sentez hızı ve ses kalitesi bu makinede ölçülmedi. Nihai ses değerlendirmesi ve klipler eksiksiz indirilen Antalia modeliyle üretildi.

`verify_mix.py` nihai AAC kanalını 16 kHz mono örneklere çözer. Her anlatım parçasının kaynak WAV’ından 10 ms aralıklı ses şiddeti zarfı çıkarır. Montajdaki beklenen yerin iki yanında 280 ms arayarak zaman kaymasını, korelasyonu, doygun örnek sayısını ve son klipten sonraki payı ölçer. Başlangıç, orta, bitiş ve ürün adlarının geçtiği seçili bölümleri `--with-asr` ile çevrimdışı çözümler. Yeniden üretim bu seçeneği açar. Model 181 MiB büyüklüğündedir. Pywhispercpp 1.5.1 ve Whisper, MIT lisanslıdır. İkisi de doğrulama sırasında kullanılır. İndirme, sabit sürüm ve model SHA-256 denetimi ile sınırlıdır. [Kuantize modelin sürümü ve SHA-256 değeri](https://huggingface.co/ggerganov/whisper.cpp/blob/c521a4b02f422512d734391fdf08bb08c0862f68/ggml-small-q5_1.bin) · [Pywhispercpp](https://pypi.org/project/pywhispercpp/1.5.1/) · [Whisper kaynağı](https://github.com/openai/whisper)

Son AAC ve sahne planının SHA-256 özetleri, her parçanın korelasyonu ve seçili kesitlerin tanıma metinleri kaydedilir. İnsan tarafından okunabilen özet `artifacts/aw-center-video/audio-qa.md`, makine çıktısı `.work/audio/final-mix-qa.json` dosyasındadır. Araç düşük eşleşme, 100 ms sınırını aşan mutlak kayma, son klibin erken kesilmesi veya sayısal doygunluk tespit ettiğinde hata koduyla çıkar. Kısaltılmış bir kurguyu doğrulamak için MP4, `scenes.json` ve `--json` hedefi komuta verilebilir.

```bash
.venv/bin/python tools/demo-video/audio/setup.py --with-asr
.venv/bin/python tools/demo-video/audio/verify_mix.py --with-asr
```
