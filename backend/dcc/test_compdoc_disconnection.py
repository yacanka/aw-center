from uuid import uuid4

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve


class CompDocDisconnectionTests(SimpleTestCase):
    """Verify removed CompDoc-to-DCC routes cannot be invoked."""

    def test_reverse_trace_route_is_removed(self):
        """DCC no longer exposes CompDoc traceability history."""

        with self.assertRaises(Resolver404):
            resolve("/dcc/compdoc-traceability/")

    def test_recommendation_route_is_removed(self):
        """DCC previews no longer accept CompDoc recommendation selections."""

        with self.assertRaises(Resolver404):
            resolve(f"/dcc/jobs/create-document/{uuid4()}/compdoc-recommendations/")
