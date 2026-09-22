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
