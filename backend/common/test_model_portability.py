from django.apps import apps
from django.db import models
from django.test import SimpleTestCase


class ModelFieldPortabilityTests(SimpleTestCase):
    def test_all_model_char_fields_define_max_length(self):
        missing_max_length = []

        for model in apps.get_models():
            for field in model._meta.fields:
                if isinstance(field, models.CharField) and field.max_length is None:
                    missing_max_length.append(f"{model._meta.label}.{field.name}")

        self.assertEqual(missing_max_length, [])
