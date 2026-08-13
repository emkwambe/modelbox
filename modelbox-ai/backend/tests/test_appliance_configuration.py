"""The shipped appliance supplies every setting its own code requires (S5-3).

A fail-closed default is only half a design. The other half is the deployment
saying so, and nothing connected the two: `MODELBOX_ALLOW_PROVIDER_CALLS`
defaults to `False` in `Settings` — correctly, since that is what keeps the test
suite offline by construction — and appeared nowhere in
`docker-compose.appliance.yml`. Every call site of `structured_completion`
routes through the choke point, so a fresh install would have refused synthesis,
paradigm translation and the Trainer alike, with a governance error.

**The isolation was structural, so it isolated the product too.** That is the
defect working exactly as designed, in a venue nobody pointed it at.

Neither existing gate could see it. The app suite runs with the flag unset on
purpose, and asserts so. The fidelity harness never starts the appliance. A
container smoke test would have caught it only by exercising synthesis, which is
the one thing the programme's zero-egress constraint forbids. So the check has
to be static: read what the deployment supplies, and hold it against what the
code demands.

The second test here is the general form and matters more than the first. A
mistyped or renamed environment variable in compose binds to nothing and fails
silently in the permissive direction — standard 12's unreachability form,
arriving through the deployment rather than through a `validation_alias`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

COMPOSE = (
    Path(__file__).resolve().parents[2] / "docker" / "docker-compose.appliance.yml"
)
SPEC = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

# The services that run application code and therefore construct a gateway.
# Named rather than inferred: inferring "services with the backend image" would
# quietly stop covering a service that switched image.
APP_SERVICES = ("modelbox-backend", "modelbox-worker")


def _env(service: str) -> dict[str, str]:
    entries = SPEC["services"][service].get("environment") or []
    out: dict[str, str] = {}
    for entry in entries:
        name, _, value = str(entry).partition("=")
        out[name.strip()] = value
    return out


def _accepted_env_names() -> set[str]:
    """Every environment name `Settings` will actually bind.

    Read off the model rather than restated, so a renamed field or a changed
    alias makes the compose check fail rather than silently stop matching.
    """
    names: set[str] = set()
    for field_name, field in Settings.model_fields.items():
        names.add(field_name.upper())
        alias = field.validation_alias
        if alias is None:
            continue
        choices = getattr(alias, "choices", None)
        if choices is None:
            names.add(str(alias).upper())
        else:
            names.update(str(choice).upper() for choice in choices)
    return names


@pytest.mark.parametrize("service", APP_SERVICES)
def test_the_appliance_supplies_the_egress_opt_in(service: str) -> None:
    """Without this the appliance refuses its own core function on a fresh install.

    The flag is deliberately not defaulted to permissive in code — that default
    is what keeps this suite offline. The deployment is the correct place to opt
    in, because the appliance is the thing that intends to call providers.
    """
    env = _env(service)
    assert "MODELBOX_ALLOW_PROVIDER_CALLS" in env, (
        f"{service} never opts in to outbound provider calls, so synthesis, "
        f"paradigm translation and the Trainer all refuse on a fresh install"
    )
    assert env["MODELBOX_ALLOW_PROVIDER_CALLS"].endswith(":-1}"), (
        f"{service} must default the opt-in on and let an operator override it; "
        f"got {env['MODELBOX_ALLOW_PROVIDER_CALLS']!r}"
    )


@pytest.mark.parametrize("service", APP_SERVICES)
def test_airgapped_remains_the_residency_control(service: str) -> None:
    """The two flags must not collapse into one another.

    `AIRGAPPED` strips every non-local provider at route resolution and is the
    governance control a regulated buyer is shown. The egress opt-in is a
    fail-closed switch for the library. Losing either would leave one flag doing
    two jobs, which is what produced this defect.
    """
    env = _env(service)
    assert "AIRGAPPED" in env, f"{service} cannot be put into air-gapped mode"
    assert env["AIRGAPPED"].endswith(":-false}"), (
        f"{service} must default to non-air-gapped and let an operator opt in"
    )


@pytest.mark.parametrize("service", APP_SERVICES)
def test_every_modelbox_env_var_binds_to_a_real_setting(service: str) -> None:
    """The general guard: a compose variable that binds to nothing is invisible.

    A typo, or a field renamed in `Settings` without the compose following,
    produces an environment variable the application silently ignores — and the
    failure direction is whatever the code default happens to be. That is the
    same shape as a bare `validation_alias` making a flag unsettable: not
    absent, not empty, just never read.

    Scoped to `MODELBOX_`-prefixed names, which are unambiguously ours. Provider
    keys and infrastructure URLs are read by other means and by other services.
    """
    accepted = _accepted_env_names()
    ours = {name for name in _env(service) if name.startswith("MODELBOX_")}
    unbound = sorted(name for name in ours if name not in accepted)
    assert not unbound, (
        f"{service} sets {unbound}, which no Settings field binds — the "
        f"application ignores them and falls back to its code defaults"
    )


def test_the_accepted_name_set_is_not_empty() -> None:
    """Fixture sanity: if alias introspection broke, the check above passes vacuously.

    `_accepted_env_names` reads pydantic internals. A pydantic upgrade that
    changed `validation_alias` would make it return field names only, and the
    test above would then pass while checking nothing about aliases — which is
    precisely the flag it exists to protect.
    """
    accepted = _accepted_env_names()
    assert "MODELBOX_ALLOW_PROVIDER_CALLS" in accepted, (
        "alias introspection no longer resolves AliasChoices, so the compose "
        "check above cannot see aliased settings"
    )
    assert "AIRGAPPED" in accepted
