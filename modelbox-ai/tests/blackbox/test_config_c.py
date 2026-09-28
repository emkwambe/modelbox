"""Configuration C: AIRGAPPED=true, sentinel provider keys, an egress-deny network.

The CI job writes sentinel values for every provider key into `.env`, sets
AIRGAPPED=true, and starts the appliance with tests/blackbox/compose/
egress-deny.yml, where every service but the UI is on an internal network
with no gateway.

* The backend starts, and says it is air-gapped.
* A synthesis request that names a cloud provider is refused at route
  resolution: the backend's log records the air-gap refusal.
* Zero outbound attempts: the egress ledger, which the gateway writes before
  it dials anything, holds no row, and the backend's log has no routing line.

The first check is the precondition: the network really denies egress, so a
pass below is not a box that merely happened to have no route out.

HTTP here goes from inside the UI container to the UI's own port
(conftest.ExecTransport): with the UI also on the internal network, Docker
Engine 28.0.4 reset every host connection to its published port. The
requests take the same path through the UI to the backend.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import World, bearer, check, compose, sql_ok, token

pytestmark = pytest.mark.config_c

_PROBE = (
    "import socket\n"
    "try:\n"
    "    socket.create_connection(('1.1.1.1', 443), timeout=5)\n"
    "except OSError:\n"
    "    raise SystemExit(3)\n"
)


def _backend_log() -> str:
    logs = compose("logs", "--no-color", "modelbox-backend")
    assert logs.returncode == 0, "setup: docker compose logs"
    return logs.stdout


def test_c0_the_backend_cannot_reach_outside() -> None:
    probe = compose("exec", "-T", "modelbox-backend", "python", "-c", _PROBE)
    check(probe.returncode == 3, f"the backend opened an outbound connection (exit {probe.returncode})")


def test_c1_the_backend_starts_airgapped(client: httpx.Client) -> None:
    health = client.get("/api/health").json()
    check(health["status"] == "ok" and health["airgapped"] is True, f"/health: {health}")


def test_c2_a_cloud_route_is_refused_at_resolution(client: httpx.Client, world: World) -> None:
    owner = bearer(token(client, world.owner.email, world.owner.password))
    response = client.post(
        "/api/v1/model/synthesize",
        headers=owner,
        json={
            "content": "Customers place orders for products.",
            "workspace_id": world.workspace_a,
            "llm_override": "anthropic_cloud",
        },
    )
    check(response.status_code >= 400, f"a cloud-routed synthesis got HTTP {response.status_code}")
    check("Air-gapped mode active" in _backend_log(),
          "the backend's log has no air-gap refusal for the request")


def test_c3_zero_outbound_attempts(client: httpx.Client, world: World) -> None:
    rows = sql_ok("SELECT count(*) FROM egress_audit;")
    check(rows == "0", f"the egress ledger holds {rows} rows")
    check("Routing task" not in _backend_log(), "the backend's log shows a request routed to a provider")
