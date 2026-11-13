"""Check custom scenario inputs and capacity conversion at the simulator boundary."""

import csv
import tempfile
import unittest
from pathlib import Path

from satcraft.data.prepare import prepare
from satcraft.data.workload import make_case
from satcraft.io import read_json
from satcraft.policies.seed import policy
from satcraft.simulator import State, replay


class SimulatorInputTests(unittest.TestCase):
    def test_custom_horizon_delivers_service_and_keeps_inputs_independent(self):
        jobs = [{"id": 1, "arrival": 0, "due": 5, "raw": 10.0, "cpu": 1, "ratio": 0.5}]
        services = [
            {
                "id": 2,
                "arrival": 0,
                "due": 5,
                "value": 4,
                "accepts": {"delivered": 1, "quality_min": 0.8},
            }
        ]
        case = make_case([[10.0, 0.0]] * 7, jobs, services)
        self.assertEqual(len(case["rates"]), 7)
        self.assertNotIn("quality_support", jobs[0])
        result, state = replay(case, policy)
        self.assertTrue(result["valid"])
        self.assertEqual(result["service_value"], 4)
        self.assertEqual(state.t, 7)

    def test_invalid_quality_distribution_is_rejected_at_construction(self):
        job = {
            "id": 1,
            "arrival": 0,
            "due": 2,
            "raw": 10.0,
            "cpu": 1,
            "ratio": 0.5,
            "quality_support": [{"quality": 0.6, "probability": 0.2}],
        }
        with self.assertRaisesRegex(ValueError, "probability distribution"):
            make_case([[10.0, 0.0]] * 3, [job], [])

    def test_processed_quality_is_environment_state_until_delivery(self):
        job = {
            "id": 1,
            "arrival": 0,
            "due": 3,
            "raw": 10.0,
            "cpu": 1,
            "ratio": 0.5,
            "quality_support": [{"quality": 0.6, "probability": 1.0}],
        }
        case = make_case([[10.0, 0.0]] * 4, [job], [])
        state = State(case)
        observation = state.observe()
        self.assertNotIn("compression_outcomes", observation)
        self.assertEqual(observation["receipts"], {})
        state.step({"modes": {1: "compress"}, "cpu_job": 1})
        self.assertEqual(state.receipts, {})
        state.step({})
        self.assertEqual(state.receipts[1]["quality"], 0.6)

    def test_trace_export_converts_mbps_to_mbit_for_configured_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "alaska_road_test_202406/processed/mpshell/raw_traces"
            folder.mkdir(parents=True)
            path = folder / "fused_trace.tcp_downlink.starlink_att.csv"
            fields = [
                "A",
                "B",
                "A_run",
                "B_run",
                "A_time",
                "B_time",
                "A_throughput_mbps",
                "B_throughput_mbps",
            ]
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for second in range(4):
                    stamp = f"2024-06-01T00:00:0{second}+00:00"
                    writer.writerow(
                        {
                            "A": "starlink",
                            "B": "att",
                            "A_run": "a",
                            "B_run": "b",
                            "A_time": stamp,
                            "B_time": stamp,
                            "A_throughput_mbps": 4,
                            "B_throughput_mbps": 2,
                        }
                    )
            output = root / "processed"
            result = prepare(
                root, output, "alaska", "att", sample_period_seconds=1.0, min_slots=1
            )
            traces = read_json(output / "traces.json")
            self.assertEqual(result, {"traces": 1, "slot_seconds": 2.0})
            self.assertEqual(traces[0]["rates"], [[8.0, 4.0], [8.0, 4.0]])
            self.assertEqual(
                read_json(output / "manifest.json")["capacity_unit"], "Mbit per slot"
            )
            self.assertEqual(
                {p.name for p in output.iterdir()}, {"traces.json", "manifest.json"}
            )


if __name__ == "__main__":
    unittest.main()
