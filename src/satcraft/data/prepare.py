"""Build simulation cases from locally downloaded measurement files."""

import hashlib
from dataclasses import asdict
from pathlib import Path

from satcraft.io import read_json, write_json
from .traces import load_pair
from .workload import PROFILES, QUALITY_SEEDS, digest, make_case

DATASET_URL = "https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue"


def prepare(dataset_root, output, runs_per_region=15, source_manifest=None):
    if runs_per_region < 1:
        raise ValueError("runs_per_region must be positive")
    output = Path(output)
    pool, audits = {}, []
    for region in ("alaska", "hawaii"):
        for carrier in ("att", "verizon"):
            episodes, audit = load_pair(
                Path(dataset_root), region, carrier, samples_per_block=2, min_blocks=119
            )
            audit["path"] = str(Path(audit["path"]).relative_to(dataset_root))
            audit["sha256"] = hashlib.sha256(
                (Path(dataset_root) / audit["path"]).read_bytes()
            ).hexdigest()
            audits.append(audit)
            for episode in episodes:
                if sum(b.starlink_mbps for b in episode.blocks[:8]) / 8 >= 1:
                    pool.setdefault((region, episode.a_run), []).append(episode)
    selected = {}
    if source_manifest:
        manifest = read_json(source_manifest)
        if not isinstance(manifest, list):
            raise ValueError("A source manifest is a list of source records")
        for row in manifest:
            split = {"target": "development", "transfer": "test"}.get(
                row["split"], row["split"]
            )
            if split not in ("development", "test"):
                raise ValueError("Source manifest splits must be development or test")
            matches = [
                e
                for e in pool.get((row["region"], row["a_run"]), [])
                if (e.b_run, e.carrier, e.segment)
                == (row["b_run"], row["carrier"], row["segment"])
            ]
            if len(matches) != 1:
                raise ValueError(f"Manifest source is unavailable: {row['source_id']}")
            selected.setdefault(split, []).append((matches[0], row["source_id"]))
    else:
        used = set()
        for split, legacy_name in (("test", "transfer"), ("development", "target")):
            episodes = []
            for region in ("alaska", "hawaii"):
                keys = [key for key in pool if key[0] == region and key not in used]
                keys.sort(
                    key=lambda key: digest(
                        "paper-v17/" + legacy_name + "/" + key[0] + "/" + key[1]
                    )
                )
                if len(keys) < runs_per_region:
                    raise ValueError(
                        f"Need {runs_per_region} unused eligible {region} runs for {split}; found {len(keys)}"
                    )
                for rank, key in enumerate(keys[:runs_per_region]):
                    preferred = ("att", "verizon")[rank % 2]
                    episode = min(
                        pool[key],
                        key=lambda e: (e.carrier != preferred, e.b_run, e.segment),
                    )
                    episodes.append(episode)
                    used.add(key)
            episodes.sort(
                key=lambda e: (e.a_run[:8], digest("v17/order/" + e.region + e.a_run))
            )
            selected[split] = [
                (e, f"{split}_{i + 1:02d}") for i, e in enumerate(episodes)
            ]
    if set(selected) != {"development", "test"}:
        raise ValueError("Provide both development and test sources")
    keys = {
        split: {(e.region, e.a_run) for e, _ in rows}
        for split, rows in selected.items()
    }
    if keys["development"] & keys["test"]:
        raise ValueError("Development and test sets must use distinct measured runs")
    for rows in selected.values():
        if len({(e.region, e.a_run) for e, _ in rows}) != len(rows) or len(
            {i for _, i in rows}
        ) != len(rows):
            raise ValueError(
                "Each split must contain unique source runs and identifiers"
            )
    sources, counts = [], {}
    for split, rows in selected.items():
        for episode, source_id in rows:
            sources.append(
                {
                    "split": split,
                    "source_id": source_id,
                    "region": episode.region,
                    "carrier": episode.carrier,
                    "a_run": episode.a_run,
                    "b_run": episode.b_run,
                    "segment": episode.segment,
                    "day": episode.day,
                }
            )
    for split, seeds in QUALITY_SEEDS.items():
        source_split = "development" if split == "validation" else split
        cases = []
        for episode, source_id in selected[source_split]:
            rates = [(b.starlink_mbps, b.cell_mbps) for b in episode.blocks[:119]]
            source = {
                "source_id": source_id,
                "region": episode.region,
                "a_run": episode.a_run,
            }
            cases.extend(
                make_case(rates, source, profile, seed, split)
                for profile in PROFILES
                for seed in seeds
            )
        write_json(output / f"{split}.json", cases)
        counts[split] = len(cases)
    write_json(output / "sources.json", sources)
    write_json(
        output / "manifest.json",
        {
            "dataset": DATASET_URL,
            "dataset_license": "CC-BY-4.0",
            "slot_seconds": 1,
            "samples_per_block": 2,
            "slots": 119,
            "calibration_slots": 8,
            "profiles": list(PROFILES),
            "case_counts": counts,
            "source_selection": "supplied manifest"
            if source_manifest
            else "deterministic SHA ordering of eligible sources",
            "inputs": audits,
        },
    )
    return counts
