"""Product dependencies, delivered quality, and completed-service value."""

import copy
import time
from . import physics as base


def satisfied(expr, receipts):
    if not expr:
        return True
    if "all" in expr:
        return all((satisfied(x, receipts) for x in expr["all"]))
    if "any" in expr:
        return any((satisfied(x, receipts) for x in expr["any"]))
    r = receipts.get(expr["delivered"])
    return r is not None and expr.get("quality_min", 0) <= r["quality"] <= expr.get(
        "quality_max", 1
    )


def leaves(expr):
    if not expr:
        return set()
    if "delivered" in expr:
        return {expr["delivered"]}
    return set().union(
        *(leaves(x) for key in ["all", "any"] for x in expr.get(key, []))
    )


class State(base.State):
    def __init__(self, case):
        super().__init__(case)
        self.receipts = {}
        self.fulfilled = {}

    def observe(self, arrivals=True):
        o = super().observe(arrivals)
        for j in o["jobs"]:
            j["ready"] = satisfied(j.get("requires"), self.receipts)
        o["receipts"] = {i: dict(r) for (i, r) in self.receipts.items()}
        o["services"] = [
            copy.deepcopy(s)
            for s in self.case["services"]
            if s["arrival"] <= self.t < s["due"] and s["id"] not in self.fulfilled
        ]
        return o

    def step(self, action, rates=None, arrivals=True, log=False):
        o = self.observe(arrivals)
        ready = {j["id"] for j in o["jobs"] if j["ready"]}
        if any((i not in ready for i in action.get("modes", {}))):
            raise ValueError("A dependency-blocked product cannot select a mode")
        cpu = action.get("cpu_job")
        if cpu is not None and cpu not in ready:
            raise ValueError("CPU input dependencies are not satisfied")
        before = len(self.completed)
        super().step(action, rates, arrivals, log)
        for j in self.completed[before:]:
            quality = (
                1.0
                if j["choice"] == "raw"
                else self.case["compression_outcomes"][str(j["id"])]
            )
            j["delivered_quality"] = quality
            self.receipts[j["id"]] = {
                "id": j["id"],
                "quality": quality,
                "finished": j["finished"],
                "mode": j["choice"],
            }
        for service in self.case["services"]:
            if (
                service["id"] not in self.fulfilled
                and service["arrival"] < self.t <= service["due"]
                and satisfied(service["accepts"], self.receipts)
            ):
                self.fulfilled[service["id"]] = {
                    "value": service["value"],
                    "finished": self.t,
                }
        if log:
            self.records[-1]["new_receipts"] = [
                self.receipts[j["id"]] for j in self.completed[before:]
            ]
            self.records[-1]["fulfilled_services"] = copy.deepcopy(self.fulfilled)

    def result(self):
        r = super().result()
        r.update(
            service_value=sum((s["value"] for s in self.fulfilled.values())),
            max_service_value=sum((s["value"] for s in self.case["services"])),
            services_completed=len(self.fulfilled),
            services_total=len(self.case["services"]),
            fulfilled=copy.deepcopy(self.fulfilled),
        )
        return r


def from_observation(o, predicted_rates, quality="good", quota=None):
    jobs = copy.deepcopy(o["jobs"])
    T = o["horizon"]
    rates = [[0.0, 0.0] for _ in range(T)]
    for t in range(o["t"], T):
        rates[t] = (
            list(predicted_rates[t - o["t"]])
            if isinstance(predicted_rates, list)
            else list(predicted_rates)
        )
    outcomes = {
        str(j["id"]): j["quality_support"][-1 if quality == "good" else 0]["quality"]
        for j in jobs
    }
    case = {
        "jobs": [],
        "services": copy.deepcopy(o["services"]),
        "rates": rates,
        "compression_outcomes": outcomes,
        "cell_budget": o["cell_budget"]
        if quota is None
        else min(o["cell_budget"], quota),
        "warmup": o["radio"]["warmup"],
        "active_slots": o["radio"]["active"],
    }
    s = State(case)
    s.t = o["t"]
    s.jobs = {j["id"]: j for j in jobs}
    s.receipts = copy.deepcopy(o["receipts"])
    s.budget = case["cell_budget"]
    s.active = o["radio"]["active"]
    s.mode = o["radio"]["mode"]
    s.delay = o["radio"]["ready_in"] if s.mode == "WARMING" else 0
    s.history = [tuple(x) for x in o["past_rates"]]
    s.prepared = True
    return s


def evaluate(case, policy, log=False):
    s = State(case)
    mem = {}
    times = []
    busy = []
    while s.t < len(case["rates"]):
        o = s.observe()
        start = time.perf_counter()
        a = policy(copy.deepcopy(o), mem)
        dt = time.perf_counter() - start
        times.append(dt)
        if o["jobs"]:
            busy.append(dt)
        s.step(a, log=log)
    r = s.result()
    r.update(
        case=case["id"],
        steps=s.t,
        policy_wall_s=sum(times),
        decision_max_s=max(times),
        busy_p95_s=sorted(busy)[int(0.95 * (len(busy) - 1))] if busy else 0.0,
    )
    return (r, s)
