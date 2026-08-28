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


# ---------------------------------------------------------------------------
# Provider credentials actually reach the container (G1)
# ---------------------------------------------------------------------------
# The same shape as the egress opt-in above, one layer down: the appliance
# declared the setting and the deployment did not deliver it. Every provider key
# was written as `${ANTHROPIC_API_KEY:-}`, and interpolation reads Compose's
# *project directory* — this file's own folder. The documented quickstart puts
# `.env` one level up, so a documented install resolved every key to the empty
# string and failed at the first synthesis with the whole chain exhausted.
#
# Two assertions, because there are two ways to lose the keys and the second is
# the one that would be reintroduced by someone "restoring" the explicit list:
# `environment:` overrides `env_file:`, so an empty-defaulting entry there
# silently wins over the file.
KEY_SERVICES = ("modelbox-backend", "modelbox-worker", "litellm-proxy")
PROVIDER_KEY_SUFFIX = "_API_KEY"


@pytest.mark.parametrize("service", KEY_SERVICES)
def test_provider_keys_are_delivered_by_file(service: str) -> None:
    """A key read from the wrong directory is a key the container never gets."""
    spec = SPEC["services"][service]
    declared = spec.get("env_file") or []
    files = [str(entry) for entry in declared]
    assert any(name.endswith("../.env") for name in files), (
        f"{service} has no env_file, so provider keys depend on Compose's "
        f"project directory rather than on this file's location — the "
        f"documented install delivers none of them"
    )


@pytest.mark.parametrize("service", KEY_SERVICES)
def test_no_provider_key_is_restated_in_environment(service: str) -> None:
    """`environment:` wins over `env_file:`, so restating a key clobbers it."""
    restated = sorted(
        name for name in _env(service) if name.endswith(PROVIDER_KEY_SUFFIX)
    )
    assert not restated, (
        f"{service} restates {restated} under `environment:`, which overrides "
        f"`env_file` — an empty default there silently discards the real value"
    )


README = Path(__file__).resolve().parents[2] / "README.md"


def test_the_documented_install_passes_the_env_file() -> None:
    """`env_file:` covers credentials. It does not cover interpolation.

    Every `${VAR}` in the compose file is substituted before any container
    exists, from Compose's project directory — which is `docker/`, not the
    directory holding `.env`. So `UI_PORT`, `POSTGRES_PASSWORD`,
    `ENCRYPTION_KEY` and `AIRGAPPED` all silently take their defaults unless
    the invocation names the file.

    Silently is the operative word for three of the four: the appliance comes
    up on the default database password and looks fine. Only `UI_PORT` fails
    loudly, and only because something else already holds port 3000 — which is
    how this was found at all.
    """
    quickstart = [
        line
        for line in README.read_text(encoding="utf-8").splitlines()
        if "docker compose" in line and "docker-compose.appliance.yml" in line
    ]
    assert quickstart, "README no longer documents how to start the appliance"
    missing = [line.strip() for line in quickstart if "--env-file" not in line]
    assert not missing, (
        "the documented install omits --env-file, so compose-level variables "
        f"fall back to defaults: {missing}"
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
