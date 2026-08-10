"""Database connection + introspection endpoints (Phase 2, FR-2.1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_membership,
    require_workspace_role,
    resolve_user_workspace,
)
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.metadata_store import (
    CONNECTION_ENGINES,
    DatabaseConnection,
    DataModel,
    WorkspaceMember,
)
from app.schemas.data_model import (
    ConnectionCreateRequest,
    ConnectionInfo,
    IntrospectRequest,
    SynthesizeResponse,
)
from app.services.graph_engine import GraphEngine
from app.services.graph_repository import GraphRepository
from app.services.introspection import (
    IntrospectionDriverError,
    IntrospectionService,
)

router = APIRouter(prefix="/connectors", tags=["connectors"])


def _to_info(connection: DatabaseConnection) -> ConnectionInfo:
    return ConnectionInfo(
        connection_id=connection.connection_id,
        workspace_id=connection.workspace_id,
        name=connection.name,
        engine=connection.engine,
        uri_masked=f"{connection.engine.lower()}://***",
    )


@router.post(
    "",
    response_model=ConnectionInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Register an external database connection (ADMIN+)",
)
async def create_connection(
    payload: ConnectionCreateRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> ConnectionInfo:
    engine = payload.engine.upper()
    if engine not in CONNECTION_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported engine: {payload.engine}",
        )
    workspace_id = await resolve_user_workspace(
        session, user, payload.workspace_id
    )
    await require_workspace_role(session, user.user_id, workspace_id, "ADMIN")

    connection = DatabaseConnection(
        workspace_id=workspace_id,
        name=payload.name,
        engine=engine,
        connection_uri_encrypted=encrypt_secret(payload.connection_uri),
    )
    session.add(connection)
    await session.flush()
    return _to_info(connection)


@router.get(
    "",
    response_model=list[ConnectionInfo],
    summary="List database connections (URIs masked)",
)
async def list_connections(
    session: SessionDep, user: CurrentUserDep
) -> list[ConnectionInfo]:
    rows = (
        await session.execute(
            select(DatabaseConnection)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id
                == DatabaseConnection.workspace_id,
            )
            .where(WorkspaceMember.user_id == user.user_id)
            .order_by(DatabaseConnection.name)
        )
    ).scalars().all()
    return [_to_info(c) for c in rows]


@router.post(
    "/introspect",
    response_model=SynthesizeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Introspect a saved connection into a data model",
)
async def introspect_connection(
    payload: IntrospectRequest, session: SessionDep, user: CurrentUserDep
) -> SynthesizeResponse:
    connection = await session.get(DatabaseConnection, payload.connection_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection {payload.connection_id} not found.",
        )
    await require_membership(session, user.user_id, connection.workspace_id)

    uri = decrypt_secret(connection.connection_uri_encrypted)
    engine = connection.engine
    try:
        if engine == "POSTGRESQL":
            graph = await IntrospectionService.introspect_postgresql(
                uri, payload.schema_name
            )
        elif engine == "SNOWFLAKE":
            graph = await IntrospectionService.introspect_snowflake(
                uri, payload.schema_name
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Introspection for {engine} is not yet supported.",
            )
    except IntrospectionDriverError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface connection/query failures
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Introspection failed: {exc}",
        ) from exc

    model = DataModel(
        workspace_id=connection.workspace_id,
        title=f"{connection.name}:{payload.schema_name}",
        current_paradigm="3NF",
        target_dialect=engine.lower(),
    )
    session.add(model)
    await session.flush()
    await GraphRepository(session).replace_graph(
        model.model_id, graph.entities, graph.relationships
    )

    return SynthesizeResponse(
        model_id=model.model_id,
        paradigm="3NF",  # type: ignore[arg-type]
        entities=graph.entities,
        relationships=graph.relationships,
        suggested_metrics=[],
        validation=GraphEngine().validate(graph.entities, graph.relationships),
    )
