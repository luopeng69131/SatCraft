"""Export user-selected NUWiNS trace pairs as reusable simulator inputs."""

import hashlib
import math
from pathlib import Path

from satcraft.io import write_json
from .traces import load_pair

DATASET_URL = "https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue"


def prepare(
    dataset_root,
    output,
    region,
    carrier,
    samples_per_slot=2,
    sample_period_seconds=0.5,
    min_slots=8,
    max_gap_seconds=1.0,
):
    """Preserve all eligible run/segment pairs selected by the caller.

    Mean Mbps times the nominal slot duration gives Mbit per simulator slot.
    """
    if type(samples_per_slot) is not int or samples_per_slot < 1:
        raise ValueError("samples_per_slot must be a positive integer")
    if type(min_slots) is not int or min_slots < 1:
        raise ValueError("min_slots must be a positive integer")
    if any(
        not math.isfinite(x) or x <= 0 for x in (sample_period_seconds, max_gap_seconds)
    ):
        raise ValueError("Sample duration and gap threshold must be positive")
    root, output = Path(dataset_root), Path(output)
    episodes, audit = load_pair(
        root,
        region,
        carrier,
        samples_per_block=samples_per_slot,
        min_blocks=min_slots,
        max_gap_s=max_gap_seconds,
    )
    slot_seconds = samples_per_slot * sample_period_seconds
    traces = [
        {
            "source_id": episode.key,
            "region": episode.region,
            "carrier": episode.carrier,
            "a_run": episode.a_run,
            "b_run": episode.b_run,
            "segment": episode.segment,
            "day": episode.day,
            "slot_seconds": slot_seconds,
            "rates": [
                [block.starlink_mbps * slot_seconds, block.cell_mbps * slot_seconds]
                for block in episode.blocks
            ],
        }
        for episode in episodes
    ]
    source = Path(audit["path"])
    checksum = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    audit["sha256"] = checksum.hexdigest()
    audit["path"] = str(source.relative_to(root))
    write_json(output / "traces.json", traces)
    write_json(
        output / "manifest.json",
        {
            "dataset": DATASET_URL,
            "dataset_license": "CC-BY-4.0",
            "slot_seconds": slot_seconds,
            "capacity_unit": "Mbit per slot",
            "samples_per_slot": samples_per_slot,
            "region": region,
            "carrier": carrier,
            "trace_count": len(traces),
            "input": audit,
        },
    )
    return {"traces": len(traces), "slot_seconds": slot_seconds}
