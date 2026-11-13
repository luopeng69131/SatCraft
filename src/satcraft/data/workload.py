"""Construct user-defined service scenarios and a small synthetic example."""

import copy
import math
import random


def make_case(
    rates,
    jobs,
    services,
    *,
    case_id="example",
    source_id=None,
    profile="custom",
    cell_budget=120.0,
    warmup=1,
    active_slots=None,
    quality_seed=0,
):
    """Build a scenario from per-slot capacities, products, and service predicates.

    Capacities and product sizes use Mbit; processing and radio budgets use slots.
    Processing qualities are sampled into environment-private outcome records.
    """
    pairs = [list(pair) for pair in rates]
    if not pairs or any(
        len(pair) != 2 or any(not math.isfinite(x) or x < 0 for x in pair)
        for pair in pairs
    ):
        raise ValueError("Supply finite, nonnegative satellite/cellular capacities")
    if not math.isfinite(cell_budget) or cell_budget < 0:
        raise ValueError("Cellular traffic budget must be finite and nonnegative")
    active_slots = len(pairs) if active_slots is None else active_slots
    if any(type(x) is not int or x < 0 for x in (warmup, active_slots)):
        raise ValueError(
            "Startup and activation allowances are nonnegative slot counts"
        )
    products = copy.deepcopy(list(jobs))
    contracts = copy.deepcopy(list(services))
    if len({job["id"] for job in products}) != len(products):
        raise ValueError("Product identifiers must be unique")
    if len({service["id"] for service in contracts}) != len(contracts):
        raise ValueError("Service identifiers must be unique")
    outcomes, rng = {}, random.Random(quality_seed)
    for job in products:
        job.setdefault("requires", None)
        support = job.setdefault(
            "quality_support", [{"quality": 1.0, "probability": 1.0}]
        )
        if (
            not support
            or any(
                not math.isfinite(item["quality"])
                or not 0 <= item["quality"] <= 1
                or not math.isfinite(item["probability"])
                or item["probability"] < 0
                for item in support
            )
            or not math.isclose(sum(item["probability"] for item in support), 1.0)
        ):
            raise ValueError("Quality support must define a probability distribution")
        if type(job["cpu"]) is not int or job["cpu"] < 1:
            raise ValueError("Processing demand is a positive integer number of slots")
        if not math.isfinite(job["raw"]) or job["raw"] < 0 or not 0 < job["ratio"] <= 1:
            raise ValueError("Product size and processing ratio are invalid")
        if not 0 <= job["arrival"] < job["due"] <= len(pairs):
            raise ValueError("Product lifetime must fit within the scenario")
        outcomes[str(job["id"])] = rng.choices(
            [item["quality"] for item in support],
            weights=[item["probability"] for item in support],
            k=1,
        )[0]
    for service in contracts:
        if not 0 <= service["arrival"] < service["due"] <= len(pairs):
            raise ValueError("Service lifetime must fit within the scenario")
    return {
        "id": case_id,
        "source_id": source_id or case_id,
        "profile": profile,
        "quality_seed": quality_seed,
        "rates": pairs,
        "jobs": products,
        "services": contracts,
        "compression_outcomes": outcomes,
        "cell_budget": float(cell_budget),
        "warmup": warmup,
        "active_slots": active_slots,
    }


def demo_cases(seed=7):
    """Create one 48-slot teaching scenario with two dependent services."""
    rng = random.Random(seed)
    rates = [
        [
            max(0.0, 18 + 7 * math.sin(t / 5) + rng.uniform(-2, 2)),
            max(0.0, 9 + 6 * math.cos(t / 7)),
        ]
        for t in range(48)
    ]
    for t in range(19, 25):
        rates[t][0] = 0.0

    def receipt(job, quality=0.85):
        return {"delivered": job, "quality_min": quality}

    jobs = [
        {
            "id": 1,
            "arrival": 8,
            "due": 26,
            "raw": 180.0,
            "cpu": 2,
            "ratio": 0.25,
            "quality_support": [
                {"quality": 0.6, "probability": 0.5},
                {"quality": 0.95, "probability": 0.5},
            ],
        },
        {
            "id": 2,
            "arrival": 8,
            "due": 32,
            "raw": 45.0,
            "cpu": 1,
            "ratio": 0.5,
            "requires": receipt(1, 0.5),
        },
        {
            "id": 3,
            "arrival": 8,
            "due": 32,
            "raw": 90.0,
            "cpu": 2,
            "ratio": 0.5,
            "requires": {"delivered": 1, "quality_max": 0.8},
        },
        {"id": 4, "arrival": 12, "due": 46, "raw": 400.0, "cpu": 4, "ratio": 0.2},
    ]
    services = [
        {
            "id": 101,
            "arrival": 8,
            "due": 32,
            "value": 10,
            "accepts": {"all": [receipt(2), {"any": [receipt(1), receipt(3)]}]},
        },
        {"id": 102, "arrival": 12, "due": 46, "value": 3, "accepts": receipt(4)},
    ]
    return [
        make_case(
            rates,
            jobs,
            services,
            case_id="inspection-example",
            profile="balanced",
            cell_budget=100.0,
            warmup=2,
            active_slots=18,
            quality_seed=seed,
        )
    ]
