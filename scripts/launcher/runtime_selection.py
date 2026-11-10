"""One system-first selection policy for source, frozen Manager and CLI."""
from pathlib import Path

def _python_choice(args):
    if getattr(args, 'install_python', False):
        return {}
    if not getattr(args, 'python_executable', None):
        from scripts.launcher.system_python import PROBE_TIMEOUT_SECONDS, SystemPythonError, discover_python
        progress = getattr(args, 'progress', None)
        if callable(progress):
            progress(f'Sistem Python’u denetleniyor; her aday için en fazla {PROBE_TIMEOUT_SECONDS} saniye beklenir')
        selection = getattr(args, 'python_command', None)
        try:
            args.python_executable = discover_python(selection) if selection else discover_python()
        except SystemPythonError as error:
            args.python_probe_error = error
            if selection or error.reason in {'timeout', 'start_failed', 'process_failed', 'invalid_response'}:
                raise
            # Resolve the choice once so later provisioning cannot repeat a
            # failed automatic search or accidentally ignore managed fallback.
            args.install_python = True
            if callable(progress):
                progress('Uygun sistem Python bulunamadı; yönetilen Python hazırlanacak')
            return {}
    return {'python_executable': args.python_executable}


def _node_choice(args):
    if getattr(args, 'install_node', False):
        return {}
    if getattr(args, 'node_executable', None):
        return {'node_executable': args.node_executable}
    if getattr(args, '_node_checked', False):
        return {}
    from scripts.launcher.system_node import SystemNodeError, discover_node
    progress = getattr(args, 'progress', None)
    if callable(progress):
        progress('Sistem Node.js kurulumu denetleniyor')
    selection = getattr(args, 'node_command', None)
    from time import monotonic
    args.node_probe_deadline = monotonic() + 60
    try:
        args.node_executable = discover_node(selection) if selection else discover_node()
    except SystemNodeError as error:
        args.node_probe_error = error
        if selection or error.reason in {'timeout', 'start_failed', 'process_failed', 'invalid_response'}:
            raise
        if callable(progress):
            progress('Uygun sistem Node.js bulunamadı; yönetilen Node.js hazırlanacak')
        args._node_checked = True
        return {}
    args._node_checked = True
    return {'node_executable': args.node_executable}


def tool_choices(args, profile=None):
    if profile is not None:
        # A prepared venv stays bound to its recorded interpreter. Explicit
        # replacements still pass the venv identity check before any install.
        if not getattr(args, 'python_command', None) and not getattr(args, 'install_python', False) and not getattr(args, 'python_executable', None):
            args.python_executable = Path(profile['python_executable']) if profile.get('python_executable') else None
            args.install_python = args.python_executable is None
        if not getattr(args, 'node_command', None) and not getattr(args, 'install_node', False) and not getattr(args, 'node_executable', None):
            args.node_executable = Path(profile['node_executable']) if profile.get('node_executable') else None
            args._node_checked = True
    return {**_python_choice(args), **_node_choice(args)}

