# Measured capacity inputs

## Source and local inputs

The reader supports paired Starlink/cellular measurements from
[NUWiNS](https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue),
associated with *Exploring the 5G Digital Divide in the Non-Contiguous US:
LEO Satellites to the Rescue?* ([DOI](https://doi.org/10.1145/3771568)).
Alaska measurements were collected in June 2024 and Maui measurements in
August 2024. Obtain the measurement archives from the original project and
extract them locally.

The loader reads files such as:

```text
alaska_road_test_202406/processed/mpshell/raw_traces/
  fused_trace.tcp_downlink.starlink_att.csv
```

Required CSV fields are `A`, `B`, `A_run`, `B_run`, `A_time`, `B_time`,
`A_throughput_mbps` and `B_throughput_mbps`.

## Process a selected access pair

```bash
satcraft prepare --dataset-root /path/to/nuwins/datasets   --region alaska --carrier att   --samples-per-slot 2 --sample-period-seconds 0.5   --min-slots 8 --output /path/to/processed-traces
```

Choose `alaska` or `hawaii` and a carrier whose paired CSV is present. The
processor groups samples within measured run pairs, validates paired timestamps
and rates, splits at timestamp gaps, and retains segments meeting `--min-slots`.

Each nominal slot averages `--samples-per-slot` samples. Its duration is that
sample count times `--sample-period-seconds`. Mean Mbps times this duration
gives **Mbit per simulator slot**. Configure both values to match the source
sampling cadence. `--max-gap-seconds` controls segment boundaries.

Outputs:

- `traces.json`: paired capacity arrays and region, carrier, run and segment identifiers.
- `manifest.json`: source checksum, processing settings, units and loader statistics.

## Combine capacities with your workload

```python
from satcraft.data.workload import make_case
from satcraft.io import read_json
from satcraft.policies.seed import policy
from satcraft.simulator import replay

trace = read_json("/path/to/processed-traces/traces.json")[0]
horizon = len(trace["rates"])
case = make_case(
    trace["rates"],
    jobs=[{"id": 1, "arrival": 0, "due": horizon,
           "raw": 20.0, "cpu": 2, "ratio": 0.25}],
    services=[{"id": 101, "arrival": 0, "due": horizon,
               "value": 1, "accepts": {"delivered": 1, "quality_min": 0.85}}],
    case_id="measured-workflow", source_id=trace["source_id"],
    cell_budget=40.0, warmup=1, active_slots=8,
)
result, state = replay(case, policy)
```

Deadlines, processing costs and startup in this example are expressed in the
exported trace's slot duration. The [scenario guide](simulator.md) describes
quality-dependent workloads and execution events.

## Attribution and license

**Measurement authors:** Sizhe Wang, Moinak Ghoshal, Yufei Feng, Imran Khan,
Phuc Dinh, Omar Basit, Zhekun Yu, Y. Charlie Hu, and Dimitrios Koutsonikolas.

**Source:** [original measurement repository](https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue).

**Dataset license:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
as specified in the source repository's
[LICENSE-DATA](https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue/blob/main/LICENSE-DATA).
SatCraft's reader aggregates samples into slot capacities and records processing
metadata. Preserve attribution when sharing derived measurements.
