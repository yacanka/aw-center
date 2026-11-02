"""Public command arguments and terminal wizard for managed installations."""

from __future__ import annotations

import argparse
from pathlib import Path

from .model import LauncherError, Project


def add_installation_commands(commands) -> None:
    for name, help_text in (
        ("wizard", "Windows kurulum ve çalıştırma menüsü."),
        ("provision", "Ortamı kur veya eksik kurulum adımlarını tamamla."),
        ("doctor", "Ortamı değiştirmeden kurulum durumunu denetle."),
        ("start", "Kayıtlı dev/prod profilini foreground çalıştır."),
        ("prepare-install-bundle", "Tam Windows offline kurulum paketi hazırla."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--profile", choices=("dev", "prod"), default="dev")
        if name in {"wizard", "provision", "prepare-install-bundle"}:
            _sources(command)
            command.add_argument("--assets", type=Path, help="Onaylı asset-manifest.json içeren dizin.")
            command.add_argument("--feature-catalog", type=Path, help="Açıkça onaylanan yerel native araç kataloğu.")
        if name == "provision":
            command.add_argument("--host")
            command.add_argument("--backend-port", type=int)
            command.add_argument("--frontend-port", type=int)
            command.add_argument("--tls-cert-file", type=Path)
            command.add_argument("--tls-key-file", type=Path)
            command.add_argument("--asset-set")
            command.add_argument("--exclude-doors", action="store_true")
            command.add_argument("--migrate", action="store_true", help="Mevcut DB için migration'ı açıkça uygula.")
            command.add_argument("--no-admin", action="store_true", help="İlk yönetici oluşturmayı sonraya bırak.")
        if name == "prepare-install-bundle":
            command.add_argument("--output", type=Path, required=True)


def _sources(command: argparse.ArgumentParser) -> None:
    command.add_argument("--repository", help="HTTPS artifact deposu veya yerel/UNC paket dizini.")
    command.add_argument("--offline-dir", type=Path)
    command.add_argument("--python-index-url", help="Alternatif HTTPS Python Simple API adresi.")
    command.add_argument("--npm-registry-url", help="Alternatif HTTPS npm registry adresi.")
    command.add_argument("--ca-file", type=Path, help="Kurumsal PEM CA bundle.")


def dispatch_installation(project: Project, args: argparse.Namespace) -> int:
    from .installation import doctor, provision, start_profile

    if args.command == "wizard":
        return wizard(project, args)
    if args.command == "doctor":
        return print_checks(doctor(project, args.profile))
    if args.command == "provision":
        return print_checks(provision(project, args))
    if args.command == "start":
        start_profile(project, args.profile)
        return 0
    if args.command == "prepare-install-bundle":
        from .installation import installation_home, require_windows, source_settings
        from .installation_bundle import prepare_install_bundle
        from .installation_state import installation_lock, process_environment
        from .toolchain import ensure_toolchain

        require_windows()
        settings = source_settings(args)
        home = installation_home()
        with installation_lock(home):
            with process_environment(ensure_toolchain(home, settings)):
                output = prepare_install_bundle(project, args.output.absolute(), settings,
                                                assets=args.assets, feature_catalog=args.feature_catalog)
        print(f"Offline paket hazır: {output}")
        return 0
    raise LauncherError("Bilinmeyen kurulum komutu.")


def print_checks(checks: list[dict]) -> int:
    """Keep core readiness distinct from feature completeness and blocking failures."""
    labels = {"ready": "HAZIR", "available": "HAZIR", "missing": "EKSİK",
              "blocked": "ENGEL", "unverified": "DOĞRULANAMADI", "configured": "DOĞRULANAMADI", "degraded": "EKSİK"}
    for check in checks:
        print(f"[{labels.get(check['status'], check['status'].upper())}] {check['name']}: {check['detail']}")
    if any(check["status"] == "blocked" for check in checks):
        print("Temel ortam henüz hazır değil; engelleri giderip işlemi tekrarlayın.")
        return 1
    if any(check["status"] not in {"ready", "available"} for check in checks):
        print("Temel ortam hazır olabilir; yukarıdaki özellik eksikleri ayrıca tamamlanmalıdır.")
        return 2
    print("Kontrol edilen bütün bileşenler hazır.")
    return 0


def wizard(project: Project, initial: argparse.Namespace) -> int:
    """Offer the same workflows as the command line; retain profile choice per session."""
    from .installation import require_windows
    from .parser import build_parser

    require_windows()
    profile = initial.profile
    while True:
        print(f"\nAW Center — {profile.upper()}\n"
              "1. Kur / eksikleri tamamla\n2. Başlat\n3. Durumu denetle\n"
              "4. Dev / prod değiştir\n5. Offline paket hazırla\n0. Çıkış")
        choice = input("Seçim: ").strip()
        if choice == "0":
            return 0
        if choice == "4":
            profile = "prod" if profile == "dev" else "dev"
            continue
        commands = {"1": "provision", "2": "start", "3": "doctor", "5": "prepare-install-bundle"}
        if choice not in commands:
            print("Listeden bir seçim yapın.")
            continue
        arguments = [commands[choice], "--profile", profile]
        if choice in {"1", "5"}:
            from .installation import source_settings
            saved = source_settings(initial, project)
            for flag, label in (
                ("repository", "Alternatif artifact deposu/dizini"),
                ("offline-dir", "Offline paket dizini"),
                ("python-index-url", "Alternatif Python paket indeksi"),
                ("npm-registry-url", "Alternatif npm registry"),
                ("ca-file", "Özel CA dosyası"),
                ("assets", "Onaylı asset dizini"),
                ("feature-catalog", "Onaylı native araç kataloğu"),
            ):
                default = getattr(initial, flag.replace("-", "_"), None) or getattr(saved, flag.replace("-", "_"), None)
                value = input(f"{label} [{default or 'boş bırakılabilir'}]: ").strip() or default
                if value:
                    arguments += ["--" + flag, str(value)]
            if choice == "1" and profile == "prod":
                for flag, label in (("host", "Statik IPv4"), ("tls-cert-file", "TLS sertifikası"),
                                    ("tls-key-file", "TLS private key dosyası")):
                    value = input(f"{label} [mevcut profil varsa boş bırak]: ").strip()
                    if value:
                        arguments += ["--" + flag, value]
            if choice == "5":
                output = input("Yeni offline paket çıktı dizini: ").strip()
                if not output:
                    continue
                arguments += ["--output", output]
        try:
            dispatch_installation(project, build_parser().parse_args(arguments))
        except KeyboardInterrupt:
            print("\nİşlem durduruldu; menüye dönüldü.")
        except LauncherError as error:
            print(f"İşlem tamamlanamadı: {error}")
        except (OSError, ValueError):
            print("İşlem tamamlanamadı. Kurulum raporunu ve doctor sonuçlarını inceleyin.")
