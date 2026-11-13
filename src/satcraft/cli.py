"""Community entry points for simulation, trace processing and policy construction."""

import argparse
import json
from pathlib import Path

from satcraft.io import read_json, write_json


def _report(result):
    keys = ("valid", "total", "cases", "by_profile", "max_callback_s")
    print(json.dumps({key: result[key] for key in keys if key in result}, indent=2))


def main():
    parser = argparse.ArgumentParser(
        prog="satcraft",
        description="Scheduling policy optimization and service simulation",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser(
        "demo", help="Simulate a small synthetic service workflow"
    )
    demo.add_argument("--output", default="outputs/demo")
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--policy", choices=("frozen", "seed"), default="frozen")
    demo.add_argument(
        "--repair-demo",
        action="store_true",
        help="Pass a supplied policy through the construction workflow",
    )
    prepare = commands.add_parser(
        "prepare", help="Export locally downloaded trace pairs"
    )
    prepare.add_argument("--dataset-root", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--region", choices=("alaska", "hawaii"), required=True)
    prepare.add_argument(
        "--carrier", choices=("att", "verizon", "tmobile"), required=True
    )
    prepare.add_argument("--samples-per-slot", type=int, default=2)
    prepare.add_argument("--sample-period-seconds", type=float, default=0.5)
    prepare.add_argument("--min-slots", type=int, default=8)
    prepare.add_argument("--max-gap-seconds", type=float, default=1.0)
    simulate = commands.add_parser(
        "simulate",
        aliases=["evaluate"],
        help="Run user scenarios with a supplied policy",
    )
    simulate.add_argument("--cases", required=True)
    simulate.add_argument(
        "--policy",
        default="seed",
        help="seed, frozen, a policy.py path, or an exported deployment directory",
    )
    simulate.add_argument("--output", default="outputs/simulation.json")
    simulate.add_argument("--trace", action="store_true")
    optimize = commands.add_parser(
        "optimize", help="Construct policies using execution feedback"
    )
    optimize.add_argument("--cases", required=True)
    optimize.add_argument("--seed-policy", required=True)
    provider = optimize.add_mutually_exclusive_group(required=True)
    provider.add_argument(
        "--provider-config", help="External model-client command JSON"
    )
    provider.add_argument(
        "--candidate", action="append", help="Supplied candidate source"
    )
    optimize.add_argument("--submissions", type=int, default=6)
    optimize.add_argument(
        "--direction", default="Coordinate output readiness and cellular use."
    )
    optimize.add_argument("--preset-selector", action="append", default=[])
    optimize.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        from satcraft.data.prepare import prepare

        print(
            json.dumps(
                prepare(
                    args.dataset_root,
                    args.output,
                    args.region,
                    args.carrier,
                    args.samples_per_slot,
                    args.sample_period_seconds,
                    args.min_slots,
                    args.max_gap_seconds,
                ),
                indent=2,
            )
        )
    elif args.command == "demo":
        from satcraft.data.workload import demo_cases
        from satcraft.policies import seed
        from satcraft.policies.deployment import frozen_policy
        from satcraft.simulator import evaluate

        cases, output = demo_cases(args.seed), Path(args.output)
        write_json(output / "cases.json", cases)
        policy = frozen_policy() if args.policy == "frozen" else seed.policy
        result = evaluate(cases, policy)
        write_json(output / "evaluation.json", result)
        _report(result)
        if args.repair_demo:
            from satcraft.agent.optimize import optimize
            from satcraft.agent.providers import FileCandidateProvider

            # Reuse the starter source to illustrate submission, checks and export.
            summary = optimize(
                cases,
                Path(seed.__file__).read_text(),
                FileCandidateProvider([seed.__file__]),
                output / "repair",
                submissions=1,
            )
            print(json.dumps(summary, indent=2))
            if not summary["valid"]:
                raise SystemExit(1)
        if not result["valid"]:
            raise SystemExit(1)
    elif args.command in ("simulate", "evaluate"):
        from satcraft.policies import seed
        from satcraft.policies.deployment import frozen_policy, load_bundle
        from satcraft.simulator import evaluate, evaluate_source

        cases = read_json(args.cases)
        if args.policy == "seed":
            result = evaluate(cases, seed.policy, log=args.trace)
        elif args.policy == "frozen":
            result = evaluate(cases, frozen_policy(), log=args.trace)
        elif Path(args.policy).is_dir():
            result = evaluate(cases, load_bundle(args.policy), log=args.trace)
        else:
            result = evaluate_source(
                cases, Path(args.policy).read_text(), log=args.trace
            )
        write_json(args.output, result)
        _report(result)
        if not result["valid"]:
            raise SystemExit(1)
    else:
        from satcraft.agent.optimize import optimize
        from satcraft.agent.providers import CommandProvider, FileCandidateProvider

        if args.provider_config:
            config = read_json(args.provider_config)
            provider = CommandProvider(
                config["command"], config.get("timeout_seconds", 900)
            )
        else:
            if args.submissions > len(args.candidate):
                parser.error("Provide a --candidate file for each submission")
            provider = FileCandidateProvider(args.candidate)
        summary = optimize(
            read_json(args.cases),
            Path(args.seed_policy).read_text(),
            provider,
            args.output,
            args.submissions,
            args.direction,
            presets=[read_json(path) for path in args.preset_selector],
        )
        print(json.dumps(summary, indent=2))
        if not summary["valid"]:
            raise SystemExit(1)
