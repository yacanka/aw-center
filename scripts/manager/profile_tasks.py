"""Desktop profile actions over the Manager's existing private worker pipe."""
import threading

from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled, check_cancelled, operation_control
from .paths import worker_directory
from .transport import WorkerSession


def start_task(action, values, notify, ask):
    """Run outside the Tk thread. Deliver completion after process-tree cleanup."""
    completion = ''

    def event(message):
        nonlocal completion
        kind = message['type']
        if kind == 'input':
            session.send({'type': 'admin', 'value': ask()})
        elif kind == 'done':
            completion = 'Durduruldu.' if message.get('cancelled') else (
                'Tamamlandı.' if message.get('ok') else 'İşlem başarısız.')
        elif kind == 'profile':
            notify('tls', message['paths'])
        else:
            notify(kind, message.get('message', ''))

    session = WorkerSession(event)

    def work():
        try:
            session.run({'profile_action': action, 'values': dict(values)})
        finally:
            notify('done', completion)

    threading.Thread(target=work, name='awcenter-profile-action', daemon=True).start()
    return session


def execute_profile(request, emit, ask, stop):
    from scripts.launcher.installation_profiles import installation_home
    from scripts.launcher.resource_locks import resource_locks, path_claims
    from .operations import _system_failure

    def notify(kind, text):
        check_cancelled()
        emit({'type': 'status' if kind == 'phase' else kind, 'message': text})

    try:
        action = request['profile_action']
        values = dict(request['values'])
        source = worker_directory()
        values['source_root'] = str(source)
        profile = values['profile']
        if profile not in {'dev', 'prod'}:
            raise LauncherError('Geçersiz çalışma profili.')
        if action in {'check', 'install'}:
            from .profile_resources import execute
        elif action in {'run', 'build', 'tls'}:
            from .profile_runtime import execute
        else:
            raise LauncherError('Geçersiz Manager işlemi.')
        claims = path_claims(source, write=action in {'install', 'build'})
        claims.update({'runtime': action == 'install', 'profile:' + profile: action != 'check'})
        with operation_control(stop, hide_server_window=True), resource_locks(installation_home(), claims):
            check_cancelled()
            result = execute(action, values, notify, ask)
            if action == 'tls' and result:
                emit({'type': 'profile', 'paths': result})
    except OperationCancelled:
        emit({'type': 'done', 'ok': True, 'cancelled': True})
        return
    except Exception as error:
        if isinstance(error, LauncherError):
            reason = str(error)
        elif isinstance(error, OSError):
            reason = _system_failure(error)[1]
        else:
            reason = f'Manager işlemi tamamlanamadı ({type(error).__name__}).'
        emit({'type': 'error', 'message': reason})
        emit({'type': 'done', 'ok': False})
        return
    emit({'type': 'done', 'ok': True})
