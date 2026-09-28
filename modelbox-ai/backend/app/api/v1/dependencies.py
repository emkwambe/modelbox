"""Shared FastAPI dependencies for the v1 API.

Assembles service classes with their injected async session + LLM gateway so
route handlers receive fully-constructed engines and stay logic-free. Also
hosts the authentication + workspace-authorization dependencies (Slice 3A).
"""

from __future__ import annotations

import datetime
import functools
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import TokenError, decode_access_token, hash_api_key
from app.models.metadata_store import (
    ApiKey,
    DataModel,
    User,
    Workspace,
    WorkspaceMember,
)
from app.services.exporter_service import ExporterService
from app.services.llm_gateway import LLMGateway, get_llm_gateway
from app.services.paradigm_translator import ParadigmTranslator
from app.services.synthesis_engine import SynthesisEngine

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
GatewayDep = Annotated[LLMGateway, Depends(get_llm_gateway)]


# ---------------------------------------------------------------------------
# Service providers
# ---------------------------------------------------------------------------
def get_synthesis_engine(
    session: SessionDep, gateway: GatewayDep
) -> SynthesisEngine:
    """Provide a request-scoped :class:`SynthesisEngine`."""
    return SynthesisEngine(session, gateway)


def get_paradigm_translator(
    session: SessionDep, gateway: GatewayDep
) -> ParadigmTranslator:
    """Provide a request-scoped :class:`ParadigmTranslator`."""
    return ParadigmTranslator(session, gateway)


def get_exporter_service() -> ExporterService:
    """Provide a stateless :class:`ExporterService`."""
    return ExporterService()


SynthesisEngineDep = Annotated[SynthesisEngine, Depends(get_synthesis_engine)]
ParadigmTranslatorDep = Annotated[
    ParadigmTranslator, Depends(get_paradigm_translator)
]
ExporterServiceDep = Annotated[ExporterService, Depends(get_exporter_service)]


# ---------------------------------------------------------------------------
# Authentication & workspace authorization (Slice 3A)
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _user_from_api_key(session: AsyncSession, raw_key: str) -> User | None:
    """Resolve the user behind an ``X-API-Key`` (None if invalid/expired)."""
    record = (
        await session.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw_key))
        )
    ).scalar_one_or_none()
    if record is None:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    if record.expires_at is not None:
        expires = record.expires_at
        if expires.tzinfo is None:  # SQLite returns naive datetimes
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        if expires <= now:
            return None

    record.last_used_at = now
    await session.flush()

    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    api_key: Annotated[str | None, Depends(_api_key_header)] = None,
) -> User:
    """Resolve the caller from a Bearer JWT or an ``X-API-Key`` (401 on failure)."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Programmatic access: X-API-Key (for CI/CD pipelines and agents).
    if api_key:
        user = await _user_from_api_key(session, api_key)
        if user is None:
            raise unauthorized
        return user

    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise unauthorized from exc

    # Resolution is delegated, because "who is this token" stopped being a
    # primary-key lookup the moment an external IdP was in scope. An OIDC
    # subject is an opaque provider string, so the old `uuid.UUID(sub)` path
    # rejected every real identity provider with a 401 that looked like a
    # signature problem. See `services/federated_identity.py`.
    from app.services import federated_identity

    user = await federated_identity.resolve(session, payload)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_membership(
    session: AsyncSession, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> WorkspaceMember:
    """Return the caller's membership in ``workspace_id`` or raise 403."""
    member = (
        await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace.",
        )
    return member


async def resolve_user_workspace(
    session: AsyncSession, user: User, workspace_id: uuid.UUID | None
) -> uuid.UUID:
    """Resolve the workspace for a write op, enforcing/creating membership.

    If ``workspace_id`` is given, membership is required. Otherwise the user's
    first workspace is used, or a personal one is created (as OWNER).
    """
    if workspace_id is not None:
        await require_membership(session, user.user_id, workspace_id)
        return workspace_id

    existing = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.user_id == user.user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.workspace_id

    workspace = Workspace(name=f"{user.email}'s Workspace")
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.workspace_id,
            user_id=user.user_id,
            role="OWNER",
        )
    )
    await session.flush()
    return workspace.workspace_id


# Role hierarchy for RBAC: OWNER > ADMIN > MEMBER (Slice B2).
#: The role ladder, lowest to highest (G10).
#:
#: **Extended rather than replaced.** The sprint plan names the roles
#: viewer / modeller / approver / admin, and the obvious move is to adopt that
#: vocabulary wholesale. It would also rewrite the role of every existing
#: member, invalidate the CHECK constraint every row was written under, and
#: require a data migration whose failure mode is somebody silently losing
#: access. `MEMBER` *is* the modeller — it is the role that edits a model — so
#: the ladder gains the two levels it genuinely lacked and keeps the three it
#: had.
#:
#: `VIEWER` exists because read-only access had no expression at all: the
#: lowest role could edit every model in the workspace, so "let the auditor
#: look" and "let the auditor change things" were the same grant.
_ROLE_LEVEL: dict[str, int] = {
    "VIEWER": 1,
    "MEMBER": 2,
    "APPROVER": 3,
    "ADMIN": 4,
    "OWNER": 5,
}


async def require_workspace_role(
    session: AsyncSession,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    min_role: str,
) -> WorkspaceMember:
    """Assert the caller has at least ``min_role`` in ``workspace_id``."""
    member = await require_membership(session, user_id, workspace_id)
    if _ROLE_LEVEL.get(member.role, 0) < _ROLE_LEVEL.get(min_role, 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action requires minimum role of {min_role}.",
        )
    return member


# ---------------------------------------------------------------------------
# Route authorization (Sprint 7, Step 2)
# ---------------------------------------------------------------------------
# Every route declares its minimum role through exactly one of the dependencies
# below, and each carries that role as `policy_role`. `route_policy.py` holds
# the table; `test_route_policy.py` walks every route and fails on any whose
# dependency chain does not carry the role the table declares.
#
# Enforcement lives in dependencies rather than in handler bodies because only
# a dependency is visible to that walk. A check inside a handler cannot be told
# apart from a missing one without reading the code, which is how
# `transform-paradigm` shipped checking membership alone.
#
# The factories are cached per role, so `require_model_role("MEMBER")` is one
# object everywhere: a test can override exactly the dependency a route uses.

AUTHENTICATED = "AUTHENTICATED"


def _declares(role: str, scope: str):
    """Attach the role a dependency enforces, for the route-policy walk."""

    def mark(fn):
        fn.policy_role = role
        fn.policy_scope = scope
        return fn

    return mark


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _as_uuid(value: object, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise _bad_request(f"{name} must be a UUID.") from exc


async def _json_body(request: Request) -> dict:
    """The request's JSON object, read once and cached by Starlette.

    Read here so a dependency can authorize against a workspace named in the
    body without the route changing its request shape. FastAPI still parses
    and validates the body for the handler as before.
    """
    try:
        data = await request.json()
    except ValueError as exc:
        raise _bad_request("Request body must be JSON.") from exc
    if not isinstance(data, dict):
        raise _bad_request("Request body must be a JSON object.")
    return data


async def _load_model(session: AsyncSession, model_id: uuid.UUID) -> DataModel:
    model = await session.get(DataModel, model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found.",
        )
    return model


@_declares(AUTHENTICATED, "authenticated")
async def require_authenticated(user: CurrentUserDep) -> User:
    """Any signed-in caller. For routes that touch no workspace's data."""
    return user


@functools.cache
def require_model_role(min_role: str):
    """The model named by the ``model_id`` path parameter, at ``min_role``+.

    404 if the model is absent, 403 if the caller is not a member of its
    workspace or holds a lower role.
    """

    @_declares(min_role, "model")
    async def _checker(
        model_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
    ) -> DataModel:
        model = await _load_model(session, model_id)
        await require_workspace_role(session, user.user_id, model.workspace_id, min_role)
        return model

    _checker.__qualname__ = f"require_model_role({min_role!r})"
    return _checker


@functools.cache
def require_query_workspace_role(min_role: str):
    """The workspace named by the required ``workspace_id`` query parameter."""

    @_declares(min_role, "query")
    async def _checker(
        workspace_id: Annotated[uuid.UUID, Query()],
        session: SessionDep,
        user: CurrentUserDep,
    ) -> uuid.UUID:
        await require_workspace_role(session, user.user_id, workspace_id, min_role)
        return workspace_id

    _checker.__qualname__ = f"require_query_workspace_role({min_role!r})"
    return _checker


@functools.cache
def require_body_workspace_role(min_role: str):
    """The workspace named by the body's optional ``workspace_id``.

    Omitted means the caller's first workspace, or a new personal one where
    they are OWNER (:func:`resolve_user_workspace`). The role is checked on
    whichever workspace results, so the default cannot bypass it.
    """

    @_declares(min_role, "body")
    async def _checker(
        request: Request, session: SessionDep, user: CurrentUserDep
    ) -> uuid.UUID:
        raw = (await _json_body(request)).get("workspace_id")
        requested = None if raw is None else _as_uuid(raw, "workspace_id")
        workspace_id = await resolve_user_workspace(session, user, requested)
        await require_workspace_role(session, user.user_id, workspace_id, min_role)
        return workspace_id

    _checker.__qualname__ = f"require_body_workspace_role({min_role!r})"
    return _checker


@functools.cache
def require_resource_role(min_role: str, model_cls: type, param: str, source: str):
    """A row that carries ``workspace_id``, named by a path or body field.

    ``source`` is ``"path"`` or ``"body"``; ``param`` is the field. The row is
    loaded, 404 if absent, and the role checked on its workspace.
    """

    @_declares(min_role, f"{source}-resource")
    async def _checker(
        request: Request, session: SessionDep, user: CurrentUserDep
    ):
        if source == "path":
            raw = request.path_params.get(param)
        else:
            raw = (await _json_body(request)).get(param)
        if raw is None:
            raise _bad_request(f"{param} is required.")
        resource_id = _as_uuid(raw, param)
        row = await session.get(model_cls, resource_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{model_cls.__name__} {resource_id} not found.",
            )
        await require_workspace_role(session, user.user_id, row.workspace_id, min_role)
        return row

    _checker.__qualname__ = (
        f"require_resource_role({min_role!r}, {model_cls.__name__}, {param!r})"
    )
    return _checker


@functools.cache
def require_body_models_role(min_role: str, fields: tuple[str, ...]):
    """Every model named by the body fields in ``fields``, each at ``min_role``+."""

    @_declares(min_role, "body-models")
    async def _checker(
        request: Request, session: SessionDep, user: CurrentUserDep
    ) -> list[DataModel]:
        body = await _json_body(request)
        models: list[DataModel] = []
        for field in fields:
            model = await _load_model(session, _as_uuid(body.get(field), field))
            await require_workspace_role(
                session, user.user_id, model.workspace_id, min_role
            )
            models.append(model)
        return models

    _checker.__qualname__ = f"require_body_models_role({min_role!r}, {fields!r})"
    return _checker


@functools.cache
def require_listed_workspaces(min_role: str):
    """The workspaces a listing may read: those where the caller is ``min_role``+.

    An optional ``workspace_id`` query parameter narrows it to one, and names a
    workspace the caller holds no such role in is a 403 rather than an empty
    list, so a refusal is not mistaken for an empty workspace.
    """

    @_declares(min_role, "listing")
    async def _checker(
        session: SessionDep,
        user: CurrentUserDep,
        workspace_id: Annotated[uuid.UUID | None, Query()] = None,
    ) -> list[uuid.UUID]:
        rows = (
            await session.execute(
                select(WorkspaceMember).where(WorkspaceMember.user_id == user.user_id)
            )
        ).scalars().all()
        allowed = [
            row.workspace_id
            for row in rows
            if _ROLE_LEVEL.get(row.role, 0) >= _ROLE_LEVEL[min_role]
        ]
        if workspace_id is None:
            return allowed
        if workspace_id not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action requires minimum role of {min_role}.",
            )
        return [workspace_id]

    _checker.__qualname__ = f"require_listed_workspaces({min_role!r})"
    return _checker


AuthenticatedDep = Annotated[User, Depends(require_authenticated)]
ModelViewerDep = Annotated[DataModel, Depends(require_model_role("VIEWER"))]
ModelMemberDep = Annotated[DataModel, Depends(require_model_role("MEMBER"))]
