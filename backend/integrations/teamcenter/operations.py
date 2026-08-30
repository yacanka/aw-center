"""Validated Teamcenter operation model conversion shared by HTTP and workers."""

from collections import defaultdict

from integrations.teamcenter.models import ModelReference, PropertyUpdate


def build_property_updates(raw_updates):
    """Convert validated property updates into transport-layer value objects."""

    updates = defaultdict(list)
    for item in raw_updates:
        model = ModelReference(**item["object"])
        for name, values in item["properties"].items():
            updates[model].append(PropertyUpdate.many(name, values))
    return updates
