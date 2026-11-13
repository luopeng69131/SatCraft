"""Simulate a synthetic service episode with the bundled SatCraft policy."""

from satcraft.data.workload import demo_cases
from satcraft.policies.deployment import frozen_policy
from satcraft.simulator import replay

result, state = replay(demo_cases()[0], frozen_policy(), log=True)
print({key: result[key] for key in ("valid", "service_value", "max_service_value")})
print("Recorded slots:", len(state.records))
