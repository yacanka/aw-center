from collections.abc import Iterable, Mapping
from typing import Any

from .auth import create_authenticator
from .config import TeamcenterClientConfig
from .exceptions import TeamcenterError
from .models import ModelReference, PropertyUpdate
from .transport import TeamcenterTransport


class TeamcenterClient:
    """Expose supported Teamcenter query and data-management operations."""

    def __init__(self, config: TeamcenterClientConfig, transport=None) -> None:
        self.config = config
        self.transport = transport or TeamcenterTransport(config)
        self.authenticator = create_authenticator(config, self.transport)
        self.authenticated = False

    def login(self) -> dict[str, Any]:
        """Authenticate the client session."""
        result = self.authenticator.login()
        self.authenticated = True
        return result

    def logout(self) -> None:
        """Terminate the current client session."""
        if self.authenticated:
            self.authenticator.logout()
        self.authenticated = False

    def call(self, service: str, body: dict[str, Any], *, idempotent: bool) -> dict[str, Any]:
        """Call one supported Teamcenter service."""
        if not self.authenticated:
            self.login()
        return self.transport.call(service, body, idempotent=idempotent)

    def find_saved_queries(self) -> dict[str, Any]:
        """Return saved queries visible to the integration account."""
        return self.call(self.config.endpoints.find_saved_queries, {}, idempotent=True)

    def execute_saved_query(self, query_uid, entries, values, maximum) -> dict[str, Any]:
        """Execute a Teamcenter saved query with validated parallel criteria."""
        if len(entries) != len(values):
            raise ValueError("entries and values must contain the same number of items.")
        query_input = {
            "query": {"uid": query_uid, "type": "ImanQuery"},
            "entries": entries,
            "values": values,
            "maxNumToReturn": maximum,
            "limitList": [],
        }
        return self.call(
            self.config.endpoints.execute_saved_queries,
            {"queryInput": [query_input]},
            idempotent=True,
        )

    def load_objects(self, uids: Iterable[str]) -> dict[str, Any]:
        """Load Teamcenter objects by UID."""
        return self.call(self.config.endpoints.load_objects, {"uids": list(uids)}, idempotent=True)

    def get_properties(self, objects, properties) -> dict[str, Any]:
        """Read selected properties for Teamcenter model objects."""
        body = {"objects": [item.to_json() for item in objects], "attributes": list(properties)}
        return self.call(self.config.endpoints.get_properties, body, idempotent=True)

    def set_properties(
        self, updates: Mapping[ModelReference, Iterable[PropertyUpdate]]
    ) -> dict[str, Any]:
        """Write selected Teamcenter properties without automatic retries."""
        info = [self.property_update_payload(model, values) for model, values in updates.items()]
        return self.call(self.config.endpoints.set_properties, {"info": info}, idempotent=False)

    @staticmethod
    def property_update_payload(model, values) -> dict[str, Any]:
        """Build one Teamcenter property-update payload."""
        return {"object": model.to_json(), "vecNameVal": [item.to_json() for item in values]}

    def close(self) -> None:
        """Close all network resources."""
        self.transport.close()
        self.authenticated = False

    def __enter__(self) -> "TeamcenterClient":
        self.login()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            try:
                self.logout()
            except TeamcenterError:
                self.authenticated = False
        finally:
            self.close()
