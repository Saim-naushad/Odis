from __future__ import annotations

from pathlib import Path

from application.observation_pipeline import ObservationPipeline
from application.reasoning_session import ReasoningSession
from domain.entities.operational_goal import OperationalGoal
from infrastructure.sources import CsvObservationSource, StaticObservationSource


def _example_csv_path() -> Path:
    return Path(__file__).resolve().parents[3] / "examples" / "data" / "heatwave.csv"


def main() -> None:
    goal = OperationalGoal(
        id="goal-grid-stability",
        description="Maintain grid stability during peak demand",
    )

    csv_source = CsvObservationSource(_example_csv_path())
    loaded_observations = csv_source.read()

    pipeline = ObservationPipeline(session=ReasoningSession())
    result = pipeline.process(goal, StaticObservationSource(loaded_observations))

    print(f"CSV loaded: {len(loaded_observations)} observations")
    print("Assessment:")
    print(result.situation.assessment)
    print("Priority:")
    print(result.plan.priority.name)
    print("Recommendation:")
    print(result.plan.recommendation)


if __name__ == "__main__":
    main()
