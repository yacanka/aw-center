"""Managed first-install and foreground lifecycle orchestration.

Existing setup/dev/prod retain their conservative contracts. Only explicit
provisioning creates profiles, prepares dependencies or initializes a database.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path

from . import runtime
from .installation_dependencies import capture, install_dependencies
from .installation_profiles import (
    installation_home, inspect_profile, load_profile, profile_environment,
    provision_profile, read_profile_environment,
)
from .installation_readiness import wait_until_ready
from .installation_sources import SourceSettings, _https_url
from .installation_state import (installation_lock, load_sources, private_directory,
                                 process_environment, runtime_session, save_report, save_sources)
from .model import LauncherError, Project, Scope
from .process import controlled_run, environment, non_notification_environment
from .toolchain import ensure_toolchain, inspect_toolchain


def require_windows() -> None:
    if os.name != "nt" or platform.machine().casefold() not in {"amd64", "x86_64"}:
        raise LauncherError("Kurulum yardımcısı yalnız Windows x64 destekler. Diğer platformlarda mevcut launcher komutlarını kullanın.")


def source_settings(args, project: Project | None = None) -> SourceSettings:
    """Resolve CLI defaults or isolate explicit desktop form choices from them."""
    use_saved = getattr(args, "use_saved_sources", True)
    saved = load_sources(installation_home()) if use_saved and os.environ.get("LOCALAPPDATA") else {}
    repository = (getattr(args, "repository", None)
                  or (os.environ.get("AWCENTER_PACKAGE_REPOSITORY") if use_saved else None)
                  or saved.get("repository"))
    offline = (getattr(args, "offline_dir", None)
               or (os.environ.get("AWCENTER_OFFLINE_DIR") if use_saved else None)
               or saved.get("offline_dir"))
    if not offline and (Path.cwd() / "install-manifest.json").is_file():
        offline = Path.cwd()
    if not offline and project and (project.root.parent / "install-manifest.json").is_file():
        offline = project.root.parent
    python_index = getattr(args, "python_index_url", None) or saved.get("python_index_url")
    npm_registry = getattr(args, "npm_registry_url", None) or saved.get("npm_registry_url")
    for url in (python_index, npm_registry):
        if url:
            _https_url(url)
    if repository and "://" in str(repository):
        _https_url(str(repository))
    return SourceSettings(repository=repository, offline_dir=Path(offline) if offline else None,
                          mode=getattr(args, "source_mode", None) or saved.get("mode", "online"),
                          python_index_url=python_index, npm_registry_url=npm_registry,
                          ca_file=Path(getattr(args, "ca_file", None) or saved["ca_file"]) if getattr(args, "ca_file", None) or saved.get("ca_file") else None)


def backend_inspection(project: Project, profile: dict) -> dict:
    """Read a bounded, declared JSON result; do not expose stderr or raw configuration."""
    if not project.python.is_file():
        return {"schema": "error", "admin_exists": None, "diagnostics": []}
    values = environment({**profile_environment(profile), "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        result = controlled_run([str(project.python), "-m", "scripts.launcher.installation_probe", "inspect"],
                                cwd=project.root, env=values, text=True, capture_output=True,
                                check=False, timeout=30)
        if result.returncode or len(result.stdout) > 64 * 1024:
            raise ValueError
        content = json.loads(result.stdout)
        if not isinstance(content, dict) or content.get("schema") not in {"ready", "pending", "missing", "error"}:
            raise ValueError
        return content
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"schema": "error", "admin_exists": None, "diagnostics": []}


def _core_checks(project: Project, profile: dict) -> list[dict]:
    checks = inspect_profile(project, profile)
    for check in checks:
        if check["status"] not in {"ready", "available"}:
            check["status"] = "blocked"
    if any(check["status"] == "blocked" for check in checks):
        return checks
    backend = backend_inspection(project, profile)
    state = backend["schema"]
    checks.append({"name": "database", "status": "ready" if state == "ready" else "blocked",
                   "detail": "Şema güncel." if state == "ready" else "Şema eksik veya doğrulanamadı; açık provision/migration işlemi gerekli."})
    checks.append({"name": "administrator", "status": "ready" if backend.get("admin_exists") else "missing",
                   "detail": "Aktif yönetici mevcut." if backend.get("admin_exists") else "İlk yönetici oluşturulmalı."})
    if profile["name"] == "dev":
        ready = (project.frontend / "node_modules" / ".package-lock.json").is_file()
        checks.append({"name": "frontend-packages", "status": "ready" if ready else "blocked",
                       "detail": "Frontend paketleri mevcut." if ready else "Frontend npm kurulumu gerekli."})
    return checks


def doctor(project: Project, name: str) -> list[dict]:
    """Inspect only: no downloads, directory creation, repairs or migrations."""
    try:
        home = installation_home()
        profile = load_profile(project, name, home)
    except (LauncherError, OSError):
        return [{"name": "profile", "status": "blocked", "detail": "Profil eksik veya güvenli biçimde okunamıyor; provision çalıştırın."}]
    checks = inspect_toolchain(home)
    for check in checks:
        if check["status"] != "ready":
            check["status"] = "blocked"
    checks.extend(_core_checks(project, profile))
    from .installation_features import inspect_features
    checks.extend(inspect_features(project, profile))
    return checks


def _django(project: Project, profile: dict, arguments: list[str], tool_env: dict) -> None:
    role = {} if arguments[:2] == ["check", "--deploy"] else non_notification_environment()
    result = capture([project.python, project.manage_py, *arguments], project,
                     {**tool_env, **profile_environment(profile), **role})
    if result.returncode:
        raise LauncherError("Django kurulum kontrolü başarısız; yapılandırma değerleri ve komut çıktısı gizlendi.")


def _initialize_schema(project: Project, profile: dict, args, tool_env: dict) -> None:
    state = backend_inspection(project, profile)
    if state["schema"] == "error":
        raise LauncherError("Backend yapılandırması veya veritabanı doğrulanamadı; migration uygulanmadı.")
    database = Path(read_profile_environment(profile)["DATABASE_URL"].removeprefix("sqlite:///"))
    fresh = not database.exists()
    if state["schema"] != "ready" and not fresh and not args.migrate:
        raise LauncherError("Mevcut veritabanı migration bekliyor. Yedeği doğrulayıp provision --migrate ile açıkça uygulayın.")
    if fresh or args.migrate:
        _django(project, profile, ["migrate", "--noinput"], tool_env)
    _django(project, profile, ["migrate", "--check"], tool_env)
    _django(project, profile, ["check_project_registry"], tool_env)


def _initial_admin(project: Project, profile: dict, args, tool_env: dict) -> None:
    if args.no_admin or backend_inspection(project, profile).get("admin_exists"):
        return
    provider = getattr(args, "admin_provider", None)
    options = {}
    operation = "initial-admin"
    if provider is not None:
        credentials = provider()
        if (not isinstance(credentials, dict) or set(credentials) != {"username", "password"}
                or any(not isinstance(value, str) or not value for value in credentials.values())):
            raise LauncherError("İlk yönetici bilgileri sağlanmadı; mevcut hesaplar değiştirilmedi.")
        operation = "initial-admin-json"
        options = {"input": json.dumps(credentials), "text": True, "capture_output": True, "timeout": 60}
    result = controlled_run([str(project.python), "-m", "scripts.launcher.installation_probe", operation],
                            cwd=project.root, env=environment({**tool_env, **profile_environment(profile)}),
                            check=False, safe_boundary=True, **options)
    if result.returncode:
        raise LauncherError("İlk yönetici oluşturulamadı; mevcut hesaplar değiştirilmedi.")


def _select_assets(project: Project, profile: dict, source: Path | None, requested: str | None) -> dict:
    """Import first, then explicitly rebind only model/template paths, preserving keys."""
    from .installation_bundle import verify_asset_source
    from .installation_features import import_asset_set
    from .installation_profiles import update_asset_set

    if source:
        manifest = verify_asset_source(Path(source))
        if requested and requested != manifest["asset_set"]:
            raise LauncherError("Seçilen asset-set ile onaylı kaynak kimliği uyuşmuyor.")
        import_asset_set(Path(source), Path(profile["installation_home"]))
        requested = manifest["asset_set"]
    elif requested and requested != profile["asset_set"]:
        existing = Path(profile["installation_home"]) / "assets" / "sets" / requested
        if verify_asset_source(existing)["asset_set"] != requested:
            raise LauncherError("Asset-set doğrulanamadı; profil değiştirilmedi.")
    if requested and requested != profile["asset_set"]:
        return update_asset_set(project, profile, requested)
    return profile


def provision(project: Project, args) -> list[dict]:
    require_windows()
    home = installation_home()
    settings = source_settings(args, project)
    bundle = None
    if settings.offline_dir and (settings.offline_dir / "install-manifest.json").is_file():
        from .installation_bundle import verify_install_bundle
        bundle = verify_install_bundle(project, settings.offline_dir)
    with installation_lock(home):
        def phase(label):
            progress = getattr(args, "progress", None)
            if progress is not None:
                progress(label)
            save_report(home, args.profile, [{"name": "provision", "status": "blocked",
                        "detail": f"Son başlatılan aşama henüz tamamlanmadı: {label}. İşlemi tekrar çalıştırabilirsiniz."}])

        phase("özel profil")
        options = {name: getattr(args, name, None) for name in (
            "host", "backend_port", "frontend_port", "tls_cert_file", "tls_key_file", "asset_set", "exclude_doors")}
        assets = getattr(args, "assets", None)
        if bundle and bundle.get("asset_set") and not assets:
            assets = settings.offline_dir / "assets" / bundle["asset_set"]
        if assets and not options["asset_set"]:
            from .installation_bundle import verify_asset_source
            options["asset_set"] = verify_asset_source(Path(assets))["asset_set"]
        profile = provision_profile(project, args.profile, home, **options)
        print(f"Özel yapılandırma dosyası: {profile['env_file']}")
        profile_environment(profile)  # Reject inherited application overrides before package changes.
        save_sources(home, settings)
        phase("runtime hazırlığı")
        tool_env = ensure_toolchain(home, settings)
        phase("kilitli bağımlılıklar")
        install_dependencies(project, settings, tool_env)
        phase("veritabanı şeması")
        _initialize_schema(project, profile, args, tool_env)
        phase("ilk yönetici")
        _initial_admin(project, profile, args, tool_env)
        phase("ek araçlar ve varlıklar")
        profile = _select_assets(project, profile, assets, getattr(args, "asset_set", None))
        from .installation_features import install_features
        feature_options = {}
        if assets:
            feature_options["assets"] = assets
        if getattr(args, "feature_catalog", None):
            feature_options["feature_catalog"] = args.feature_catalog
        elif bundle and bundle.get("feature_catalog"):
            # The explicitly selected, verified release bundle is the authority.
            # Copy its declaration to private storage before the catalog reader
            # enforces owner-only permissions on subsequently consumed metadata.
            from .installation_permissions import secure_path
            directory = private_directory(home / "config")
            destination = directory / "bundle-features.catalog.json"
            if destination.exists():
                from .installation_permissions import require_private
                require_private(destination)
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                temporary = Path(output.name)
                secure_path(temporary)
                output.write((settings.offline_dir / "feature-catalog.json").read_bytes())
            os.replace(temporary, destination)
            feature_options["feature_catalog"] = destination
        features = install_features(project, profile, settings, **feature_options)
        if profile["name"] == "prod":
            phase("production build ve deployment kontrolleri")
            # Build through the pinned npm shim, not the npm bundled with Node.
            from .installation_dependencies import _npm_command
            result = capture([*_npm_command(tool_env), "run", "build", "--prefix", project.frontend], project, tool_env)
            if result.returncode:
                raise LauncherError("Production frontend build başarısız; servis başlatılmadı.")
            _django(project, profile, ["check", "--deploy", "--fail-level", "ERROR"], tool_env)
            _django(project, profile, ["collectstatic", "--clear", "--noinput"], tool_env)
            _django(project, profile, ["verify_frontend_artifact"], tool_env)
        checks = _core_checks(project, profile) + features
        save_report(home, profile["name"], checks)
        return checks


def _worker_ready(project: Project, directory: Path) -> bool:
    command = [project.python, project.manage_py, "check_job_worker_health", "--worker-id-file", directory / "job"]
    try:
        result = subprocess.run([str(part) for part in command], cwd=project.root,
                                env=environment(), capture_output=True, text=True, timeout=5, check=False)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def start_profile(project: Project, name: str, *, on_ready=None) -> None:
    require_windows()
    profile = load_profile(project, name)
    home = Path(profile.get("installation_home", Path(profile["env_file"]).parent.parent))
    checks = inspect_toolchain(home)
    if any(check["status"] != "ready" for check in checks):
        raise LauncherError("Managed runtime eksik veya değişmiş; açık provision gerekli.")
    from .toolchain import toolchain_environment
    from .installation_features import feature_environment
    tools = toolchain_environment(home)
    with process_environment(tools):
        selected = profile_environment(profile)
        pointers = {key: selected[key] for key in ("AWCENTER_ENV_FILE", "DJANGO_SETTINGS_MODULE") if key in selected}
        values = {**tools, **pointers, **feature_environment(project, profile)}
    with process_environment(values), runtime_session(profile) as directory:
        _django(project, profile, ["migrate", "--check"], {})
        def ready(processes):
            wait_until_ready(processes, profile, directory,
                             worker_check=lambda: _worker_ready(project, directory))
            if on_ready is not None:
                on_ready(profile)
        options = {"migrate": False, "exclude_doors": profile.get("exclude_doors", False),
                   "ready": ready, "worker_heartbeat_dir": directory, "protect_credentials": True}
        if name == "dev":
            runtime.dev(project, Scope(), host=profile["host"], backend_port=profile["backend_port"],
                        frontend_port=profile["frontend_port"], no_backend_reload=False, **options)
        else:
            runtime.prod(project, host=profile["host"], port=profile["backend_port"],
                         env_file=Path(profile["env_file"]), certificate_file=Path(profile["tls_cert_file"]),
                         private_key_file=Path(profile["tls_key_file"]), **options)
