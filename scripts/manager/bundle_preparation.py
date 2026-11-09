"""Resumable Windows Manager preparation in a private, worker-locked workspace."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from scripts.launcher import installation_bundle as bundle
from scripts.launcher import toolchain
from scripts.launcher.certificates import package_trust_environment
from scripts.launcher.installation_permissions import require_unlinked
from scripts.launcher.installation_sources import ArtifactDownloadError, fetch_artifact, _verify
from scripts.launcher.installation_state import private_directory, process_environment
from scripts.launcher.model import LauncherError, Scope
from scripts.launcher.offline_manifest import artifact_metadata, file_sha256, lock_metadata
from scripts.launcher.package_cache import acquire_cached
from scripts.launcher.process import OperationCancelled
from .distribution import MANIFEST
from .payload import prepare_source_payload


class BundleInputsError(LauncherError):
    code = 'bundle_waiting_for_files'
    remedy = ('Dosyadan ekle ile katalogdaki runtime arşivini veya Offline depo seç ile '
              'doğrulanmış bağımlılık paketini seçip Tekrar denetle ve dene düğmesine basın.')

    def __init__(self, items):
        super().__init__('Dosya bekleniyor · Windows x64\n' + '\n'.join(items))


def _import_runtime(source, catalog, cache):
    require_unlinked(source)
    artifact = next((item for item in catalog.values() if item.filename == source.name), None)
    if artifact is None:
        raise BundleInputsError(['Dosya adı Windows x64 runtime kataloğunda bulunamadı.'])
    try:
        _verify(source, artifact)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            staged = Path(temporary) / artifact.filename
            shutil.copyfile(source, staged)
            _verify(staged, artifact)
            os.replace(staged, cache / artifact.filename)
    except (LauncherError, FileNotFoundError):
        raise BundleInputsError([f'{artifact.filename} · dosya eksik veya SHA-256 uyuşmuyor.']) from None


def _acquire_runtime(artifact, cache, settings, issues):
    try:
        return fetch_artifact(artifact, cache, settings)
    except OperationCancelled:
        raise
    except LauncherError as error:
        if isinstance(error, ArtifactDownloadError):
            reason = str(error)
        elif 'artifact unavailable' in str(error):
            reason = 'Seçili kaynaklarda bulunamadı'
        elif 'SHA-256' in str(error):
            reason = 'SHA-256 doğrulaması başarısız'
        else:
            raise
        issues.append(f'{artifact.filename} ({artifact.version}) · {reason}')
        return None


def _prepare_tools(home, catalog, settings, hosts, issues):
    from scripts.launcher.system_python import discover_python, SystemPythonError
    from scripts.launcher.system_node import discover_node, find_npm_cli, SystemNodeError
    paths = {}
    cache = home / 'cache/runtimes'
    private_directory(home / 'runtimes', root=home)
    for name in ('python', 'node', 'npm'):
        artifact = catalog[name]
        if name in hosts:
            try:
                paths[name] = (discover_python if name == 'python' else discover_node)(hosts[name])
            except (SystemPythonError, SystemNodeError) as error:
                issues.append(f'{name} · {error} {error.remedy}')
            continue
        if name == 'npm' and 'node' in hosts:
            cli = find_npm_cli(paths['node'], artifact.version, compatible=True) if 'node' in paths else None
            if cli:
                paths[name] = cli
            else:
                issues.append(bundle.BundleHostRuntimeError('npm').remedy)
            continue
        archive = _acquire_runtime(artifact, cache, settings, issues)
        if archive is None:
            continue
        if name != 'npm' or 'node' in paths:
            paths[name] = toolchain._install(home, artifact, archive, node=paths.get('node'), progress=settings.progress)
    return paths


def _locked_inputs(project):
    # Only reviewed package-name/version syntax may enter the operator report.
    # Exclude URLs, command output and arbitrary metadata from local lock files.
    wheels = re.findall(r'^([A-Za-z0-9_.-]+==[A-Za-z0-9.+!-]+)',
                        project.requirements.read_text(encoding='utf-8'), re.MULTILINE)
    packages = json.loads((project.frontend / 'package-lock.json').read_text(encoding='utf-8'))
    npm = set()
    for path, metadata in packages.get('packages', {}).items():
        name = path.rsplit('node_modules/', 1)[-1]
        version = metadata.get('version', '')
        if (re.fullmatch(r'(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+', name)
                and isinstance(version, str) and re.fullmatch(r'[A-Za-z0-9.+-]+', version)
                and _supports_platform(metadata.get('os', []), 'win32')
                and _supports_platform(metadata.get('cpu', []), 'x64')):
            npm.add(f'{name}@{version}')
    return {'wheels': sorted(set(wheels)), 'npm': sorted(npm)}


def _supports_platform(selectors, value):
    allowed = [item for item in selectors if not item.startswith('!')]
    return '!' + value not in selectors and (not allowed or value in allowed)


def _report_pending_packages(settings, packages, issues):
    for kind, names in packages.items():
        if not any(issue.startswith(kind + ' ·') for issue in issues):
            continue
        for start in range(0, len(names), 12):
            settings.report(f'{kind} · doğrulanmayı bekleyen kilit girdileri · ' +
                            ', '.join(names[start:start + 12]))


def _source_identity(settings):
    """Keep retries within the selected policy without persisting source details."""
    if settings.ca_file:
        require_unlinked(settings.ca_file)
    values = [settings.mode, str(settings.repository or ''), str(settings.offline_dir or ''),
              settings.python_index_url, settings.npm_registry_url,
              file_sha256(settings.ca_file) if settings.ca_file else None,
              [str(path) for path in settings.runtime_dirs]]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _packages(project, work, temporary, settings, paths, identity, issues):
    from scripts.launcher.installation_dependencies import PackageSourceError, PackageTimeoutError
    names = {'python': 'AWCENTER_MANAGED_PYTHON', 'node': 'AWCENTER_MANAGED_NODE', 'npm': 'AWCENTER_MANAGED_NPM_CLI'}
    env = {names[name]: str(path) for name, path in paths.items()}
    directories = [path.parent for path in paths.values()]
    if 'npm' in paths and paths['npm'].is_relative_to(work / 'runtimes'):
        directories.insert(0, paths['npm'].parent.parent.parent / 'bin')
    if 'python' in paths:
        directories.append(paths['python'].parent / 'Scripts')
    env['PATH'] = os.pathsep.join([*map(str, directories), os.environ.get('PATH', '')])
    env.update(toolchain.MANAGED_RUNTIME_ENVIRONMENT)
    if settings.mode == 'offline':
        env.update(PIP_NO_INDEX='1', NPM_CONFIG_OFFLINE='true')
    results = {}
    versions = {}
    with process_environment(env):
        for kind, needed in (('wheels', ('python',)), ('npm', ('node', 'npm'))):
            if any(tool not in paths for tool in needed):
                issues.append(f'{kind} · kilitli paketlerin doğrulanması için {" + ".join(needed)} bekleniyor.')
                continue
            component_versions = bundle._component_versions(project, env, kind)
            versions.update(component_versions)
            candidate = temporary / kind
            locks = (project.requirements,) if kind == 'wheels' else (project.package_json, project.frontend / 'package-lock.json')
            def acquire():
                with package_trust_environment(env, python=paths.get('python') if kind == 'wheels' else None,
                                               node=paths.get('node') if kind == 'npm' else None,
                                               ca_file=settings.ca_file, progress=settings.report) as trusted:
                    if kind == 'wheels':
                        bundle._acquire_wheels(project, candidate, settings, trusted)
                    else:
                        bundle._acquire_npm(project, candidate, settings, trusted)
                        bundle._verify_npm_offline(project, candidate, trusted)
                return True
            try:
                results[kind] = acquire_cached(work / 'p', kind=kind, locks=locks,
                    target=[bundle.target_metadata(), identity if kind == 'npm' else 'wheels-v1', component_versions],
                    mode=settings.mode, source=_source_identity(settings), candidate=candidate,
                    acquire=acquire, report=settings.report)
            except LauncherError as error:
                if not isinstance(error, (PackageSourceError, PackageTimeoutError)) and 'are unavailable from' not in str(error):
                    raise
                issues.append(f'{kind} · {locks[-1].name} için doğrulanmış {kind} deposu gerekli.')
        if issues:
            raise BundleInputsError(issues)
        dependencies = temporary / 'dependencies'
        dependencies.mkdir()
        for kind, data in results.items():
            shutil.copytree(data, dependencies / ('npm-cache' if kind == 'npm' else kind))
        manifest = {'format_version': 1, 'target': bundle.target_metadata(), 'commit': bundle.source_provenance(project),
                    'toolchain': versions,
                    'locks': lock_metadata(project, Scope()), 'artifacts': artifact_metadata(dependencies)}
        (dependencies / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return dependencies


def _reuse_output(project, output, saved, external, settings):
    previous = Path(saved['output'])
    require_unlinked(previous)
    if output != previous and output.is_relative_to(previous):
        raise LauncherError('installation bundle output must be outside all input directories')
    if not previous.is_dir():
        return None
    try:
        # The private receipt pins the manager inventory from a fully verified
        # publication. One strict inventory pass verifies the identical bytes.
        if file_sha256(previous / MANIFEST) != saved['digest']:
            return None
        manager = bundle._json_object(previous / MANIFEST)
        if set(manager.get('host_runtimes', {})) != external:
            return None
        # Installed media may acquire a private .env, database or uploads. Only
        # pristine exports are eligible for redistribution.
        bundle._verify_inventory(previous, manager['artifacts'], exclude=(MANIFEST,))
    except OperationCancelled:
        raise
    except (LauncherError, OSError):
        settings.report('Önceki çıktı değişmiş; mevcut dosyalar korunarak yeni paket hazırlanıyor')
        return None
    settings.report('Önceki paket doğrulandı ve yeniden kullanılıyor')
    if previous == output or (previous.parent == output.parent and output.name.startswith('AWCenter-offline-')):
        return previous
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.copy-') as copying:
        copied = Path(copying) / 'bundle'
        copied.mkdir()
        (copied / '_internal').mkdir()
        for entry in [*manager['artifacts'], {'path': MANIFEST}]:
            relative = bundle._relative_path(entry['path'])
            original = bundle._safe_path(previous, previous / relative)
            destination = copied / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
        bundle.verify_install_bundle(project, copied)
        if file_sha256(copied / MANIFEST) != saved['digest']:
            raise LauncherError('Manager kopyası doğrulanamadı.')
        copied.rename(output)
    return output


def _save_progress(temporary, receipt, values):
    pending = temporary / 'receipt.json'
    pending.write_text(json.dumps(values), encoding='utf-8')
    os.replace(pending, receipt)


def prepare(project, output, settings, distribution, workspace, hosts, import_file, assets, feature_catalog):
    from scripts.build_manager import freeze_manager, _builder_wheels
    from scripts.launcher.installation_features import read_feature_catalog
    target = bundle._require_windows_target()
    catalog = bundle._catalog()
    work = private_directory(workspace)
    cache = private_directory(work / 'cache/runtimes', root=work)
    features = read_feature_catalog(feature_catalog) if feature_catalog else {}
    if import_file:
        _import_runtime(import_file, {**catalog, **features}, cache)
    packages = _locked_inputs(project)
    settings.report(f'Windows x64 · {len(packages["wheels"])} Python ve {len(packages["npm"])} npm kilit girdisi')
    settings = replace(settings, mode='restricted' if settings.mode == 'online' else settings.mode, runtime_dirs=(cache, *settings.runtime_dirs))
    external = set(hosts)
    if 'node' in hosts:
        external.add('npm')
    with tempfile.TemporaryDirectory(dir=work, prefix='.b-') as stage:
        temporary = Path(stage)
        fingerprint = prepare_source_payload(project, temporary / 'source')['fingerprint']
        identity = hashlib.sha256(json.dumps([fingerprint, target, sorted(external),
            _source_identity(settings),
            bundle._runtime_metadata(catalog), bundle.verify_asset_source(assets) if assets else None,
            file_sha256(feature_catalog) if feature_catalog else None,
            file_sha256(distribution / MANIFEST) if distribution else None], sort_keys=True).encode()).hexdigest()
        receipt = work / (identity + '.json')
        require_unlinked(receipt)
        if receipt.is_file():
            saved = bundle._json_object(receipt)
            if saved.get('status') == 'waiting':
                settings.report('Kayıtlı hazırlık açıldı; eksik girdiler yeniden denetleniyor')
            else:
                reused = _reuse_output(project, output, saved, external, settings)
                if reused:
                    return reused
        issues = []
        settings.report('Windows x64 · Python, Node.js, npm, wheels ve npm-cache kaynakları denetleniyor')
        sources = ['kalıcı önbellek', 'seçili yerel depolar']
        if settings.mode != 'offline' and settings.repository:
            sources.append('seçili kurum deposu')
        if settings.mode == 'restricted':
            sources.append('resmî kaynak')
        settings.report('Aranacak kaynaklar · ' + ', '.join(sources))
        paths = _prepare_tools(work, catalog, settings, hosts, issues)
        for artifact in features.values():
            _acquire_runtime(artifact, cache, settings, issues)
        frozen_manager = work / ('manager-' + fingerprint[:16])
        require_unlinked(frozen_manager)
        if distribution is None and not frozen_manager.exists() and settings.mode == 'offline' and not _builder_wheels(settings):
            issues.append('AWCenterManager.exe + _internal · aynı sürümün hazır Manager dizinini seçin '
                          'veya depoya manager-wheels ekleyin.')
        try:
            dependencies = _packages(project, work, temporary, settings, paths, fingerprint, issues)
        except BundleInputsError as error:
            _report_pending_packages(settings, packages, issues)
            _save_progress(temporary, receipt, {'status': 'waiting', 'inputs': issues})
            issues.append('Aranan kaynaklar · ' + ', '.join(sources))
            raise BundleInputsError(issues) from error
        if distribution is None:
            from .distribution import verify_distribution
            distribution = frozen_manager
            if not distribution.exists():
                frozen = freeze_manager(project, temporary / 'manager', settings, python=paths['python'])
                frozen.rename(distribution)
            if verify_distribution(distribution)['source_fingerprint'] != fingerprint:
                raise LauncherError('Manager source fingerprint verification failed')
        result = bundle.prepare_install_bundle(project, output, settings, assets=assets, feature_catalog=feature_catalog,
            manager_distribution=distribution, external_runtimes=external, prepared_dependencies=dependencies)
        _save_progress(temporary, receipt, {'status': 'ready', 'output': str(result), 'digest': file_sha256(result / MANIFEST)})
        return result
