"""Platform defaults for automatic reasoning orchestration."""

from application.profiles.fuel_cell_profile import FuelCellOperationalProfile
from domain.entities.operational_goal import OperationalGoal

DEFAULT_OPERATIONAL_GOAL = OperationalGoal(
    id="platform-default-goal",
    description="Maintain stable fuel cell operation",
)

DEFAULT_OPERATIONAL_PROFILE = FuelCellOperationalProfile.default()
