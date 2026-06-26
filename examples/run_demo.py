import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXAMPLES_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXAMPLES_DIR))

from application.reasoning_replay import ReplayResult
from heatwave_demo import main as run_heatwave_demo
from oscillating_operations_demo import main as run_oscillating_demo
from stable_operations_demo import main as run_stable_operations_demo

SCENARIO_SEPARATOR = "=" * 60


def print_scenario_header(number: int, name: str) -> None:
    print()
    print(SCENARIO_SEPARATOR)
    print(f"Scenario {number}: {name}")
    print(SCENARIO_SEPARATOR)
    print()


def print_replay_summary(replay: ReplayResult) -> None:
    print()
    print("Replay Summary")
    print("--------------")
    print(f"Run ID:             {replay.run.id}")
    print(f"Observation count:  {len(replay.observations)}")
    print(f"Trend:              {replay.trend.direction.name.title()}")
    print(f"Variation:          {replay.variation.level.name}")
    print(f"Assessment:         {replay.situation.assessment}")
    print(f"Priority:           {replay.plan.priority.name}")
    print(f"Published events:   {len(replay.events)}")
    print()


def print_summary() -> None:
    print()
    print(SCENARIO_SEPARATOR)
    print("Summary")
    print(SCENARIO_SEPARATOR)
    print()
    print("ODIS currently demonstrates:")
    print()
    print("✓ Independent signal detectors")
    print("✓ Multi-signal operational assessment")
    print("✓ Explainable planning")
    print("✓ Deterministic reasoning across scenarios")
    print()
    print("Richer detectors — rate-of-change, anomaly detection, and others —")
    print("remain future work within the same architecture.")
    print()


def main() -> None:
    print("ODIS Unified Demonstration")
    print(SCENARIO_SEPARATOR)

    print_scenario_header(1, "Heatwave")
    heatwave_result, heatwave_observations, heatwave_events = run_heatwave_demo()
    print_replay_summary(
        ReplayResult.from_execution(
            heatwave_result, heatwave_observations, heatwave_events
        )
    )

    print_scenario_header(2, "Stable Operations")
    stable_result, stable_observations, stable_events = run_stable_operations_demo()
    print_replay_summary(
        ReplayResult.from_execution(
            stable_result, stable_observations, stable_events
        )
    )

    print_scenario_header(3, "Oscillating Operations")
    oscillating_result, oscillating_observations, oscillating_events = (
        run_oscillating_demo()
    )
    print_replay_summary(
        ReplayResult.from_execution(
            oscillating_result, oscillating_observations, oscillating_events
        )
    )

    print_summary()


if __name__ == "__main__":
    main()
