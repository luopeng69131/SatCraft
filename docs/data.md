# Measurement data and processing

[English README](../README.md) · [中文 README](../README_zh-CN.md)

## Source

SatCraft uses paired Starlink/cellular access measurements from the
[NUWiNS release](https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue):
*Exploring the 5G Digital Divide in the Non-Contiguous US: LEO Satellites to
the Rescue?*, SIGMETRICS 2026, [DOI: 10.1145/3771568](https://doi.org/10.1145/3771568).

| Campaign | Collection | Paired measurements |
| --- | --- | --- |
| Alaska | June 2024 | Starlink/AT&T, Starlink/Verizon |
| Maui, Hawaii | August 2024 | Starlink/AT&T, Starlink/Verizon |

The original release provides aligned throughput observations. SatCraft
reads these observations as exogenous access-capacity sequences and combines
them with generated service workloads.

## Download from the measurement authors

Choose a local storage location for the original release:

```bash
export SATCRAFT_DATA_HOME=/path/to/measurement-storage
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone \
  https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue.git \
  "$SATCRAFT_DATA_HOME/nuwins"
git -C "$SATCRAFT_DATA_HOME/nuwins" lfs pull \
  --include="datasets/alaska_road_test_202406.processed.tar.gz,datasets/hawaii_road_test_202408.processed.tar.gz"
tar -xzf "$SATCRAFT_DATA_HOME/nuwins/datasets/alaska_road_test_202406.processed.tar.gz" \
  -C "$SATCRAFT_DATA_HOME/nuwins/datasets"
tar -xzf "$SATCRAFT_DATA_HOME/nuwins/datasets/hawaii_road_test_202408.processed.tar.gz" \
  -C "$SATCRAFT_DATA_HOME/nuwins/datasets"
```

The reader expects:

```text
datasets/
  alaska_road_test_202406/processed/mpshell/raw_traces/
    fused_trace.tcp_downlink.starlink_att.csv
    fused_trace.tcp_downlink.starlink_verizon.csv
  hawaii_road_test_202408/processed/mpshell/raw_traces/
    fused_trace.tcp_downlink.starlink_att.csv
    fused_trace.tcp_downlink.starlink_verizon.csv
```

Required CSV fields are `A`, `B`, `A_run`, `B_run`, `A_time`, `B_time`,
`A_throughput_mbps`, and `B_throughput_mbps`. `A` denotes Starlink; `B`
identifies the paired carrier. Timestamps retain their timezone information.

## Processing stages

1. **Validate pairs.** Require finite nonnegative rates, matching operator
   labels, and timestamp offsets of at most 0.55 seconds.
2. **Preserve boundaries.** Group by both measurement run IDs. Split a segment
   when either timestamp stops increasing or advances by more than one second.
3. **Aggregate access slots.** Average successive pairs of approximately
   500-ms samples into nominal one-second slots. Retain segments with at least
   119 slots and initial eight-slot mean Starlink capacity of at least 1 Mbps.
4. **Locate measured sources.** The source index specifies region, carrier,
   both run IDs, segment, split, and a source identifier. Development and test
   sources have distinct Starlink run IDs within each region.
5. **Generate services.** Use the first eight observed slots to set the
   capacity reference. Release six batches at slots 8, 24, 40, 56, 72, and 88.
   Each batch contains four product tasks and two service contracts.
6. **Create resource and quality variants.** Expand each measured source over
   the four resource profiles and the quality seeds for its split.

The nominal one-second replay maps each numerical rate in Mbps to the Mbit
available in a slot. The input measurements are downlink throughput; the
service model uses the resulting capacity sequence to study joint scheduling.
Computing demands, processing ratios, deadlines, and quality outcomes are
produced by [the workload generator](../src/satcraft/data/workload.py).

## Build the configured splits

From the SatCraft project directory:

```bash
satcraft prepare \
  --dataset-root "$SATCRAFT_DATA_HOME/nuwins/datasets" \
  --source-manifest configs/measurement_sources.json \
  --output "$SATCRAFT_DATA_HOME/satcraft-processed"
```

| Split | Measured sources | Resource profiles | Quality seeds | Cases | Use |
| --- | ---: | ---: | --- | ---: | --- |
| Development | 30 | 4 | 1701–1703 | 360 | Policy optimization and selector fitting |
| Validation | Development sources | 4 | 1711–1712 | 240 | Evaluation under new quality realizations |
| Test | 30 other sources | 4 | 1721–1723 | 360 | Comparison across measured access traces |

[configs/measurement_sources.json](../configs/measurement_sources.json)
contains source locators. The processor writes the generated cases and input
checksums to the selected output directory. Omitting `--source-manifest` selects
eligible runs by deterministic SHA ordering; `--runs-per-region` controls the
size of those newly selected splits.

## Resource profiles

| Profile | Load multiplier | Computing multiplier | Cellular startup | Activation allowance |
| --- | ---: | ---: | ---: | ---: |
| Balanced | 1.25 | 1.0 | 2 slots | 60 slots |
| Network pressure | 1.75 | 1.0 | 2 slots | 60 slots |
| Computing pressure | 1.25 | 1.4 | 2 slots | 60 slots |
| Cellular activation pressure | 1.25 | 1.0 | 4 slots | 45 slots |

Cellular sending allowance equals eight times the initial Starlink reference
capacity. Each episode has one computing processor. Processing can reduce
transmission volume; the resulting quality is revealed when the product is
delivered. Product dependencies and service acceptance determine which
supplementary work becomes useful.

## Generated case fields

| Field | Meaning |
| --- | --- |
| `rates` | `[Starlink, cellular]` capacities for each slot |
| `jobs` | Product sizes, processing requirements, deadlines, dependencies and quality support |
| `services` | Product-acceptance predicates, deadlines and service values |
| `compression_outcomes` | Realized processing quality, accessed by the environment on delivery |
| `cell_budget`, `warmup`, `active_slots` | Cellular sending and activation constraints |
| `source_id`, `profile`, `quality_seed` | Grouping and evaluation metadata |

## Attribution and license

**Measurement authors:** Sizhe Wang, Moinak Ghoshal, Yufei Feng, Imran Khan,
Phuc Dinh, Omar Basit, Zhekun Yu, Y. Charlie Hu, and Dimitrios Koutsonikolas.

**Source:** [original measurement repository](https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue).

**Dataset license:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/),
as specified in the source repository's
[LICENSE-DATA](https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue/blob/main/LICENSE-DATA).
The source index in this project identifies selected records from that release.
SatCraft's processing aggregates samples into slots, selects contiguous
segments, and combines these capacities with generated workloads. Preserve
attribution to the measurement authors when sharing derived measurements.
