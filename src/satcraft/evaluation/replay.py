"""Complete service executions with action checks and runtime budgets."""

import copy
import signal
import time
from contextlib import contextmanager
from dataclasses import dataclass

from satcraft.environment.service import State
from .checks import load_policy


@dataclass(frozen=True)
class RuntimeLimits:
    callback_seconds: float = 2.0
    episode_seconds: float = 90.0


def _timeout(*_):
    raise TimeoutError("Policy execution exceeded its time budget")


@contextmanager
def time_budget(seconds):
    if seconds <= 0:
        raise TimeoutError("Policy execution exceeded its time budget")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    start = time.perf_counter()
    signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(
                signal.ITIMER_REAL,
                max(1e-6, previous_timer[0] - (time.perf_counter() - start)),
                previous_timer[1],
            )


def replay(case, policy, limits=None, log=False):
    limits = limits or RuntimeLimits()
    state, memory, times = State(case), {}, []
    start, error = time.perf_counter(), None
    try:
        while state.t < len(case["rates"]):
            observation = state.observe()
            observation["context"] = {"resource_profile": case["profile"]}
            remaining = limits.episode_seconds - (time.perf_counter() - start)
            tick = time.perf_counter()
            with time_budget(min(limits.callback_seconds, remaining)):
                action = policy(copy.deepcopy(observation), memory)
            times.append(time.perf_counter() - tick)
            if not isinstance(action, dict):
                raise ValueError("A scheduling action must be a dictionary")
            state.step(action, log=log)
        if state.cell_used > case["cell_budget"] + 1e-6 or state.active < 0:
            raise ValueError("Resource budget exceeded")
    except Exception as exception:
        error = f"{type(exception).__name__}: {exception}"
    result = state.result()
    result.update(
        case=case["id"],
        source_id=case["source_id"],
        profile=case["profile"],
        quality_seed=case["quality_seed"],
        valid=error is None,
        error=error,
        raw_service_value=result["service_value"],
        service_value=result["service_value"] if error is None else 0,
        policy_wall_s=sum(times),
        max_callback_s=max(times, default=0.0),
        wall_s=time.perf_counter() - start,
        physical_steps=state.t,
        selected_policy=memory.get("selected_policy"),
    )
    return result, state


def evaluate(cases, policy, limits=None, log=False):
    if not cases:
        raise ValueError("Provide at least one case")
    rows, traces = [], {}
    for case in cases:
        row, state = replay(case, policy, limits, log)
        rows.append(row)
        if log:
            traces[case["id"]] = state.records
    result = {
        "valid": all(row["valid"] for row in rows),
        "total": sum(row["service_value"] for row in rows),
        "cases": len(rows),
        "rows": rows,
        "by_profile": {
            p: sum(r["service_value"] for r in rows if r["profile"] == p)
            for p in sorted({r["profile"] for r in rows})
        },
        "max_callback_s": max(r["max_callback_s"] for r in rows),
    }
    if log:
        result["traces"] = traces
    return result


def evaluate_source(cases, source, limits=None, log=False):
    limits = limits or RuntimeLimits()
    try:
        with time_budget(limits.callback_seconds):
            policy = load_policy(source)
        return evaluate(cases, policy, limits, log)
    except Exception as exception:
        return {
            "valid": False,
            "total": 0,
            "cases": len(cases),
            "rows": [],
            "error": f"{type(exception).__name__}: {exception}",
        }
