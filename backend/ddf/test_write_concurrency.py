"""Concurrent partial DDF edits preserve unrelated fields."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase

from .models import DDF
from .serializers import DDFSerializer


class DdfWriteConcurrencyTests(TransactionTestCase):
    def test_overlapping_partial_edits_preserve_both_fields(self):
        user = get_user_model().objects.create_user("ddf-concurrent")
        document = DDF.objects.create(created_by=user, doc_name="Original")
        ready = Barrier(2)
        first_saved = Event()

        def update(index, values):
            try:
                serializer = DDFSerializer(
                    DDF.objects.get(pk=document.pk), data=values, partial=True,
                )
                serializer.is_valid(raise_exception=True)
                ready.wait(timeout=10)
                if index:
                    self.assertTrue(first_saved.wait(timeout=10))
                serializer.save()
            finally:
                if not index:
                    first_saved.set()
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(update, 0, {"doc_name": "Updated"})
            second = pool.submit(update, 1, {"comments": ["New comment"]})
            first.result(timeout=30)
            second.result(timeout=30)
        document.refresh_from_db()
        self.assertEqual(document.doc_name, "Updated")
        self.assertEqual(document.comments, ["New comment"])
