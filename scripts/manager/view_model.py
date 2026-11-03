"""Display-independent validation and bounded, sanitized manager event state."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


DEFAULT_VALUES = {
    "profile": "dev", "source_root": "", "source_mode": "online",
    "repository": "", "offline_dir": "", "python_index_url": "",
    "npm_registry_url": "", "ca_file": "", "assets": "",
    "feature_catalog": "", "host": "", "backend_port": "",
    "frontend_port": "", "tls_cert_file": "", "tls_key_file": "",
    "migrate": False, "output": "",
}
SOURCE_ACTIONS = {"provision", "test-sources", "bundle"}
CHECK_LABELS = {
    "ready": "HAZIR", "available": "HAZIR", "missing": "EKSİK",
    "blocked": "ENGEL", "unverified": "DOĞRULANAMADI",
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
    mode = values["source_mode"]
    if mode == "offline" and not values["offline_dir"]:
        raise FormError("offline_dir", "Çevrimdışı bağımlılık paketinin dizinini seçin.")
    for field in ("python_index_url", "npm_registry_url"):
        if values[field]:
            _https(values[field], field)
    repository = values["repository"]
    if "://" in repository:
        _https(repository, "repository")


def _validate_provision(values: dict) -> None:
    for field in ("backend_port", "frontend_port"):
        value = values[field]
        if value and (not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535):
            raise FormError(field, "Port 1 ile 65535 arasında bir tam sayı olmalıdır.")
    if values["profile"] == "dev":
        if values["host"] and values["host"] != "127.0.0.1":
            raise FormError("host", "Geliştirme profili için 127.0.0.1 kullanın.")
        if values["backend_port"] and values["backend_port"] == values["frontend_port"]:
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
    if action not in SOURCE_ACTIONS | {"start", "doctor"}:
        raise FormError("profile", "Geçersiz işlem.")
    result = {key: str(values.get(key, default)).strip()
              for key, default in DEFAULT_VALUES.items() if key != "migrate"}
    result["migrate"] = values.get("migrate") is True
    if result["profile"] not in {"dev", "prod"}:
        raise FormError("profile", "Geliştirme veya üretim profilini seçin.")
    if result["source_mode"] not in {"online", "corporate", "offline"}:
        raise FormError("source_mode", "Geçerli bir kaynak modu seçin.")
    if result["source_mode"] == "offline":
        for field in ("repository", "python_index_url", "npm_registry_url"):
            result[field] = ""
    if result["profile"] == "prod":
        result["frontend_port"] = ""
    else:
        result["tls_cert_file"] = result["tls_key_file"] = ""
    if action in SOURCE_ACTIONS:
        _validate_sources(result)
    if action == "provision":
        _validate_provision(result)
    if action == "bundle" and not result["output"]:
        raise FormError("output", "Çevrimdışı paket için çıktı dizini seçin.")
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

    def record_action(self, action: str, values: dict) -> None:
        self.last_action = action
        self.last_values = normalize_values(action, values)
        self.busy = True
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
            self._append(self.status)
        elif kind == "error":
            self.error_message = safe_text(event.get("message", "İşlem tamamlanamadı."))
            self.error_remedy = safe_text(event.get("remedy", "Kaynakları ve durum raporunu inceleyip yeniden deneyin."))
            self.error_code = safe_text(event.get("code", ""), limit=100)
            self.status = "İşlem tamamlanamadı. Aşağıdaki çözüm adımını uygulayın."
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
            if event.get("cancelled") is True:
                self.status = "İşlem durduruldu. Yeni bir işlem başlatabilirsiniz."
            elif event.get("ok") is True:
                self.status = "İşlem tamamlandı."
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
        return "AW Center — güvenli durum raporu\n" + "\n".join(self._report_lines)


class ManagerTaskStates:
    """Keep each task's report and form feedback isolated from other workers.

    Task rows come from the controller. In particular, a worker's ``done`` event
    does not end an active row while the controller is still cleaning up.
    """

    ACTIVE_STATUSES = frozenset({"running", "ready", "stopping", "finishing"})

    def __init__(self):
        self.general = ManagerState()
        self.states: dict[str, ManagerState] = {}
        self.tasks: dict[str, dict[str, str]] = {}
        self.selected_id: str | None = None

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
        self.tasks = rows
        self.states = {task_id: self.states[task_id] for task_id in rows}
        self.select(selected_id if selected_id is not None else self.selected_id)

    def handle_event(self, event: dict) -> None:
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
