"""Database connection + introspection endpoints (Phase 2, FR-2.1)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_body_workspace_role,
    require_listed_workspaces,
    require_resource_role,
)
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.metadata_store import (
    CONNECTION_ENGINES,
    DatabaseConnection,
    DataModel,
)
from app.schemas.data_model import (
    ConnectionCreateRequest,
    ConnectionInfo,
    IntrospectRequest,
    SynthesizeResponse,
)
from app.services import audit_log
from app.services.graph_engine import GraphEngine
from app.services.graph_repository import GraphRepository
from app.services.introspection import (
    IntrospectionDriverError,
    IntrospectionService,
    InvalidIdentifierError,
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
    workspace_id: Annotated[uuid.UUID, Depends(require_body_workspace_role("ADMIN"))],
) -> ConnectionInfo:
    engine = payload.engine.upper()
    if engine not in CONNECTION_ENGINES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported engine: {payload.engine}",
        )
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
    session: SessionDep,
    ws_ids: Annotated[list[uuid.UUID], Depends(require_listed_workspaces("VIEWER"))],
) -> list[ConnectionInfo]:
    if not ws_ids:
        return []
    rows = (
        await session.execute(
            select(DatabaseConnection)
            .where(DatabaseConnection.workspace_id.in_(ws_ids))
            .order_by(DatabaseConnection.name)
        )
    ).scalars().all()
    return [_to_info(c) for c in rows]


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a database connection (ADMIN+)",
)
async def delete_connection(
    connection_id: uuid.UUID,
    session: SessionDep,
    connection: Annotated[
        DatabaseConnection,
        Depends(
            require_resource_role("ADMIN", DatabaseConnection, "connection_id", "path")
        ),
    ],
) -> Response:
    """Remove a stored connection. Requires ADMIN+ in its workspace."""
    await session.delete(connection)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/introspect",
    response_model=SynthesizeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Introspect a saved connection into a data model",
)
async def introspect_connection(
    payload: IntrospectRequest,
    session: SessionDep,
    user: CurrentUserDep,
    connection: Annotated[
        DatabaseConnection,
        Depends(
            require_resource_role("MEMBER", DatabaseConnection, "connection_id", "body")
        ),
    ],
) -> SynthesizeResponse:
    """Introspect a saved connection into a new model (MEMBER+)."""
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
        elif engine == "BIGQUERY":
            graph = await IntrospectionService.introspect_bigquery(
                uri, payload.schema_name
            )
        elif engine == "MYSQL":
            graph = await IntrospectionService.introspect_mysql(
                uri, payload.schema_name
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Introspection for {engine} is not yet supported.",
            )
    except InvalidIdentifierError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
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
    await audit_log.record(
        action="MODEL_CREATED",
        actor_user_id=user.user_id,
        actor_email=user.email,
        workspace_id=model.workspace_id,
        resource_type="model",
        resource_id=str(model.model_id),
        detail={"title": model.title, "via": "introspection", "engine": engine},
    )

    return SynthesizeResponse(
        model_id=model.model_id,
        paradigm="3NF",  # type: ignore[arg-type]
        entities=graph.entities,
        relationships=graph.relationships,
        suggested_metrics=[],
        validation=GraphEngine().validate(graph.entities, graph.relationships),
    )
