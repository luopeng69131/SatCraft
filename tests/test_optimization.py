"""Integration checks for candidate feedback, retention, export, and providers."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from satcraft.agent.optimize import optimize
from satcraft.agent.providers import CommandProvider, FileCandidateProvider
from satcraft.data.workload import demo_cases
from satcraft.evaluation.replay import evaluate
from satcraft.io import read_json
from satcraft.policies import seed
from satcraft.policies.deployment import load_bundle


class OptimizationTests(unittest.TestCase):
    def test_failed_candidate_feedback_and_valid_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad = root / "bad.py"
            bad.write_text("import os\ndef policy(o, m): return {}\n")
            good = Path(seed.__file__)
            cases = demo_cases()[:1]
            result = optimize(
                cases,
                good.read_text(),
                FileCandidateProvider([bad, good]),
                root / "optimization",
                submissions=2,
            )
            self.assertTrue(result["valid"])
            self.assertEqual(result["retained_policies"], 2)
            ledger = read_json(root / "optimization/ledger.json")
            self.assertFalse(ledger[0]["valid"])
            self.assertTrue(ledger[1]["valid"])
            prompt = (root / "optimization/attempts/candidate_02/prompt.md").read_text()
            self.assertIn("Policy imports must use", prompt)
            deployment = evaluate(cases, load_bundle(root / "optimization/deployment"))
            self.assertEqual(deployment["total"], result["deployment_total"])

    def test_command_provider_passes_prompt_and_preserves_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            client = Path(temporary) / "client.py"
            client.write_text(
                "import json, sys\nprompt = sys.stdin.read()\nprint(json.dumps({'code': 'def policy(o, m): return {}', 'rationale': prompt, 'usage': {'output_tokens': 7}}))\n"
            )
            proposal = CommandProvider([sys.executable, str(client)]).propose(
                "execution feedback"
            )
            self.assertEqual(proposal.rationale, "execution feedback")
            self.assertEqual(proposal.usage["output_tokens"], 7)


if __name__ == "__main__":
    unittest.main()
