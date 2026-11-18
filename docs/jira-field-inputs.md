# JIRA alan değerleri

Subtask ve task taslaklarında alanın live create metadata şeması sunucu tarafındaki
`integrations/jira/field_values.py` üzerinden doğrulanır ve payload'a çevrilir.
Subtask worker tüm satırları ilk create çağrısından önce yeniden kontrol eder.

- Metin, tarih (`YYYY-MM-DD`), saat dilimi içeren ISO tarih-saat, boolean,
  sayı ve tam sayı desteklenir. Sayısal metinler sayıya çevrilir; NaN, sonsuz
  ve tam sayı alanlarındaki kesirler reddedilir.
- User, option, priority, component, version ve group alanları JIRA nesne
  referanslarına çevrilir. Seçenekler mümkünse sabit ID ile gönderilir.
  Eski listelerdeki seçenek adları benzersiz olduklarında kullanılabilir.
- Array alanları liste bekler; her öğe kendi şemasına göre çevrilir.
- Cascading select alanında üst seçim değiştiğinde alt seçim temizlenir.
  Backend alt seçimin doğru üst seçime ait olduğunu doğrular.
- İstekler scalar değerleri ve sınırlı `id`, `name`, `key`, `accountId`, `value`
  referanslarını kabul eder. Cascading alanlarda bir `child` referansı eklenebilir.
  Tam issue nesneleri veya keyfi JSON nesneleri payload'a aktarılmaz.
- Tanınmayan eklenti/object şemaları için nesne biçimi tahmin edilmez.
  Desteklenmeyen zorunlu alanlar oluşturmayı engeller. Böyle alanlara destek
  eklemek için ilgili JIRA eklentisinin create sözleşmesi gereklidir.

JIRA izinleri, workflow validator'ları veya metadata dışındaki eklenti kuralları
uzak sunucuda yine hata üretebilir; yerel tip doğrulaması bu kuralları garanti etmez.
Referans: https://developer.atlassian.com/server/jira/platform/jira-rest-api-examples/

## Word şablonlarında JIRA alanlarını kullanma

**JIRA Documents** ekranı `/app/jira/documents` adresindedir. Şablon yayımlayacak kullanıcıya veya gruba `integrations.manage_jira_document_templates` iznini verin. Belge üretmek için AW Center oturumu ve ilgili kaydı okuyabilen bir JIRA bağlantısı yeterlidir.

**Template library** sekmesinde bir DOCX ve örnek issue seçin. Örneğin, başlıkta ve üst bilgide kullanılan `{{Belge adı}}` alanını JIRA Summary alanına bir kez bağlayabilirsiniz. Eşleştirmediğiniz `{{Hazırlayan notu}}` için belge üretilirken tek bir isteğe bağlı metin kutusu açılır. Alan adları büyük/küçük harfe duyarlıdır. Kaynak DOCX ortak katalogda kullanılacağı için içerdiği sabit metin ve görselleri yayımlamadan önce kontrol edin.

**Generate document** sekmesinde hedef task veya subtask linkini girin. Ekran aynı JIRA projesi ve issue türü için yayımlanmış şablonları gösterir. Üretim anındaki JIRA değerleri kullanılır. Bağlı bir alan boşsa dosyada boş kalır. Artık okunamayan alanlar için publisher eşleştirmeyi güncelleyebilir. Sonucu ekrandan veya Job Center üzerinden indirebilirsiniz.

API uçları `/api/integrations/jira/` altındadır. `document-templates/` kataloğu listeler ve yeni şablon kabul eder. `document-templates/inspect/` yüklenen dosyadaki alanları döndürür. Detay adresine yapılan PATCH güncel `version` gerektirir. `document-generation/resolve/` hedef issue için seçenekleri getirir. `document-generation/jobs/` ise `issue`, `template_id`, `version`, isteğe bağlı `manual_values` ve `Idempotency-Key` başlığı ile özel bir DOCX işi başlatır. Tekrar gönderim için aynı anahtar kullanılır. Şablon değişmişse sunucu 409 döndürür. Kullanıcı **Look up issue** ile güncel seçenekleri yükler.
