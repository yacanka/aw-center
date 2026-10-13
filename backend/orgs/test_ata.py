"""ATA normalization across direct API writes and model validation."""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .ata import normalize_ata_chapter
from .models import Panel
from .serializers import PanelSerializer


class AtaTests(SimpleTestCase):
    def test_digit_free_text_preserves_spelling_and_internal_spacing(self):
        for value in ("General", "ATA chapter", "Not  applicable", "Türkçe metin"):
            with self.subTest(value=value):
                self.assertEqual(normalize_ata_chapter(f"  {value}  "), value)
                serializer = PanelSerializer(data={"name": "Panel", "ata": value})
                self.assertTrue(serializer.is_valid(), serializer.errors)
                self.assertEqual(serializer.validated_data["ata"], value)
                Panel._meta.get_field("ata").clean(value, None)

    def test_numeric_inputs_keep_existing_normalization_and_reject_mixed_text(self):
        for value, expected in ((27, "27-00"), (27.0, "27-00"), ("ATA 2700", "27-00"), ("2/3", "02-03")):
            with self.subTest(value=value):
                self.assertEqual(normalize_ata_chapter(value), expected)
                serializer = PanelSerializer(data={"name": "Panel", "ata": value})
                self.assertTrue(serializer.is_valid(), serializer.errors)
                self.assertEqual(serializer.validated_data["ata"], expected)
        for value in (None, True, "", "   ", "General 27", "123", "27-100", "chapter 9X"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_ata_chapter(value)
        with self.assertRaises(ValidationError):
            Panel._meta.get_field("ata").clean("General 27", None)
