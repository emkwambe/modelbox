"""The minimum role for every route in the appliance (Sprint 7, Step 2).

One table, read by `tests/test_route_policy.py`, which walks every route the
application serves and fails if a route is missing here, if an entry names a
route that no longer exists, or if a route's dependency chain does not carry
the role declared below.

Values:

* ``PUBLIC`` — no authentication. Only the routes in :data:`PUBLIC_ALLOWLIST`
  may be public, and adding one is a deliberate edit to that set.
* ``SCIM`` — authenticated by the SCIM bearer token, not by a user.
* ``AUTHENTICATED`` — any signed-in caller; the route reads or computes nothing
  that belongs to a workspace.
* A workspace role — ``VIEWER`` < ``MEMBER`` < ``APPROVER`` < ``ADMIN`` <
  ``OWNER``. Reads, validation and export need ``VIEWER``; anything that
  writes a graph, calls a model provider or introspects a database needs
  ``MEMBER``; connectors, API keys and the audit trail need ``ADMIN``.

Default deny: a route with no entry here fails the test, so a new route is
unreachable in CI until someone decides what it requires.
"""

from __future__ import annotations

PUBLIC = "PUBLIC"
SCIM = "SCIM"
AUTHENTICATED = "AUTHENTICATED"
# The appliance owner flag (`create-owner`), above every workspace role: it
# reads events that belong to no workspace.
APPLIANCE_OWNER = "APPLIANCE_OWNER"

#: The only routes that may be reached without authenticating.
PUBLIC_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health"),
        ("POST", "/api/v1/auth/token"),
        ("POST", "/api/v1/auth/register"),
    }
)

_V1 = "/api/v1"

ROUTE_POLICY: dict[tuple[str, str], str] = {
    ("GET", "/health"): PUBLIC,
    # --- auth --------------------------------------------------------------
    ("POST", f"{_V1}/auth/token"): PUBLIC,
    ("POST", f"{_V1}/auth/register"): PUBLIC,
    ("GET", f"{_V1}/auth/me"): AUTHENTICATED,
    ("POST", f"{_V1}/auth/api-keys"): "ADMIN",
    ("GET", f"{_V1}/auth/api-keys"): "ADMIN",
    ("DELETE", f"{_V1}/auth/api-keys/{{key_id}}"): "ADMIN",
    # --- synthesis jobs ----------------------------------------------------
    ("POST", f"{_V1}/jobs/synthesize"): "MEMBER",
    ("GET", f"{_V1}/jobs/{{job_id}}"): "VIEWER",
    # --- models ------------------------------------------------------------
    ("POST", f"{_V1}/model/synthesize"): "MEMBER",
    ("GET", f"{_V1}/model"): "VIEWER",
    ("POST", f"{_V1}/model/diff"): "VIEWER",
    ("POST", f"{_V1}/model/validate-graph"): AUTHENTICATED,
    ("GET", f"{_V1}/model/{{model_id}}"): "VIEWER",
    ("PATCH", f"{_V1}/model/{{model_id}}"): "MEMBER",
    ("DELETE", f"{_V1}/model/{{model_id}}"): "ADMIN",
    ("POST", f"{_V1}/model/{{model_id}}/approve"): "APPROVER",
    ("PUT", f"{_V1}/model/{{model_id}}/graph"): "MEMBER",
    ("POST", f"{_V1}/model/{{model_id}}/validate"): "VIEWER",
    ("GET", f"{_V1}/model/{{model_id}}/export"): "VIEWER",
    ("POST", f"{_V1}/model/{{model_id}}/export/synthetic-data"): "VIEWER",
    ("GET", f"{_V1}/model/{{model_id}}/export/contract"): "VIEWER",
    ("GET", f"{_V1}/model/{{model_id}}/export/semantic"): "VIEWER",
    ("GET", f"{_V1}/model/{{model_id}}/export/dictionary"): "VIEWER",
    ("GET", f"{_V1}/model/{{model_id}}/export/zip"): "VIEWER",
    ("POST", f"{_V1}/model/{{model_id}}/transform-paradigm"): "MEMBER",
    # --- workspaces --------------------------------------------------------
    ("GET", f"{_V1}/workspaces"): AUTHENTICATED,
    # --- trainer -----------------------------------------------------------
    ("POST", f"{_V1}/trainer/assignments"): "MEMBER",
    ("GET", f"{_V1}/trainer/assignments"): "VIEWER",
    ("GET", f"{_V1}/trainer/assignments/{{assignment_id}}"): "VIEWER",
    ("POST", f"{_V1}/trainer/socratic/step"): "MEMBER",
    ("POST", f"{_V1}/trainer/grade"): "MEMBER",
    # --- connectors --------------------------------------------------------
    ("POST", f"{_V1}/connectors"): "ADMIN",
    ("GET", f"{_V1}/connectors"): "VIEWER",
    ("DELETE", f"{_V1}/connectors/{{connection_id}}"): "ADMIN",
    ("POST", f"{_V1}/connectors/introspect"): "MEMBER",
    # --- audit and egress --------------------------------------------------
    ("GET", f"{_V1}/audit/events"): "ADMIN",
    ("GET", f"{_V1}/audit/export"): "ADMIN",
    ("GET", f"{_V1}/audit/appliance-events"): APPLIANCE_OWNER,
    ("GET", f"{_V1}/audit/appliance-export"): APPLIANCE_OWNER,
    ("GET", f"{_V1}/egress/events"): "VIEWER",
    # --- SCIM --------------------------------------------------------------
    ("GET", f"{_V1}/scim/v2/Users"): SCIM,
    ("GET", f"{_V1}/scim/v2/Users/{{user_id}}"): SCIM,
    ("POST", f"{_V1}/scim/v2/Users"): SCIM,
    ("PATCH", f"{_V1}/scim/v2/Users/{{user_id}}"): SCIM,
    ("DELETE", f"{_V1}/scim/v2/Users/{{user_id}}"): SCIM,
    # --- export status (a statement about the build; needs sign-in) --------
    ("GET", f"{_V1}/export/status"): AUTHENTICATED,
    # --- offline DDL import (Sprint 8) ---------------------------------------
    ("GET", f"{_V1}/import/dialects"): AUTHENTICATED,
    ("POST", f"{_V1}/import/ddl"): "MEMBER",
    ("GET", f"{_V1}/model/{{model_id}}/import-report"): "VIEWER",
}
