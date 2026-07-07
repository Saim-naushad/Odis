from __future__ import annotations

from collections.abc import Callable, Iterable

from application.hypothesis import Hypothesis


class HypothesisRefiner:
    __slots__ = ()

    def refine(
        self,
        hypotheses: Iterable[Hypothesis],
        is_consistent: Callable[[Hypothesis], bool],
    ) -> tuple[Hypothesis, ...]:
        return tuple(
            hypothesis
            for hypothesis in hypotheses
            if is_consistent(hypothesis)
        )

