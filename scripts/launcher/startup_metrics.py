"""Request-local counts for native startup evidence, never paths or tool output."""
from contextlib import contextmanager
from contextvars import ContextVar


STARTUP_WORK = ('source_inventory', 'runtime_inventory', 'dependency_inventory', 'optional_tool_inventory')
_active = ContextVar('awcenter_startup_work', default=None)


def count_startup_work(name):
    current = _active.get()
    if current is not None and name in STARTUP_WORK:
        current['counts'][name] += 1


def emit_startup_work():
    current = _active.get()
    if current is not None:
        current['emit']({'type': 'startup-work', 'policy': current['policy'], 'counts': dict(current['counts'])})


@contextmanager
def startup_work(emit, policy='managed'):
    if policy not in {'managed', 'developer'}:
        raise ValueError('Invalid startup evidence policy')
    token = _active.set({'emit': emit, 'policy': policy, 'counts': dict.fromkeys(STARTUP_WORK, 0)})
    try:
        yield
    finally:
        try:
            emit_startup_work()
        finally:
            _active.reset(token)
