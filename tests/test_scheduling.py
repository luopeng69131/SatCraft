"""Behavioral checks for timing, quality, policy selection, and replay limits."""

import csv
import tempfile
import unittest
from pathlib import Path

from satcraft.data.traces import load_pair
from satcraft.environment.service import State, satisfied
from satcraft.evaluation.replay import RuntimeLimits, evaluate_source, replay
from satcraft.policies.deployment import DeployedPolicy, idle_action
from satcraft.selection.tree import fit_tree, predict


def case():
    return {
        "id": "timing",
        "source_id": "example",
        "profile": "balanced",
        "quality_seed": 0,
        "rates": [[10.0, 10.0] for _ in range(4)],
        "cell_budget": 20.0,
        "warmup": 1,
        "active_slots": 3,
        "jobs": [
            {
                "id": 1,
                "arrival": 0,
                "due": 2,
                "raw": 10.0,
                "cpu": 1,
                "ratio": 0.2,
                "requires": None,
                "quality_support": [{"quality": 0.6, "probability": 1.0}],
            }
        ],
        "services": [
            {
                "id": 10,
                "arrival": 0,
                "due": 2,
                "value": 8,
                "accepts": {"delivered": 1, "quality_min": 0.85},
            }
        ],
        "compression_outcomes": {"1": 0.6},
    }


class SchedulingTests(unittest.TestCase):
    def test_computing_output_waits_until_next_slot_and_quality_controls_value(self):
        state = State(case())
        action = idle_action()
        action.update(modes={1: "compress"}, cpu_job=1, net_order=[1])
        state.step(action)
        self.assertEqual(len(state.completed), 0)
        state.step(idle_action())
        self.assertEqual(state.receipts[1]["finished"], 2)
        self.assertEqual(state.result()["service_value"], 0)
        self.assertTrue(satisfied({"delivered": 1, "quality_max": 0.8}, state.receipts))

    def test_delivery_at_deadline_completes_service(self):
        scenario = case()
        scenario["services"][0]["accepts"]["quality_min"] = 0.5
        state = State(scenario)
        action = idle_action()
        action.update(modes={1: "compress"}, cpu_job=1)
        state.step(action)
        state.step(idle_action())
        self.assertEqual(state.result()["service_value"], 8)

    def test_cellular_startup_consumes_activation_before_transmission(self):
        scenario = case()
        scenario["rates"] = [[0.0, 10.0]] * 4
        state = State(scenario)
        action = idle_action()
        action.update(modes={1: "raw"}, cell_enabled=True, cell_cap=10.0)
        state.step(action)
        self.assertEqual(state.cell_used, 0)
        self.assertEqual(state.active, 2)
        action["modes"] = {}
        state.step(action)
        self.assertEqual(state.cell_used, 10)

    def test_invalid_source_and_callback_timeout(self):
        rejected = evaluate_source([case()], "import os\ndef policy(o, m): return {}")
        self.assertFalse(rejected["valid"])
        source = "def policy(o, m):\n    while True: pass\n"
        result = evaluate_source([case()], source, RuntimeLimits(0.02, 0.2))
        self.assertFalse(result["valid"])
        self.assertEqual(result["total"], 0)
        self.assertIn("TimeoutError", result["rows"][0]["error"])

    def test_selector_stays_fixed_after_initial_observations(self):
        calls = []

        def record(name):
            def policy(observation, memory):
                calls.append(name)
                return idle_action()

            return policy

        selector = {
            "calibration_slots": 8,
            "trees": {
                "balanced": {
                    "feature": 0,
                    "threshold": 5,
                    "left": {"policy": "low"},
                    "right": {"policy": "high"},
                }
            },
        }
        deployed = DeployedPolicy(
            selector, {"low": record("low"), "high": record("high")}
        )
        memory = {}
        observation = {
            "t": 8,
            "context": {"resource_profile": "balanced"},
            "past_rates": [[1, 0]] * 8,
        }
        deployed(observation, memory)
        observation.update(t=9, past_rates=[[100, 0]] * 8)
        deployed(observation, memory)
        self.assertEqual(calls, ["low", "low"])

    def test_tree_learns_condition_dependent_policy_utility(self):
        rows = [
            {
                "features": [x] + [0] * 10,
                "utility": {"a": 8 if x < 3 else 0, "b": 8 if x >= 3 else 0},
            }
            for x in range(6)
        ]
        tree = fit_tree(rows, ["a", "b"], min_leaf=3)
        self.assertEqual(predict(tree, rows[0]["features"]), "a")
        self.assertEqual(predict(tree, rows[-1]["features"]), "b")

    def test_trace_loader_preserves_gaps_and_rejects_misaligned_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "alaska_road_test_202406/processed/mpshell/raw_traces"
            folder.mkdir(parents=True)
            path = folder / "fused_trace.tcp_downlink.starlink_att.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "A",
                        "B",
                        "A_run",
                        "B_run",
                        "A_time",
                        "B_time",
                        "A_throughput_mbps",
                        "B_throughput_mbps",
                    ],
                )
                writer.writeheader()
                for second in (0, 0.5, 4, 4.5):
                    stamp = f"2024-06-01T00:00:{second:06.3f}+00:00"
                    writer.writerow(
                        {
                            "A": "starlink",
                            "B": "att",
                            "A_run": "source",
                            "B_run": "paired",
                            "A_time": stamp,
                            "B_time": stamp,
                            "A_throughput_mbps": 4,
                            "B_throughput_mbps": 2,
                        }
                    )
                writer.writerow(
                    {
                        "A": "starlink",
                        "B": "att",
                        "A_run": "source",
                        "B_run": "paired",
                        "A_time": "2024-06-01T00:00:06+00:00",
                        "B_time": "2024-06-01T00:00:08+00:00",
                        "A_throughput_mbps": 4,
                        "B_throughput_mbps": 2,
                    }
                )
            episodes, audit = load_pair(
                root, "alaska", "att", samples_per_block=2, min_blocks=1
            )
            self.assertEqual(len(episodes), 2)
            self.assertEqual(audit["invalid_rows"], 1)
            self.assertEqual(audit["gap_cuts"], 1)
            self.assertEqual(episodes[0].blocks[0].starlink_mbps, 4)


if __name__ == "__main__":
    unittest.main()
