# Merkezi AI ve AW Center Asistanı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI sorgularını bağımsız tüketilebilen ortak fonksiyonlarda merkezileştirmek ve bu fonksiyonlarla yetkiye uygun uygulama rehberliği sunan bir asistan eklemek.

**Architecture:** `integrations/ai` feature bağımsız, durumsuz sorgu ve transport katmanıdır. `integrations/assistant` rehber, yetki ve sohbet kullanım senaryosunu; `features/assistant` tarayıcı arayüzünü sahiplenir. Assessment mevcut dış sözleşmesini koruyarak merkezi katmana delege eder.

**Tech Stack:** CPython 3.11, Django/DRF, requests, Vue 3, TypeScript, Pinia, Naive UI, Vitest, Playwright. Yeni bağımlılık yok.

**Spec:** `docs/superpowers/specs/2026-10-05-central-ai-assistant-design.md`

## Global Constraints

- Browser auth yalnız session cookie ve CSRF; mevcut project/domain policy'leri backend otoritesidir.
- Yeni Django app, migration, agent framework, dinamik callable çözümleme veya genel amaçlı araç çalıştırma API'si yok.
- AI çekirdeği feature modüllerini, kullanıcı/proje modellerini, jobs veya HTTP request nesnesini kullanmaz.
- Merkezi girişler `complete_text(messages, *, policy, configuration=None)` ve `complete_json(messages, *, policy, configuration=None)`.
- Güncel mesaj 4.000 karakter; geçmiş en fazla 12 mesaj ve toplam 24.000 karakter; yol 200 karakter; yanıt 8.000 karakter.
- Browser JSON gövdesi 64 KiB, rehber bağlamı 64 KiB; en fazla dört uygulama kartı ve dört kaynak.
- Asistan connect en fazla 5 saniye, read en fazla 25 saniye, response en fazla 64 KiB; kullanıcı başına dakikada 10 istek.
- Read timeout toplam süre garantisi değildir; otomatik retry ve arka planda bırakılan timeout thread'i yok.
- Native JSON mode veya function calling desteği varsayılmaz; model URL'si, HTML'i ve Markdown linki yürütülmez.
- Sohbet yalnız frontend belleğinde, session-scoped; reset/logout/kullanıcı değişimi/session expiry eski yanıtı geçersiz kılar.
- Mevcut Naive UI tema ve responsive sözleşmesi korunur. Credential, prompt, yanıt ve private path loglanmaz.
- Eski ve yeni provider ayarları aile halinde seçilir; kısmi yapılandırmalar birleştirilmez.
- Kullanıcının mevcut değişiklikleri korunur. Gerçek env dosyaları değiştirilmez veya commit edilmez.

## Review Focus

1. Compose'un tanımlanmamış merkezi env alanlarını boş değerlerle üretmesi legacy fallback'i bozmamalı; Task 2 deployment testi bunu doğrular.
2. Yeni sohbet sonrası eski isteğin tamamlanması yeni pending state'i veya mesajları değiştirmemeli; Task 6 race testi bunu doğrular.
3. Yetki sohbet sırasında geri alındığında eski context ve kartlar erişim otoritesi sayılmamalı; Task 4 ve 5 testleri tekrar yetkilendirmeyi doğrular.
4. Çok baytlı metin karakter sınırını geçmeden byte sınırını aşabilir; Task 1 ve 5 UTF-8 testleri ağ çağrısından önce reddi doğrular.
5. Integration Hub canlı probe isteği modele sorgu göndermemeli veya configuration bilgisini canlı sağlık gibi göstermemeli; Task 2 ve 7 bunu doğrular.

## Başlangıç ve dosya haritası

Uygulamadan önce using-git-worktrees becerisiyle mevcut checkout/attachment durumunu
incele. Bu plan çalışma ağacındaki henüz commit edilmemiş AI chat ve Watcher
değişiklikleri üzerine hazırlanmıştır. Temiz HEAD worktree'si bu bağımlılıkları
içermez; onları kaybetmeden uygun çalışma alanını seç. Kullanıcının değişikliklerini
taşımak için toplu commit veya reset yapma. Mevcut farkların snapshot'ını yalnız
local geçici alanda tut; secret içerebilecek diff'i çıktıya basma.

Yeni kaynaklar görevlerin Files alanlarında listelenmiştir. `ai/` ve `assistant/`
paketlerine boş `__init__.py` ekle; Django app kaydı ekleme. Core config ve
transport merkezi pakette, domain prompt'ları ilgili feature'da kalır.
Frontend API ve store dışında shared HTTP client kullanma.

Her görevin testleri önce beklenen nedenle başarısız olmalı, sonra minimal
uygulamayla geçmelidir. Yeni kaynakları ve yalnız göreve ait mevcut dosya
hunk'larını commit et; kullanıcıya ait önceden mevcut değişiklikleri stage etme.
Temiz ayrım mümkün değilse değişiklikleri çalışma ağacında koruyup raporla.

## Task 1: Durumsuz ortak AI istemcisi

**Files:** Create `backend/integrations/ai/{__init__,contracts,config,client,transport}.py`; create `backend/integrations/tests/test_ai_client.py`; modify `backend/awcenter/test_architecture.py`.

**Interfaces:**
- `ChatMessage(role: Literal['system','user','assistant'], content: str)` frozen dataclass.
- `AIRequestPolicy(purpose: str, max_request_bytes: int, max_response_bytes: int, connect_timeout: float, read_timeout: float)` frozen dataclass.
- `AIConfiguration(url: str, model: str, token: str, allowed_hosts: tuple[str,...], connect_timeout: float, read_timeout: float, max_response_bytes: int)` frozen dataclass; token repr dışında.
- `AIServiceError(detail: str, code: str, response_status: int)` güvenli hata.
- `complete_text(messages: Sequence[ChatMessage], *, policy: AIRequestPolicy, configuration: AIConfiguration | None = None) -> str`.
- `complete_json(...) -> dict[str, Any]`, aynı parametreler.
- `resolve_configuration(*, prefer_assessment: bool = False) -> AIConfiguration` Task 2'de ayarlara bağlanır; Task 1 explicit configuration ile test edilir.

- [ ] **Test yaz:** `test_text_request_is_bounded` payload'da yalnız model/messages/stream=false bulunduğunu, redirect=false ve policy/config minimum timeout/byte limitlerinin uygulandığını doğrulasın. `test_json_requires_object` list, null, invalid JSON ve duplicate keys'i reddetsin; otomatik ikinci çağrı olmasın.
- [ ] **Sınır testlerini yaz:** `test_utf8_limit_applies_to_encoded_payload`, geçersiz role/content, boş yanıt, 302/401/500, yanlış Content-Type, bozuk choices, oversized body, NaN/infinite timeout, malformed URL/port ve allowlist dışı host. İstisnada token/upstream body bulunmasın. Örnek assertion: `self.assertEqual(post.call_count, 0)` geçersiz configuration/girdi için.
- [ ] **İzolasyon testini yaz:** `test_concurrent_calls_keep_separate_messages_and_policies` iki explicit configuration/policy ile çağrıları barrier kontrollü fake transport'ta kesiştirsin; her payload yalnız kendi mesajını taşısın. Architecture testi ai paketinden feature/model importunu reddetsin; `django.conf` yalnız config modülünde olsun.
- [ ] **Red doğrula:** `cd backend` ardından `../.venv/bin/python manage.py test integrations.tests.test_ai_client awcenter.test_architecture`; eksik ai modülü/sözleşmesi nedeniyle FAIL beklenir.
- [ ] **Uygula:** Mevcut assessment transport davranışını merkezi transport'a aktar. Config doğrulaması network'ten önce; `requests.post` response context manager ile kapanır. Mesaj listesini kopyala, mutable default/session/history ekleme. İstek boyutunu gerçek JSON encoding üstünden ölç. Policy limitleri yapılandırmayı yalnız daraltır.
- [ ] **Green doğrula:** Aynı test komutu PASS. Commit: `feat: add isolated central AI query functions`.

## Task 2: Yapılandırma ve güvenli işletim yüzeyi

**Files:** Modify `backend/awcenter/settings.py`, `backend/awcenter/checks.py`, `backend/integrations/ai/config.py`, `backend/integrations/catalog.py`, `backend/integrations/probes.py`, `.env.example`, `backend/.env.example`, `docker-compose.yml`; create `backend/integrations/tests/test_ai_config.py`; modify `backend/integrations/tests/test_catalog.py`, `backend/integrations/tests/test_probes.py`, `backend/awcenter/test_production_checks.py`, `backend/awcenter/test_deployment_contract.py`; create `docs/ai-assistant.md`.

**Interfaces:** Task 1 `resolve_configuration` gerçek settings resolver olur. `configuration_status() -> Literal['configured','unconfigured','invalid']` yalnız güvenli durumu döndürür. Yeni Integration Hub kimliği `ai-chat`, route `None`; mevcut `ai` yerel model girdisi korunur.

- [ ] **Seçim testlerini yaz:** `test_central_absence_uses_whole_legacy_family`, `test_partial_central_config_does_not_borrow_legacy_fields`, `test_explicit_empty_central_config_is_invalid`, `test_assessment_prefers_explicit_legacy_family`, `test_assessment_uses_central_when_legacy_absent`. Bütün aileler yoksa unconfigured; kısmi/bozuk aile varsa invalid.
- [ ] **Deployment testini yaz:** Yeni env anahtarları hiç verilmediğinde Compose render'ı onları boş değerle etkinleştirmesin. Açık boş merkezi alan ile hiç verilmemiş alanı ayrı fixture'larda test et. AI credentials notification/cleanup lifecycle'larına aktarılmasın. `test_ai_chat_probe_does_not_call_provider` POST çağrısı olmadığını, `ai-chat` girdisinin live health almadığını doğrulasın.
- [ ] **Red doğrula:** `../.venv/bin/python manage.py test integrations.tests.test_ai_config integrations.tests.test_catalog integrations.tests.test_probes awcenter.test_production_checks awcenter.test_deployment_contract` backend içinden; yeni beklentiler FAIL.
- [ ] **Uygula:** Spec'teki yedi `AI_API_*` ayarını ekle; raw unset ile explicit empty ayrımını çözümleme aşamasına kadar koru. Legacy ayarların mevcut varsayılanlarını koru. Örnek merkezi env satırlarını yorum halinde tut. Compose opsiyonel merkezi anahtarlarını unset kalabilen passthrough ile ver; credential ve endpoint için `${...:-}` boş-string enjeksiyonu yapma. Configuration validator mevcut production check kimliğini koruyan assessment kontrolünde ve yeni merkezi kontrolünde ortak kullanılır.
- [ ] **İşletim bağla:** `ai-chat` yalnız configured/attention gösterir; probes bu girdiyi network/cache probe akışına sokmadan geri verir. Dokümana yeni/legacy öncelikleri, devre dışı durum, limitler, provider'a gönderilen sohbet verisi ve canlı doğrulama sınırını yaz. Ayar hatasında payload veya secret loglama.
- [ ] **Green doğrula:** Yukarıdaki testler PASS. Commit: `feat: configure central AI access with legacy compatibility`.

## Task 3: Assessment tüketicilerini ortak transport'a bağlama

**Files:** Modify `backend/integrations/assessment.py`, `backend/integrations/tests/test_assessment.py`; regression targets `backend/ddf/tests.py`, `backend/dcc/test_watcher.py`.

**Interfaces:** `request_assessment(prompt) -> str` ve `AssessmentServiceError(detail, code, response_status)` korunur. Wrapper Task 1 client'ına tek user mesajı ve assessment policy'siyle delege eder; Task 2 `prefer_assessment=True` resolver kullanır.

- [ ] **Test yaz:** `test_assessment_delegates_to_central_client` eski prompt/payload ve seçilen configuration'ın korunduğunu doğrulasın. `test_ai_error_maps_to_existing_assessment_error` mevcut configuration/unavailable/rejected/response-invalid kodlarının aynı status/detail sözleşmesiyle eşleştiğini doğrulasın. Yeni invalid-input hatası güvenli ve deterministik olsun.
- [ ] **Red doğrula:** `../.venv/bin/python manage.py test integrations.tests.test_assessment` backend içinden; delegation testleri FAIL.
- [ ] **Uygula:** Assessment dosyasındaki network, JSON ve config tekrarını kaldır; yalnız uyarlama bırak. Testlerde patch hedefini gerçek merkezi transport'a taşı; payload ve güvenlik assertion'larını silme. DDF/Watcher prompt ve domain davranışını değiştirme.
- [ ] **Green ve regresyon:** `../.venv/bin/python manage.py test integrations.tests.test_assessment integrations.tests.test_ai_client ddf dcc.test_watcher awcenter.test_architecture` PASS. Commit: `refactor: route assessments through central AI client`.

## Task 4: Yetkili uygulama rehberi ve route sözleşmesi

**Files:** Create `backend/integrations/assistant/{__init__,catalog,access,context}.py`, `backend/integrations/assistant/guide_data.json`, `backend/integrations/tests/test_assistant_catalog.py`; create `frontend/src/features/assistant/models/navigation.ts`, `frontend/src/features/assistant/models/navigation.test.ts`.

**Interfaces:** `GuideEntry` frozen dataclass: `id`, `title`, `path`, `purpose`, `inputs`, `outputs`, `steps`, `limitations`, `keywords`. `authorized_guides(user) -> tuple[GuideEntry,...]`; `build_context(guides, *, current_path: str, message: str) -> str`; frontend `resolveAssistantPath(path: string, router: Router) -> string | null` yalnız kayıtlı internal route kabul eder.

- [ ] **Rehber kaynağını incele:** `app/router/routes.ts` ve `app/services/mainMenu.ts` içindeki görünür araçların gerçek page/API/use-case'lerini oku. Home, integrations, jobs, accelerator/outlook, DOORS araçları, Teamcenter, Compare, PDF Split, Media Converter, Translator, DDF Assistant, Powerpoint Gallery, JIRA, Organization, Compliance Docs araçları ve yetkili developer/users alanlarına rehber ekle. Aktif ekranların desteklemediği davranış yazma.
- [ ] **Test yaz:** `test_catalog_matches_effective_menu_access` sıradan kullanıcı/staff/superuser/DDF permission için uygun girdileri doğrulasın. `test_project_guides_require_enabled_capability_and_domain_role` grup/doğrudan role, kapalı proje ve yanlış capability durumlarını kapsasın. `test_context_refilters_after_role_revocation` önceki history/path'in yetki sağlamadığını doğrulasın.
- [ ] **Contract test yaz:** Frontend Vitest testi Node filesystem ile canonical `backend/integrations/assistant/guide_data.json` dosyasını okuyup Vue router.resolve ve createMainMenuOptions ile stable hedefleri karşılaştırsın; Python runtime veya backend sunucusu gerekmesin. Backend catalog aynı JSON girdilerini doğrulanmış GuideEntry değerlerine dönüştürür; id tekrarlarını reddeder. Dinamik `/compdocs/<slug>` hedefleri için enabled test projesi kullan. Redirect alias, `//host`, dış URL, backslash, query/fragment ve bilinmeyen route reddedilsin. Üretim frontend kodu backend dosyasını import etmez; üretim backend kodu frontend kaynaklarını okumaz.
- [ ] **Red doğrula:** Backend `../.venv/bin/python manage.py test integrations.tests.test_assistant_catalog`; root `npm --prefix frontend run test:unit -- src/features/assistant/models/navigation.test.ts`; yeni katalog eksikliği nedeniyle FAIL.
- [ ] **Uygula:** Mevcut orgs policy/registry ile filtrele. `build_context` UTF-8 64 KiB bütçesini genel yardım, geçerli mevcut sayfa, sonra deterministik keyword eşleşmesi/id sırasıyla doldursun. Kullanıcının sorusunda veya açık sayfada açıkça seçilen yetkili proje dışında proje detayını prompt'a ekleme. Tüm yetkili proje linkleri catalog endpoint'inde mevcut olabilir. Frontend raw model text'inden path üretmez.
- [ ] **Green doğrula:** İki test komutu PASS. Commit: `feat: add permission-aware assistant application guide`.

## Task 5: Asistan sohbet ve katalog API'leri

**Files:** Create `backend/integrations/assistant/{serializers,service,views,throttling}.py`, `backend/integrations/tests/test_assistant_api.py`, `backend/integrations/tests/test_assistant_service.py`; modify `backend/integrations/urls.py`.

**Interfaces:** `answer_question(user, *, message: str, history: list[dict[str,str]], current_path: str = '') -> dict`; `GET assistant/catalog/` returns `{status, applications}`; `POST assistant/chat/` returns `{answer, applications, sources}`. Kart alanları `{id, title, path, description}`, kaynak alanları `{id, title, path}`. API path'leri `/api/integrations/` tabanındadır.

- [ ] **API test yaz:** Anonymous GET/POST reddi; gerçek session ve `APIClient(enforce_csrf_checks=True)` ile CSRF zorunluluğu; boş mesaj, 4.001 karakter, 13 geçmiş mesajı, 24.001 geçmiş karakteri, 201 karakter path, 65.537-byte body, sahte system/tool rolü, geçersiz object tipleri. Invalid istek network'e ulaşmasın. Query/fragment context'e alınmasın.
- [ ] **Service test yaz:** Fake provider geçerli JSON, bozuk JSON, eksik/yanlış tip alan, 8.001 karakter yanıt, bilinmeyen/yetkisiz id, tekrarlı id ve dört kart üstü liste döndürsün. Şema/uzunluk ihlali güvenli invalid-response; bilinmeyen id filtrelenir, geçerli id sırası korunarak dedupe ve dört sınırı uygulanır. Yanıtın URL/HTML içermesi kart hedefi yaratmasın.
- [ ] **İşletim test yaz:** Aynı kullanıcı için sabit 60 saniyelik bucket'ta 11. çağrı 429, farklı kullanıcı etkilenmez; cache key payload taşımaz. `atomic_cache_add` ile on ayrı slot claim'i eşzamanlı isteklerde limiti korusun, süre bitince slotlar yenilensin. Cache exception güvenli unavailable olur; lock alınamadığı için false dönen claim, dolu slot gibi fail-closed davranır. Role revocation sonraki POST'ta yeniden uygulanır. AI unavailable ve konfigürasyonsuz katalog durumu credentials sızdırmaz.
- [ ] **Red doğrula:** `../.venv/bin/python manage.py test integrations.tests.test_assistant_api integrations.tests.test_assistant_service` backend içinden; endpoint/service eksikliği nedeniyle FAIL.
- [ ] **Uygula:** Session/CSRF ve input doğrulamasından sonra yetkili rehberi üret. Body byte sınırını güvenilmeyen Content-Length yerine gerçekten okunan bounded içerikte de uygula. System prompt JSON şemasını, katalog dayanağını, kullanıcının dilini ve belirsizlikte soru sormayı tanımlar. User/history verilerini system talimatına birleştirme. Task 1 complete_json çağrısı asistan policy'sini kullanır; yalnız izin verilen id'ler Task 4 rehberinden kartlara çözülür. Ortak error_response kullan.
- [ ] **Green doğrula:** Yukarıdaki testler ve `awcenter.test_architecture` PASS. Commit: `feat: serve bounded assistant conversations and navigation`.

## Task 6: Session kapsamlı sohbet durumu ve temalı panel

**Files:** Create `frontend/src/features/assistant/api/{assistant,assistant.test}.ts`, `frontend/src/features/assistant/stores/{assistant,assistant.test}.ts`, `frontend/src/features/assistant/components/{AssistantPanel.vue,AssistantPanel.test.ts,AssistantMessage.vue}`; modify `frontend/src/app/layouts/ProtectedLayout.vue`; gerekirse `frontend/src/app/plugins/naiveUiFeatures.ts` yalnız kullanılan component kaydı.

**Interfaces:** `fetchAssistantCatalog(signal?: AbortSignal): Promise<AssistantCatalog>`; `sendAssistantMessage(input: AssistantRequest, signal?: AbortSignal): Promise<AssistantReply>`; `useAssistantStore` exposes `messages`, `pending`, `error`, `catalog`, `send(message, currentPath)`, `retry()`, `resetConversation()` ve `$reset()`. API tipleri Task 5 alanlarıyla aynı; `messages` kart/kaynakları korur, history yalnız role/content taşır.

- [ ] **API/store test yaz:** Body'de model/config/token olmaması; history trim'inin 12 mesaj/24.000 karakter/64 KiB budget'a uyması; 4.000 üstü kullanıcı mesajının gönderilmemesi; iki eşzamanlı send'in engellenmesi. Retry son başarısız user mesajını çoğaltmasın. History'den çıkarma eski tam mesajlar üzerinden yapılır, system mesajı üretilmez.
- [ ] **Race test yaz:** Deferred promise ile A isteği başlat, reset et, B isteği başlat, A'yı tamamla: `expect(store.pending).toBe(true)` ve `expect(store.messages.some(m => m.content === 'old reply')).toBe(false)`. `$reset` generation değerini başlangıca döndürüp eski cevabı yeniden geçerli kılmamalı; session reset yolunu gerçek plugin üzerinden test et. Catalog fetch de aynı reset korumasına sahip olsun.
- [ ] **Component test yaz:** HTML/Markdown link literal metin; kart yalnız `resolveAssistantPath` ile gider; hata/429/unconfigured fallback, keyboard gönderme ve çok satırlı giriş, yeni sohbet, panel kapat/aç, focus dönüşü. Session/user değişiminde sohbet ve bekleyen istek temizlensin. Sohbet mesajlarının configured AI servisine gönderildiği kısa açıklama görünür olsun.
- [ ] **Red doğrula:** Root `npm --prefix frontend run test:unit -- src/features/assistant`; eksik kaynaklar nedeniyle FAIL.
- [ ] **Uygula:** Store instance'ına ait abort/generation state kullan; global mutable request state veya browser storage yok. `registerSessionScopedStore` ile uyumlu `$reset` implement et. HTTP timeout 35 saniye; abort sonrası stale result ve stale finally uygulanmaz. Katalog panel ilk açıldığında yüklenir, prompt iletilen path yalnız route.path olur.
- [ ] **Paneli bağla:** Naive UI drawer, mobilde viewport genişliği, desktop'ta en fazla 440px; useThemeVars renk/fontları. Protected shell içinde lazy feature yüklemesi ve erişilebilir sabit düğme; mevcut Quick command ile çakışma olmasın. Application/source kartları router navigation yapar; kendi kendine route değişmez. Panel kapatma aynı sohbete dönüşü korur, reset ayrı işlemdir.
- [ ] **Green doğrula:** `npm --prefix frontend run test:unit -- src/features/assistant` ve `npm --prefix frontend run typecheck` PASS. Commit: `feat: add session-isolated AW Center assistant panel`.

## Task 7: Bütünleşik doğrulama ve kullanım dokümantasyonu

**Files:** Create `frontend/e2e/assistant.spec.ts`; update `docs/ai-assistant.md`, `docs/architecture.md`; sadece gerekiyorsa `frontend/src/features/integrations/pages/IntegrationHub.vue` ve ilişkili testler.

**Interfaces:** Önceki görevlerin gerçek public API/route/store sözleşmeleri. Yeni ürün API'si yok.

- [ ] **E2E yaz ve red doğrula:** Mevcut session fixture yaklaşımıyla provider sonuçlarını API düzeyinde mock et. 375px ve 1440px, light ve dark modlarda panel açılışı, örnek soru, uygulama kartına basma, sayfa değişiminde sohbetin kalması, reset, error/retry ve logout akışları. `npm --prefix frontend run test:e2e -- assistant.spec.ts`.
- [ ] **Negatif E2E ekle:** Kötü amaçlı cevap render'ında çalıştırılan script veya external navigation yok; keyboard/Escape ve focus geri dönüşü; 820x390 landscape ekranında yatay overflow yok; pending yanıt resetten sonra görünmez. Integration Hub'da ai-chat yapılandırması live available olarak gösterilmez. Ekran görüntülerini test output'una kaydet ve incele.
- [ ] **İlgili backend kapıları:** Backend içinde `../.venv/bin/python manage.py check`; `../.venv/bin/python manage.py test integrations.tests ddf dcc.test_watcher awcenter.test_architecture awcenter.test_production_checks awcenter.test_deployment_contract`. Task 2 env aktarımı için root `.venv/bin/python -m unittest scripts.test_launcher scripts.test_launcher_jobs scripts.test_release_metadata`.
- [ ] **Frontend kapıları:** Root `npm --prefix frontend run format:check`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run test:ci`, `npm --prefix frontend run test:e2e -- assistant.spec.ts session.spec.ts session-theme.spec.ts`, `npm --prefix frontend run build`. İlk local E2E öncesi frontend içinde `npx playwright install chromium`; binary commit edilmez.
- [ ] **Artifact kapıları:** Backend içinde `../.venv/bin/python manage.py collectstatic --clear --noinput` ve `../.venv/bin/python manage.py verify_frontend_artifact`. `git diff --check`; kapsam dışı mevcut hatalar ayrı raporlanır, test skip veya assertion zayıflatma yapılmaz.
- [ ] **Canlı doğrulama:** Yapılandırılmış servis erişilebiliyorsa yalnız uydurma/generic uygulama soruları kullan: “İki belgeyi karşılaştırmak istiyorum”, “Where can I split a PDF?”, belirsiz “Belgeyle işlem yapacağım”, desteklenmeyen özellik ve sahte yönlendirme talebi. Gerçek kullanıcı/iş verisi gönderme. Canlı çağrı yapılamadıysa mock geçişini canlı doğrulama diye raporlama. Production CPython 3.11 eşliği ayrıca kontrol edilir.
- [ ] **Dokümantasyon ve teslim:** Yeni AI araçlarının complete_text/complete_json kullanımı için secret içermeyen örnek, configuration önceliği, stateless sınır, sohbet veri akışı, limitler ve yeni rehber ekleme/test yöntemi yaz. Sonuçları gerçek komut çıktılarıyla kaydet; yalnız task'a ait değişiklikleri commit et. Commit: `test: verify assistant integration and document central AI usage`.

## Öz denetim

Spec'in çekirdek/izolasyon gereksinimleri Task 1; configuration ve işletim Task 2;
uyumluluk Task 3; rehber/yetki/route Task 4; sohbet sözleşmesi/limitler Task 5;
session ve UI Task 6; deployment/artifact ve canlı sınırlar Task 7 ile karşılanır.
Fonksiyon adları ve response alanları görevler arasında aynıdır. Review Focus'taki
beş risk için owning task'ta somut test bulunur. Yeni framework veya schema değişimi
öngörülmez. Bu plan henüz uygulanmamıştır.
