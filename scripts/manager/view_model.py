"""Display-independent validation and bounded, sanitized manager event state."""

from __future__ import annotations

import ipaddress
import re
import time
from urllib.parse import urlsplit, urlunsplit


DEFAULT_VALUES = {
    "profile": "dev", "source_root": "", "source_mode": "restricted",
    "repository": "", "offline_dir": "", "python_index_url": "",
    "npm_registry_url": "", "ca_file": "", "assets": "",
    "feature_catalog": "", "host": "", "backend_port": "",
    "frontend_port": "", "tls_cert_file": "", "tls_key_file": "",
    "migrate": False, "install_python": False, "install_node": False, "python_command": "", "node_command": "",
    "bundle_host_python": False, "bundle_host_node": False, "bundle_import": "",
    "output": "", "env_file": "", "manager_distribution": "",
    "source_selection": "automatic", "migration_policy": "automatic",
}
SOURCE_ACTIONS = {"provision", "ensure", "test-sources", "bundle"}
CHECK_LABELS = {
    "ready": "HAZIR", "available": "HAZIR", "missing": "EKSİK",
    "blocked": "ENGEL", "invalid": "ENGEL", "unverified": "DOĞRULANAMADI",
    "configured": "DOĞRULANAMADI", "degraded": "EKSİK",
}
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SECRET = re.compile(
    r"\b([\w-]*(?:password|passwd|pwd|secret|token|authorization|credential|"
    r"private[_-]?key|encryption[_-]?key|api[_-]?key|connection[_-]?string|database[_-]?url)[\w-]*)"
    r"\b\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|(?:(?:Bearer|Basic)\s+)?[^\s,;]+)", re.IGNORECASE,
)


class FormError(ValueError):
    """A safe, user-facing validation error associated with one form field."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


def _https(value: str, field: str) -> None:
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "https" and parsed.hostname and parsed.username is None
                 and parsed.password is None and not parsed.query and not parsed.fragment)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise FormError(field, "HTTPS adresi kullanın; kullanıcı bilgisi, sorgu veya token eklemeyin.")


def _validate_sources(values: dict) -> None:
    for field in ("python_index_url", "npm_registry_url"):
        if values[field]:
            _https(values[field], field)
    repository = values["repository"]
    if "://" in repository:
        _https(repository, "repository")


def _validate_provision(values: dict) -> None:
    for field in ("backend_port", "frontend_port"):
        value = values[field]
        if value == 'auto' and values['profile'] == 'dev':
            continue
        if value and (not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535):
            raise FormError(field, "Port 1 ile 65535 arasında bir tam sayı olmalıdır.")
    if values["profile"] == "dev":
        if values["host"] and values["host"] != "127.0.0.1":
            raise FormError("host", "Geliştirme profili için 127.0.0.1 kullanın.")
        if values["backend_port"] not in {'', 'auto'} and values["backend_port"] == values["frontend_port"]:
            raise FormError("frontend_port", "Frontend ve backend portları farklı olmalıdır.")
        return
    if not values["host"]:
        return  # An existing private profile may supply the host and TLS paths.
    try:
        host = ipaddress.ip_address(values["host"])
    except ValueError:
        host = None
    if host is None or host.version != 4 or host.is_loopback or host.is_unspecified or host.is_multicast:
        raise FormError("host", "Üretim için sabit, loopback olmayan bir IPv4 adresi girin.")


def normalize_values(action: str, values: dict) -> dict[str, str | bool]:
    """Return only non-secret supported fields; never perform disk or network I/O."""
    if action not in SOURCE_ACTIONS | {"start", "doctor", "inspect"}:
        raise FormError("profile", "Geçersiz işlem.")
    result = {key: (values.get(key) is True if isinstance(default, bool) else str(values.get(key, default)).strip())
              for key, default in DEFAULT_VALUES.items()}
    if result["profile"] not in {"dev", "prod"}:
        raise FormError("profile", "Geliştirme veya üretim profilini seçin.")
    if result["source_mode"] not in {"online", "restricted", "corporate", "offline"}:
        raise FormError("source_mode", "Geçerli bir kaynak modu seçin.")
    if result['migration_policy'] not in {'automatic', 'confirm'}:
        raise FormError('migration_policy', 'Geçerli bir migration politikası seçin.')
    if result['source_selection'] not in {'automatic', 'explicit'}:
        raise FormError('source_root', 'Geçerli bir kaynak seçimi kullanın.')
    if result["source_mode"] == "offline":
        for field in ("repository", "python_index_url", "npm_registry_url"):
            result[field] = ""
    if result["profile"] == "prod":
        result["frontend_port"] = ""
    else:
        result["tls_cert_file"] = result["tls_key_file"] = ""
    if action in SOURCE_ACTIONS:
        _validate_sources(result)
    if action in {"provision", "ensure"}:
        _validate_provision(result)
    return result


def validate_admin(username: str, password: str, confirmation: str) -> dict[str, str]:
    """Validate basic form constraints; the worker also applies Django policy."""
    username = username.strip()
    # Mirror users.username_policy without importing Django before provisioning.
    if not re.fullmatch(r"[A-Za-zÇĞİÖŞÜçğıöşü][0-9]{5}", username):
        raise FormError("username", "Kullanıcı adı bir harf ve ardından tam beş rakam olmalıdır (örnek: U12345).")
    if not 8 <= len(password) <= 128 or password.isdigit() or "\x00" in password:
        raise FormError("password", "Parola 8–128 karakter olmalı ve yalnız rakamlardan oluşmamalıdır.")
    if password != confirmation:
        raise FormError("confirmation", "Parola tekrarı eşleşmiyor.")
    return {"username": username, "password": password}


def _redact_url(match: re.Match) -> str:
    try:
        parsed = urlsplit(match.group())
        hostname = parsed.hostname
        if not hostname:
            return "[adres gizlendi]"
        if ":" in hostname:
            hostname = f"[{hostname}]"
        netloc = hostname + (f":{parsed.port}" if parsed.port else "")
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "[adres gizlendi]"


def safe_text(value: object, *, limit: int = 2000) -> str:
    """Defense in depth for reviewed structured events, never raw child output."""
    if not isinstance(value, (str, int, bool)):
        return ""
    text = "".join(character for character in str(value) if character >= " " or character in "\n\t")
    text = _URL.sub(_redact_url, text)
    return _SECRET.sub(lambda match: match.group(1) + "=[gizlendi]", text)[:limit]


def _ready_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048 or any(character.isspace() for character in value):
        return ""
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname and parsed.username is None
                 and parsed.password is None and not parsed.query and not parsed.fragment)
        parsed.port
    except ValueError:
        return ""
    return value if valid else ""


def _source_check_status(checks):
    blocked = sum(check['status'] == 'ENGEL' for check in checks)
    incomplete = sum(check['status'] not in {'HAZIR', 'ENGEL'} for check in checks)
    if blocked:
        return f'Kaynak denetimi başarısız — {blocked} aşamada engel; rapordaki nedenleri inceleyin.'
    if incomplete or not checks:
        return 'Kaynak denetimi eksik — erişim veya dosya bütünlüğü tamamen doğrulanamadı.'
    return 'Kaynak denetimi başarılı — denetlenen indirmeler ve dosya bütünlükleri doğrulandı.'


class ManagerState:
    """Retain actionable errors and a bounded report without credentials or forms."""

    def __init__(self):
        self.busy = False
        self.status = "Hazır. Bir profil seçip işlem başlatın."
        self.phase = ""
        self.error_message = ""
        self.error_remedy = ""
        self.error_code = ""
        self.ready_url = ""
        self.checks: list[dict[str, str]] = []
        self.last_action: str | None = None
        self.last_values: dict[str, str | bool] = {}
        self._report_lines: list[str] = []
        self.started_at = time.monotonic()
        self.phases: list[str] = []
        self.healthy = True
        self.finished_at = None
        self.last_health = ''

    def record_action(self, action: str, values: dict) -> None:
        self.last_action = action
        self.last_values = normalize_values(action, values)
        self.busy = True
        self.started_at = time.monotonic()
        self.finished_at = None
        self.phases = []
        self.phase = ""
        self.error_message = self.error_remedy = self.error_code = self.ready_url = ""
        self.checks = []
        self.status = "İşlem başlatılıyor."
        self._append(f"İşlem: {action}; profil: {self.last_values['profile']}; kaynak: {self.last_values['source_mode']}")

    def _append(self, message: str) -> None:
        if message:
            self._report_lines.append(message)
            self._report_lines = self._report_lines[-200:]

    def handle_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind in {"phase", "status"}:
            self.status = safe_text(event.get("message", ""))
            if kind == "phase":
                self.phase = self.status
                if not self.phases or self.phases[-1] != self.phase:
                    self.phases = [*self.phases[-19:], self.phase]
            elapsed = int(time.monotonic() - self.started_at)
            self._append(f'[{elapsed // 60:02}:{elapsed % 60:02}] {self.status}')
        elif kind == 'health':
            healthy = event.get('healthy') is True
            if healthy != self.healthy:
                self._append(safe_text(event.get('message', '')))
            self.healthy = healthy
            self.last_health = safe_text(event.get('message', ''))
            self.status = safe_text(event.get('message', ''))
        elif kind == "error":
            self.error_message = safe_text(event.get("message", "İşlem tamamlanamadı."))
            self.error_remedy = safe_text(event.get("remedy", "Kaynakları ve durum raporunu inceleyip yeniden deneyin."))
            self.error_code = safe_text(event.get("code", ""), limit=100)
            self.status = "İşlem tamamlanamadı. Aşağıdaki çözüm adımını uygulayın."
            if self.error_code == "bundle_waiting_for_files":
                self.status = "Dosya bekleniyor. Tamamlanan adımlar kaydedildi."
            self._append(f"Hata ({self.error_code}): {self.error_message}\nÇözüm: {self.error_remedy}")
        elif kind == "checks":
            self._handle_checks(event.get("checks"))
        elif kind == "ready":
            self.ready_url = _ready_url(event.get("url"))
            if self.ready_url:
                self.status = "AW Center hazır. Tarayıcıda açabilirsiniz."
                self._append("Hazır: " + self.ready_url)
        elif kind == "done":
            self.busy = False
            self.finished_at = time.monotonic()
            self.ready_url = ''
            if event.get("cancelled") is True:
                self.status = "İşlem durduruldu. Yeni bir işlem başlatabilirsiniz."
            elif event.get("ok") is True:
                blocked = sum(check['status'] == 'ENGEL' for check in self.checks)
                missing = sum(check['status'] not in {'HAZIR', 'ENGEL'} for check in self.checks)
                self.status = (_source_check_status(self.checks) if self.last_action == 'test-sources' else
                               f'Kurulum engellendi — {blocked} engel.' if blocked else
                               f'Eksiklerle kullanılabilir — {missing} eksik / doğrulanmamış özellik.' if missing else
                               'Hazır — denetim tamamlandı.' if self.checks else 'İşlem tamamlandı.')
            elif not self.error_message:
                self.status = "İşlem tamamlanamadı. Durum raporunu inceleyin."
            self._append(self.status)

    def _handle_checks(self, checks: object) -> None:
        if not isinstance(checks, list):
            return
        self.checks = []
        for check in checks[:100]:
            if not isinstance(check, dict):
                continue
            item = {"name": safe_text(check.get("name", ""), limit=100),
                    "status": CHECK_LABELS.get(str(check.get("status")), "BİLİNMİYOR"),
                    "detail": safe_text(check.get("detail", ""))}
            self.checks.append(item)
            self._append(f"[{item['status']}] {item['name']}: {item['detail']}")

    def report(self) -> str:
        elapsed = int((self.finished_at or time.monotonic()) - self.started_at)
        health = '\nSon sağlık: ' + self.last_health if self.last_health else ''
        return f"AW Center — güvenli durum raporu\nSüre: {elapsed // 60:02}:{elapsed % 60:02}{health}\n" + "\n".join(self._report_lines)


class ManagerTaskStates:
    """Keep each task's report and form feedback isolated from other workers.

    Task rows come from the controller. In particular, a worker's ``done`` event
    does not end an active row while the controller is still cleaning up.
    """

    ACTIVE_STATUSES = frozenset({"running", "ready", "degraded", "stopping", "finishing"})

    def __init__(self):
        self.general = ManagerState()
        self.states: dict[str, ManagerState] = {}
        self.tasks: dict[str, dict[str, str]] = {}
        self.selected_id: str | None = None
        self.profiles: dict[str, dict] = {}

    def profile_presentation(self, profile: str) -> dict:
        """Live profile ownership wins over read-only inspection and task selection."""
        for task in reversed(list(self.tasks.values())):
            if task['profile'] != profile or task['action'] not in {'start', 'provision', 'ensure'}:
                continue
            if task['status'] not in self.ACTIVE_STATUSES:
                continue
            state = self.states[task['id']]
            ready = task['status'] == 'ready' and state.healthy and bool(state.ready_url)
            return {'status': task['status'], 'action': 'open' if ready else None,
                    'label': 'Tarayıcıda aç' if ready else 'İşlem sürüyor', 'task_id': task['id'],
                    'url': state.ready_url if ready else '', 'detail': state.status}
        snapshot = self.profiles.get(profile, {})
        status = snapshot.get('status', 'inspecting')
        actions = {'inspecting': ('ensure', 'AW Center’ı aç'), 'not_installed': ('ensure', 'AW Center’ı aç'),
                   'stopped': ('ensure', 'AW Center’ı aç'),
                   'incomplete': ('ensure', 'Tamamla ve aç'), 'blocked': ('doctor', 'Eksikleri göster')}
        action, label = actions.get(status, (None, 'Denetleniyor…'))
        return {'status': status, 'action': action, 'label': label, 'task_id': None, 'url': '',
                'detail': snapshot.get('detail', ''), 'tools': snapshot.get('tools', '')}

    @property
    def current(self) -> ManagerState:
        return self.states.get(self.selected_id, self.general)

    def select(self, task_id: str | None) -> None:
        self.selected_id = task_id if task_id in self.tasks else None

    def update_tasks(self, tasks: list[dict], selected_id: str | None = None) -> None:
        rows = {}
        for task in tasks:
            task_id = task["id"]
            action, profile = task["action"], task["profile"]
            if task_id not in self.states:
                state = ManagerState()
                state.record_action(action, {**task.get("values", {}), "profile": profile})
                self.states[task_id] = state
            rows[task_id] = {"id": task_id, "action": action, "profile": profile,
                             "status": task["status"]}
            self.states[task_id].busy = task["status"] in self.ACTIVE_STATUSES
            if not self.states[task_id].busy:
                self.states[task_id].ready_url = ''
        self.tasks = rows
        self.states = {task_id: self.states[task_id] for task_id in rows}
        self.select(selected_id if selected_id is not None else self.selected_id)

    def handle_event(self, event: dict) -> None:
        if event.get('type') == 'profile':
            if event.get('profile') in {'dev', 'prod'}:
                self.profiles[event['profile']] = event
            return
        task_id = event.get("task_id")
        if task_id is None:
            self.general.handle_event(event)
            self.selected_id = None
            return
        state = self.states.get(task_id)
        if state is None:
            return  # The controller has already released this task's history.
        state.handle_event(event)
        row = self.tasks.get(task_id)
        if row:
            state.busy = row["status"] in self.ACTIVE_STATUSES
