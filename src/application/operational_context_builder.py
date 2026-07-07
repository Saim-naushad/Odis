from __future__ import annotations

from application.operational_context import OperationalContext


class OperationalContextBuilder:
    def build(
        self,
        description: str,
        operating_mode: str | None = None,
        objective: str | None = None,
    ) -> OperationalContext:
        return OperationalContext(
            description=description,
            operating_mode=operating_mode,
            objective=objective,
        )
