"""Read synchronized NUWiNS Starlink/cellular throughput pairs."""

import csv
import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

SAMPLES_PER_BLOCK = 10
MAX_SAMPLE_GAP_S = 1.0
MIN_BLOCKS = 8


@dataclass(frozen=True)
class Block:
    starlink_mbps: float
    cell_mbps: float


@dataclass(frozen=True)
class Episode:
    region: str
    carrier: str
    day: str
    a_run: str
    b_run: str
    segment: int
    blocks: Tuple[Block, ...]

    @property
    def key(self) -> str:
        return "/".join(
            (self.region, self.carrier, self.a_run, self.b_run, str(self.segment))
        )

    @property
    def run_key(self) -> str:
        return "/".join((self.region, self.carrier, self.a_run, self.b_run))


def _parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def load_pair(
    root: Path,
    region: str,
    carrier: str,
    samples_per_block: int = SAMPLES_PER_BLOCK,
    max_gap_s: float = MAX_SAMPLE_GAP_S,
    min_blocks: int = MIN_BLOCKS,
) -> Tuple[List[Episode], Dict]:
    """Load one Starlink/cellular pair, preserving run and gap boundaries."""
    if region not in ("alaska", "hawaii"):
        raise ValueError("Only Alaska/Hawaii have released pre-aligned pairs")
    if carrier not in ("att", "verizon", "tmobile"):
        raise ValueError("Unknown carrier")
    folder = (
        "alaska_road_test_202406" if region == "alaska" else "hawaii_road_test_202408"
    )
    path = (
        Path(root)
        / folder
        / "processed"
        / "mpshell"
        / "raw_traces"
        / ("fused_trace.tcp_downlink.starlink_%s.csv" % carrier)
    )
    if not path.is_file():
        raise FileNotFoundError(str(path))
    runs = defaultdict(list)
    total_rows = 0
    invalid_rows = 0
    offsets = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total_rows += 1
            try:
                if row["A"] != "starlink" or row["B"] != carrier:
                    raise ValueError("Unexpected path labels")
                a = float(row["A_throughput_mbps"])
                b = float(row["B_throughput_mbps"])
                ta = _parse_time(row["A_time"])
                tb = _parse_time(row["B_time"])
                if not (
                    math.isfinite(a) and math.isfinite(b) and (a >= 0) and (b >= 0)
                ):
                    raise ValueError("Invalid rate")
                if abs((ta - tb).total_seconds()) > 0.55:
                    raise ValueError("Pair misalignment exceeds 0.55 s")
            except (ValueError, KeyError, TypeError):
                invalid_rows += 1
                continue
            runs[row["A_run"], row["B_run"]].append((ta, tb, a, b))
            offsets.append(abs((ta - tb).total_seconds()))
    episodes = []
    retained_rows = 0
    gap_cuts = 0
    short_segments = 0
    for (a_run, b_run), rows in sorted(runs.items()):
        rows.sort(key=lambda item: item[0])
        segments = []
        part = []
        prior = None
        for item in rows:
            if prior is not None:
                da = (item[0] - prior[0]).total_seconds()
                db = (item[1] - prior[1]).total_seconds()
                if da <= 0 or db <= 0 or da > max_gap_s or (db > max_gap_s):
                    if part:
                        segments.append(part)
                    part = []
                    gap_cuts += 1
            part.append(item)
            prior = item
        if part:
            segments.append(part)
        for segment_id, segment in enumerate(segments):
            count = len(segment) // samples_per_block
            if count < min_blocks:
                short_segments += 1
                continue
            blocks = []
            for k in range(count):
                batch = segment[k * samples_per_block : (k + 1) * samples_per_block]
                blocks.append(
                    Block(
                        sum((x[2] for x in batch)) / samples_per_block,
                        sum((x[3] for x in batch)) / samples_per_block,
                    )
                )
            retained_rows += count * samples_per_block
            episodes.append(
                Episode(
                    region, carrier, a_run[:8], a_run, b_run, segment_id, tuple(blocks)
                )
            )
    offsets.sort()
    audit = {
        "path": str(path),
        "rows": total_rows,
        "invalid_rows": invalid_rows,
        "source_runs": len(runs),
        "episodes": len(episodes),
        "retained_rows": retained_rows,
        "retained_fraction": retained_rows / total_rows if total_rows else 0,
        "gap_cuts": gap_cuts,
        "short_segments": short_segments,
        "pair_offset_p50_s": offsets[len(offsets) // 2] if offsets else None,
        "pair_offset_p95_s": offsets[int(0.95 * (len(offsets) - 1))]
        if offsets
        else None,
    }
    return (episodes, audit)
