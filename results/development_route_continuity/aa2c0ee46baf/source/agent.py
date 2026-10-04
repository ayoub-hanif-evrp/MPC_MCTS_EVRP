"""Each EV owns an MPC controller; seeds are independent of scheduling order."""

from hashlib import sha256

from .model import Observation, VehicleState
from .mpc import MPCConfig, MPCController, PlanningResult


def agent_seed(experiment_seed: int, scenario_seed: int, epoch: int, vehicle_id: int) -> int:
    material = f"{experiment_seed}:{scenario_seed}:{epoch}:{vehicle_id}".encode("ascii")
    return int.from_bytes(sha256(material).digest()[:8], "big")


class EVAgent:
    def __init__(self, vehicle_id: int, config: MPCConfig):
        self.id = vehicle_id
        self.controller = MPCController(config)

    def plan(self, state: VehicleState, observation: Observation, seed: int) -> PlanningResult:
        if state.id != self.id:
            raise ValueError("An agent plans only for its own vehicle")
        return self.controller.plan(state, observation, seed)
