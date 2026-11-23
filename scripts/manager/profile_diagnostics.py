"""Expose actionable Django gate failures without forwarding settings or tracebacks."""
from pathlib import Path
import re


_CHECK_SETTINGS = {
    1: 'DATABASE_URL seçili dağıtımın veritabanı türüyle eşleşmeli', 2: 'Container için Redis CACHE_URL gerekli',
    3: 'SECRET_KEY en az 50 karakterlik üretim anahtarı olmalı',
    4: 'SESSION_COOKIE_SECURE=True ve CSRF_COOKIE_SECURE=True gerekli',
    5: 'SESSION_COOKIE_SAMESITE Lax veya Strict olmalı', 6: 'ALLOWED_HOSTS içinde * kullanılamaz',
    7: 'TRUST_PROXY_HEADERS ve TRUSTED_PROXY_COUNT dağıtım türüyle eşleşmeli',
    8: 'STATIC_ROOT backend kaynak klasöründen ayrı olmalı',
    9: 'PRIVATE_MEDIA_ROOT, STATIC_ROOT dışında olmalı', 10: 'JIRA_URL HTTPS olmalı', 11: 'DOCPROOF_URL HTTPS olmalı',
    12: 'TEAMCENTER_BASE_URL HTTPS olmalı', 13: 'JIRA_SESSION_ENCRYPTION_KEY gerekli',
    18: 'JIRA_SESSION_ENCRYPTION_KEY geçerli Fernet anahtarı olmalı',
    19: 'DOCPROOF_USERNAME, DOCPROOF_PASSWORD', 20: 'DOCPROOF_VERIFY_SSL', 21: 'TEAMCENTER_VERIFY_SSL',
    24: 'SMTP için EMAIL_USE_TLS veya EMAIL_USE_SSL açılmalı', 25: 'FRONTEND_RESET_URL HTTPS /app/login olmalı',
    26: 'FRONTEND_INVITATION_URL HTTPS /app/invite olmalı', 27: 'NUMARATOR_BASE_URL HTTPS olmalı',
    28: 'NUMARATOR_CREDENTIAL_ID ve NUMARATOR_PROJECT_FORMATS gerekli',
    29: 'Numaratör TLS doğrulaması veya CA dosyası gerekli',
    30: 'AWCENTER_DEPLOYMENT_MODE windows-native veya container olmalı',
    31: 'SQLite DATABASE_URL kaynak dışında mutlak bir yol ve DATABASE_CONN_MAX_AGE=0 olmalı',
    32: 'PRIVATE_MEDIA_ROOT kaynak dışında olmalı', 33: 'Windows-native dağıtım Windows gerektirir',
    34: 'DOORS_ENABLED için Windows worker gerekli',
    35: 'CACHE_DIRECTORY kaynak ağacı dışında paylaşılan dosya önbelleği olmalı',
    36: 'STATIC_ROOT, MEDIA_ROOT, MODEL_RUNTIME_DIR ve CUSTOM_TEMPLATE_DIR kaynak dışında mutlak yollar olmalı',
    37: 'JIRA TLS doğrulaması veya CA dosyası gerekli', 38: 'Merkezi AI sağlayıcı ayarları eksik veya geçersiz',
    39: 'DOCPROOF_CERTIFICATE_FILE mevcut bir mutlak yol olmalı', 40: 'Üretim için DEBUG=False gerekli',
}


def django_failure(command, stderr, settings):
    missing = re.search(r"ModuleNotFoundError: No module named '([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)'", stderr)
    if missing:
        return 'Eksik Python modülü: ' + missing.group(1) + '. Kaynaklar sekmesinden Python paketlerini kurun.'
    codes = dict.fromkeys(re.findall(r'\(([a-z][a-z0-9_]*\.[EW][0-9]{3})\)', stderr))
    if codes:
        details = [f'{code} ({_CHECK_SETTINGS[int(code[-3:])]})'
                   if code.startswith('awcenter.E') and int(code[-3:]) in _CHECK_SETTINGS else code for code in codes]
        return 'Kontrol edin: ' + ', '.join(details)
    if command == 'verify_frontend_artifact':
        if 'Frontend entry file is missing:' in stderr:
            return 'Eksik giriş dosyası: ' + str(Path(settings.get('FRONTEND_DIST_DIR', 'frontend/dist')) / 'index.html')
        match = re.search(r'(?:[Aa]rtifact|[Aa]sset) is missing or empty: ((?:/?(?:assets|app|core)/)[A-Za-z0-9_.@/-]+)\s*$',
                          stderr, flags=re.M)
        if match:
            return 'Eksik veya boş frontend dosyası: ' + match.group(1)
        return 'Frontend derlemesini ve toplanmış statik dosyaları kontrol edin.'
    if command == 'collectstatic':
        return 'STATIC_ROOT yolunu ve yazma iznini kontrol edin.'
    if command in ('migrate', 'showmigrations'):
        return 'DATABASE_URL, SQLite erişimi ve migration geçmişini kontrol edin.'
    return ''
