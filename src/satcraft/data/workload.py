"""Generate dependent product tasks, service contracts, and quality outcomes."""

import hashlib
import math
import random

PROFILES = (
    {
        "id": "balanced",
        "pressure": 1.25,
        "cpu_scale": 1.0,
        "warmup": 2,
        "active_slots": 60,
    },
    {
        "id": "network_pressure",
        "pressure": 1.75,
        "cpu_scale": 1.0,
        "warmup": 2,
        "active_slots": 60,
    },
    {
        "id": "cpu_pressure",
        "pressure": 1.25,
        "cpu_scale": 1.4,
        "warmup": 2,
        "active_slots": 60,
    },
    {
        "id": "radio_pressure",
        "pressure": 1.25,
        "cpu_scale": 1.0,
        "warmup": 4,
        "active_slots": 45,
    },
)
QUALITY_SEEDS = {
    "development": (1701, 1702, 1703),
    "validation": (1711, 1712),
    "test": (1721, 1722, 1723),
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def make_case(rates, source, profile, quality_seed, split):
    if len(rates) < 119:
        raise ValueError("The service workload requires 119 nominal one-second slots")
    rates = [list(pair) for pair in rates[:119]]
    reference = sum(pair[0] for pair in rates[:8]) / 8
    if reference <= 0:
        raise ValueError("Initial Starlink mean capacity must be positive")
    region, run = source["region"], source["a_run"]
    rng = random.Random(
        int(digest("paper-v17/workload/" + region + "/" + run)[:16], 16)
    )
    ids = rng.sample(range(10000, 99999), 24)
    cpu = [max(1, n + rng.choice([-1, 0, 1])) for _ in range(6) for n in (2, 3, 14, 5)]
    qr = random.Random(
        int(digest(f"v17/quality/{region}/{run}/{quality_seed}")[:16], 16)
    )
    case = {
        "id": f"{source['source_id']}_{profile['id']}_q{quality_seed}",
        "source_id": source["source_id"],
        "profile": profile["id"],
        "split": split,
        "pressure": profile["pressure"],
        "quality_seed": quality_seed,
        "rates": rates,
        "cell_budget": 8 * reference,
        "warmup": profile["warmup"],
        "active_slots": profile["active_slots"],
        "jobs": [],
        "services": [],
        "compression_outcomes": {},
        "synthetic_compute": True,
        "contract_type": "overlapping_quality_repair",
    }

    def receipt(jid, quality=0.85):
        return {"delivered": jid, "quality_min": quality}

    for batch, arrival in enumerate((8, 24, 40, 56, 72, 88)):
        root, report, evidence, supplement = ids[4 * batch : 4 * batch + 4]
        requirements = [
            None,
            receipt(root, 0.5),
            {"any": [receipt(root), receipt(supplement)]},
            {"delivered": root, "quality_max": 0.8},
        ]
        for k, jid in enumerate((root, report, evidence, supplement)):
            case["jobs"].append(
                {
                    "id": jid,
                    "arrival": arrival,
                    "due": arrival + (12, 12, 28, 20)[k],
                    "raw": (2, 3, 7, 4)[k] * profile["pressure"] * reference,
                    "cpu": math.ceil(cpu[4 * batch + k] * profile["cpu_scale"]),
                    "ratio": (0.2, 0.25, 0.12, 0.5)[k],
                    "requires": requirements[k],
                    "quality_support": [
                        {"quality": 0.6, "probability": 0.5},
                        {"quality": 0.95, "probability": 0.5},
                    ]
                    if k == 0
                    else [{"quality": 0.95, "probability": 1.0}],
                }
            )
            case["compression_outcomes"][str(jid)] = (
                (0.6 if qr.random() < 0.5 else 0.95) if k == 0 else 0.95
            )
        case["services"].extend(
            [
                {
                    "id": 900001 + 2 * batch,
                    "arrival": arrival,
                    "due": arrival + 12,
                    "value": 4,
                    "accepts": {"all": [receipt(root, 0.5), receipt(report)]},
                },
                {
                    "id": 900002 + 2 * batch,
                    "arrival": arrival,
                    "due": arrival + 28,
                    "value": 8,
                    "accepts": receipt(evidence),
                },
            ]
        )
    return case


def demo_cases(seed=7):
    """Create illustrative access sequences and service workloads in memory."""
    rng = random.Random(seed)
    rates = [
        [
            max(0.0, 70 + 30 * math.sin(t / 9) + rng.uniform(-8, 8)),
            max(0.0, 35 + 30 * math.cos(t / 13)),
        ]
        for t in range(119)
    ]
    for t in range(44, 53):
        rates[t][0] = 0.0
    source = {"source_id": "demo", "region": "demo", "a_run": f"generated_{seed}"}
    return [make_case(rates, source, profile, 1701, "demo") for profile in PROFILES]
