# Architecture and code guide

## The service workflow

SatCraft schedules product tasks on a mobile node with one computing processor
and satellite/cellular access. A product can be transmitted in its original
form or processed locally into a smaller output. Dependencies gate execution;
delivered quality determines service acceptance and the usefulness of
supplementary work. The objective is the value of complete services delivered
with acceptable quality by their deadlines.

<img src="assets/background.png" width="960" alt="The joint scheduling scenario">

## Offline optimization

[`agent/optimize.py`](../src/satcraft/agent/optimize.py) connects the main steps:

```python
proposal = provider.propose(prompt)
evaluation = evaluate_source(cases, proposal.code, limits, log=True)
if evaluation["valid"]:
    library.add(name, proposal.code, evaluation)
feedback = feedback_summary(evaluation)
```

A submission snapshots the candidate source. Source checks validate permitted
imports and the policy interface; complete executions then check actions,
dependencies, resource use, and runtime. Every attempted submission has a
record. Every admissible submission enters the policy library. The working
source advances when a valid candidate improves aggregate utility, while
retained alternatives remain available to the selector.

[`selection/tree.py`](../src/satcraft/selection/tree.py) groups quality
realizations by measured source and resource profile. It learns shallow trees
whose leaves select the policy with the greatest sum of development utility.
It can also relabel supplied preset trees and choose the best resulting tree.
Default constraints are depth three and at least three measured sources per
leaf. The optimizer exports the selector and policy sources into a deployment
directory and evaluates that combined system over complete episodes.

## Online execution

[`policies/deployment.py`](../src/satcraft/policies/deployment.py) implements
episode-level policy selection. At slot eight, it extracts 11 features from
the first eight observed access slots: both means, their ratio, variation,
trends, zero-capacity fractions, and last-to-mean ratios. A tree associated
with the known resource profile selects one policy. The policy computes
actions and updates its own episode memory at each subsequent slot.

The packaged deployment contains the 20 policies referenced by the frozen
selector. Their transition behavior follows the original evaluated policy
sources. Each policy is a separate module under
[`policies/library/`](../src/satcraft/policies/library); the selector is stored
in [`selector.json`](../src/satcraft/policies/selector.json).

## Observation and action interface

| Observation | Content |
| --- | --- |
| `t`, `horizon` | Current slot and episode length |
| `jobs` | Arrived, unexpired products and their computing/transmission progress |
| `services` | Active, incomplete service contracts |
| `receipts` | Delivered products and revealed quality |
| `past_rates` | Up to eight completed slots of observed access capacity |
| `cell_budget` | Remaining cellular sending allowance |
| `radio` | Mode, startup delay, and remaining activation allowance |
| `context.resource_profile` | Known resource configuration |

A policy implements `policy(observation, memory)` and returns:

```python
{
    "modes": {task_id: "raw"},    # or "compress", for undecided ready tasks
    "cpu_job": None,              # or one ready computing task ID
    "net_order": [],              # shared transmission-queue priorities
    "cell_enabled": False,
    "cell_cap": 0.0,              # Mbit cellular sending cap this slot
}
```

`memory` is an episode-local dictionary updated by the policy. The
[starting policy](../src/satcraft/policies/seed.py) illustrates this interface.

## Transition order

The environment selects modes and advances one computing task, applies cellular
activation and startup, and serves the transmission queue with the realized
satellite and available cellular capacities. An output computed in a slot
becomes eligible for transmission in the following slot. Deliveries reveal
quality and trigger service acceptance. A service completed at its deadline
contributes its value.

[`environment/physics.py`](../src/satcraft/environment/physics.py) implements
computing, radio, and transmission transitions;
[`environment/service.py`](../src/satcraft/environment/service.py) adds
delivered-product predicates and service-completion accounting.

## Main entry points

```text
src/satcraft/
  agent/          candidate providers, prompts, bounded repair loop
  evaluation/     source checks, runtime budgets, full-run feedback
  policies/       policy snapshots, frozen library, deployment execution
  selection/      access features, utility-based trees
  environment/    physical transitions and service acceptance
  data/           paired measurement reader and workload generator
  cli.py          demo, prepare, evaluate, optimize
```
