"""Shared FastAPI dependencies for the v1 API.

Assembles service classes with their injected async session + LLM gateway so
route handlers receive fully-constructed engines and stay logic-free.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.services.exporter_service import ExporterService
from app.services.llm_gateway import LLMGateway, get_llm_gateway
from app.services.paradigm_translator import ParadigmTranslator
from app.services.synthesis_engine import SynthesisEngine

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
GatewayDep = Annotated[LLMGateway, Depends(get_llm_gateway)]


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
