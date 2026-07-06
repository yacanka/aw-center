from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase


class ModelOrderingTests(SimpleTestCase):
    """Regression tests for deterministic pagination ordering."""

    def test_project_models_define_default_ordering(self):
        """Every concrete repository model must declare default ordering."""
        unordered_models = [
            model._meta.label
            for model in apps.get_models()
            if self._is_repository_model(model) and not model._meta.ordering
        ]

        self.assertEqual([], unordered_models)

    def _is_repository_model(self, model):
        """Return True for concrete, database-backed models owned by this repo."""
        return (
            not model._meta.abstract
            and not model._meta.proxy
            and model._meta.app_config.path.startswith(str(settings.BASE_DIR))
        )
