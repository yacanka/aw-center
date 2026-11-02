# Windows kurulum ve çalıştırma yardımcısı

Windows x64 üzerinde kaynak paketini açıp `AWCenter.cmd` dosyasına çift tıklayın.
Sihirbaz dev kurulumu, durum kontrolü, başlatma, prod ve offline paket işlemlerini
aynı terminalden sunar. PowerShell, önceden kurulmuş Python/Node veya Git gerekmez.
Windows'un `curl.exe`, `certutil.exe`, `tar.exe`, `icacls.exe` ve `whoami.exe`
araçları kullanılabilir olmalıdır. Kurum politikası bunları engelliyorsa yardımcı
politikayı aşmaz; araç erişimi kurum tarafından sağlanmalıdır.

## İlk dev kurulumu

CMD içinde kaynak dizininden:

```bat
AWCenter.cmd provision --profile dev
AWCenter.cmd doctor --profile dev
AWCenter.cmd start --profile dev
```

İlk işlem sabitlenmiş Python 3.11, Node 22 ve npm 10.9.4'ü kullanıcıya özel
hazırlar; `.venv` ve kilitli uygulama paketlerini kurar. Özel yapılandırma dosyasının
konumunu gösterir. Yeni boş veritabanını oluşturur ve ilk yöneticinin kullanıcı
adı/parolasını sorar. Kullanıcı adı bir harf ve beş rakamdır; parola gizli alınır.
Mevcut aktif yönetici varsa hesap veya parola değiştirilmez. Etkileşimsiz ilk
kurulumda `--no-admin` ile bu adım ertelenebilir; giriş yapabilmek için daha sonra
aynı provision işlemini terminalden tamamlayın.

Dev varsayılanı `http://127.0.0.1:5173/app/`, API `http://127.0.0.1:8000/api/`
adresidir. Başlatma çıktısındaki hostname'i aynen kullanın. Sunucular ve worker'lar
hazır olmadan başarı adresi gösterilmez. Terminal açık kalır; `Ctrl+C` sahip olunan
süreçleri durdurur ve sihirbaz kullanılıyorsa menüye döner.

`doctor` salt okunurdur: runtime indirmez, anahtar üretmez, migration uygulamaz,
izin düzeltmez ve eksik SQLite dosyası oluşturmaz. Python bile yoksa CMD yalnız
bu eksiği bildirir. Durumlar temel kurulum engellerini, özellik eksiklerini ve
yalnız yapılandırılmış fakat henüz çalıştırılarak doğrulanmamış bileşenleri ayırır.
Çıkış kodu `0` kontrol edilenlerin hazır, `1` engelleyici hata, `2` eksik veya
doğrulanmamış özellik, `130` iptal anlamındadır. Normal kontrollü kapanış `0` döner.

Tekrar provisioning anahtarları, verileri ve mevcut kullanıcıları korur. Mevcut
veritabanında bekleyen migration için yedek alın ve açıkça
`AWCenter.cmd provision --profile dev --migrate` çalıştırın. Yönetilen profil
olmayan eski bir kurulumdaki özel env/veritabanı otomatik sahiplenilmez veya
resetlenmez; mevcut özel yapılandırma korunarak ayrıca taşınmalıdır.

## Kaynaklar ve bütünlük

```bat
AWCenter.cmd provision --profile dev --repository "https://packages.example.com/awcenter" --python-index-url "https://packages.example.com/pypi/simple" --npm-registry-url "https://packages.example.com/npm" --offline-dir "D:\AWCenter-package"
```

Edinim sırası public kaynak, seçilen depo, offline dizindir. Doğrulanmış yerel
önbellek yeniden kullanılır. Artifact deposu dosya sunucusu veya yerel/UNC klasörü;
Python indeksi Simple API, npm adresi npm uyumlu registry olmalıdır. Bunlar aynı
protokol değildir. Son kullanılan secretsiz kaynak tercihleri özel config altında
saklanır. Değiştirmek için sihirbazda yeni değer girin veya ilgili CLI flag'ini
kullanın; kullanılmayacak eski tercih config/sources.json içinden kaldırılabilir.

Artifact dosyaları depo kökünde veya `runtimes/` altında bulunabilir. Aynı dosya,
seçilen kaynak ne olursa olsun onaylı sürüm/hash ile eşleşmelidir. Ağ erişimsizliği
ve bulunamayan dosyada sonraki kaynak denenir; hash, TLS, izin, disk veya kurulum
hatasında güvenlik kontrolü gevşetilmez. Pip/npm kurulum hataları alternatif
kaynağa geçilerek gizlenmez. Kaynak URL'sine kullanıcı adı, parola veya token
yazmayın. Auth gerektiren depolar için kurumun erişim sağlayan proxy/gateway veya
yerel paket dizinini kullanın; yardımcı interaktif depo oturumu yönetmez.

`HTTPS_PROXY` süreç ortamından alınabilir. Kurumsal CA için `--ca-file` kullanın;
TLS doğrulaması kapanmaz. Bootstrap kullanıcı curl ayarlarını okumaz. Sistem
Python/Node, global PATH, registry ve Windows execution policy değiştirilmez.

Bootstrap güveni release ile gelen sabit SHA-256 kayıtlarına dayanır. İzole Python
başlangıcının native DLL/encoding kapanışı CMD ile doğrulanır; kaynak modülleri
yüklenmeden önce builtin-only doğrulayıcı, runtime'ın tamamını release'in sabit
dosya envanteriyle karşılaştırır ve ek dosyaları reddeder. Yazılabilir kurulum
receipt'i güven kökü değildir. Envanter üreticisi sabit arşiv hash'ini yeniden
doğrular. Python/Node/npm sürüm yükseltmesi katalog ve bootstrap envanterlerinin
birlikte güncellenmesini ve Windows testlerini gerektirir. Python dağıtımının
lisans/noticeleri, Node ve npm lisans dosyaları runtime arşivlerinde korunur.

## Özellikleri tamamlama

Temel sistem bütün özelliklerin eksiklerini listeler. Varsayılan katalog Python,
Node ve npm içerir. FFmpeg/FFprobe, LibreOffice ve Poppler'in kurumca onaylanmış
**taşınabilir** ZIP/tar.gz dağıtımları `--feature-catalog` ile kurulabilir. Katalog
yerel, kullanıcıya özel izinlere sahip açıkça onaylanmış dosya olmalıdır; internet
veya mirror manifest'i kendiliğinden çalıştırma yetkisi vermez.

Katalog JSON'u `format_version: 1`, `artifacts` listesi içerir. Her kayıt yalnız
`name`, `version`, `filename`, `url`, `sha256`, `archive`, `executable` alanlarını
kullanır. İzinli isimler `ffmpeg`, `libreoffice`, `poppler`; executable sırasıyla
`ffmpeg.exe`, `soffice.exe`, `pdftoppm.exe` ile biten arşiv içi göreli yoldur.
Arbitrary installer komutu, MSI/admin kurulumu veya Office/DOORS lisansı çalıştırılmaz.

```bat
AWCenter.cmd provision --profile dev --feature-catalog "%LOCALAPPDATA%\AWCenter\config\approved-tools.json"
AWCenter.cmd provision --profile dev --assets "D:\approved-assets"
```

Asset dizininde `asset-manifest.json` bulunmalıdır: `format_version: 1`, basit bir
`asset_set` kimliği ve her dosyanın `path`, `size`, `sha256` kaydını içeren
`artifacts` listesi. Yalnız `ai-models/` ve `document-templates/` içeriği kabul
edilir; template dosyaları DOCX olmalıdır. Dört model dizini `opus-mt-tr-en`,
`opus-mt-en-tr`, `paraphrase-multilingual`, `ms-marco-cross-encoder` adlarını kullanır.
Model ağırlığı otomatik tahmin edilip farklı bir modele bağlanmaz. Asset setleri
değişmezdir; farklı içerik için yeni kimlik kullanın. Sonradan onaylı set seçimi,
yalnız model/template yollarını değiştirir; anahtarlar ve iş verisi korunur.

Lisanslı DOORS/Office, kurum JSON eşleştirmeleri, SMTP ve diğer entegrasyonların
endpoint/credential/trust bilgileri yetkili kanaldan sağlanır ve gösterilen özel
env dosyasına eklenir. Sırlar komuta veya URL'ye yazılmaz. Entegrasyonlar varsayılan
kapalıdır; tamamlanmamış alanlar varken temel uygulama kullanılabilir. SMTP yalnız
notification worker'a verilir; frontend süreçleri backend sırlarını almaz.
Salt dosya/COM/endpoint varlığı gerçek bağlantı veya lisans doğrulaması sayılmaz.

## Tam offline paket

Hedefle aynı Windows x64/CPython 3.11 ortamında:

```bat
AWCenter.cmd prepare-install-bundle --output "D:\AWCenter-package" --assets "D:\approved-assets" --feature-catalog "%LOCALAPPDATA%\AWCenter\config\approved-tools.json"
```

Son iki argüman isteğe bağlıdır. Paket `source/`, `runtimes/`, `dependencies/`,
isteğe bağlı `assets/` ve kök `install-manifest.json` içerir. Hedefte
`source\AWCenter.cmd` açılır; kardeş manifest bulunduğunda paket kökü seçilir.
Runtime ve dependency manifestleri platformu, lock'ları ve dosyaları doğrular.
Npm lifecycle/build smoke'u paket yayımlanmadan çalışır. Paket hazırlanması
başarısızsa tamamlanmamış çıktı yayınlanmaz. Secretsiz production örneği yeniden
üretilir; gerçek env, kullanıcı/veritabanı ve özel iş JSON'u dağıtılmaz.

Paket güvenilen release kanalından edinilmelidir. Aynı kaynaktan gelen manifest
ve dosyaların hash eşleşmesi kendi başına yayıncı kimliğini kanıtlamaz. Seçilmiş
offline paket içinde bulunmayan kurum/lisans girdileri eksik olarak raporlanır.

## Production

Dev ve prod aynı kaynak/venv'yi paylaşmaz. Review edilmiş prod kaynak kopyasını
`%LOCALAPPDATA%\AWCenter\releases\<release-id>\source` altında hazırlayın ve o
dizinden çalıştırın:

```bat
AWCenter.cmd provision --profile prod --host 192.0.2.10 --tls-cert-file "%LOCALAPPDATA%\AWCenter\tls\application\tls.crt" --tls-key-file "%LOCALAPPDATA%\AWCenter\tls\application\tls.key"
AWCenter.cmd start --profile prod
```

Statik IP tahsisi, sertifika/IP SAN, istemci güveni ve subnet ile sınırlı firewall
kurum tarafından hazırlanmalıdır. Yardımcı sistem güven ayarlarını değiştirmez.
`check --deploy`, pending migration, frontend build/static/artifact ve TLS
kapıları korunur. SQLite/private state repository dışında, yerel NTFS'tedir.
DOORS için aynı interaktif Windows oturumu ve tek DOORS-capable worker sınırı
geçerlidir. Terminal/oturum kapanınca prod durur; Windows Service kurulmaz.

Kurulumun son aşaması ve sonuçları `%LOCALAPPDATA%\AWCenter\logs` altında
sınırlı JSON raporunda bulunur; tarih/saat İstanbul biçimindedir. Ham paket komutu
çıktıları veya credential'lar rapora yazılmaz. Gerçek Windows, lisanslı Office/DOORS
ve kurum bağlantıları üzerinde kabul doğrulaması yapılmadan bunlar çalışıyor
varsayılmamalıdır. Mevcut manuel prod akışı ve operasyon sınırları için
[deployment rehberine](deployment.md) bakın.
