# AW Center ve Numarator'ü birlikte çalıştırma

İki uygulama ayrı veritabanlarıyla çalışır. Numara üretimi yalnız AW Center'ın
mevcut local job worker'ından Numarator özel API'sine gider.

| Servis | Adres |
| --- | --- |
| AW Center arayüzü | `http://127.0.0.1:5173/app/compdocs/ozgur` |
| AW Center backend | `http://127.0.0.1:8000` |
| Numarator arayüzü | `http://127.0.0.1:5174` |
| Numarator backend | `http://127.0.0.1:8100` |

## Format ve erişim hazırlığı

1. Numarator arayüzünde kullanılacak formatları oluştur ve aktif hale getir.
   Cover page çıktısı en fazla 32 karakter olmalıdır. AW Center context olarak
   `project` slug'ını gönderir; diğer dinamik alanlar format içinde varsayılan
   değer taşımalıdır.
2. Numarator'de AW Center için ayrı API anahtarı oluştur. `allowed_formats`
   yalnız bu formatların UUID'lerini içersin. Gerekli scope'lar:
   `formats:read`, `numbers:generate`, `numbers:read`, `numbers:status`.
3. AW Center'ın git dışındaki yerel environment dosyasında entegrasyonu aç.
   Aşağıdaki kodları Numarator'de oluşturduğun gerçek format kodlarıyla değiştir:

```dotenv
NUMARATOR_ENABLED=True
NUMARATOR_BASE_URL=http://127.0.0.1:8100
NUMARATOR_CREDENTIAL_ID=aw-center-local-v1
NUMARATOR_VERIFY_SSL=True
NUMARATOR_PROJECT_FORMATS={"ozgur":["COVER_PAGE","COVER_PAGE_YEAR"]}
```

API anahtarını aynı git dışı dosyada `NUMARATOR_API_KEY` olarak sakla. Dosya
erişimini mevcut kullanıcıyla sınırla; anahtarı tarayıcıya veya komut argümanına
koyma. Development launcher web, frontend, notification ve cleanup süreçlerinde
bu credential'ı boş process override ile maskeler; local job worker okuyabilir.

Format listesi proje bazında yönetici tarafından izin verilen kodlardan oluşur.
Bir kod verilirse eski tek-format sözleşmesi korunur; birden fazla kod verilirse
kullanıcı formda seçim yapar. Numarator ayrıca API anahtarının gerçek format
izinlerini ve formatın aktifliğini üretim sırasında doğrular.

## Başlatma

Numarator repo kökünde:

```bash
python launcher.py dev --backend-port 8100 --frontend-port 5174 --migrate
```

AW Center repo kökünde, ikinci terminalde:

```bash
python launcher.py dev --backend-port 8000 --frontend-port 5173 --migrate --exclude-doors
```

`--migrate` yalnız ilk kurulumda veya bekleyen migration varsa gerekir.
`AWCENTER_ENV_FILE` ile farklı bir yerel profile geçilebilir. Mevcut veritabanının
migration geçmişi uyumsuzsa geçmişi değiştirme veya veriyi silme; önce backup al
ve ayrı geliştirme veritabanı kullanan bir profil seç.

Numarator launcher seçilen backend portunu Vite proxy'sine, frontend portunu
Django development CSRF/CORS ayarlarına iletir. Development cookie adları
`dn_csrftoken` ve `dn_sessionid` olduğundan aynı hosttaki AW Center oturumuyla
çakışmaz. Production cookie davranışı korunur.

## Arayüzde numara atama

1. AW Center'da ilgili projenin Compliance Documents ekranını aç.
2. Cover Page No alanı boş bir belgeyi düzenle veya yeni belge oluştur.
3. **Create with Numarator** seçeneğini ve **Cover page number format** alanından
   izinli formatı seç.
4. **Get number from Numarator** düğmesine bas.

Kaydetme belge snapshot'ını ve seçilen formatı kalıcı tahsis kaydına yazar.
Mevcut belgede form değişiklikleri, cover page numarası, sürüm ve history aynı
transaction içinde kaydedilir. İşlem sırasında belge/cover page sürümü değişirse
yerel yazım durur. Başarılı yerel kayıttan sonra Numarator'e `used` bildirilir.
Geçici hata için **Retry** aynı tahsisi devam ettirir; yeni numara tüketmez.
Sayfa yenilendiğinde mevcut belge tekrar açılırsa kullanıcıya ait tamamlanmamış
tahsis yüklenir; aynı işlem ekrandaki **Retry** düğmesinden sürdürülebilir.
Manuel giriş ve numarası dolu belgelerin normal düzenleme akışı korunur.

macOS worker'ı Windows ile aynı `spawn` bootstrap'ını kullanır. Bu seçim macOS
sistem kütüphanelerinin thread başlatması nedeniyle `fork` sonrası ortaya çıkabilen
çökmeyi giderir. [Python multiprocessing açıklaması](https://docs.python.org/3.11/library/multiprocessing.html#contexts-and-start-methods)
bu platformda `spawn` kullanımını destekler.

## Doğrulama

AW Center'da `compliance.test_numbering`, Numarator client contract testleri ve
frontend `editor.test.ts`; Numarator'de launcher ile cookie/CSRF testleri bu
sözleşmeyi kapsar. İki gerçek servisle kabul kontrolünde seçilen formatın çıktısı,
aynı isteğin tekrarında tek tahsis ve uzak kaydın `used` durumu birlikte doğrulanır.
