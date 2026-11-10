# User Preferences and User Content Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Execution authorized by the user on 2026-10-13; native execution in the existing codex branch preserves pre-existing uncommitted edits.

**Goal:** Görünüm resetinin kullanıcı içeriğini silmesini önlemek ve JIRA listeleri ile analiz sorularını kendi feature modellerine taşımak.

**Architecture:** `UserPreferences` tercih deposu olarak kalır; `integrations.JiraUserContent` ve `word.DocumentAnalysisUserContent` kullanıcı içeriğini ayrı JSON aggregate'lerinde saklar. Feature servisleri owner scope, validation ve optimistic concurrency sınırlarını yönetir. Genel user/session API'sinden içerik çıkarılır; eski API adapterı ve çift yazma eklenmez.

**Tech Stack:** CPython 3.11, Django/DRF, SQLite ve PostgreSQL, Vue 3/TypeScript, Pinia, Naive UI, Vitest ve Playwright; yeni dependency yok.

**Spec:** `docs/superpowers/specs/2026-10-13-user-preferences-content-separation-design.md` (ilk tasarım onaylandı; integrations/JIRA taşımasıyla güncellenmiş kapsam kullanıcı incelemesine hazır).

## Global Constraints

- AW Center ilk kez ürün olarak kullanılacak. Bu görevde eski API uyumu gerekmiyor; eski endpoint veya payload için alias, uyumluluk adapterı ve çift yazma eklenmeyecek.
- İsimlendirme “JIRA preference servisi” ve “JIRA kullanıcı içerik modeli” olacak; bu sorumluluklar DCC tercihi/içeriği olarak adlandırılmayacak.
- JIRA uygulaması `backend/integrations/jira/` ve `frontend/src/features/integrations/jira/` içinde yönetilir; canonical HTTP `/api/integrations/jira/` olur. Runtime Django app mevcut `integrations` app'idir, yeni JIRA app'i eklenmez.
- Capability ve role domain `jira` olur; gerçek DCC document/template terimleri, immutable job kind'leri ve historical migration kimlikleri bu uygulama adından bağımsızdır.
- API uyumluluğunun gerekmemesi mevcut veriyi silme izni değildir. Migration geçmişi korunacak ve mevcut içerik yeni migration'larla taşınacak.
- Görünüm reseti: `theme`, `has_particles`, `items_per_page`, `compact_view` ve `extra_settings.watcher`; diğer tercihler, extra anahtarları ve içerik version'ları korunur.
- JIRA kayıt sınırları: 50 liste, liste başına 100 satır ve 100 metadata alanı, toplam 1 MiB UTF-8 JSON. Taslak/boş satırlar kaydedilebilir. Migration veri kırpmaz.
- Word mevcut 20 soru/500 karakter sınırlarını, soru UUID'lerini ve immutable job snapshot sözleşmesini korur.
- Browser auth SessionAuthentication ve server-side cookie; unsafe isteklerde CSRF; owner yalnız request.user'dan alınır.
- Preference/Word read-modify-write en fazla üç deneme; version conflict 409, storage busy 503. SQLite'ta yalnız select_for_update'a güvenilmez.
- Kullanıcının mevcut dirty/untracked değişiklikleri korunur. Bu plan ara görevlerle release edilmez; bütün cutover aynı release'e aittir.
- Shared/production database üzerinde migration veya reset çalıştırılmaz; tüm veri doğrulaması disposable test state üzerindedir.
- Görev commit'i yapılırsa yalnız görev hunks'ları stage edilir; mevcut kullanıcı değişiklikleri topluca commit edilmez. İşlemler kullanıcının seçtiği execution workflow'a göre yapılır.

## Review Focus

1. Eski kayıtta opsiyonel `fields` yok veya boş taslak satır var: migration payload'ı korur, yeni kayıt API'si eksik metadata'yı boş liste olarak kabul eder (Görev 1/2).
2. İki tab aynı sürümle ilk kaydı yaratır: yalnız bir yazma başarılı olur, diğeri 409 alır; sessiz overwrite olmaz (Görev 2).
3. Görünüm reseti soru ekleme ve Watcher kaydetmeyle çakışır: içerik korunur, başarılı tercih mutasyonları version sırasına uygun uygulanır (Görev 3/4).
4. Frontend yükleme hatası veya hesap değişimi: eski hesaba ait/gecikmiş cevap yeni hesapta görüntülenmez; yükleme hatası boş kayıt olarak kaydedilmez (Görev 5).
5. Taşınmış içerik yeni yazma limitinden büyük veya bozuk: migration içeriği silmez; okuyucu frontend çökmemeli, geçersiz yapı için açık hata sunmalı ve kullanıcı onayı olmadan üzerine boş veri yazmamalı (Görev 1/2/5).

## Dosya ve sorumluluk haritası

- Ön koşul taşıma: `backend/dcc/` runtime kaynakları → `backend/integrations/jira/`; frontend `features/dcc/` → `features/integrations/jira/`. Var olan JIRA client/session/config modülleri birleştirme sırasında korunur, aynı adlı hedef dosya üstüne yazılmaz.
- `backend/integrations/jira/user_content_models.py`: JIRA kullanıcı içerik modeli; `backend/integrations/models.py` model discovery export'unu içerir.
- `backend/integrations/jira/user_content.py`: kayıt validation'ı, owner-scoped GET/PUT ve version fencing servisi.
- `backend/integrations/jira/user_content_views.py`, `backend/integrations/jira/urls.py`: authenticated saved-list HTTP yüzeyi.
- `backend/word/apps.py`, `backend/word/models.py`, `backend/word/migrations/`: mevcut Word paketinin persistence kaydı.
- `backend/word/custom_checks.py`: ayrı içerik aggregate'ine soru ekleme/silme.
- `backend/users/preference_service.py`: scalar preference yazması ve appearance reset; ortak feature import etmez.
- `backend/integrations/jira/preferences.py`: Watcher preference normalizasyonu ve CAS yazması; mevcut `watcher_preferences.py` HTTP yüzeyi bu servisi kullanır.
- `backend/users/models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`: model/HTTP/admin içerik ayrımı ve preference yazma sınırları.
- `backend/users/management/commands/copy_users.py`: eski DB içeriğini yeni feature modellerine taşıyan mevcut import işlemi.
- `frontend/src/features/integrations/jira/api/jiraSavedLists.ts`, `components/SubtaskList.vue`: session'dan bağımsız JIRA içerik akışı.
- `frontend/src/features/session/models/auth.ts`: `IPreferences.jira_list` kaldırılması.
- Yeni backend migration/API/concurrency ve frontend component/API testleri; mevcut checklist, Watcher ve E2E testlerinin güncellenmesi.

## Görev 0: JIRA uygulamasının integrations sınırına taşınması

**Files:** Move existing runtime `backend/dcc/` modules/tests/admin/templates to `backend/integrations/jira/`; move existing frontend `frontend/src/features/dcc/` to `frontend/src/features/integrations/jira/`; create `backend/integrations/models.py`, `backend/integrations/jira/legacy_dcc/apps.py`, `legacy_dcc/__init__.py`, `legacy_dcc/migrations/__init__.py`; move original dcc migration files unchanged to `legacy_dcc/migrations/`; create `backend/integrations/migrations/0001_adopt_jira_models.py`, `backend/integrations/jira/legacy_dcc/migrations/0003_retire_runtime_models.py`, `backend/orgs/migrations/0005_jira_role_domain.py`, `backend/integrations/jira/test_application_migration.py`. Modify `backend/integrations/apps.py`, `urls.py`, `backend/awcenter/settings.py`, `urls.py`, `test_architecture.py`, `release_smoke.py`, `test_release_smoke.py`, `backend/automations/catalog.py`, `backend/projects/constants.py`, `registry.py`, `api.py`, registry/alignment tests, `backend/orgs/models.py`, `access_policy.py`, tests, `backend/users/access_summary.py`, corresponding frontend project models/parser/store/tests and app routes/menu/access tests. Update `AGENTS.md` and `docs/architecture.md` with the new application boundary.

**Interfaces:** Runtime models `integrations.JiraTrackedIssue` (former DccRecord), `integrations.JiraReminderDelivery` (former DccReminderDelivery), `integrations.JiraIssueDraft`, `integrations.JiraIssueDraftEvent`; `ProjectRoleAssignment.Domain.JIRA = 'jira'`; registry `PROJECT_CAPABILITY_JIRA = 'jira'`; frontend `ProjectJiraRole`, `hasProjectJiraRole` and `roles.jira`. Existing persisted job kinds are unchanged; executor modules live under `integrations.jira.*`.

- [ ] MigrationExecutor upgrade tests seed existing dcc records, draft/events, reminders, assigned users/project M2M and group/direct model permissions. After adoption and retirement assert same PK/FK/M2M membership, content type IDs and equivalent permission grants, and no table/data drop. Fresh install must expose only integrations runtime models and pass `makemigrations --check --dry-run`. Role-domain migration must preserve subject/project/role and reject target conflicts without overwriting grants.
- [ ] Architecture and route tests assert no runtime root `dcc` imports, exactly one signal subscription, new canonical prefix, absence of `/api/dcc/` aliases, and no provider credential leakage. First run tests against old state to demonstrate the missing new contracts.
- [ ] Build a collision inventory before moving: existing `integrations/jira/views.py` is the JiraSessionView surface; move old dcc/views.py as `record_views.py`. Use `workflow_models.py` for moved record/reminder models; keep `issue_draft_models.py`; explicit exports in root integrations/models.py make model discovery deterministic. Existing `frontend/features/integrations` resources merge with the nested jira feature; adapters and business HTTP remain behind integrations.
- [ ] Preserve old migration bytes and label `dcc` with `LegacyDccMigrationsConfig(name='integrations.jira.legacy_dcc', label='dcc')` plus migration discovery under its own package; no root backend/dcc runtime package remains. Adoption migration depends on legacy dcc/0002, jobs/orgs/contenttypes/auth historical state and creates integration model states with explicit existing db_table/M2M db_table/constraint names via SeparateDatabaseAndState. Retirement depends on adoption and deletes only old model states (database_operations=[]). Check migration graph for cycles.
- [ ] Model content type migration reuses existing IDs, updates app/model names and relevant permission codenames while preserving user/group links; fail safely on conflicting target rows. Keep relation/physical table names unchanged. No `remove_stale_contenttypes` or destructive cleanup command.
- [ ] Move live modules and templates, update imports and patch targets; IntegrationsConfig.ready imports JIRA signals once, migration-only legacy config has no ready hooks/models/admin. Client/config/session behavior remains intact. Update catalog dotted_path values without changing job kinds, job parameters, signed confirmation payloads, idempotency keys or artifact digests.
- [ ] Convert project capability/domain/parser/store/guards/access summary consistently to jira. Org migration alters choices and existing stored domains forward-only; seed/project slugs stay unchanged. Keep document-controller/template property names where they describe DCC documents rather than application identity.
- [ ] Include JIRA urls once under integrations (`jira/`); move existing session route into the same include. Update API clients, frontend imports, lazy routes, menu, command palette and E2E request mocks. Rename tracking runtime model/interface names to JIRA; user-visible product label is JIRA, business DCC document labels remain valid.
- [ ] Run `manage.py test integrations.jira projects orgs users.test_auth_csrf awcenter.test_architecture awcenter.test_release_smoke jobs.tests.test_dcc_jobs jobs.tests.test_dcc_preview` on disposable SQLite. Run equivalent adoption/role/permission tests on disposable PostgreSQL and registry check. Run frontend typecheck and route/access/store/feature tests; require PASS or report environment blockers. Deployment/release smoke source and fixtures must use new API/capability while persisting unchanged job kind values.
- [ ] This task is completed before preference/content cutover tasks; do not commit unrelated pre-existing changes when staging moved source. Review diffs against the original working tree, not only HEAD, so existing uncommitted Watcher/ECR changes survive the move.

## Görev 1: Ayrı içerik modelleri ve kayıpsız taşıma

**Files:** Create `backend/integrations/jira/user_content_models.py`; modify `backend/integrations/models.py`, `backend/users/models.py`, `backend/awcenter/settings.py`; create `backend/word/apps.py`, `backend/word/models.py`, `backend/word/migrations/__init__.py`, `backend/users/test_content_migrations.py`; generated schema migrations `integrations/0002_jira_user_content.py`, `word/0001_initial.py`, `users/0002_preference_version.py`; create data migration `users/0003_move_user_content.py`.

**Interfaces:** `JiraUserContent(user, subtask_lists, version, created_at, updated_at)` ve `DocumentAnalysisUserContent(user, checks, version, created_at, updated_at)`; user OneToOne/primary key; list JSON default=list; PositiveInteger version default=0. `UserPreferences.version` backend içi PositiveInteger default=0.

- [ ] MigrationExecutor testi yaz: users/0001'de oluşturulan iki kullanıcıya farklı listeler/soru UUID'leri koy; latest taşıma state'inde owner, JSON equality, sıra ve UUID equality assert et. Boş içerik ve shape/limit dışı JSON da bire bir korunmalı. Test migration sonrasında latest state'e dönmeli.
- [ ] `DATABASE_URL=sqlite:///:memory: ../.venv/bin/python manage.py test users.test_content_migrations` çalıştır (`backend/` içinde); yeni modeller/taşıma yokken hedef davranışın başarısızlığını doğrula.
- [ ] İki modeli ve Word AppConfig'i ekle; generated schema migration'larını Django ile üret. Version 0, henüz API üzerinden yazılmamış aggregate'i belirtir. Data migration, historical models ve `schema_editor.connection.alias` kullanarak her preference sahibinin JSON'unu kopyalasın; runtime validation/normalizasyon çağırmasın.
- [ ] Graph: integrations/0002 users/0001 + integrations/0001 adoption state'ine, Word/users schema migration'ları users/0001'e, users/0003 ise users/0002 + integrations/0002 + word/0001'e bağımlı olsun. Bu görevde eski kolonları henüz düşürme; son cutover Görev 4'te.
- [ ] Migration testini tekrar çalıştır; yeni modellerde kullanıcılar arası isolation ve bağımsız default list instance testleri ekle. Beklenen sonuç: tüm hedef testler PASS.

## Görev 2: JIRA kullanıcı içerik servisi ve API

**Files:** Create `backend/integrations/jira/user_content.py`, `backend/integrations/jira/user_content_views.py`, `backend/integrations/jira/test_jira_user_content.py`, `backend/integrations/jira/test_jira_content_concurrency.py`; modify `backend/integrations/jira/urls.py`, `backend/integrations/jira/test_subtask_jobs.py`.

**Interfaces:** `get_saved_lists(user) -> {lists: list, version: int}`; `replace_saved_lists(user, lists, *, version: int) -> {lists: list, version: int}`; `validate_saved_lists(value) -> list`; HTTP `GET/PUT /api/integrations/jira/subtasks/saved-lists/`.

- [ ] API testleri yaz: missing row GET `{lists: [], version: 0}`; version 0 PUT sonrası version 1; aynı version PUT 409/`JIRA_CONTENT_VERSION_CONFLICT`; ikinci kullanıcı GET boş; anonymous/CSRF failures; request owner field'ı reddedilir. Upstream JIRA client'ının çağrılmadığını assert et.
- [ ] Validation testleri yaz: [] ve blank draft kabul; optional fields yoksa kabul; liste/title/list/fields tipleri yanlışsa 400. 50/100/100 ve 1 MiB sınırında başarılı, bir fazlasında 400; UTF-8 çok byte metni gerçek byte hesabıyla sınırlandır. Tam saved payload/sıra round-trip testi kullanıcı preference API'si yerine yeni API'yi kullansın.
- [ ] Testleri çalıştır ve endpoint/service yokken FAIL gözle. Sonra owner-scoped model sorgusu, conditional version update, ilk kayıt unique-constraint yarışı ve HTTP hata mapping'ini uygula. JSON payload key/value'larını kayıt sırasında sessizce kırpma. Finite olmayan sayıları geçersiz JSON olarak reddet.
- [ ] Aynı version ve ilk yaratma için bağımsız bağlantılar/barrier ile concurrency testi çalıştır: bir başarı + bir conflict, version tek artış, kazanan JSON equality. Test hem SQLite hem PostgreSQL üzerinde çalışabilsin.
- [ ] DB locked/busy sınıflandırmasını backend driver hata koduyla dar tut; diğer OperationalError'ları busy diye maskeleme. En fazla üç transaction attempt, attempt'ler arasında transaction dışı 20/40 ms bounded backoff; üçüncü busy failure 503/`CONTENT_STORAGE_BUSY`. Bu akışı test et.
- [ ] `manage.py test integrations.jira.test_jira_user_content integrations.jira.test_jira_content_concurrency integrations.jira.test_subtask_jobs` çalıştır; hedef API ve concurrency testlerinde PASS.

## Görev 3: Analiz sorularının yeni içerik modeline geçirilmesi

**Files:** Modify `backend/word/custom_checks.py`, `backend/jobs/tests/test_document_analysis_checklists.py`; create `backend/word/test_custom_check_concurrency.py`.

**Interfaces:** Var olan `get_custom_checks(user)`, `create_custom_check(user, question)`, `delete_custom_check(user, identifier)` imzaları korunur. Yeni sorgular yalnız `DocumentAnalysisUserContent` kullanır. Mevcut Word HTTP ve job snapshot tüketicileri değişmez.

- [ ] Checklist testlerinde resetten sonra sorunun aynı UUID/metinle kaldığını assert et; read sırasında `UserPreferences.document_analysis_checks` erişiminin yapılmadığını test et. Önce eski uygulamada FAIL doğrula.
- [ ] Servisi yeni modele geçir; var olan normalize_custom_checks, duplicate ve 20/500 limitlerini koru. Soru ekleme/silmede fresh checks + version CAS, en fazla üç deneme ve conflict 409/`ANALYSIS_CONTENT_VERSION_CONFLICT` uygula; yalnız tanınan SQLite busy hataları için Görev 2 ile aynı retry policy'yi kullan. Küçük ortak driver-error helper gerekiyorsa `backend/awcenter/database_errors.py` ile sınırlı tut; genel persistence framework ekleme.
- [ ] İki eşzamanlı farklı soru eklemede iki soru da kalsın; aynı soru eklemede duplicate, add/delete yarışında başarılı değişiklikler korunsun; retry tükenmesi açık conflict olsun. TransactionTestCase ile ayrı bağlantılar kullan, sleep tabanlı race test yazma.
- [ ] `manage.py test jobs.tests.test_document_analysis_checklists word.test_custom_check_concurrency` çalıştır; existing owner isolation, UUID, job snapshot ve count/length testleri PASS. Appearance resetinin yeni içeriğe dokunmadığını doğrula.

## Görev 4: Tercih yazmaları, appearance reset ve eski kolonların kaldırılması

**Files:** Create `backend/users/preference_service.py`, `backend/users/test_preferences.py`, `backend/users/test_preference_concurrency.py`, `backend/integrations/jira/preferences.py`; modify `backend/users/models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `tests.py`, `test_copy_users.py`, `management/commands/copy_users.py`, `backend/integrations/jira/watcher_preferences.py`, `backend/integrations/jira/test_watcher.py`; generate `backend/users/migrations/0004_remove_content_fields.py`.

**Interfaces:** `update_user_preferences(user, values: dict) -> UserPreferences`; `reset_appearance(user) -> UserPreferences`; `mutate_extra_settings(user, transform) -> UserPreferences` (transform fresh dict üzerinde çalışır); JIRA `normalize_jira_preferences(extra_settings) -> dict` ve `update_jira_preferences(user, values) -> dict`.

- [ ] Regression testleri yaz: stale User kaydının yeni dark theme'yi değiştirmemesi; reset has_particles=false, theme=system, items_per_page=25, compact_view=false; language/timezone/privacy/notification ve extra diğer key'ler aynı; JIRA/Word içerik JSON ve version aynı. Genel preferences GET'te iki içerik alanı yok; bu alanları PUT/PATCH/nested user update ile göndermek 400. `extra_settings` yazma girişimi açık 400; generic extra mutation route'ları yok. Önce FAIL gözle.
- [ ] User post-save preference-save receiver'ını kaldır; yeni kullanıcı preference creation'ını koru. Scalar serializer yazmalarını service üzerinden only-submitted fields + F(version)+1 olarak yap. Nested user serializer ve admin yollarını da fresh partial preference yazmasıyla hizala; admin extra_settings/version salt okunur olsun. Genel serializer `jira_list`, `document_analysis_checks` ve salt-okunur feature JSON mutation girişimlerini açıkça reddetsin.
- [ ] Appearance reset, model metadata default'larını explicit görünüm allowlist'ine uygulasın; fresh extra_settings içinden yalnız watcher key'ini çıkarsın. Users servisi JIRA/DCC import etmesin. JIRA default resolver eksik watcher key'i için zaten varsayılan üretir. Reset eski model metodunu kullanıyorsa metod yalnız bu servise yönlendirilsin; reset logic iki yerde bulunmasın.
- [ ] JIRA preference normalizasyonunu/JSON mutation'ı `preferences.py` servisine ayır; HTTP serializer ve proje-role kontrolü mevcut watcher yüzeyinde kalabilir. Version CAS + Görev 2 retry sınırları uygula. Stale object, scalar+Watcher, iki Watcher proje kaydı ve reset+Watcher concurrency testleri ekle; başarılı işlemler version sırasına uygun sonucunu korusun.
- [ ] `copy_users` introspection'ı kaldırılan iki eski JSON kolonu için explicit descriptor'larla sürdür; preference scalar'larını users, iki JSON'u ilgili içerik modeli üzerinden yaz. Hesap başına atomic rollback ve gizli veri loglamama testlerini güncelle. Bu importer runtime API aliası değildir.
- [ ] Runtime modelden eski kolonları kaldır; migration 0004'ün dependency'si users/0003 olsun. MigrationExecutor latest testini 0004'e ilerlet; yeni JSON korunur ve eski kolon/model fields kaldırılmış assert et.
- [ ] `manage.py test users.tests users.test_preferences users.test_preference_concurrency users.test_copy_users users.test_auth_csrf users.test_content_migrations integrations.jira.test_watcher` çalıştır; PASS. Çalışma ağacındaki existing serializer update_fields koruması ve Watcher testlerini kaybetme.

## Görev 5: Frontend JIRA içerik akışını session'dan ayırma

**Files:** Create `frontend/src/features/integrations/jira/api/jiraSavedLists.ts`, `jiraSavedLists.test.ts`, `frontend/src/features/integrations/jira/components/SubtaskList.test.ts`; modify `frontend/src/features/integrations/jira/components/SubtaskList.vue`, `frontend/src/features/integrations/jira/models/jira.ts`, `frontend/src/features/session/models/auth.ts`, `frontend/e2e/subtask-generator.spec.ts`, `frontend/e2e/watcher-settings.spec.ts` (yalnız etkilenen fixtures); create `frontend/e2e/preferences-content.spec.ts`.

**Interfaces:** `SavedJiraLists { lists: ISubtaskListItem[]; version: number }`; `fetchSavedJiraLists(): Promise<SavedJiraLists>`; `saveJiraLists(payload: SavedJiraLists): Promise<SavedJiraLists>`. Feature API dışında shared HTTP import edilmez.

- [ ] API testi GET/PUT path'ini ve `{lists, version}` payload'ını assert et. Component testi initial GET, typed lists render, empty first list, editVersion koruması, successful save version update, 409/503 sonrası draft korunması ve GET failure'da Save disabled + retry gösterilmesini assert et. Önce eski component ile FAIL doğrula.
- [ ] API fonksiyonlarını ekle ve component session import/`session.getPreferences.jira_list`/`session.updatePreference` kullanımını kaldır. Initial GET yalnız başarı durumunda edit state'i başlatsın; load hata halinde boş varsayılan içerik persist edilmesin. Kaydetmede mevcut editVersion mantığını koru; explicit reload taslağı değiştirecekse kullanıcıya Naive UI confirm sun.
- [ ] Cevap yapısını runtime'da doğrula: missing/negative/noninteger version veya bozuk list shape bir load error'dur. Limit aşan taşınmış içerik geçerli shape ile okunabilir; backend save validation hatası kullanıcıya gösterilir. Shape hatasında silent normalize/filter ile veri kaybetme.
- [ ] Session değişimi ve component unmount için pending response'ları sequence/disposed + authenticated user identity ile fence et; başka hesabın sonucu yeni hesaba uygulanamaz. ID erişimi gerekiyorsa session store yalnız account identity için kullanılabilir, içerik storage olarak kullanılmaz.
- [ ] `IPreferences.jira_list` kaldır; JIRA liste tipi yorumunu artık “original/main branch compatibility” yerine kullanıcı içeriği sözleşmesi olarak güncelle. E2E fixtures yeni saved-list API'sini kullansın.
- [ ] Yeni E2E: liste ve soru kaydet, görünüm resetini API üzerinden çağır, tema/parçacıkların reset ve içeriklerin UUID/payload equality'sini doğrula; ikinci hesapta içerik yok. Test gerçek JIRA upstream çağrısı gerektirmesin.
- [ ] `frontend/` içinde `npx vitest run src/features/integrations/jira/api/jiraSavedLists.test.ts src/features/integrations/jira/components/SubtaskList.test.ts src/features/session/pages/Settings.test.ts src/features/session/stores/session.test.ts src/app/services/theme.test.ts` ve typecheck çalıştır; hedef testler PASS. Değişen frontend dosyalarını Prettier ile formatla.

## Görev 6: Bütünleşik doğrulama ve dokümantasyon

**Files:** Modify `docs/user-administration.md`, `docs/jira-watcher.md`, `docs/architecture.md`, `AGENTS.md`; plan checkbox/evidence güncellemesi. Build çıktıları kaynak gibi commit edilmez; yeni migration'lar kaynak dosyasıdır ve değişiklik kapsamına dahildir.

**Interfaces:** Önceki görevlerdeki modeller, yeni saved-list API'si ve appearance reset tek release davranışıdır.

- [ ] `rg` ile runtime `jira_list`/`document_analysis_checks` erişimlerini kontrol et: yalnız historical migration, legacy import descriptor ve removed-field rejection/test references kalabilir. Session bootstrap/user administration cevaplarının içerik taşımadığını testlerle doğrula. Docs, JIRA isimlerini, yeni endpoint'i ve reset kapsamını anlatsın; eski API uyumu önerilmesin.
- [ ] Root dcc importu, eski browser API prefix'i ve capability/role domain runtime referansı kalmadığını kontrol et. Historical migration, physical table/constraint adı, persisted job kind ve DCC document terminolojisini uygulama adıyla karıştırarak toplu replace etme. Fresh install ile existing-state upgrade aynı runtime schema'yı üretmeli; migration-only eski app yeni runtime permission üretmemeli.
- [ ] Repository kökünden `python launcher.py check`, `python launcher.py test`, `python launcher.py prod --help`; ayrıca `.venv/bin/python -m unittest scripts.test_launcher scripts.test_launcher_jobs scripts.test_release_metadata` çalıştır. Launcher test akışı zaten bu unittest'leri çalıştırdıysa gerekçesiz tekrar etme.
- [ ] Frontend `npm --prefix frontend run format:check`, `typecheck`, `test:ci`, `build` çalıştır; launcher aynı kontrolleri başarıyla çalıştırdıysa yalnız eksik olanları çalıştır. İlk local Chromium kullanımıysa `frontend/` içinde `npx playwright install chromium`; sonra `npx playwright test e2e/subtask-generator.spec.ts e2e/preferences-content.spec.ts e2e/watcher-settings.spec.ts e2e/session-theme.spec.ts` çalıştır. Testlerin ayarladığı isolated backend/fixture düzenini koru.
- [ ] Build sonrası `backend/` içinde `../.venv/bin/python manage.py collectstatic --clear --noinput` ve `../.venv/bin/python manage.py verify_frontend_artifact` çalıştır; bunlar generated static state'tir.
- [ ] Disposable SQLite ve PostgreSQL'de migration ve concurrency testlerini çalıştır. PostgreSQL bağlantısını external test environment üzerinden ver; credential'ı plana/çıktıya yazma. Yalnız disposable PostgreSQL DB üzerinde migrate, `migrate --check`, `makemigrations --check --dry-run` ve hedef migration/concurrency testlerini çalıştır. PostgreSQL sağlanamıyorsa SQLite başarısını PostgreSQL kanıtı olarak sunma; eksik kontrol ve riski açıkça bildir.
- [ ] Görev diff'ini spec'e göre incele; owner/CSRF, migration graph, CAS, stale signals, draft preservation ve mevcut dirty değişikliklere müdahale kontrolü yap. Yeni bağımsız agent yalnız seçilen workflow veya kullanıcı yetkisi gerektiriyorsa kullanılır.
- [ ] Sonuçta değişen dosyaları, başarılı/başarısız/çalıştırılamayan kontrolleri ve gerçek DB migration'ının çalıştırılmadığını raporla. Implementation onayı verilmeden bu planı uygulama.

## Uygulama önerisi

Bu görev için native/aynı oturumda uygulama önerilir: migration graph, preference yazma yolları ve frontend cutover birbiriyle sıkı bağlıdır; mevcut çalışma ağacında aynı dosyalara ait kullanıcı değişiklikleri vardır. Bağımsız alt ajanlar kullanılacaksa önce açık dosya sahipliği ve mevcut değişikliklerin aktarımı netleştirilmelidir. Kullanıcı planı inceleyip execution method seçmeden implementation başlamaz.

## Uygulama ve doğrulama kaydı — 2026-10-13

- Görev 0–5 uygulandı: integrations sınırı, migration-only history, relation/permission/role taşıması, ayrı JIRA ve Word içerik modelleri, appearance reset/CAS, yeni feature API ve frontend akışı. Migration dosya adları Django tarafından üretildi; explicit M2M state migration nedeniyle integrations içerik migration'ı 0003 oldu.
- Bağımsız incelemenin üç Important bulgusu regresyon testleriyle düzeltildi: hesap başlık taslağı, admin discovery/ilişki yetkileri ve tarihsel JSON null.
- CPython 3.11: etkilenen 254 backend testi, son inceleme regresyonları, SQLite gerçek bağlantı yarışları ve PostgreSQL migration/owner/CSRF/CAS/permission testleri geçti.
- Bütün backend paketi: 1110 test, 1 kapsam dışı mevcut tarih/timezone test hatası, 2 mevcut skip. Hata: compliance.tests.ComplianceApiTests.test_table_filters_and_ordering_are_applied_by_the_server; fixture UTC date kullanırken filtre Europe/Istanbul local date kullanıyor. Assertion kaldırılmadı veya skip eklenmedi.
- Frontend: 323 unit test ve test:ci script'leri, format:check, typecheck, build geçti. Etkilenen 15 Chromium E2E testi geçti; Watcher light/dark ve 375/1440px doğrulandı. Eski login/Excel selector'ları (.heading-dot / Enter Url) HEAD'de de ilgili elementlerle eşleşmiyor; kapsam dışı bırakıldı ve başarısız koşu raporlandı.
- launcher check, 41 launcher/release metadata testi, prod --help, collectstatic, verify_frontend_artifact ve PostgreSQL registry/migration drift/pending kontrolleri geçti.
- Shared/production DB migrate/reset, push/merge veya uygulama source commit'i yapılmadı. Mevcut kullanıcı değişiklikleri korundu; görev kodu çalışma ağacında duruyor.

- Son ek regresyon: admin M2M assignment inline'ları parent change permission ile eski personel erişimini koruyor (SQLite ve PostgreSQL testi geçti). JSON null migration/import preservation ve reactive account-title fence testleri geçti.
- Compliance tarih hatası aynı test UTC timezone diagnostic koşusunda geçti; production yerel tarih davranışı değiştirilmedi.
- Migration şema/model metadata'sı korunurken explicit through modeller ve integration app template/admin discovery kullanıldı. Testlerin oluşturduğu root private_media git dışında tutulur.
