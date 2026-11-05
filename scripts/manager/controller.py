"""Independent owned tasks; Tk only schedules work and renders tagged events."""
from __future__ import annotations

from dataclasses import dataclass, field
import queue
import threading
import uuid
import webbrowser

from .task_policy import ACTION_LABELS, claims_for, conflicts
from .paths import new_bundle_output, normalize_task_paths
from .transport import WorkerSession
from .view_model import DEFAULT_VALUES, _ready_url


@dataclass
class ManagerTask:
    id: str
    action: str
    values: dict
    session: object
    status: str = 'running'
    claims: tuple = field(default_factory=tuple)
    result: dict | None = None
    cancel_requested: bool = False
    browser_opened: bool = False
    events: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=256))

    @property
    def active(self):
        return self.session is not None

    def snapshot(self):
        return {'id': self.id, 'action': self.action, 'profile': self.values['profile'],
                'status': self.status, 'values': dict(self.values)}


class ManagerController:
    def __init__(self, root, view_factory, source_root, *, session_factory=None, browser_opener=None):
        self.root = root
        self.source_root = str(source_root)
        self.events = queue.Queue()
        self.tasks: dict[str, ManagerTask] = {}
        self.session_factory = session_factory or WorkerSession
        self.browser_opener = browser_opener or webbrowser.open
        self.closing = self.closed = False
        self.inspection_ids = {}
        self.view = view_factory(root, self.action, self.stop, self.window_close, source_root=source_root)
        self.view.on_open = self.open_browser
        self.view.on_exit = self.close
        self.view.on_inspect = self.inspect_selected
        root.after_idle(self.inspect_selected)
        root.after(100, self.poll)

    def inspect_selected(self):
        values = self.view.form_values()
        if not isinstance(values, dict) or self.closing:
            return
        profile = values.get('profile', 'dev')
        if any(task.active and task.action in {'start', 'provision'} and task.values['profile'] == profile
               for task in self.tasks.values()):
            return
        previous = self.tasks.get(self.inspection_ids.get(profile))
        if previous and previous.active:
            self._request_stop(previous)
        task_id = self.action('inspect', values)
        if task_id:
            self.inspection_ids[profile] = task_id
            self.view.handle_event({'type': 'profile', 'profile': profile, 'status': 'inspecting'})

    def window_close(self):
        if self.busy:
            self.root.iconify()
        else:
            self.close()

    @property
    def busy(self):
        return any(task.active for task in self.tasks.values())

    def action(self, action, values):
        if self.closing:
            return None
        if action not in ACTION_LABELS or values.get('profile', 'dev') not in {'dev', 'prod'}:
            self._general_error('invalid_action', 'Geçersiz işlem veya profil.')
            return None
        snapshot = {key: value for key, value in values.items() if key in DEFAULT_VALUES}
        snapshot.setdefault('profile', 'dev')
        snapshot['source_root'] = snapshot.get('source_root') or self.source_root
        if action == 'bundle' and not snapshot.get('output'):
            from scripts.launcher.model import LauncherError
            try:
                snapshot['output'] = str(new_bundle_output())
            except LauncherError:
                self.view.handle_event({'type': 'error', 'code': 'profile_unavailable',
                    'message': 'Otomatik paket hedefi için Windows kullanıcı kayıt alanı bulunamadı.',
                    'remedy': 'LOCALAPPDATA kullanıcı profilini kontrol edin veya bir çıktı klasörü seçin.'})
                return None
        snapshot = normalize_task_paths(snapshot)
        claims = claims_for(action, snapshot)
        for task in self.tasks.values():
            if action != 'inspect' and task.active and conflicts(claims, task.claims):
                self._general_error('task_conflict',
                    f"{ACTION_LABELS[task.action]} ({task.values['profile']}) aynı profil, kaynak veya paylaşılan runtime'ı kullanıyor.")
                return None
        if sum(task.active for task in self.tasks.values()) >= 16:
            self._general_error('task_capacity', 'Aynı anda en fazla 16 yönetim işlemi çalıştırılabilir.')
            return None
        task_id = uuid.uuid4().hex
        inbox = queue.Queue(maxsize=256)
        def emit(event):
            # Backpressure is local to this worker. One noisy task cannot fill
            # shared memory or sit ahead of every other task's completion.
            inbox.put({**event, 'task_id': task_id})
        session = self.session_factory(emit)
        task = ManagerTask(task_id, action, snapshot, session, claims=claims, events=inbox)
        self.tasks[task_id] = task
        def run():
            try:
                # Bind this operation's session, never a replaceable global field.
                session.run({**snapshot, 'action': action})
            finally:
                emit({'type': '_closed'})
        try:
            threading.Thread(target=run, name=f'awcenter-{action}-{task_id[:8]}', daemon=True).start()
        except Exception:
            task.result = {'ok': False}
            emit({'type': 'error', 'code': 'task_start_failed', 'message': 'İşlem süreci başlatılamadı.'})
            emit({'type': '_closed'})
        self._publish_tasks(selected_id=task_id if action != 'inspect' else None)
        return task_id

    def _general_error(self, code, message):
        self.view.handle_event({'type': 'error', 'code': code, 'message': message,
            'remedy': 'Bağımsız işlemleri kullanabilirsiniz. Çakışan işlem için görev listesinden ilgili işi durdurun veya tamamlanmasını bekleyin.'})

    def _publish_tasks(self, selected_id=None):
        completed = [task.id for task in self.tasks.values() if not task.active]
        for task_id in completed[:-50]:
            self.tasks.pop(task_id)
        self.view.update_tasks([task.snapshot() for task in self.tasks.values() if task.action != 'inspect'], selected_id=selected_id)

    def stop(self, task_id=None):
        task_id = task_id or self.view.selected_task_id()
        task = self.tasks.get(task_id)
        if task is not None and task.active:
            self._request_stop(task)
            self._render(task, {'type': 'status', 'message': 'Durduruluyor. Aktif veritabanı işleminin güvenli bitişi beklenebilir.'})
            self._publish_tasks()

    @staticmethod
    def _request_stop(task):
        task.cancel_requested = True
        task.status = 'stopping'
        task.session.stop()  # Nonblocking private outbound queue.

    def close(self):
        if not self.busy:
            self.closed = True
            self.root.destroy()
        elif self.view.confirm_stop():
            self.closing = True
            # Deliver every cancellation before touching a potentially broken
            # dialog/renderer, so one view cannot strand other owned workers.
            for task in list(self.tasks.values()):
                if task.active:
                    self._request_stop(task)
                    try:
                        self.view.dismiss_admin(task.id)
                    except Exception:
                        self.events.put({'type': 'status', 'task_id': task.id,
                            'message': 'İşlem durduruluyor; yönetici penceresi kapanırken hata oluştu.'})
            self._publish_tasks()

    def poll(self):
        try:
            inboxes = [self.events, *(task.events for task in self.tasks.values() if task.active)]
            for inbox in inboxes:
                for _ in range(8):
                    try:
                        event = inbox.get_nowait()
                    except queue.Empty:
                        break
                    self._consume_event(event)
                    if self.closed:
                        return
        finally:
            if not self.closed:
                self.root.after(100, self.poll)

    def _consume_event(self, event):
        try:
            self._handle_event(event)
        except Exception:
            # A broken task renderer must not starve other task events.
            try:
                self._general_error('ui_event_failed', 'Bir görevin durum bilgisi gösterilemedi; diğer işlemler devam ediyor.')
            except Exception:
                pass

    def _render(self, task, event):
        self.view.handle_event({**event, 'task_id': task.id, 'action': task.action,
                                'profile': task.values['profile']})

    def _handle_event(self, event):
        task = self.tasks.get(event.get('task_id'))
        if task is None or not task.active:
            return
        kind = event['type']
        if task.action == 'inspect' and kind != '_closed':
            if self.inspection_ids.get(task.values['profile']) != task.id:
                return
            if kind == 'profile':
                self.view.handle_event({**event, 'task_id': None})
            elif kind in {'phase', 'status'}:
                self.view.handle_event({'type': 'profile', 'profile': task.values['profile'],
                    'status': 'inspecting', 'detail': event.get('message', '')})
            elif kind == 'error':
                self.view.handle_event({'type': 'profile', 'profile': task.values['profile'],
                    'status': 'blocked', 'detail': event.get('message', 'Ortam doğrulanamadı.') +
                    ' ' + event.get('remedy', '')})
            elif kind == 'done':
                task.result = event
            return
        if kind == '_closed':
            task.session = None
            result = task.result or {'ok': False}
            task.status = ('failed' if not result.get('ok') else
                           'cancelled' if result.get('cancelled') or task.cancel_requested else 'done')
            try:
                self.view.dismiss_admin(task.id)
                self._publish_tasks()
                if task.action in {'start', 'provision'} and not self.closing:
                    self.root.after_idle(self.inspect_selected)
            finally:
                if self.closing and not self.busy:
                    self.closed = True
                    self.root.destroy()
            return
        if kind == 'input' and event.get('kind') == 'admin':
            if self.closing or task.cancel_requested:
                self.stop(task.id)
            else:
                self.view.request_admin(task.id, lambda value: self._admin_response(task.id, value))
            return
        if kind == 'done':
            task.result = event
            task.status = 'finishing'
        elif kind == 'ready':
            task.status = 'stopping' if task.cancel_requested else 'ready'
            # Provision is now a running server: no setup writes remain.
            task.claims = claims_for('start', task.values)
        elif kind == 'health' and not task.cancel_requested:
            task.status = 'ready' if event.get('healthy') is True else 'degraded'
        if kind in {'done', 'ready', 'health'}:
            self._publish_tasks()
        self._render(task, event)
        if kind == 'ready' and not self.closing and not task.cancel_requested and not task.browser_opened:
            task.browser_opened = True
            self.open_browser(event.get('url'), task.id)

    def _admin_response(self, task_id, value):
        task = self.tasks.get(task_id)
        if task is None or not task.active or task.cancel_requested or self.closing:
            return
        try:
            task.session.send({'type': 'admin', 'value': value})
        except Exception:
            self._render(task, {'type': 'error', 'code': 'admin_send_failed', 'message': 'Yönetici bilgileri iletilemedi; yalnız bu işlem durduruluyor.'})
            self.stop(task_id)
            return
        if value is None:
            self.stop(task_id)

    def open_browser(self, url, task_id=None):
        url = _ready_url(url)
        if not url or self.closing:
            return
        def launch():
            try:
                opened = self.browser_opener(url)
            except Exception:
                opened = False
            if opened is False:
                self.events.put({'type': 'status', 'task_id': task_id,
                    'message': 'Uygulama hazır; tarayıcı açılamadı. Adresi rapordan kopyalayabilirsiniz.'})
        threading.Thread(target=launch, name='awcenter-browser', daemon=True).start()
