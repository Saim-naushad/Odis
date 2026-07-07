from pathlib import Path

from application.observation_pipeline import ObservationPipeline
from application.reasoning_session import ReasoningSession
from domain.entities.operational_goal import OperationalGoal
from domain.value_objects.priority import Priority
from infrastructure.sources.csv_observation_source import CsvObservationSource


def test_csv_heatwave_example_runs_end_to_end() -> None:
    csv_path = (
        Path(__file__).resolve().parents[2] / "examples" / "data" / "heatwave.csv"
    )

    goal = OperationalGoal(
        id="goal-grid-stability",
        description="Maintain grid stability during peak demand",
    )

    result = ObservationPipeline(session=ReasoningSession()).process(
        goal,
        CsvObservationSource(csv_path),
    )

    assert result.situation.assessment == "Increasing operational stress detected"
    assert result.plan.priority == Priority.HIGH
