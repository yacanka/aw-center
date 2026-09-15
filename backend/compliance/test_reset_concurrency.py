"""Real connection regression for reset preparation versus an in-flight HTTP write."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import connections
from django.http import JsonResponse
from django.test import RequestFactory, TransactionTestCase, override_settings, skipUnlessDBFeature

from awcenter.developer_reset_middleware import DeveloperResetWriteMiddleware
from orgs.models import Person

from .models import DeveloperResetState
from .reset_guard import lock_reset_state


@override_settings(DEBUG=True, AWCENTER_DEPLOYMENT_MODE="development")
class ResetConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_preparation_waits_for_inflight_write_and_blocks_later_writes(self):
        # PostgreSQL exercises separate connections and a real row lock. SQLite's
        # in-memory shared-cache test DB fails immediately on competing writers.
        DeveloperResetState.objects.create(pk=1)
        entered = Event()
        finish_write = Event()
        preparing = Event()
        prepared = Event()

        def write_view(request):
            entered.set()
            if not finish_write.wait(5):
                raise TimeoutError("Test writer was not released")
            Person.objects.create(person_id="concurrent-reset", name="Test")
            return JsonResponse({"created": True})

        middleware = DeveloperResetWriteMiddleware(write_view)

        def write():
            try:
                request = RequestFactory().post("/api/projects/test/organization/people/")
                return middleware(request).status_code
            finally:
                connections.close_all()

        def prepare():
            try:
                preparing.set()
                with lock_reset_state() as state:
                    count = Person.objects.filter(person_id="concurrent-reset").count()
                    state.active = True
                    state.save()
                prepared.set()
                return count
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(write)
            try:
                self.assertTrue(entered.wait(5))
                preparation = pool.submit(prepare)
                self.assertTrue(preparing.wait(5))
                self.assertFalse(prepared.wait(0.1))
            finally:
                finish_write.set()
            self.assertEqual(writer.result(timeout=5), 200)
            self.assertEqual(preparation.result(timeout=5), 1)
            self.assertEqual(pool.submit(write).result(timeout=5), 409)
        self.assertEqual(Person.objects.filter(person_id="concurrent-reset").count(), 1)
