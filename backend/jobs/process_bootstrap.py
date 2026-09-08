"""Import-safe bootstrap for spawned job executor processes."""

from importlib import import_module


def bootstrap_executor_process(job_id, kind, resolver_path, connection):
    """Initialize Django before importing model-backed worker code."""

    try:
        import django

        django.setup()
        resolve_executor = load_callable(resolver_path)
        from .worker import execute_in_child
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
