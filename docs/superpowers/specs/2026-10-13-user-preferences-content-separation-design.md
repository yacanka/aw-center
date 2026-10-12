# Kullanıcı tercihleri ve kullanıcı içeriğinin ayrılması

Durum: Uygulama öncesi kullanıcı incelemesine hazır.

## Kullanıcı tarafından belirlenen kararlar

- AW Center ilk kez ürün olarak kullanılacak. Bu görevde eski API uyumu gerekmiyor; eski endpoint veya payload için alias, uyumluluk adapterı ve çift yazma eklenmeyecek.
- Görünüm tercihleri ile kullanıcının oluşturduğu içerik ayrı sorumluluklar ve ayrı modeller olacak.
- İsimlendirme “JIRA preference servisi” ve “JIRA kullanıcı içerik modeli” olacak; bu sorumluluklar DCC tercihi/içeriği olarak adlandırılmayacak.
- Tercih sıfırlama kayıtlı JIRA listelerini veya özel doküman analiz sorularını silmeyecek.
- API uyumluluğunun gerekmemesi mevcut veriyi silme izni değildir. Migration geçmişi korunacak ve mevcut içerik yeni migration'larla taşınacak.

Bu kararlar bu görevin sonraki planlama ve uygulama aşamalarında esas alınır.

## Mevcut durum

`users.UserPreferences` hem ortak seçenekleri hem `jira_list` ve `document_analysis_checks` JSON alanlarını taşıyor. JIRA Watcher görünümü `extra_settings.watcher` içinde saklanıyor. Word servisleri soru JSON'unu kendi sözleşmesiyle doğruluyor. Frontend JIRA listelerini session store üzerinden kaydediyor.

Genel preferences serializer'ında yalnız gönderilen kolonları yazan mevcut çalışma ağacı değişikliği korunacak. Ancak User post-save signal'ının preference nesnesinin tamamını kaydetmesi eski değerlerin yeni değerleri ezmesine yol açabiliyor. Reset içerikleri siliyor ve `has_particles` alanını atlıyor.

## Model ve modül sınırları

### Genel ve feature görünüm tercihleri

`users.UserPreferences` ortak tercih deposu olarak kalır. `jira_list` ve `document_analysis_checks` bu modelden kaldırılır. Kullanıcı oluşturulunca yalnız bu preference kaydının oluşturulması korunur; her User kaydında preferences kaydeden signal kaldırılır.

JIRA preference servisi Watcher görünümünün doğrulaması, varsayılanları ve güncellenmesinden sorumludur. İlk aşamada `extra_settings.watcher` saklama biçimi korunur; ayrı JIRA preference tablosu eklenmez. Mevcut `backend/dcc/watcher_preferences.py` yüzeyi JIRA sorumluluğunu açıkça adlandıran servis ve HTTP doğrulamasıyla düzenlenir. Var olan Watcher route'unun değiştirilmesi bu ayrım için gerekli değildir.

`extra_settings` genel API üzerinden feature tercihlerini değiştirmek için kullanılamaz: genel preferences serializer'ında salt okunur olur, generic extra-setting mutation endpoint'leri kaldırılır. Feature yazmaları açık şema ve feature erişim kontrolünden geçer. Kullanıcı içerikleri session bootstrap cevabına veya genel user administration serializer'ına eklenmez.

### JIRA kullanıcı içeriği

`JiraUserContent`, `settings.AUTH_USER_MODEL` ile OneToOne ilişkili, `subtask_lists` JSONField(default=list), `version` ve timestamp alanları olan ayrı bir modeldir. Veri yalnız sahibi tarafından okunup değiştirilir. Mevcut liste sırası, başlıkları, alan metadata'sı ve satır değerleri korunur.

JIRA adı mantıksal sahipliği belirtir. Mevcut subtask feature'ı `backend/dcc/` ve `frontend/src/features/dcc/` içinde olduğundan model, servis ve frontend API bu mevcut modül içinde JIRA isimleriyle yer alır. Bu görev yeni kök `jira` Django app'i oluşturmaz ve DCC klasörünün tamamını yeniden adlandırmaz.

### Doküman analiz kullanıcı içeriği

Mevcut `backend/word/` paketi içinde `DocumentAnalysisUserContent` modeli oluşturulur: kullanıcı OneToOne ilişkisi, `checks` JSONField(default=list), `version` ve timestamp alanları. Word şu an INSTALLED_APPS içinde değildir; mevcut pakete minimal AppConfig ve migration dizini eklenip model discovery için kaydedilir. Yeni bir kök feature paketi oluşturulmaz.

`word/custom_checks.py` yeni modele erişir. Mevcut soru UUID'leri, sırası, metni, 20 soru/500 karakter sınırları, sahiplik denetimi ve job içine immutable snapshot alınması korunur. İçerik modelleri ihtiyaç halinde oluşturulur; User save signal'ıyla tekrar kaydedilmez.

## API ve frontend akışı

- Genel `/api/users/preferences/` GET/PATCH yalnız tercihleri taşır; `jira_list` kaldırılır. Kaldırılan içerik alanları write request'lerinde açık doğrulama hatası verir; sessizce kabul edilmez.
- Yeni `/api/dcc/subtasks/saved-lists/` GET cevabı `{ lists, version }`, PUT isteği `{ lists, version }` olur. Olmayan içerik kaydı için GET `{ lists: [], version: 0 }` döner. İlk PUT version 0 ile yaratır; başarılı yazma version'ı artırır. Aynı sürümle yarışan yazmalardan biri 409 ve `JIRA_CONTENT_VERSION_CONFLICT` alır.
- Frontend `SubtaskList.vue`, feature API'siyle yükler ve kaydeder; session store'dan JIRA içerik erişimi kaldırılır. Kaydedilmemiş düzenlemeler hata veya version conflict durumunda korunur. Yükleme başarısızsa boş veri olarak kabul edilip mevcut içerik üzerine kaydedilmez; tekrar yükleme sunulur.
- Word analysis-check endpoint'leri zaten feature API'sidir; URL ve soru payload'ını sırf ayrım için değiştirmeye gerek yoktur. Backend saklama modeli değişir.
- Session store yalnız genel tercihlerle ilgilenir. Bu görev ayrı bir genel preference framework'ü veya registry oluşturmaz.

JIRA listeleri için kayıt sözleşmesi boş/taslak satırlara izin verir; canlı JIRA job doğrulaması doğrudan kayıt API'sine uygulanmaz. Liste kökü array, her liste object, başlık string, `list` array ve `fields` mevcut frontend metadata yapısında array olmalıdır. Alan değerleri mevcut JSON veri tiplerini korur. Yazmalar en fazla 50 liste, liste başına 100 satır ve 100 alan metadata girdisi, toplam 1 MiB UTF-8 JSON ile sınırlanır. Bu sınırlar kayıt servisine aittir; migration veri kırpmaz. Sınırı aşan eski içerik okunabilir, ancak tekrar kaydetmek için açık hata ile küçültülmesi gerekir.

Tüm unsafe endpoint'ler SessionAuthentication ve CSRF sözleşmesini korur. Kullanıcı kimliği request body'den alınmaz. İçerik kaydetmek upstream JIRA çağrısı veya job başlatmaz; ilgili job/inspection proje yetkileri değişmez. Hatalar ortak `{ detail, code, request_id }` sözleşmesini kullanır, içerik veya credential loglanmaz.

## Görünüm resetinin kapsamı

`/api/users/preferences/reset/` yalnız görünüm tercihlerini sıfırlar:

- `theme`, `has_particles`, `items_per_page`, `compact_view` model varsayılanlarına döner.
- JIRA Watcher görünümü varsayılana döner; `extra_settings` içindeki diğer anahtarlar korunur.
- Dil, timezone, bildirim, abonelik ve gizlilik seçenekleri görünüm resetinin kapsamı dışındadır; mevcut değerleri korunur.
- JIRA listeleri, analiz soruları ve içerik version'ları değişmez.

Genel görünüm alanlarının varsayılanları model metadata'sından alınır. Feature varsayılanları JIRA preference servisinin mevcut normalizasyonuna aittir. Yeni reset-all-content endpoint'i eklenmez. Compliance kolonlarının tarayıcıya özel saklanması bu görevde değiştirilmez ve hesap reseti bu yerel ayarları sıfırladığını iddia etmez.

## Tutarlı yazma ve eşzamanlılık

Preference PATCH yalnız gönderilen kolonları kaydeder. User save, parola değişikliği ve auth last-login kaydı tercih veya içerik kaydetmez.

JSON read-modify-write işlemleri transaction içinde güncel kayıttan yapılır. JIRA içerik PUT için optimistic version compare-and-swap kullanılır. Word soru ekleme/silme ve Watcher/reset işlemleri, SQLite'ta select_for_update satır kilidi sağlamadığı için yalnız bu kilide güvenmez: güncel değer/version koşuluyla update ve sınırlı tekrar deneme kullanır. Yarış sonunda sessiz veri kaybı yerine ortak hata sözleşmesiyle conflict/retry hatası üretilir. İçerik modellerinin oluşturulmasında OneToOne unique constraint yarışı güvenli şekilde ele alınır.

Preference tablosuna backend içi `version` sayacı eklenir; genel preference API'sine yeni zorunlu request alanı eklenmez. Tüm preference servis yazmaları sayacı atomik artırır; JIRA JSON güncellemesi ve reset, okudukları sürümle koşullu update yapar. Scalar PATCH yalnız gönderilen kolonları yazar ve güncel DB sayacını artırır. JSON/reset yeniden denemeleri fresh veriyle hesaplanır; en fazla üç denemeden sonra `PREFERENCE_VERSION_CONFLICT` ile 409 döner. Word içerik read-modify-write için aynı üç deneme sınırı ve `ANALYSIS_CONTENT_VERSION_CONFLICT` kullanılır. SQLite busy/locked hataları ham exception olarak sızdırılmaz; transaction dışında bounded yeniden deneme ve sonunda `CONTENT_STORAGE_BUSY` ile 503 kullanılır. Testler gerçek SQLite bağlantıları üzerinden yarış senaryolarını doğrular; PostgreSQL için transaction sınırları da korunur.

## Migration ve mevcut verinin korunması

1. JIRA ve Word içerik modellerini ekleyen yeni schema migration'ları oluşturulur.
2. Historical model ve schema_editor connection alias kullanarak eski iki JSON alanı sahipleriyle bire bir yeni modellere kopyalanır. UUID, sıra ve payload değiştirilmez. Migration'da runtime service import edilmez, normalizasyonla veri kırpılmaz ve içerik loglanmaz.
3. Kullanıcı içerik modelleri ile taşıma migration'larına bağımlı yeni users migration'ı eski iki kolonu kaldırır. Böylece eski alanlar kopyalama tamamlanmadan düşürülemez.
4. `copy_users` komutu tutulur: eski veritabanından alınan preference ve içerikleri yeni sahiplerine yönlendirir. API uyumluluğu katmanı eklenmez; mevcut veri içe aktarma işlevi kaybedilmez. Hesap başına atomic sınır korunur.

Shared/production database resetlenmez. Uygulama sırasında migration önce disposable SQLite ve PostgreSQL üzerinde doğrulanır. Gerçek state üzerinde migration çalıştırmak bu tasarım/uygulama görevinin parçası değildir. Yeni kod ve schema aynı release ile kullanılır; eski binary'yle eşzamanlı çalışma veya rolling upgrade bu ilk ürün çıkışının gereksinimi değildir.

## Kabul ölçütleri ve doğrulama

- Görünüm reseti tüm hedef alanları sıfırlar, hedef dışı tercihleri ve iki içerik kümesini korur.
- Migration eski JSON değerlerini ve soru UUID'lerini değiştirmeden taşır; boş kullanıcı kayıtları çalışır ve migration graph döngüsüzdür.
- Genel preference API'sinde içerik yoktur ve eski yazma alanları reddedilir.
- JIRA ve Word içerikleri kullanıcılar arasında erişilemez; CSRF korunur.
- Invalid shape ve limit aşımları açık hatadır; içerik sessizce kırpılmaz.
- Eski User/preference nesnesinin kaydedilmesi yeni tercihleri veya içerikleri ezmez.
- SQLite yarışlarında JIRA listesi değiştirme, soru ekleme/silme, Watcher kaydetme ve reset için veri kaybı oluşmaz.
- Frontend yükleme/kaydetme hatasında ve conflict'te taslak kaybolmaz; session store JIRA listesi içermez.
- İlgili users, JIRA subtask/Watcher, Word/checklist ve job snapshot testleri; frontend unit, typecheck, format, build ve etkilenen E2E akışları çalıştırılır.
- Model değişikliği için SQLite/PostgreSQL migration testleri, PostgreSQL üzerinde `makemigrations --check --dry-run` ve `migrate --check` çalıştırılır. Çevre nedeniyle çalışmayan kontroller açıkça raporlanır.

## Kapsam dışı

İçerik paylaşımı, liste/soru başına relational kayıt, versiyon geçmişi, genel preference plugin sistemi, DCC feature'ının toplu yeniden adlandırılması, Compliance localStorage taşıması ve kullanılmayan preference alanlarının toplu silinmesi bu göreve dahil değildir.
