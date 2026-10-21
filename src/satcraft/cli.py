"""Command-line entry points for examples, data preparation, and optimization."""

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
        description="Agentic joint scheduling for satellite–cellular edge services",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser(
        "demo", help="Run the frozen policy on generated example scenarios"
    )
    demo.add_argument("--output", default="outputs/demo")
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument(
        "--repair-demo",
        action="store_true",
        help="Replay a supplied policy through the offline repair workflow",
    )
    prepare = commands.add_parser(
        "prepare", help="Process locally downloaded NUWiNS traces"
    )
    prepare.add_argument("--dataset-root", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--runs-per-region", type=int, default=15)
    prepare.add_argument(
        "--source-manifest", help="Source locators for exact run selection"
    )
    evaluate = commands.add_parser(
        "evaluate", help="Evaluate a frozen, bundled, or source policy"
    )
    evaluate.add_argument("--cases", required=True)
    evaluate.add_argument(
        "--policy",
        default="frozen",
        help="frozen, a policy.py path, or an exported deployment directory",
    )
    evaluate.add_argument("--output", default="outputs/evaluation.json")
    evaluate.add_argument("--case-limit", type=int)
    evaluate.add_argument("--trace", action="store_true")
    optimize = commands.add_parser(
        "optimize", help="Optimize policy code through complete-execution feedback"
    )
    optimize.add_argument("--cases", required=True)
    optimize.add_argument("--seed-policy", required=True)
    provider = optimize.add_mutually_exclusive_group(required=True)
    provider.add_argument(
        "--provider-config", help="External model-client command JSON"
    )
    provider.add_argument(
        "--candidate",
        action="append",
        help="Replay supplied candidate source files in order",
    )
    optimize.add_argument("--submissions", type=int, default=6)
    optimize.add_argument(
        "--direction",
        default="Coordinate computing-output readiness, cellular startup, and resources needed by later service arrivals.",
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
                    args.runs_per_region,
                    args.source_manifest,
                ),
                indent=2,
            )
        )
    elif args.command == "demo":
        from satcraft.data.workload import demo_cases
        from satcraft.evaluation.replay import evaluate
        from satcraft.policies.deployment import frozen_policy

        cases = demo_cases(args.seed)
        output = Path(args.output)
        write_json(output / "cases.json", cases)
        result = evaluate(cases, frozen_policy())
        write_json(output / "evaluation.json", result)
        _report(result)
        if args.repair_demo:
            from satcraft.agent.optimize import optimize
            from satcraft.agent.providers import FileCandidateProvider
            from satcraft.policies import seed
            from satcraft.policies.library import policy_04

            summary = optimize(
                cases,
                Path(seed.__file__).read_text(),
                FileCandidateProvider([policy_04.__file__]),
                output / "repair",
                submissions=1,
            )
            print(json.dumps(summary, indent=2))
            if not summary["valid"]:
                raise SystemExit(1)
        if not result["valid"]:
            raise SystemExit(1)
    elif args.command == "evaluate":
        from satcraft.evaluation.replay import evaluate, evaluate_source
        from satcraft.policies.deployment import frozen_policy, load_bundle

        cases = read_json(args.cases)
        if args.case_limit is not None:
            if args.case_limit < 1:
                parser.error("--case-limit must be positive")
            cases = cases[: args.case_limit]
        if args.policy == "frozen":
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
