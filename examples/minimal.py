"""Run a complete service episode using the frozen SatCraft policy."""

from satcraft.data.workload import demo_cases
from satcraft.evaluation.replay import replay
from satcraft.policies.deployment import frozen_policy

result, state = replay(demo_cases()[0], frozen_policy())
print(
    {
        key: result[key]
        for key in ("valid", "service_value", "max_service_value", "selected_policy")
    }
)
