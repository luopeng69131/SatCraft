"""Causal contract scheduling with quality and link-capacity belief branches."""

import math
import itertools
import random

QUALITY_PATHS = True


def _dnf(expr, index, receipts, qualities):
    if not expr:
        return (0,)
    if "all" in expr:
        masks = (0,)
        for child in expr["all"]:
            rhs = _dnf(child, index, receipts, qualities)
            masks = tuple(set((a | b for a in masks for b in rhs)))
        return masks
    if "any" in expr:
        return tuple(
            set(
                (
                    a
                    for child in expr["any"]
                    for a in _dnf(child, index, receipts, qualities)
                )
            )
        )
    jid = expr["delivered"]
    (lo, hi) = (expr.get("quality_min", 0), expr.get("quality_max", 1))
    if jid in receipts:
        return (0,) if lo <= receipts[jid]["quality"] <= hi else ()
    if jid not in index:
        return ()
    i = index[jid]
    return (1 << i,) if lo <= qualities[i] <= hi else ()


def _leaves(expr):
    if not expr:
        return set()
    if "delivered" in expr:
        return {expr["delivered"]}
    return set().union(
        *(_leaves(x) for key in ("all", "any") for x in expr.get(key, ()))
    )


def _future_curve(jobs, services, star, cell, span, warmup, cycle=None):
    n = len(jobs)
    index = {j["id"]: i for (i, j) in enumerate(jobs)}
    bits = [1 << i for i in range(n)]
    modes = []
    breaks = {0.0}
    for cm in range(1 << n):
        work = [
            j["raw"] * (j["ratio"] if cm & bits[i] else 1.0)
            for (i, j) in enumerate(jobs)
        ]
        cpus = [j["cpu"] if cm & bits[i] else 0 for (i, j) in enumerate(jobs)]
        supports = [
            [(q["quality"], q["probability"]) for q in j["quality_support"]]
            if cm & bits[i]
            else [(1.0, 1.0)]
            for (i, j) in enumerate(jobs)
        ]
        worlds = []
        for outcomes in itertools.product(*supports):
            prob = math.prod((q[1] for q in outcomes))
            if prob <= 0:
                continue
            quality = [q[0] for q in outcomes]
            requirements = [_dnf(j.get("requires"), index, {}, quality) for j in jobs]
            memo = {}
            depth = {}

            def closure(i, visiting=0):
                if i in memo:
                    return memo[i]
                if visiting & bits[i]:
                    return ()
                out = []
                levels = []
                for req in requirements[i]:
                    parts = (bits[i],)
                    d = 1
                    for k in range(n):
                        if req & bits[k]:
                            rhs = closure(k, visiting | bits[i])
                            parts = tuple(set((a | b for a in parts for b in rhs)))
                            d = max(d, 1 + depth.get(k, 1))
                    out.extend(parts)
                    if parts:
                        levels.append(d)
                memo[i] = tuple(set(out))
                depth[i] = min(levels, default=span + 1)
                return memo[i]

            recipes = []
            for service in services:
                out = []
                for needed in _dnf(service["accepts"], index, {}, quality):
                    parts = (0,)
                    for i in range(n):
                        if needed & bits[i]:
                            parts = tuple(
                                set((a | b for a in parts for b in closure(i)))
                            )
                    out.extend(parts)
                recipes.append(tuple(set(out)))
            attainable = {(0.0, 0.0)}
            for sm in range(1, 1 << len(services)):
                parts = (0,)
                value = 0.0
                for k, s in enumerate(services):
                    if sm & 1 << k:
                        parts = tuple(set((a | b for a in parts for b in recipes[k])))
                        value += s["value"]
                for mask in parts:
                    members = [i for i in range(n) if mask & bits[i]]
                    level = max((depth.get(i, 1) for i in members), default=0)
                    if sum((cpus[i] for i in members)) + level > span:
                        continue
                    needed = max(
                        0.0,
                        sum((work[i] for i in members))
                        - star
                        * max(
                            0, min(span - level, cycle if cycle is not None else span)
                        ),
                    )
                    if needed > cell * max(0, span - warmup):
                        continue
                    attainable.add((round(needed, 6), value))
            worlds.append((prob, tuple(attainable)))
            breaks.update((b for (b, v) in attainable))
        modes.append(worlds)
    curve = []
    last = -1.0
    for budget in sorted(breaks):
        value = max(
            (
                sum(
                    (
                        p
                        * max(
                            (v for (b, v) in offers if b <= budget + 1e-06), default=0.0
                        )
                        for (p, offers) in worlds
                    )
                )
                for worlds in modes
            ),
            default=0.0,
        )
        if value > last + 1e-08:
            curve.append((budget, value))
            last = value
    return curve


def _repeat_curve(curve, batches, budget):
    """Allocate observed workload offers across inferred later arrivals."""
    frontier = [(0.0, 0.0)]
    for _ in range(batches):
        offers = sorted(
            (
                (round(a + b, 5), x + y)
                for (a, x) in frontier
                for (b, y) in curve
                if a + b <= budget + 1e-06
            ),
            key=lambda offer: (offer[0], -offer[1]),
        )
        frontier = []
        best = -1.0
        for cost, value in offers:
            if value > best + 1e-08:
                frontier.append((cost, value))
                best = value
    return frontier


def _curve_value(curve, budget):
    lo = 0
    hi = len(curve)
    while lo < hi:
        mid = (lo + hi) // 2
        if curve[mid][0] <= budget + 1e-06:
            lo = mid + 1
        else:
            hi = mid
    if not lo:
        return 0.0
    if lo == len(curve):
        return curve[-1][1]
    (a, va) = curve[lo - 1]
    (b, vb) = curve[lo]
    return va + (vb - va) * max(0.0, min(1.0, (budget - a) / max(1e-08, b - a)))


def _observed_quality_repair(expr, receipts):
    if not expr:
        return False
    if "delivered" in expr:
        record = receipts.get(expr["delivered"])
        return (
            record is not None
            and expr.get("quality_max", 1.0) < 1.0
            and (
                expr.get("quality_min", 0.0) <= record["quality"] <= expr["quality_max"]
            )
        )
    return any(
        (
            _observed_quality_repair(child, receipts)
            for key in ("all", "any")
            for child in expr.get(key, ())
        )
    )


def policy(o, state):
    now = o["t"]
    observed = state.setdefault("_observed_capacity_history", [])
    last_seen = state.get("_observed_capacity_last_slot", -1)
    for offset, pair in enumerate(o["past_rates"]):
        slot = now - len(o["past_rates"]) + offset
        if slot > last_seen:
            observed.append((slot, tuple(pair)))
            last_seen = slot
    state["_observed_capacity_last_slot"] = last_seen
    if len(observed) > o["horizon"]:
        del observed[: -o["horizon"]]
    jobs = sorted(o["jobs"], key=lambda j: (j["due"], j["arrival"], j["raw"], j["cpu"]))
    services = o["services"]
    empty = {
        "modes": {},
        "cpu_job": None,
        "net_order": [],
        "cell_enabled": False,
        "cell_cap": 0.0,
    }
    if not jobs or not services:
        return empty
    (n, ns) = (len(jobs), len(services))
    ids = [j["id"] for j in jobs]
    index = {jid: i for (i, jid) in enumerate(ids)}
    bits = [1 << i for i in range(n)]
    allbits = (1 << n) - 1
    receipts = o["receipts"]
    due = [j["due"] - now for j in jobs]
    end = min(48, max(due))
    sdue = [s["due"] - now for s in services]
    values = [s["value"] for s in services]
    hist = o["past_rates"]
    if hist:
        near = hist[-3:]
        recent = [sum((p[k] for p in near)) / len(near) for k in (0, 1)]
        mean = [sum((p[k] for p in hist)) / len(hist) for k in (0, 1)]
        star = max(0.0, 0.78 * recent[0] + 0.22 * mean[0]) * 0.91
        cell = max(0.0, 0.8 * recent[1] + 0.2 * mean[1]) * 0.9
        state["long_star"] = 0.95 * state.get("long_star", mean[0]) + 0.05 * mean[0]
        state["long_cell"] = 0.95 * state.get("long_cell", mean[1]) + 0.05 * mean[1]
        history_window = max((j["due"] - j["arrival"] for j in jobs))
        window = [pair for (slot, pair) in observed if slot >= now - history_window]
        window_star = (
            sum((pair[0] for pair in window)) / len(window) if window else mean[0]
        )
        star = 0.55 * window_star + 0.45 * mean[0]
        if len(hist) >= 6 and cell < 0.1 * max(window_star, mean[0]):
            older_star = sum((p[0] for p in hist[-6:-3])) / 3.0
            star = min(star, max(0.0, recent[0] + (recent[0] - older_star)))
        if len(hist) >= 6:
            older_cell = sum((p[1] for p in hist[-6:-3])) / 3.0
            cell = max(0.45 * cell, min(cell, cell + 0.8 * (recent[1] - older_cell)))
    else:
        star = cell = 1.0
    rate = max(1.0, star + cell * 0.5)
    if hist:
        short_star = sum((p[0] for p in hist[-3:])) / len(hist[-3:])
        short_cell = sum((p[1] for p in hist[-3:])) / len(hist[-3:])
        context_star = sum((p[0] for p in hist)) / len(hist)
        star = 0.65 * short_star + 0.2 * context_star + 0.15 * window_star
        if short_star < 0.55 * window_star:
            star = min(star, 1.1 * short_star + 0.05 * window_star)
        if len(hist) >= 3 and all((p[0] <= 1e-08 for p in hist[-3:])):
            star = 0.0
        cell = 0.72 * short_cell + 0.28 * cell
        if len(hist) >= 3 and short_cell < 0.2 * mean[1]:
            cell = min(cell, 1.1 * short_cell)
        immediate_star = 0.65 * hist[-1][0] + 0.35 * short_star
        immediate_cell = 0.55 * hist[-1][1] + 0.45 * short_cell
        if star == 0.0:
            immediate_star = 0.0
        star_curve = [
            max(0.0, star + (immediate_star - star) * max(0.0, 1.0 - tick / 5.0))
            for tick in range(end)
        ]
        cell_curve = [
            max(0.0, cell + (immediate_cell - cell) * max(0.0, 1.0 - tick / 4.0))
            for tick in range(end)
        ]
    else:
        star_curve = [star] * end
        cell_curve = [cell] * end
    rate = max(1.0, star + 0.5 * cell)
    budget = o["cell_budget"]
    radio = o["radio"]
    warmup = radio["warmup"]
    span = max((j["due"] - j["arrival"] for j in jobs))
    waves = max(1.0, (o["horizon"] - min((j["arrival"] for j in jobs))) / max(1, span))
    allowance = min(budget, budget / waves * 1.25)
    epoch = max([j["arrival"] for j in jobs] + [s["arrival"] for s in services])
    arrivals = state.setdefault("observed_epochs", [])
    for arrival in sorted(
        set([j["arrival"] for j in jobs] + [s["arrival"] for s in services])
    ):
        if arrival not in arrivals:
            arrivals.append(arrival)
    arrivals.sort()
    gaps = sorted((b - a for (a, b) in zip(arrivals, arrivals[1:]) if b > a))
    durations = sorted(set((s["due"] - s["arrival"] for s in services)))
    prior_period = durations[-1] - durations[0] if len(durations) > 1 else span
    period = gaps[len(gaps) // 2] if gaps else max(1, prior_period)
    if state.get("future_epoch") != epoch:
        template = [dict(j) for j in jobs if j["arrival"] == epoch]
        contracts = [dict(s) for s in services if s["arrival"] == epoch]
        if template and contracts:
            state["future_jobs"] = template
            state["future_services"] = contracts
            state["future_epoch"] = epoch
            state["future_curve"] = []
    future_span = max(
        (j["due"] - j["arrival"] for j in state.get("future_jobs", jobs)), default=span
    )
    future_batches = max(0, int((o["horizon"] - epoch - future_span) // max(1, period)))
    state["future_batches"] = future_batches
    confirmed_loss = len(hist) >= 3 and all((p[0] <= 1e-08 for p in hist[-3:]))
    conservative_star = min(star, recent[0]) if hist else star
    if confirmed_loss:
        conservative_star = 0.0
    curve_key = (
        epoch,
        future_batches,
        round(conservative_star, 1),
        round(cell, 1),
        period,
    )
    previous_key = state.get("future_curve_key")
    if future_batches and (
        previous_key is None
        or previous_key[0:2] != curve_key[0:2]
        or now % 4 == 0
        or confirmed_loss
    ):
        one = _future_curve(
            state.get("future_jobs", jobs),
            state.get("future_services", services),
            conservative_star,
            cell,
            future_span,
            warmup,
            period,
        )
        state["future_curve"] = _repeat_curve(one, future_batches, budget)
        state["future_curve_key"] = curve_key
    future_curve = state.get("future_curve", []) if future_batches else []
    future_before = _curve_value(future_curve, budget)
    allowance = min(budget, budget / max(1.0, future_batches + 1.0) * 1.3)
    state["budget_accounting"] = {
        "epoch": epoch,
        "future_batches": future_batches,
        "inferred_period": period,
        "future_curve": future_curve,
        "estimated_future_value": future_before,
        "confirmed_starlink_loss": confirmed_loss,
    }
    base_status = [
        0 if j["status"] == "wait" else 1 if j["status"] == "cpu" else 2 for j in jobs
    ]
    left_cpu = [j["cpu_left"] for j in jobs]
    fixed_compress = sum(
        (bits[i] for (i, j) in enumerate(jobs) if j["choice"] == "compress")
    )
    fixed_raw = sum((bits[i] for (i, j) in enumerate(jobs) if j["choice"] == "raw"))
    free = [
        i
        for i in range(n)
        if not (fixed_compress | fixed_raw) & bits[i] and left_cpu[i] < due[i]
    ]
    children = [[] for _ in jobs]
    for i, j in enumerate(jobs):
        for jid in _leaves(j.get("requires")):
            if jid in index:
                children[index[jid]].append(i)
    models = {}
    rng = random.Random(7129 + now * 967)

    def model(cm):
        if cm in models:
            return models[cm]
        work = [
            float(j["tx_left"])
            if base_status[i]
            else j["raw"] * (j["ratio"] if cm & bits[i] else 1)
            for (i, j) in enumerate(jobs)
        ]
        supports = []
        for i, j in enumerate(jobs):
            supports.append(
                [(q["quality"], q["probability"]) for q in j["quality_support"]]
                if cm & bits[i]
                else [(1.0, 1.0)]
            )
        worlds = []
        for outcomes in itertools.product(*supports):
            prob = math.prod((q[1] for q in outcomes))
            if prob <= 0:
                continue
            qualities = tuple((q[0] for q in outcomes))
            ready = [_dnf(j.get("requires"), index, receipts, qualities) for j in jobs]
            memo = {}

            def closure(i, visiting=0):
                if i in memo:
                    return memo[i]
                if visiting & bits[i]:
                    return ()
                out = []
                for mask in ready[i]:
                    parts = (bits[i],)
                    for k in range(n):
                        if mask & bits[k]:
                            parts = tuple(
                                set(
                                    (
                                        a | b
                                        for a in parts
                                        for b in closure(k, visiting | bits[i])
                                    )
                                )
                            )
                    out.extend(parts)
                memo[i] = tuple(set(out))
                return memo[i]

            recipes = []
            for s in services:
                out = []
                for mask in _dnf(s["accepts"], index, receipts, qualities):
                    parts = (0,)
                    for k in range(n):
                        if mask & bits[k]:
                            parts = tuple(
                                set((a | b for a in parts for b in closure(k)))
                            )
                    out.extend(parts)
                recipes.append(tuple(set(out)))
            worlds.append((prob, qualities, ready, recipes))
        if len(worlds) > 16:
            worlds.sort(key=lambda w: -w[0])
            worlds = worlds[:16]
            total = sum((w[0] for w in worlds))
            worlds = [(p / total, q, r, f) for (p, q, r, f) in worlds]
        equality = [
            [sum((bits[i] for i in range(n) if a[1][i] == b[1][i])) for b in worlds]
            for a in worlds
        ]
        tail = [0.0] * n
        for _ in range(n):
            previous = tail[:]
            for i in range(n):
                tail[i] = max(
                    [0.0]
                    + [
                        min(
                            end,
                            previous[k]
                            + work[k] / rate
                            + (
                                left_cpu[k]
                                if cm & bits[k] and base_status[k] != 2
                                else 0
                            )
                            + 1,
                        )
                        for k in children[i]
                    ]
                )
        if QUALITY_PATHS:
            world_tails = []
            for prob, quals, ready, recipes in worlds:
                valid = 0
                for offers in recipes:
                    for mask in offers:
                        valid |= mask
                local = [0.0] * n
                for _ in range(n):
                    before = local[:]
                    for i in range(n):
                        dependents = [
                            k
                            for k in children[i]
                            if valid & bits[k]
                            and any((req & bits[i] for req in ready[k]))
                        ]
                        local[i] = max(
                            [0.0]
                            + [
                                min(
                                    end,
                                    before[k]
                                    + work[k] / rate
                                    + (
                                        left_cpu[k]
                                        if cm & bits[k] and base_status[k] != 2
                                        else 0
                                    )
                                    + 1,
                                )
                                for k in dependents
                            ]
                        )
                world_tails.append((prob, local))
            tail = [
                sum((prob * local[i] for (prob, local) in world_tails))
                for i in range(n)
            ]
        priority = []
        for i in range(n):
            value = sum(
                (
                    values[s] * p
                    for (p, q, r, recipes) in worlds
                    for s in range(ns)
                    if any((mask & bits[i] for mask in recipes[s]))
                )
            )
            priority.append(value + 1.25 * tail[i])
        cp = tuple(sorted(range(n), key=lambda i: (-priority[i], due[i], left_cpu[i])))
        np = tuple(
            sorted(range(n), key=lambda i: (due[i] - tail[i], -priority[i], work[i]))
        )
        upper = sum(
            (
                p * sum((values[s] for s in range(ns) if recipes[s]))
                for (p, q, r, recipes) in worlds
            )
        )
        m = (work, worlds, equality, tail, cp, np, upper, [{} for _ in worlds])
        models[cm] = m
        return m

    def simulate(plan, capacity_factor=1.0):
        predicted_star = star * capacity_factor
        (cm, sm, cp, np, style) = plan
        (work, worlds, equality, tail, _, _, upper, caches) = model(cm)
        score = 0.0
        first = None
        for wi, (prob, quals, requirements, recipes) in enumerate(worlds):
            status = base_status[:]
            tx = work[:]
            cpu = left_cpu[:]
            done = 0
            dead = 0
            fulfilled = 0
            earned = 0.0
            early = 0.0
            spent = 0.0
            enabled = radio["mode"] != "OFF"
            delay = radio["ready_in"] if enabled else warmup
            active = radio["active"]
            acts = 0
            started = 0
            cache = caches[wi]
            for tick in range(end):
                predicted_star = star_curve[tick] * capacity_factor
                predicted_cell = cell_curve[tick] * (
                    0.85 if capacity_factor < 1.0 else 1.0
                )
                dead |= sum(
                    (
                        bits[i]
                        for i in range(n)
                        if due[i] <= tick and (not done & bits[i])
                    )
                )
                key = (done, dead, fulfilled, sm)
                useful = cache.get(key)
                if useful is None:
                    useful = 0
                    compatible = [
                        k
                        for k in range(len(worlds))
                        if not done & (allbits ^ equality[wi][k])
                    ]
                    for s in range(ns):
                        if not sm & 1 << s or fulfilled & 1 << s or sdue[s] <= tick:
                            continue
                        for k in compatible:
                            candidates = [r for r in worlds[k][3][s] if not r & dead]
                            if candidates:
                                chosen = min(
                                    candidates,
                                    key=lambda r: sum(
                                        (
                                            work[i] / rate + 0.55 * left_cpu[i]
                                            for i in range(n)
                                            if r & bits[i] and (not done & bits[i])
                                        )
                                    ),
                                )
                                useful |= chosen & ~done
                    cache[key] = useful
                if not useful:
                    break
                ready = [
                    i
                    for i in range(n)
                    if useful & bits[i]
                    and (not dead & bits[i])
                    and any((not r & ~done for r in requirements[i]))
                ]
                readyset = set(ready)
                chosen_cpu = next(
                    (
                        i
                        for i in cp
                        if i in readyset and status[i] != 2 and cm & bits[i]
                    ),
                    None,
                )
                compressed_ready = [i for i in ready if status[i] != 2 and cm & bits[i]]
                emergencies = [
                    i
                    for i in compressed_ready
                    if due[i]
                    - tick
                    - cpu[i]
                    - tx[i] / max(1.0, predicted_star + 0.4 * cell)
                    <= warmup + 1.0
                ]
                if emergencies:
                    chosen_cpu = min(
                        emergencies,
                        key=lambda i: (due[i] - tick - cpu[i], cpu[i], due[i]),
                    )
                modes = {}
                if chosen_cpu is not None and status[chosen_cpu] == 0:
                    status[chosen_cpu] = 1
                    modes[ids[chosen_cpu]] = "compress"
                for i in np:
                    if i in readyset and status[i] == 0 and (not cm & bits[i]):
                        status[i] = 2
                        modes[ids[i]] = "raw"
                queue = [
                    i
                    for i in np
                    if status[i] == 2
                    and (not (done | dead) & bits[i])
                    and useful & bits[i]
                ]
                queue += [
                    i
                    for i in np
                    if status[i] == 2 and (not (done | dead | useful) & bits[i])
                ]
                live = [
                    i
                    for i in range(n)
                    if useful & bits[i] and (not (done | dead) & bits[i])
                ]
                deficit = 0.0
                urgent = 0.0
                start_delay = delay if enabled else warmup
                deadlines = [
                    (max(tick + 1.0, due[i] - 0.72 * tail[i]), i) for i in live
                ]
                deadlines.sort()
                demand = 0.0
                for deadline, i in deadlines:
                    demand += tx[i]
                    lack = demand - predicted_star * max(0.0, deadline - tick - 0.6)
                    deficit = max(deficit, lack)
                    urgent = max(
                        urgent,
                        lack
                        - predicted_cell
                        * max(0.0, deadline - tick - start_delay - (4 if style else 2)),
                    )
                    release = cpu[i] if status[i] != 2 and cm & bits[i] else 0
                    lack = tx[i] - predicted_star * max(
                        0.0, due[i] - tick - release - 0.72 * tail[i] - 0.6
                    )
                    deficit = max(deficit, lack)
                    urgent = max(
                        urgent,
                        lack
                        - predicted_cell
                        * max(0.0, due[i] - tick - start_delay - (4 if style else 2)),
                    )
                need = min(budget - spent, max(0.0, deficit))
                cap = min(budget - spent, max(0.0, urgent))
                soon = bool(queue) or any(
                    (status[i] == 1 and cpu[i] <= start_delay + 1 for i in live)
                )
                if style == 2:
                    cap = need
                use = (
                    cap > 0.001
                    and active > 0
                    and (need > 0.001)
                    and soon
                    and (predicted_cell > max(1e-08, 0.025 * predicted_star))
                )
                if (
                    enabled
                    and soon
                    and (active > 0)
                    and (need > 0.001)
                    and (predicted_cell > max(1e-08, 0.025 * predicted_star))
                ):
                    use = use or need > predicted_cell * 0.2
                    if use:
                        cap = max(cap, min(need, predicted_cell))
                near_output = any(
                    (status[i] == 1 and cpu[i] <= start_delay + 2 for i in live)
                )
                queued_bytes = sum((tx[i] for i in queue if useful & bits[i]))
                useful_backup = predicted_cell > max(1e-08, 0.06 * predicted_star)
                if (
                    enabled
                    and active > start_delay + 1
                    and (budget - spent > 0.0)
                    and useful_backup
                    and (
                        queued_bytes > predicted_star * (start_delay + 1) or near_output
                    )
                    and (need > 0.001)
                ):
                    use = True
                    cap = max(cap, min(need, predicted_cell))
                if tick == 0:
                    action = {
                        "modes": modes,
                        "cpu_job": ids[chosen_cpu] if chosen_cpu is not None else None,
                        "net_order": [ids[i] for i in queue],
                        "cell_enabled": bool(use),
                        "cell_cap": max(0.0, cap),
                    }
                    if first is None:
                        first = action
                cell_available = 0.0
                if use:
                    if not enabled:
                        delay = warmup
                        started += 1
                    active -= 1
                    acts += 1
                    enabled = True
                    if delay:
                        delay -= 1
                    else:
                        cell_available = min(predicted_cell, cap)
                else:
                    enabled = False
                    delay = warmup
                output_cpu = None
                if chosen_cpu is not None:
                    cpu[chosen_cpu] -= 1
                    if cpu[chosen_cpu] == 0:
                        output_cpu = chosen_cpu
                free = predicted_star
                paid = cell_available
                for i in queue:
                    amount = min(tx[i], free)
                    tx[i] -= amount
                    free -= amount
                    amount = min(tx[i], paid)
                    tx[i] -= amount
                    paid -= amount
                    spent += amount
                    if tx[i] <= 1e-08:
                        done |= bits[i]
                if output_cpu is not None:
                    status[output_cpu] = 2
                for s in range(ns):
                    if (
                        not fulfilled & 1 << s
                        and tick < sdue[s]
                        and any((not r & ~done for r in recipes[s]))
                    ):
                        fulfilled |= 1 << s
                        earned += values[s]
                        early += values[s] * (sdue[s] - tick - 1) / max(1, sdue[s])
            progress = 0.0
            for s in range(ns):
                if fulfilled & 1 << s or not sm & 1 << s:
                    continue
                for r in recipes[s]:
                    count = max(1, r.bit_count())
                    part = 0.0
                    for i in range(n):
                        if r & bits[i]:
                            part += (
                                1.0
                                if done & bits[i]
                                else 0.65 * (1 - tx[i] / max(work[i], 1e-08))
                                + 0.35 * (1 - cpu[i] / max(left_cpu[i], 1))
                            )
                    progress = max(progress, values[s] * part / count)
            score += prob * (
                earned
                + 0.15 * early
                + 0.12 * progress
                - 0.003 * spent
                - 0.006 * max(0.0, spent - allowance)
                - 0.012 * acts
                - 0.007 * started
                + _curve_value(future_curve, budget - spent)
                - future_before
            )
        return (score, first)

    masks = [0, (1 << ns) - 1] if future_curve else [(1 << ns) - 1]
    masks += [1 << s for s in sorted(range(ns), key=lambda s: -values[s])]
    if ns > 2:
        masks += [(1 << ns) - 1 ^ 1 << s for s in range(ns)]
    masks = list(dict.fromkeys(masks))
    choices = []
    for sub in range(1 << min(len(free), 10)):
        cm = fixed_compress | sum(
            (bits[i] for (k, i) in enumerate(free) if sub & 1 << k)
        )
        m = model(cm)
        choices.append((cm, m))
    choices.sort(key=lambda p: (-p[1][6], sum(p[1][0])))
    best_score = -1e30
    best_plan = None
    best_action = None
    elite = []
    visited = set()

    def attempt(plan):
        nonlocal best_score, best_plan, best_action
        if plan in visited:
            return
        visited.add(plan)
        (middle_score, action) = simulate(plan)
        (low_score, low_action) = simulate(plan, 0.7)
        (high_score, _) = simulate(plan, 1.2)
        score = 0.5 * middle_score + 0.3 * low_score + 0.2 * high_score
        if (
            action is not None
            and low_action is not None
            and (low_score > 0.0)
            and low_action["cell_enabled"]
            and (cell > 0.05 * max(1.0, star))
        ):
            action["cell_enabled"] = True
            action["cell_cap"] = max(
                action["cell_cap"], min(budget, low_action["cell_cap"])
            )
        elite.append((score, plan))
        if score > best_score + 1e-09:
            (best_score, best_plan, best_action) = (score, plan, action)

    for cm, m in choices:
        if 1.15 * m[6] < best_score:
            continue
        for sm in masks:
            attempt((cm, sm, m[4], m[5], 2))
    structured = sorted(elite, key=lambda x: -x[0])[:8]
    for _, seed in structured:
        (cm, sm, cp, np, style) = seed
        (work, worlds, equality, tail, _, _, _, caches) = model(cm)
        urgency = [
            due[i]
            - left_cpu[i]
            - work[i] / max(1.0, star + 0.35 * cell)
            - 0.5 * tail[i]
            for i in range(n)
        ]
        cpu_orders = [
            cp,
            tuple(sorted(range(n), key=lambda i: (due[i], left_cpu[i]))),
            tuple(sorted(range(n), key=lambda i: (urgency[i], due[i]))),
            tuple(sorted(range(n), key=lambda i: (left_cpu[i], due[i]))),
        ]
        net_orders = [
            np,
            tuple(sorted(range(n), key=lambda i: (due[i], work[i]))),
            tuple(sorted(range(n), key=lambda i: (due[i] - 0.85 * tail[i], work[i]))),
        ]
        for cpu_order in cpu_orders:
            for net_order in net_orders:
                for radio_style in (0, 2):
                    attempt((cm, sm, cpu_order, net_order, radio_style))
    elite.sort(reverse=True, key=lambda x: x[0])
    frontier = elite[:6]
    for k in range(72):
        if not frontier:
            break
        source = best_plan if k % 3 else frontier[k % len(frontier)][1]
        (cm, sm, cp, np, style) = source
        (cp, np) = (list(cp), list(np))
        if k % 6 == 0:
            style = (style + 1) % 3
        elif n > 1:
            order = cp if k % 2 else np
            (a, b) = rng.sample(range(n), 2)
            (order[a], order[b]) = (order[b], order[a])
        attempt((cm, sm, tuple(cp), tuple(np), style))
    if best_action is None:
        return empty
    modes = best_action["modes"]
    horizon_bytes = 1.35 * star + (
        cell if best_action["cell_enabled"] and radio["mode"] == "ON" else 0.0
    )
    ahead = 0.0
    keep = {}
    for jid in best_action["net_order"]:
        i = index[jid]
        if modes.get(jid) == "raw":
            paid_rate = (
                cell if best_action["cell_enabled"] and radio["mode"] == "ON" else 0.0
            )
            raw_time = jobs[i]["raw"] / max(1.0, star + 0.25 * paid_rate)
            compressed_time = (
                left_cpu[i]
                + jobs[i]["raw"] * jobs[i]["ratio"] / max(1.0, star + 0.25 * paid_rate)
                + 1.0
            )
            keep_option = (
                jobs[i]["cpu"] >= 8
                and jobs[i]["ratio"] <= 0.25
                and (left_cpu[i] + 2 < due[i])
                and (raw_time > compressed_time + 2.0)
            )
            if keep_option:
                if best_action["cpu_job"] is None and (
                    not any((j["status"] == "cpu" for j in jobs))
                ):
                    keep[jid] = "compress"
                    best_action["cpu_job"] = jid
            elif ahead <= horizon_bytes + 1e-08:
                keep[jid] = "raw"
                ahead += jobs[i]["raw"]
        elif base_status[i] == 2:
            ahead += jobs[i]["tx_left"]
    for jid, mode in modes.items():
        if mode == "compress":
            keep[jid] = mode
    best_action["modes"] = keep
    best_action["net_order"] = [
        jid
        for jid in best_action["net_order"]
        if base_status[index[jid]] == 2 or keep.get(jid) == "raw"
    ]
    if best_action["cpu_job"] is None:
        pending = [
            i
            for (i, j) in enumerate(jobs)
            if j["status"] == "cpu" and j.get("ready", True)
        ]
        if pending:
            i = min(pending, key=lambda k: (due[k], left_cpu[k]))
            best_action["cpu_job"] = ids[i]
    if (
        confirmed_loss
        and radio["mode"] == "ON"
        and (radio["active"] > 0)
        and (cell > 1e-08)
        and (budget > 0.0)
    ):
        prefix = 0.0
        due_prefix = 0.0
        for jid in best_action["net_order"]:
            i = index[jid]
            prefix += jobs[i]["tx_left"]
            if due[i] <= 1:
                due_prefix = prefix
        if due_prefix > 0.0:
            best_action["cell_enabled"] = True
            best_action["cell_cap"] = max(
                best_action["cell_cap"], min(budget, due_prefix)
            )
    if (
        radio["mode"] == "WARMING"
        and radio["active"] > radio["ready_in"] + 1
        and (budget > 0.0)
    ):
        queued = sum((jobs[index[jid]]["tx_left"] for jid in best_action["net_order"]))
        pending = any(
            (
                j["status"] == "cpu" and j["cpu_left"] <= radio["ready_in"] + 2
                for j in jobs
            )
        )
        if cell > max(1e-08, 0.06 * star) and (
            queued > star * (radio["ready_in"] + 1) or pending
        ):
            best_action["cell_enabled"] = True
            best_action["cell_cap"] = max(best_action["cell_cap"], min(budget, cell))
    return best_action
