"""Shared cache requirements for supported production deployment profiles."""

from pathlib import Path


def production_cache_is_valid(deployment_mode, cache_config, repository_dir):
    """Keep startup checks and ephemeral integration storage on the same policy."""

    backend = cache_config.get("BACKEND", "")
    if deployment_mode == "container":
        return "redis" in backend.casefold()
    if deployment_mode != "windows-native":
        return False
    directory = Path(cache_config.get("LOCATION", ""))
    return (
        backend == "django.core.cache.backends.filebased.FileBasedCache"
        and directory.is_absolute()
        and not directory.resolve().is_relative_to(Path(repository_dir).resolve())
    )
