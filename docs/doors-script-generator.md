# DOORS Script Generator (Excel)

Generator, Excel çalışma kitabının ilk sayfasındaki başlıkları DOORS object
attribute'larına eşleştirir ve bağımsız bir DXL script üretir. AW Center scripti
çalıştırmaz; harici DXL library/include kurulumu gerekmez.

## Attribute adlarını modülden yükleme

DOORS Column Names varsayılan olarak manuel alanlardır. İsteğe bağlı **DOORS
Module Path** alanına modül yolunu girip **Load Attributes** butonuna basıldığında
mevcut Windows worker üzerinden yalnız object attribute adları okunur. Bu okuma
obje değerlerini export etmez. Worker kullanılamıyorsa manuel eşleştirme kullanılabilir.

İş tamamlanınca alanlar aranabilir, temizlenebilir, tek seçimli dropdown olur.
Listede aynı adla bulunan mevcut eşleştirmeler korunur; bulunmayanlar temizlenir ve
ilgili Excel kolonları kullanıcıya bildirilir. Unique Attribute seçimleri korunur.
Yüklü durumda modül yolu kilitlidir; aynı buton **Unload Attributes** gösterir.
Unload, seçilen adları manuel alanlarda korur ve modül yolunu yeniden düzenlenebilir
yapar. Yeni Excel yüklemek attribute listesini kaldırmaz.

Yükleme sırasında modül yolu, yükleme butonu ve Generate devre dışıdır; mevcut job
durumu ve cancellation ekranda gösterilir. Başarısız/iptal edilen okumada, boş liste
veya 1000 attribute sınırı aşımında manuel alanlar ve değerleri korunur. Ekran
kapatıldıktan veya yükleme sıfırlandıktan sonra eski sonuçlar uygulanmaz. Job URL
parametresi üzerinden geri dönüldüğünde tamamlanan attribute listesi yeniden okunur;
Excel dosyası ve eşleştirmeler browser storage'a kaydedilmez.

Modül yolu yalnız attribute keşfi içindir. Üretilen DXL, DOORS'ta mevcut açık
modülde çalışır; yüklenen listenin bu modüle ait olması kullanıcı tarafından
doğrulanmalıdır. Listede read-only attribute'lar da olabilir; unique alan olarak
kullanılabilirler, yazma yetkisi DXL çalışırken kontrol edilir.

## Modlar ve unique alanlar

- **Update Existing Objects** varsayılan moddur. Seçilen bütün **Unique Attribute**
  değerleri aynı objede eşleştiğinde unique olmayan eşleştirilmiş alanları yazar.
  Aynı kombinasyon birden fazla objede varsa hepsini günceller. Eşleşmeyen satırı
  DXL output'ta uyarıyla atlar.
- **Create New Objects**, eşleşen canlı obje yoksa modül sonuna en üst seviyede
  yeni obje ekler. Unique alanlar dahil bütün eşleştirilmiş değerleri yazar.
  Excel sırasını korur; filtreler ve mevcut alt objeler ekleme konumunu değiştirmez.
  Kombinasyon mevcutsa uyarıyla satırı atlar. Aynı scriptin önceki satırlarında
  oluşturulan objeler de mükerrerlik kontrolüne dahildir.

Her iki modda en az bir Unique Attribute gerekir. Birden fazla seçim **AND**
koşuludur; alanlardan yalnız birinin eşleşmesi yeterli değildir. Silinmiş objeler
eşleştirmeye dahil edilmez. Excel hücreleri mevcut sözleşmeye göre string'e
çevrilir ve baştaki/sondaki boşlukları temizlenir; değer eşleştirmesi büyük/küçük
harfe duyarlıdır. Unique hücrelerinden biri boşsa satır, gerçek Excel satır
numarasıyla uyarı verilerek atlanır. Tamamen boş mapped satırlar işlenmez.

Script, DOORS'ta edit modunda açık olan mevcut modülde çalıştırılır. Başlamadan
önce bütün eşleştirilmiş attribute tanımlarının mevcut ve object attribute olması
kontrol edilir. Eksik attribute oluşturulmaz. `SetObjectAttribute(Object target,
string attributeName, string value)` script içinde tanımlıdır; hedef objeyi,
attribute tanımını ve yazma yetkisini kontrol eder. Değerin attribute tipine uygun
olması gerekir; DOORS'un reddettiği yazma hataları yakalanır.

Attribute okuma/yazma veya obje oluşturma hatasında script durur. Önceki
değişiklikler ve hata alan objede kısmi yazmalar modülde kalabilir; script
transaction/rollback sağlamaz ve otomatik kaydetmez. Kullanıcı modülü inceleyerek
değişiklikleri kaydetmeli veya kendi DOORS oturumunda geri almalıdır.

## API

Attribute keşfi: authenticated, CSRF korumalı
`POST /api/integrations/doors/module-attributes-jobs/`, JSON `{ "module_path":
"/Project/Module" }` ve `Idempotency-Key` header'ı kabul eder. Mevcut `doors.run_dxl`
job'ında `list_attributes` allowlist işlemi çalışır. Owner-only, SHA-256 doğrulanan
sonuç artifact'ı `{ "type": "doors_module_attributes", "schema_version": 1,
"module_path": "...", "attributes": ["Object Text"], "operation_result": {...} }`
biçimindedir. Eksik/truncated liste başarı olarak yayımlanmaz.

Authenticated, CSRF korumalı `POST /api/integrations/doors/script/` multipart alanları:

- `file`: `.xlsx` veya `.xlsm` çalışma kitabı; formül/makro çalıştırılmaz.
- `json`: `[{"excel": "Column", "doors": "Attribute", "search": true}]` mapping dizisi.
  `search`, arayüzdeki Unique Attribute seçimini temsil eder. Excel kolonları ve
  hedef attribute adları ayrı ayrı benzersiz olmalıdır.
- `mode`: `update` veya `create`; verilmezse `update`. Diğer değerler reddedilir.

Response: `{ "script": "...", "row_count": 1, "mapping_count": 1 }`.
`row_count`, scriptte değerlendirilecek boş olmayan mapped satır sayısıdır;
DOORS'ta değiştirilen/oluşturulan obje sayısı değildir. Upload, workbook ve script
boyut limitleri korunur; workbook veya upstream hata ayrıntıları API'ye sızdırılmaz.

DXL navigation, object creation ve attribute erişimi için kaynak:
[IBM DXL Reference Manual](https://download.boulder.ibm.com/ibmdl/pub/software/rationalsdp/documentation/product_doc/DOORS/version_9-2/dxl_reference_manual.pdf).
Yerel contract testleri DXL metnini doğrular; gerçek DXL derleme ve çalışma
doğrulaması Windows + IBM DOORS üzerinde yapılmalıdır.
