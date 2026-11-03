"""Read-only source diagnostics, independent of provisioning and runtime startup."""
from pathlib import Path
import ssl

from scripts.launcher.discovery import discover_project
from scripts.launcher.installation_sources import _https_url
from scripts.launcher.process import check_cancelled


def run(args, emit):
    from scripts.launcher.installation import source_settings
    from scripts.launcher.installation_sources import _SecureRedirect
    from urllib.request import HTTPSHandler, build_opener
    settings = source_settings(args)
    checks = []
    local_source = settings.offline_dir or (settings.repository and not str(settings.repository).startswith('https://'))
    if settings.mode == 'offline' or local_source:
        from scripts.launcher.installation_dependencies import _offline_dependencies
        source = _offline_dependencies(discover_project(Path(args.source_root)), settings)
        checks.append({'name': 'Offline paket', 'status': 'ready' if source else 'missing',
                       'detail': 'Kilitli bağımlılık envanteri doğrulandı.' if source else 'Doğrulanmış bağımlılık paketi seçin.'})
    if settings.mode != 'offline':
        context = ssl.create_default_context(cafile=str(settings.ca_file) if settings.ca_file else None)
        endpoints = []
        if settings.mode == 'online':
            endpoints.extend([('PyPI', 'https://pypi.org/simple/'), ('npm', 'https://registry.npmjs.org/-/ping')])
        endpoints.extend((name, url) for name, url in (
            ('Kurumsal Python', settings.python_index_url), ('Kurumsal npm', settings.npm_registry_url),
            ('Runtime deposu', str(settings.repository) if settings.repository and str(settings.repository).startswith('https://') else None)) if url)
        opener = build_opener(_SecureRedirect(), HTTPSHandler(context=context))
        for name, url in endpoints:
            check_cancelled()
            try:
                _https_url(url)
                with opener.open(url, timeout=10) as response:
                    ready = response.status == 200
            except Exception:
                ready = False
            checks.append({'name': name, 'status': 'available' if ready else 'missing',
                           'detail': 'HTTPS bağlantısı kuruldu; paket kapsamı kurulumda doğrulanır.' if ready else 'HTTPS erişimi doğrulanamadı; adres, CA ve proxy ayarlarını kontrol edin.'})
        if not checks:
            checks.append({'name': 'Kaynaklar', 'status': 'missing', 'detail': 'Kurumsal paket adreslerini veya yerel offline paketi seçin.'})
    emit({'type': 'checks', 'checks': checks})
