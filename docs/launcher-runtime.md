# Local Django + Vue launcher

Kök `launcher.py`, repository içindeki local setup, quality, development ve offline packaging akışlarının ince girişidir. Production deployment aracı veya server supervisor'u değildir.

## Sözleşme

- CPython 3.11+ ister ve `.venv` sürümünü doğrular.
- `.env`, `.env.local`, PID veya kalıcı runtime state yazmaz.
- Child process'ler mevcut shell environment'ını miras alır; host/port ve `VITE_API_URL` yalnız process-local override'dır.
- Migration örtülü uygulanmaz. Yalnız `dev --migrate` açıkça verilirse startup öncesi `migrate --noinput` çalışır.
- Dolu veya geçersiz portta başka port seçmez; fail-fast durur.
- `dev`, seçilen scope'a göre Django/Vite ile mevcut durable job, password-reset/compliance notification ve cleanup command'larını foreground child process olarak supervise eder.
- Offline dependency bundle OS, architecture, Python, lock digest ve artifact SHA-256 manifest'ine bağlıdır; başka target veya değiştirilmiş bundle fail-closed reddedilir.
- Packaging yalnız izinli Git kaynaklarını alır; secret env, key/certificate, database, media, virtualenv, dependency tree ve generated build state'ini dışarıda bırakır. Symlink ve path escape reddedilir.

## Komutlar

```bash
python launcher.py setup
python launcher.py setup --skip-backend
python launcher.py setup --skip-frontend

python launcher.py check
python launcher.py test

python launcher.py dev --backend-port 8000 --frontend-port 5173
python launcher.py dev --migrate

python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
python launcher.py package-changes
```

`check` backend için Django system check, isolated in-memory migration drift/plan; frontend için format ve typecheck çalıştırır. `test` full Django, launcher/release metadata unittest'leri ve frontend `test:ci` çalıştırır.

Playwright browser cache'i launcher tarafından örtülü kurulmaz. İlk kullanımda `frontend/` içinde `npx playwright install chromium`, ardından repository kökünde `npm --prefix frontend run test:e2e` çalıştırın; release gate bu browser smoke'u ayrıca ister.

Her komutun parametreleri için:

```bash
python launcher.py --help
python launcher.py dev --help
python launcher.py package-offline --help
```

## Offline akış

İnternet erişimli, hedefle aynı OS/architecture/Python ortamında:

```bash
python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
```

Offline hedefte ZIP açıldıktan sonra:

```bash
python launcher.py setup --mode offline --offline-dir offline
```

Manifest target veya lock dosyalarıyla eşleşmiyorsa yeni bundle hazırlayın; doğrulamayı atlamayın.

## Production ayrımı

Production lifecycle `backend/Dockerfile`, `docker-compose.yml`, Nginx config'leri ve orchestrator tarafından yönetilir. Migration, deploy checks ve operator bootstrap one-shot container komutlarıdır. Ayrıntılar [deployment.md](deployment.md) içindedir.
