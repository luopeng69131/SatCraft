<div align="center">

# SatCraft

### Agentic Optimization of Scheduling Policies for Satellite–Cellular Edge Services

**Turn service-execution feedback into better joint computation and transmission policies.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-16816A)](LICENSE)
[![Checks](https://github.com/luopeng69131/SatCraft/actions/workflows/checks.yml/badge.svg)](https://github.com/luopeng69131/SatCraft/actions/workflows/checks.yml)

**English** · [简体中文](README_zh-CN.md)

[Background](#why-joint-scheduling) · [Method](#how-satcraft-works) · [Quick start](#quick-start) · [Measured data](#work-with-starlink-and-cellular-measurements) · [Code guide](docs/architecture.md)

</div>

## Why joint scheduling?

An inspection vehicle collects observations and sends reports and supporting
evidence to a remote assessment service. Satellite access extends connectivity
across areas with intermittent cellular coverage; local processing can reduce
the amount of data sent over either link. A useful assessment requires the
right products, adequate quality, and delivery before a shared deadline.

These decisions interact. Processing saves transmission capacity but delays
output availability. Activating cellular access too early spends its allowance
while the output is still being computed. Spending the remaining capacity on
current tasks can leave later, more valuable services incomplete. **The
scheduling problem is to coordinate processing modes, computing priorities,
transmission order, and cellular use around complete service delivery.**

<p align="center">
  <img src="docs/assets/background.png" width="960" alt="Inspection services share local computation, satellite access, and intermittent cellular access under quality, deadline, and resource constraints.">
</p>

SatCraft uses a **large language model (LLM) agent** to revise the executable
scheduling logic from complete-run feedback. It retains valid policies and
learns when to select them from initial access observations and known resource
conditions. This connects policy-code improvements to the quality and
timeliness of delivered services.

## How SatCraft works

<p align="center">
  <img src="docs/assets/framework.png" width="960" alt="SatCraft optimizes and checks policies offline, fits a context-dependent selector, and deploys the selected policy for joint scheduling.">
</p>

1. **Revise policy code.** Give the LLM agent the scheduling interface, an
   existing policy, a repair direction, and execution feedback.
2. **Evaluate complete services.** Check candidate source and replay each
   scenario, recording completed-service value, resource use, runtime, and
   execution events.
3. **Build a policy library.** Retain candidates that satisfy validity and
   execution budgets, including alternatives useful under different conditions.
4. **Select and execute.** Fit shallow utility-based trees using initial access
   features. Select one policy for an episode, then update its joint actions
   and memory as tasks progress and quality is revealed.

**Explore the implementation:** [repair loop](src/satcraft/agent/optimize.py) ·
[prompt templates](src/satcraft/agent/prompts/initial.md) ·
[full-run evaluation](src/satcraft/evaluation/replay.py) ·
[policy selector](src/satcraft/selection/tree.py) ·
[20 frozen policies](src/satcraft/policies/library)

## Quick start

**Requirements:** Linux and Python 3.10+. The scheduling and data-processing
package uses the Python standard library.

```bash
git clone https://github.com/luopeng69131/SatCraft.git
cd SatCraft
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
satcraft demo
```

The demo generates access sequences and dependent service workloads, then runs
the frozen SatCraft policy across four resource configurations. Results are
written to `outputs/demo/evaluation.json`.

A minimal Python entry point:

```python
from satcraft.data.workload import demo_cases
from satcraft.evaluation.replay import replay
from satcraft.policies.deployment import frozen_policy

result, state = replay(demo_cases()[0], frozen_policy())
print(result["service_value"], result["max_service_value"])
```

To replay a supplied candidate through checks, complete-run feedback, policy
retention, selector fitting, and deployment export:

```bash
satcraft demo --repair-demo --output outputs/repair-demo
```

### Connect an LLM agent

The optimizer exposes a `CandidateProvider` interface. `CommandProvider` sends
the repair prompt to a configured model client and receives policy code,
a rationale, and model-usage records as JSON. Implement the client in
[examples/model_client.py](examples/model_client.py), then point
[the provider configuration](configs/llm_command.example.json) to it.

```bash
satcraft optimize \
  --cases /path/to/processed/development.json \
  --seed-policy src/satcraft/policies/seed.py \
  --provider-config /path/to/llm_command.json \
  --submissions 6 \
  --output outputs/policy-repair
```

[Optimization guide →](docs/optimization.md)

## Work with Starlink and cellular measurements

SatCraft processes synchronized access measurements released by the
[NUWiNS measurement project](https://github.com/NUWiNS/sigmetrics26-exploring-the-5g-digital-divide-in-the-non-contiguous-us-leo-satellites-to-the-rescue),
associated with *Exploring the 5G Digital Divide in the Non-Contiguous US:
LEO Satellites to the Rescue?* ([ACM](https://doi.org/10.1145/3771568)).

| Measurement campaign | Collection period | Access pairs used by SatCraft |
| --- | --- | --- |
| Alaska road tests | June 2024 | Starlink + AT&T / Verizon |
| Maui, Hawaii road tests | August 2024 | Starlink + AT&T / Verizon |

Download the processed archives from the original project and extract them
under a local dataset directory. The pipeline reads paired throughput samples,
preserves run and gap boundaries, aggregates nominal one-second slots, and
generates computing tasks and quality-dependent service contracts.

```bash
satcraft prepare \
  --dataset-root /path/to/nuwins/datasets \
  --source-manifest configs/measurement_sources.json \
  --output /path/to/processed

satcraft evaluate \
  --cases /path/to/processed/test.json \
  --output outputs/test-results.json
```

The source index identifies 60 measured runs. Processing creates 360
development cases, 240 validation cases, and 360 test cases. Measured
downlink throughput supplies the exogenous link-capacity sequences; the
workload generator supplies computing demands, service dependencies, and
processed-result quality. The initial eight slots provide the observations
used for policy selection.

**Dataset attribution:** the measurements are released by Sizhe Wang and
coauthors under **CC BY 4.0**. Source links, authors, input fields, and processing
steps are documented in the [data guide](docs/data.md).

## Results at a glance

In the reported trace-driven experiment, SatCraft achieves the highest
cumulative completed-service value across the evaluated baselines, with
gains of **3.61%–16.89%**. The test set contains 360 cases with changing
Starlink and cellular access and four resource configurations.

<p align="center">
  <img src="docs/assets/performance.png" width="600" alt="Completed-service value comparison across EDF, Rolling, ADPRL, EdgeOPT, TF-DDRL, and SatCraft.">
</p>

| Method | Completed-service value ↑ |
| --- | ---: |
| EDF | 22,848 |
| Rolling | 22,800 |
| ADPRL | 20,251 |
| EdgeOPT | 21,244 |
| TF-DDRL | 22,496 |
| **SatCraft** | **23,672** |

Values are rounded to integers; learned-policy results average the evaluated
training seeds. See [the results summary](docs/results.md) for the metric
definition and evaluation configuration.

## Code map

| Module | Purpose |
| --- | --- |
| [`agent/`](src/satcraft/agent) | Bounded policy repair, prompts, model-client interface, usage ledger |
| [`evaluation/`](src/satcraft/evaluation) | Source checks, complete executions, feedback and runtime budgets |
| [`policies/`](src/satcraft/policies) | Policy library, frozen policies, episode-level selection and execution |
| [`selection/`](src/satcraft/selection) | Initial access features and utility-based tree fitting |
| [`environment/`](src/satcraft/environment) | Computing, dual-access transmission, dependencies and service acceptance |
| [`data/`](src/satcraft/data) | Measurement loading, source selection and workload generation |

## Extend SatCraft

- **Add a workload:** define product dependencies, quality conditions, deadlines,
  and service values through the case schema.
- **Add a policy:** implement `policy(observation, memory)` and evaluate complete
  service outcomes using `satcraft evaluate --policy path/to/policy.py`.
- **Add a model client:** implement `CandidateProvider.propose` or connect a
  command through `CommandProvider`.

[Architecture](docs/architecture.md) · [Data processing](docs/data.md) ·
[Policy optimization](docs/optimization.md)

## License and acknowledgments

SatCraft code is released under the [MIT License](LICENSE). The linked NUWiNS
measurements carry their original **CC BY 4.0** license and attribution;
see [data attribution](docs/data.md#attribution-and-license).
We thank the measurement authors for making their traces available to the community.
