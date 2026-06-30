"""Project registry contract constants shared by backend checks.

Adding a capability is a backend/frontend contract change. Update this file,
frontend/src/models/projectRegistry.ts, registry integrity/API tests, and the
consumer documentation in the same change so unsupported capabilities cannot
silently reach clients.
"""

PROJECT_CAPABILITY_DCC = "dcc"
PROJECT_CAPABILITY_COMPDOCS = "compdocs"
PROJECT_CAPABILITY_ORGS = "orgs"

ALLOWED_PROJECT_CAPABILITIES = frozenset(
    (
        PROJECT_CAPABILITY_DCC,
        PROJECT_CAPABILITY_COMPDOCS,
        PROJECT_CAPABILITY_ORGS,
    )
)
