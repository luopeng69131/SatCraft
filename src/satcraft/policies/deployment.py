"""Select once per episode; execute the selected policy each slot."""

import importlib
import json
from pathlib import Path

from satcraft.selection.features import access_features
from satcraft.selection.tree import predict


def idle_action():
    return {
        "modes": {},
        "cpu_job": None,
        "net_order": [],
        "cell_enabled": False,
        "cell_cap": 0.0,
    }


class DeployedPolicy:
    def __init__(self, selector, policies):
        self.selector = selector
        self.policies = policies

    def __call__(self, observation, memory):
        if "selected_policy" not in memory:
            if observation["t"] < self.selector["calibration_slots"]:
                return idle_action()
            profile = observation["context"]["resource_profile"]
            name = predict(
                self.selector["trees"][profile],
                access_features(observation["past_rates"]),
            )
            memory["selected_policy"] = name
        return self.policies[memory["selected_policy"]](
            observation, memory.setdefault("policy_memory", {})
        )


def frozen_policy():
    root = Path(__file__).parent
    selector = json.loads((root / "selector.json").read_text())
    policies = {
        f"policy_{i:02d}": importlib.import_module(
            f"satcraft.policies.library.policy_{i:02d}"
        ).policy
        for i in range(20)
    }
    return DeployedPolicy(selector, policies)


def load_bundle(directory):
    from satcraft.evaluation.checks import load_policy

    root = Path(directory)
    selector = json.loads((root / "selector.json").read_text())
    policies = {
        path.stem: load_policy(path.read_text())
        for path in (root / "policies").glob("*.py")
    }
    return DeployedPolicy(selector, policies)
