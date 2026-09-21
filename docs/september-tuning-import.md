# 17 Eylül ince ayar paketinin mimariye aktarımı

Kaynak: `git-changes-20260917-183229`, hedef: `codex/architecture-consolidation`.
Karşılaştırma yerel `main` ile paketin farkları üzerinden yapıldı; ardından her fark
mevcut dalın karşılığıyla değerlendirildi. Kaynak dosyalar doğrudan üzerine
kopyalanmadı. Paket içindeki metinler bağımsız çalışma talimatı sayılmadı.

## Dosya bazında sonuç

Aşağıdaki yollar kaynak pakete göredir. Hedef yollar repository köküne göredir.

| # | Kaynak dosya | Anlaşılan amaç ve uygulanan karşılık |
| --- | --- | --- |
| 1 | `backend/.env.development.example` | Geliştirme ayarları ve eski kullanıcı veritabanı bağlantısı. Mevcut `backend/.env.example` genişletildi; `DB_OLD_URL`, JIRA/Teamcenter CA yolları ve proje imzacı ayarı açıklanıyor. Eski browser-token değişkenleri ve makineye özgü değerler taşınmadı. |
| 2 | `backend/.env.production.example` | Production ayar örneği. İçeriği güncel Windows-native deployment sözleşmesiyle karşılaştırıldı. Eski token-cookie ve kaynak-ağacı model/template yolları yeniden eklenmedi; güvenli TLS ayarları ortak settings ve mevcut örnekte belgelendi. Deployment profili değiştirilmedi. |
| 3 | `backend/awcenter/integration_probe_adapters.py` | Sağlık sorgularında özel CA kullanımı. `backend/integrations/probe_adapters.py`, JIRA/Teamcenter/DocProof istemcileriyle aynı TLS çözümleyicilerini kullanıyor. Import anında sabitlenmiş SSL değerleri yerine çağrı anındaki ayarlar okunuyor. |
| 4 | `backend/awcenter/settings.py` | Sertifika yolları, TLS seçenekleri, harici kaynaklar ve yeni projeler. JIRA/Teamcenter CA ayarları eklendi; JIRA TLS varsayılanı açık. Mevcut model/template/private-artifact dizinleri korundu. Projeler için Django app eklenmedi; registry ve orgs migration kullanıldı. |
| 5 | `backend/common/management/commands/copy_users.py` | Eski şemalardaki kullanıcıları mevcut tercih kolonlarıyla aktarabilmek. Komut `backend/users/management/commands/copy_users.py` altında. Kolon introspection, JSON dönüşümü, hesap başına transaction ve `--update-existing` korundu. Sayaçlar commit sonrasında artıyor; hata çıktıları hesap/veritabanı ayrıntısı içermiyor. Gerçek kullanıcı aktarımı çalıştırılmadı. |
| 6 | `backend/dcc/document_fields.py` | Güncel belge tarihi ve küçük harfli panel şablon alanları. Belge tarihi snapshot oluşturulurken sabitleniyor; gerçek JIRA güncelleme tarihi `Source_Updated_Time` olarak ayrıca korunuyor. Birincil ve aday imzacı ayrıştırılıyor. Eski `Panels` alanları, aday imzacı gösterimi ve eski Gökbey yorum çözümlemesi korunuyor. |
| 7 | `backend/dcc/document_job.py` | XML özel karakterlerinin DOCX'i bozmaması. `autoescape=True` aktarıldı ve gerçek DOCX ile test edildi. Ham exception ayrıntısını kullanıcıya açan değişiklik taşınmadı. |
| 8 | `backend/dcc/document_snapshot.py` | Şablonların panel dizisi ve proje alanlarıyla beslenmesi. Canonical snapshot hâlâ schema-v2 `Panels`; küçük harfli `panels` ve `extras` uyumluluğu `document_job.build_render_context` içinde sağlanıyor. Schema-v1 kuyruğa alınmış işler desteklenmeye devam ediyor. Ham JIRA nesneleri değiştirilmeden ve bütün panellerin sınıflandırma/sorumluluk bilgisi kaybedilmeden proje policy'si render aşamasında uygulanıyor. |
| 9 | `backend/dcc/service/JIRAConnector.py` | Özel JIRA CA yolu ve user/priority alanlarının nesne olarak gönderilmesi. CA değişikliği `backend/integrations/jira/client.py` altında uygulandı. Alan kodlaması mevcut metadata tabanlı `field_values.py` ve subtask executor tarafından zaten yapılıyor; sabit dört alanlı liste eklenmedi, mevcut assignee fallback kaldırılmadı. |
| 10 | `backend/dcc/service/effectivity.py` | Yanlış yakın eşleşmeleri azaltmak için eşiği 0.90'a çıkarmak. Yardımcılar `backend/integrations/jira/effectivity.py` altında; `backend/automations/ecr_effectivity.py` bunları ECR preflight sırasında kullanıyor. Tamamı izinli seçeneklere eşleşmeyen değerler sessizce atılmıyor. Öneri kullanıcıya gösteriliyor, kullanıcı kabul edip preflight'ı tekrar çalıştırıyor; onaylı yayın planı otomatik değişmiyor. |
| 11 | `backend/dcc/services/subtask_control_contract.py` | Policy'nin panelleri filtreleyip yeniden düzenleyebilmesi. Ayrı legacy list/tuple sözleşmesi geri getirilmedi. Mevcut `render_controllers.py` dict/list doğrulaması ve derin kopya izolasyonu aynı ihtiyacı karşılıyor. |
| 12 | `backend/dcc/services/subtask_controls.py` | Gökbey varyantları, HYS, Özgür ve Hürkuş controller seçimi. Mevcut statik `render_controllers.CONTROLLERS` allowlist'i genişletildi; proje seçimi registry metadata'sında kaldı. |
| 13 | `backend/dcc/views.py` | Null DCC adı, dinamik alan aktarımı ve SSE renderer düzeltmeleri. Güncel iş akışındaki güvenli dosya adı, metadata kodlaması ve durable-job izleme bu eski kod yollarının karşılığı. Eski filesystem erişimi ve SSE route'ları geri eklenmedi. Effectivity önerisi canonical ECR preflight endpoint'ine bağlandı. |
| 14 | `backend/doors/client/checklist.py` | Yerel main ile içerik farkı yok. `backend/integrations/doors/checklist.py` üzerindeki daha yeni adapter/worker davranışı korundu; eski dosya ile üzerine yazılmadı. |
| 15 | `backend/excel/views.py` | Pandas `applymap` yerine `map` kullanımı. Mevcut `read_excel_first_sheet` zaten `map` kullanıyor; yeniden değişiklik gerekmiyor. |
| 16 | `backend/projects/gokbey/dcc_subtasks.py` | RFM, Protection, OSD alanlarını ayrı bölümlere taşımak; Protection aday imzacısını eklemek; software imzacısını değiştirmek. `backend/projects/policies/dcc_panels.py` iki yeni Gökbey varyantı için uygular. Birden fazla panelin değerlendirmeleri birleştirilerek korunur. Kişi adı kaynak koda alınmadı: `GOKBEY_SOFTWARE_AS_NAME` ile dışarıdan yapılandırılır; boşsa mevcut imzacı korunur. JIRA nesnesine mutation ve `print(fields)` eklenmedi. Eski `gokbey` policy'si mevcut kayıtlar için korundu. |
| 17 | `backend/projects/hys/dcc_subtasks.py` | Flight ve ICA isim/tarih alanları. Ortak küçük `control_flight_manuals` policy'sine aktarıldı; genel panel listesi korunuyor. |
| 18 | `backend/projects/ozgur/dcc_subtasks.py` | HYS ile aynı flight/ICA alanları. Aynı policy kullanılıyor; ICA eşlemesi büyük/küçük harften bağımsız. |
| 19 | `backend/projects/registry.py` | Özgür/Piku component yazımları, Gökbey Jandarma/Sivil ve Hürkuş projeleri. Teknik metadata registry'de; iş kayıtları `orgs/0004_seed_dcc_project_variants.py` forward-only migration'ında. Eski `gokbey` silinmedi, üyelikler başka projeye taşınmadı. `OZGUR` eski component adı da kabul ediliyor. Hürkuş yalnız `dcc` capability'sine sahip. Frontend kataloğu dinamik olduğundan sabit proje listesi eklenmedi; API capability/rol sözleşmesi test edildi. |
| 20 | `frontend/src/components/compdoc/CompDocTrackingDrawer.css` | Tracking alanlarının düzeni. Mevcut feature içindeki `CompDocTrackingPanel.css` ve panel düzeni kullanılıyor; kullanılmayan ikinci drawer CSS'i eklenmedi. |
| 21 | `frontend/src/components/compdoc/CompDocTrackingDrawer.vue` | DocProof durumu, sorumlular, notification tercihleri ve geçmişi. Mevcut compliance tracking paneli, version kontrollü API ve durable notification worker korundu. Paketteki eski senkron `sendNow`/`sent` sözleşmesi ve version göndermeyen kayıt akışı geri getirilmedi. Bu dosya doğrudan taşınmadı; mevcut mimari eşdeğerleri korundu. |
| 22 | `frontend/src/components/outlook/EcrTask.vue` | Vue proxy nedeniyle PDF kaynak Map anahtarının bulunamaması. Mevcut ECR artık nesne kimliğiyle PDF aramıyor; PDF workflow oluşturulurken private artifact'a bağlanıyor ve workflow ID ile izleniyor. Bu nedenle eski Map çözümü gerekmiyor. Mevcut `features/dcc/components/EcrTask.vue` dosyasına effectivity önerisinin açık kabul arayüzü eklendi. |
| 23 | `frontend/src/services/outlookAttachmentFiles.ts` | `toRaw` ile dosya eşlemesi. Mevcut ECR dosya eşlemesi bu Map'i kullanmadığı için kullanılmayan helper eklenmedi. `features/tools/api/outlookAttachmentFiles.ts` içindeki authenticated POST, tek kullanımlık capability ve PDF doğrulaması korundu. |
| 24 | `frontend/src/views/Home.vue` | Başlığın altındaki negatif boşluğu düzeltmek. `frontend/src/app/pages/Home.vue` içinde alt margin 18px yapıldı. Compliance Home değiştirilmedi. |
| 25 | `frontend/src/views/MainView.vue` | İç içe scrollbar ve sabit viewport yüksekliğini kaldırmak. Mevcut `app/layouts/ProtectedLayout.vue` zaten page/footer ve responsive shell yapısını kullanıyor; eski `96vh`/iç scrollbar yok. Yeni değişiklik gerekmiyor. |
| 26 | `frontend/src/views/dcc/DCCCreator.vue` | Başarı bildirimlerinin kalıcı olmaması. Mevcut feature sayfasında iki başarı bildirimi için `duration: 3000` uygulandı. |
| 27 | `scripts/launcher/packaging.py` | Yerel özel dosyaların değişiklik ZIP'ine girmemesi. `_certificates`, `_custom_templates`, `_models`, `_private_media`, `_media` ve `__pycache__` açıkça dışlandı. Tüm `_` dosyalarını dışlayan kural aktarılmadı; `__init__.py` ve `_helpers.py` gibi Python kaynaklarının paketlenmesi testle korunuyor. |

## Eksik kaynak için kararlaştırılan geçici uygulama

Paketin referans verdiği Hürkuş policy dosyası yoktu. Kullanıcının onayıyla
`backend/projects/policies/hurkus.py` panelleri değiştirmeden döndüren, çalışır
bir extension point olarak eklendi. Gerçek kurallar bu dosyada uygulanabilir.
Bu geçici davranış Hürkuş'a özgü gerçek iş kuralları içerdiği anlamına gelmez.

## Kullanıma geçiş

- Yeni proje kayıtları için normal migration akışı uygulanmalı. Mevcut geliştirme
  veya production veritabanına bu çalışma sırasında migration uygulanmadı;
  migration test veritabanlarında çalıştırıldı. Yeni projelere erişim rolleri
  mevcut yönetim akışından açıkça atanmalı; eski Gökbey erişimleri devralınmıyor.
- Harici `CUSTOM_TEMPLATE_DIR` altında `gj_dcc_template.docx`,
  `t625_dcc_template.docx`, `hk_dcc_template.docx` bulunmalı. Kaynak paket DOCX
  içermiyor; bu ortamın `.runtime/document-templates` dizininde de şablon yok.
- Gökbey software paneli için zorunlu imzacı kullanılacaksa
  `GOKBEY_SOFTWARE_AS_NAME` ortama konmalı. Kişisel değer repoya yazılmadı.
- `copy_users`, `DB_OLD_URL` ile tanımlanan `db_old` bağlantısını yalnız okur;
  hedef `default` bağlantısına yazar. Varsayılan olarak mevcut hesap alanlarını
  korur, mevcut tercihleri kaynakta bulunan kolonlarla günceller.
  `--update-existing` hesap alanlarını da günceller. Grup/izin/proje rolü ve diğer
  iş verileri bu komutla taşınmaz. Bu davranış kaynak komutun kapsamıdır. Kopyalanan
  eski kullanıcı adları otomatik yeniden adlandırılmaz; yeni altı karakter kuralına
  uymayan hesaplar yeniden adlandırılana kadar giriş yapamaz.
- Özel sertifikalar örnekteki env değişkenleriyle repository dışından verilebilir.
  Production'da sertifika doğrulamasını kapatan seçenekler reddedilir.

## Doğrulama

Doğrulama sonuçları aşağıda kayıtlıdır. Gerçek upstream sistemlere veya kullanıcı
verilerine yazma işlemi yapılmadı. DOCX testleri geçici sentetik şablonlar kullanır.

| Kontrol | Sonuç |
| --- | --- |
| Backend geniş hedefli suite: projects, dcc, kullanıcı importu, TLS/probes/JIRA session/Teamcenter, production checks, ECR workflow, DCC job/preview | 171 test geçti. |
| Son eklenen ECR öneri endpoint regresyonu dahil ECR/import suite | 21 test geçti; kullanıcı komutunun son bağlantı-kimliği düzeltmesinden sonra ayrıca 5 test geçti. |
| Frontend Vitest | 40 dosyada 171 test geçti. |
| Frontend uploads, Outlook, DCC, compliance import, kişi arama, Home ve job script kontrolleri | Ayrı çalıştırıldı, tamamı geçti. |
| Launcher ve release metadata | 40 test geçti. |
| Frontend typecheck, build ve bundle budget | Geçti. |
| Django collectstatic ve verify_frontend_artifact | Geçti. |
| Django check; makemigrations --check --dry-run | Geçti; eksik model migration'ı yok. |
| İzole SQLite üzerinde migrate, migrate --check, check_project_registry | Geçti; yeni seed migration'ı uygulandı ve registry hizalandı. |
| Değişen frontend dosyalarında Prettier; git diff --check | Geçti. |

Sonraki kullanıcı adı çalışmasında davet ekranının anonim açılışı için gerekli
Naive UI bileşenleri başlangıç listesine alındı ve kayıt-listesi testi düzeltildi.
Güncel `npm run test:ci` zinciri tümüyle geçti. Oturum/davet Playwright testleri
ayrıca **9/9** geçti; frontend typecheck, build ve artifact doğrulaması tekrar geçti.

Repository genelindeki `format:check`, bu görevde değişmeyen
`frontend/src/features/organization/api/organizationProjects.test.ts` dosyasındaki
mevcut biçim sorununu bildiriyor. İlgisiz dosya yeniden formatlanmadı.

`.env.example` ile seçilen mevcut SQLite dosyasında schema migration'ları
uygulanmamış olduğundan o dosyada `migrate --check` çıkış kodu 1 verdi; dosya
migrate edilmedi. Yukarıdaki olumlu migration sonucu ayrı geçici veritabanına aittir.

Bu makinenin mevcut venv'i CPython 3.14.6 kullanıyor. Production sözleşmesindeki
CPython 3.11, PostgreSQL ve Windows-native canlı süreçleri bu ortamda
doğrulanmadı. Gerçek JIRA/DocProof/Teamcenter sertifika bağlantıları ve gerçek
kurumsal DOCX şablonlarıyla son kontrol ayrıca gerekir.

Mimari fitness suite'inde 14 testin 12'si geçti. İki cycle testi,
`jobs.process_bootstrap ↔ jobs.worker` mevcut döngüsü nedeniyle başarısız.
Değişikliksiz `HEAD` backend kaynakları ayrı dizinde çalıştırıldığında aynı iki
hata tekrarlandı. Bu aktarım `jobs` kernel dosyalarını değiştirmedi; döngü görev
kapsamı dışında bırakıldı. Diğer mimari sınır kontrolleri geçti.

Playwright Chromium E2E: **17/17 test geçti** (4.7 dakika). Session/CSRF,
subtask listeleri ve Excel alan eşlemesi, ECR publication devam ettirme,
compliance import version conflict ve 320–1920 px arasındaki altı responsive
boyut doğrulandı. Tarayıcı geçici dizine indirildi; local test sunucusu test
sonunda kapatıldı.
