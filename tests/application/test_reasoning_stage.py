from dataclasses import dataclass

from application.operational_profile import OperationalProfile
from application.reasoning.context import ReasoningContext
from application.reasoning.stage import ReasoningStage
from tests.builders import build_goal, build_observation_sequence


@dataclass(frozen=True, slots=True)
class _AppendStage:
    name: str
    suffix: str

    def run(self, context: ReasoningContext) -> ReasoningContext:
        run_id = context.metadata.run_id or ""
        return context.with_metadata(run_id=f"{run_id}{self.suffix}")


def test_reasoning_stage_protocol_accepts_explicit_stage_tuple() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([1.0, 2.0]),
        profile=OperationalProfile.default(),
    )
    stages: tuple[ReasoningStage, ...] = (
        _AppendStage(name="First", suffix="a"),
        _AppendStage(name="Second", suffix="b"),
    )

    current = context
    for stage in stages:
        current = stage.run(current)

    assert current.metadata.run_id == "ab"
