"""Slot-level local processing and dual-access transmission.
Processing outputs become transmittable in the following slot."""

import copy, time, math


class State:
    def __init__(self, case):
        self.case = case
        self.t = 0
        self.jobs = {}
        self.completed = []
        self.expired = []
        self.history = []
        self.budget = float(case["cell_budget"])
        self.active = case["active_slots"]
        self.mode = "OFF"
        self.delay = 0
        self.cpu_used = 0
        self.cell_used = 0.0
        self.starts = 0
        self.records = []
        self.prepared = False

    def fork(self):
        out = object.__new__(State)
        out.case = self.case
        for k, v in self.__dict__.items():
            if k not in ["case", "records"]:
                setattr(out, k, copy.deepcopy(v))
        out.records = []
        return out

    def observe(self, arrivals=True):
        if not self.prepared:
            for i, j in list(self.jobs.items()):
                if j["due"] <= self.t:
                    self.expired.append(dict(j))
                    del self.jobs[i]
            if arrivals:
                for original in self.case["jobs"]:
                    if original["arrival"] == self.t:
                        j = dict(original)
                        j.update(
                            status="wait",
                            cpu_left=j["cpu"],
                            tx_left=j["raw"],
                            choice=None,
                        )
                        self.jobs[j["id"]] = j
            self.prepared = True
        return {
            "t": self.t,
            "horizon": len(self.case["rates"]),
            "jobs": [dict(j) for j in self.jobs.values()],
            "past_rates": [list(x) for x in self.history],
            "cell_budget": self.budget,
            "radio": {
                "mode": self.mode,
                "ready_in": self.delay
                if self.mode == "WARMING"
                else self.case["warmup"]
                if self.mode == "OFF"
                else 0,
                "warmup": self.case["warmup"],
                "active": self.active,
            },
        }

    def step(self, action, rates=None, arrivals=True, log=False):
        o = self.observe(arrivals)
        modes = action.get("modes", {})
        for i, choice in modes.items():
            if i not in self.jobs or self.jobs[i]["status"] != "wait":
                raise ValueError("Only undecided jobs may choose a mode")
            if choice not in ["raw", "compress"]:
                raise ValueError("Unknown execution mode")
            j = self.jobs[i]
            j["choice"] = choice
            j["status"] = "net" if choice == "raw" else "cpu"
            j["tx_left"] = j["raw"] if choice == "raw" else j["raw"] * j["ratio"]
        cpu = action.get("cpu_job")
        new_ready = None
        if cpu is not None:
            if cpu not in self.jobs or self.jobs[cpu]["status"] != "cpu":
                raise ValueError("CPU job must be ready to compute")
            j = self.jobs[cpu]
            j["cpu_left"] -= 1
            self.cpu_used += 1
            if j["cpu_left"] == 0:
                new_ready = cpu
        enabled = action.get("cell_enabled", False)
        cap = float(action.get("cell_cap", 0))
        if type(enabled) is not bool or not math.isfinite(cap) or cap < 0:
            raise ValueError("Invalid radio command")
        available = False
        active_before = self.active
        if not enabled:
            self.mode = "OFF"
            self.delay = 0
        elif self.active <= 0:
            self.mode = "OFF"
            self.delay = 0
        else:
            if self.mode == "OFF":
                self.delay = self.case["warmup"]
                self.mode = "WARMING" if self.delay else "ON"
                self.starts += 1
            self.active -= 1
            if self.mode == "WARMING":
                self.delay -= 1
                if self.delay == 0:
                    self.mode = "ON"
            else:
                available = True
        pair = self.case["rates"][self.t] if rates is None else rates
        net = [
            i
            for i in action.get("net_order", [])
            if i in self.jobs and self.jobs[i]["status"] == "net"
        ]
        if len(net) != len(set(net)):
            raise ValueError("Duplicate network order")
        seen = set(net)
        net += [
            j["id"]
            for j in sorted(self.jobs.values(), key=lambda j: (j["due"], j["id"]))
            if j["status"] == "net" and j["id"] not in seen
        ]

        def serve(amount):
            spent = 0.0
            for i in net:
                if i not in self.jobs or self.jobs[i]["status"] != "net":
                    continue
                j = self.jobs[i]
                use = min(j["tx_left"], amount)
                j["tx_left"] -= use
                amount -= use
                spent += use
                if j["tx_left"] <= 1e-08:
                    self.completed.append(dict(j, finished=self.t + 1))
                    del self.jobs[i]
                if amount <= 1e-08:
                    break
            return spent

        star = serve(max(0.0, pair[0]))
        cell = serve(min(max(0.0, pair[1]), cap, self.budget)) if available else 0.0
        self.budget -= cell
        self.cell_used += cell
        if new_ready is not None:
            self.jobs[new_ready]["status"] = "net"
        assert self.budget >= -1e-07 and self.active >= 0
        if log:
            self.records.append(
                {
                    "observation": o,
                    "action": copy.deepcopy(action),
                    "realized_rates": list(pair),
                    "star_mbit": star,
                    "cell_mbit": cell,
                    "active_used": active_before - self.active,
                    "completed_ids": [j["id"] for j in self.completed],
                }
            )
        self.history.append(tuple(pair))
        self.history = self.history[-8:]
        self.t += 1
        self.prepared = False

    def result(self):
        return {
            "completed": len(self.completed),
            "jobs": len(self.case["jobs"]),
            "cell_mbit": self.cell_used,
            "active_used": self.case["active_slots"] - self.active,
            "cpu_used": self.cpu_used,
            "starts": self.starts,
            "completed_ids": [j["id"] for j in self.completed],
        }


def evaluate(case, policy, log=False):
    s = State(case)
    ps = {}
    cost = []
    while s.t < len(case["rates"]):
        o = s.observe()
        start = time.perf_counter()
        a = policy(o, ps)
        cost.append(time.perf_counter() - start)
        s.step(a, log=log)
    r = s.result()
    ordered = sorted(cost)
    r.update(
        policy_wall_s=sum(cost),
        decision_p95_s=ordered[int(0.95 * (len(ordered) - 1))],
        decision_max_s=max(cost),
        steps=s.t,
    )
    return (r, s)
