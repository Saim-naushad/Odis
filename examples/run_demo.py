from pathlib import Path
import sys

EXAMPLES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXAMPLES_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXAMPLES_DIR))

from heatwave_demo import main as run_heatwave_demo  # noqa: E402
from oscillating_operations_demo import main as run_oscillating_demo  # noqa: E402
from stable_operations_demo import main as run_stable_operations_demo  # noqa: E402

SCENARIO_SEPARATOR = "=" * 60


def print_scenario_header(number: int, name: str) -> None:
    print()
    print(SCENARIO_SEPARATOR)
    print(f"Scenario {number}: {name}")
    print(SCENARIO_SEPARATOR)
    print()


def print_summary() -> None:
    print()
    print(SCENARIO_SEPARATOR)
    print("Summary")
    print(SCENARIO_SEPARATOR)
    print()
    print("ODIS currently demonstrates:")
    print()
    print("✓ Increasing trend reasoning")
    print("✓ Stable condition reasoning")
    print("✓ Explainable recommendations")
    print("✓ Architecture reuse across scenarios")
    print()
    print("Known limitation:")
    print()
    print("• Oscillating signals require additional signal detectors beyond trend analysis.")
    print()


def main() -> None:
    print("ODIS Unified Demonstration")
    print(SCENARIO_SEPARATOR)

    print_scenario_header(1, "Heatwave")
    run_heatwave_demo()

    print_scenario_header(2, "Stable Operations")
    run_stable_operations_demo()

    print_scenario_header(3, "Oscillating Operations")
    run_oscillating_demo()

    print_summary()


if __name__ == "__main__":
    main()
