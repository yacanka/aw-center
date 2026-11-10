"""The approved DDF prompt is private data, never an executable template."""

from rest_framework.exceptions import APIException
from awcenter.private_configuration import PrivateConfigurationError, read_private_json


class DdfPolicyConfigurationError(APIException):
    status_code = 503
    default_code = "DDF_POLICY_UNAVAILABLE"
    default_detail = "Private DDF assessment policy is unavailable or invalid."


def assessment_prompt(authority_comments):
    try:
        policy = read_private_json("DDF_ASSESSMENT_POLICY_FILE")
        if set(policy) != {"schema_version", "prompt_prefix"}:
            raise ValueError
        prefix = policy["prompt_prefix"]
        if not isinstance(prefix, str) or not prefix.strip():
            raise ValueError
        # Keep every byte of the approved prefix and the existing list rendering.
        return prefix + str(authority_comments)
    except (PrivateConfigurationError, ValueError):
        raise DdfPolicyConfigurationError() from None
