"""Platform defaults for automatic reasoning orchestration."""

from application.profiles.fuel_cell_profile import FuelCellOperationalProfile
from application.reasoning_session import ReasoningSessionConfig
from domain.entities.operational_goal import OperationalGoal

DEFAULT_OPERATIONAL_GOAL = OperationalGoal(
    id="platform-default-goal",
    description="Maintain stable fuel cell operation",
)

DEFAULT_OPERATIONAL_PROFILE = FuelCellOperationalProfile.default()

# Plant Alpha's normal-operation load cycle is 300 simulated seconds
# (NormalOperationScenario); at the default demo cadence (15s core publish
# interval, 45s sim_dt per tick) that's roughly 7 core observations per full
# cycle. 20 spans ~3 cycles per measurement type — enough for the trend
# detector's step-consistency check to average out normal oscillation, while
# still aging out a resolved fault's stale extremes within a few minutes of
# real time so `recovery` is reflected instead of staying permanently stuck.
DEFAULT_REASONING_SESSION_CONFIG = ReasoningSessionConfig(observation_window=20)
