"""Mapping between application reasoning traces and ORM models."""

from application.reasoning_trace import ReasoningTrace, TraceStep
from backend.app.infrastructure.database.models.reasoning_trace import (
    ReasoningTraceModel,
)


def reasoning_trace_to_model(run_id: str, trace: ReasoningTrace) -> ReasoningTraceModel:
    """Map an application reasoning trace to its SQLAlchemy representation."""
    return ReasoningTraceModel(
        run_id=run_id,
        steps=[
            {"name": step.name, "description": step.description}
            for step in trace.steps
        ],
    )


def reasoning_trace_to_domain(model: ReasoningTraceModel) -> ReasoningTrace:
    """Map a SQLAlchemy reasoning trace row to the application model."""
    return ReasoningTrace(
        steps=tuple(
            TraceStep(name=step["name"], description=step["description"])
            for step in model.steps
        )
    )
