"""Bounded policy repair, full-run feedback, retention, and deployment export."""

import json
from pathlib import Path

from satcraft.evaluation.replay import RuntimeLimits, evaluate_source
from satcraft.io import write_json
from satcraft.policies.store import PolicyLibrary
from satcraft.selection.tree import fit_selector


def feedback_summary(evaluation):
    rows = evaluation.get("rows", [])
    worst = sorted(rows, key=lambda row: (row["valid"], row["service_value"]))[:3]
    fields = (
        "case",
        "valid",
        "error",
        "service_value",
        "max_service_value",
        "cell_mbit",
        "active_used",
        "cpu_used",
        "max_callback_s",
        "fulfilled",
    )
    summary = {
        "valid": evaluation["valid"],
        "total": evaluation["total"],
        "error": evaluation.get("error"),
        "by_profile": evaluation.get("by_profile", {}),
        "selected_cases": [{key: row.get(key) for key in fields} for row in worst],
    }
    traces = evaluation.get("traces", {})
    summary["execution_events"] = {}
    for row in worst:
        records = traces.get(row["case"], [])
        events = []
        for record in records:
            observation = record["observation"]
            if observation["jobs"]:
                events.append(
                    {
                        "t": observation["t"],
                        "jobs": observation["jobs"],
                        "cell_budget": observation["cell_budget"],
                        "radio": observation["radio"],
                        "action": record["action"],
                        "cell_mbit": record["cell_mbit"],
                        "new_receipts": record.get("new_receipts", []),
                        "fulfilled_services": record.get("fulfilled_services", {}),
                    }
                )
        summary["execution_events"][row["case"]] = (
            events[:12] + events[-4:] if len(events) > 16 else events
        )
    return summary


def optimize(
    cases,
    seed_source,
    provider,
    output,
    submissions=6,
    direction="Coordinate cellular startup and computing-output readiness; preserve resources for later arrivals.",
    limits=None,
    presets=(),
):
    if submissions < 1:
        raise ValueError("Use at least one candidate submission")
    limits = limits or RuntimeLimits()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    library = PolicyLibrary(output / "library")
    initial = evaluate_source(cases, seed_source, limits, log=True)
    write_json(output / "seed_evaluation.json", initial)
    if not initial["valid"]:
        raise ValueError("The seed policy must pass complete-run evaluation")
    library.add("seed", seed_source, initial)
    working, best = seed_source, initial["total"]
    feedback, ledger = feedback_summary(initial), []
    prompt_root = Path(__file__).parent / "prompts"
    initial_template = (prompt_root / "initial.md").read_text()
    continuation_template = (prompt_root / "continuation.md").read_text()
    for index in range(submissions):
        name = f"candidate_{index + 1:02d}"
        attempt = output / "attempts" / name
        attempt.mkdir(parents=True)
        task = initial_template.format(
            direction=direction,
            source=working,
            feedback=json.dumps(feedback, indent=2),
            remaining=submissions - index,
            budgets=f"callback: {limits.callback_seconds} s; episode: {limits.episode_seconds} s",
        )
        prompt = task if index == 0 else continuation_template.format(task=task)
        (attempt / "prompt.md").write_text(prompt, encoding="utf-8")
        try:
            proposal = provider.propose(prompt)
        except Exception as error:
            record = {
                "name": name,
                "valid": False,
                "stage": "proposal",
                "error": f"{type(error).__name__}: {error}",
            }
            ledger.append(record)
            feedback = {
                "previous_evaluation": feedback,
                "proposal_error": record["error"],
            }
            write_json(output / "ledger.json", ledger)
            continue
        (attempt / "policy.py").write_text(proposal.code, encoding="utf-8")
        evaluation = evaluate_source(cases, proposal.code, limits, log=True)
        write_json(attempt / "evaluation.json", evaluation)
        record = {
            "name": name,
            "valid": evaluation["valid"],
            "total": evaluation["total"],
            "rationale": proposal.rationale,
            "usage": proposal.usage,
        }
        ledger.append(record)
        write_json(output / "ledger.json", ledger)
        feedback = feedback_summary(evaluation)
        if evaluation["valid"]:
            library.add(name, proposal.code, evaluation)
            if evaluation["total"] > best:
                working, best = proposal.code, evaluation["total"]
    entries = library.entries()
    selector = fit_selector(
        cases, {name: entry["evaluation"] for name, entry in entries.items()}, presets
    )
    bundle = output / "deployment"
    write_json(bundle / "selector.json", selector)
    (bundle / "policies").mkdir()
    for name, entry in entries.items():
        (bundle / "policies" / f"{name}.py").write_text(
            entry["source"], encoding="utf-8"
        )
    from satcraft.evaluation.replay import evaluate
    from satcraft.policies.deployment import load_bundle

    final = evaluate(cases, load_bundle(bundle), limits)
    write_json(output / "deployment_evaluation.json", final)
    return {
        "seed_total": initial["total"],
        "best_single_policy_total": best,
        "deployment_total": final["total"],
        "valid": final["valid"],
        "retained_policies": len(entries),
        "submissions": len(ledger),
    }
