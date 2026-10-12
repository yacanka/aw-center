"""Import-safe bootstrap for spawned job executor processes."""

from importlib import import_module

from .process_tree import establish_executor_session


def bootstrap_executor_process(job_id, kind, resolver_path, connection, start_gate=None):
    """Initialize Django before importing model-backed worker code."""

    try:
        establish_executor_session()
        # Windows must assign this process to its parent-owned Job Object before
        # any Django/feature imports or executor code can spawn descendants.
        if start_gate is not None and not start_gate.wait(timeout=10):
            raise RuntimeError("Executor containment was not established.")
        import django

        django.setup()
        resolve_executor = load_callable(resolver_path)
        from .child_execution import execute_in_child
    except BaseException as error:
        try:
            connection.send(
                {
                    "outcome": "startup_failed",
                    "error_type": type(error).__name__,
                }
            )
        finally:
            connection.close()
        return

    execute_in_child(job_id, kind, resolve_executor, connection)


def load_callable(path):
    """Resolve one trusted module-level callable after Django is ready."""

    module_name, qualified_name = path
    target = import_module(module_name)
    for attribute in qualified_name.split("."):
        target = getattr(target, attribute)
    if not callable(target):
        raise TypeError("The executor resolver is not callable.")
    return target
