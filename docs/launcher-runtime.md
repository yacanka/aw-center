# AW Center Launcher Runtime Profiles

The root `launcher.py` can prepare and run isolated development and production-like profiles without editing `backend/.env`.

## One-command workflows

```bash
python launcher.py setup
python launcher.py dev
python launcher.py prod --backend-port 8443
```

## Isolation model

Runtime state is generated under `.runtime/` and is intentionally ignored by Git:

- `.runtime/development/backend.env`
- `.runtime/development/db.sqlite3`
- `.runtime/development/media/`
- `.runtime/development/static/`
- `.runtime/production/backend.env`
- `.runtime/production/db.sqlite3`
- `.runtime/production/media/`
- `.runtime/production/static/`
- `.runtime/production/certificates/`

Django reads the selected profile through the `AWCENTER_ENV_FILE` process environment variable. This avoids profile leakage between development and production-like runs.

## Network behavior

- Development uses HTTP and Vite, with the selected backend URL written to `frontend/.env.local`.
- Production-like runs use HTTPS through `backend/run_cheroot.py`.
- If production-like certificates are missing and `openssl` is available, the launcher creates a local self-signed certificate under `.runtime/production/certificates/`.
- Hosts and ports are written into the selected runtime env so `ALLOWED_HOSTS`, CORS, CSRF, and reset URLs stay aligned.

## Security notes

The production-like profile is convenient for local validation. For a real deployment, replace the generated secret key and self-signed certificate with deployment-managed values and certificates.
