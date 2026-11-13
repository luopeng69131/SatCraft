# Satellite–cellular service simulator

The simulator advances local computation and dual-access transmission in slots.
Product deliveries reveal quality, update dependencies, and complete service
contracts. Its inputs are capacities and user-defined service workloads.

## Run a complete scenario

```python
from satcraft.data.workload import demo_cases
from satcraft.policies.seed import policy
from satcraft.simulator import replay

scenario = demo_cases()[0]
result, state = replay(scenario, policy, log=True)
print(result["service_value"], result["services_completed"])
print(result["cell_mbit"], result["active_used"], result["cpu_used"])
print(state.records[-1])
```

Use `frozen_policy()` from `satcraft.policies.deployment` to run the bundled
SatCraft policy library. The synthetic demo uses its `balanced` input profile.
The bundled selector recognizes `balanced`, `network_pressure`, `cpu_pressure`
and `radio_pressure`. A new profile can use a supplied policy or a selector
constructed through the method interface.

## Define your own service workflow

```python
from satcraft.data.workload import make_case
from satcraft.policies.seed import policy
from satcraft.simulator import replay

case = make_case(
    rates=[[12.0, 5.0] for _ in range(20)],
    jobs=[{
        "id": 1, "arrival": 0, "due": 15,
        "raw": 60.0, "cpu": 2, "ratio": 0.25,
        "quality_support": [{"quality": 0.95, "probability": 1.0}],
    }],
    services=[{
        "id": 101, "arrival": 0, "due": 15, "value": 8,
        "accepts": {"delivered": 1, "quality_min": 0.85},
    }],
    case_id="my-workflow", cell_budget=20.0, warmup=1,
    active_slots=8, quality_seed=42,
)
result, state = replay(case, policy, log=True)
```

`rates[t]` contains the satellite and cellular **Mbit available in slot t**.
Product `raw` sizes and cellular `cell_budget` also use Mbit. Processing demand
`cpu`, startup `warmup`, deadlines and activation allowance use slots. For
measured Mbps, multiply by the chosen slot duration before simulation.

`make_case` accepts arbitrary scenario lengths and samples processed quality
from each product's `quality_support`. These outcomes live in the environment;
the policy observes delivered quality through receipts.

### Dependencies and acceptance

Both product `requires` and service `accepts` use the same predicate grammar:

```python
{"delivered": 1, "quality_min": 0.85}
{"delivered": 1, "quality_max": 0.8}
{"all": [{"delivered": 1}, {"delivered": 2}]}
{"any": [{"delivered": 1, "quality_min": 0.85}, {"delivered": 3}]}
```

A product becomes ready when it has arrived and its dependencies hold. A
service contributes its value once its acceptance predicate holds by its
deadline. This can express reports plus usable evidence and conditional
supplementary work after a low-quality delivery.

## Step through the environment

```python
from satcraft.simulator import State

state, memory = State(case), {}
while state.t < len(case["rates"]):
    observation = state.observe()
    action = policy(observation, memory)
    state.step(action, log=True)
print(state.result())
```

The step-wise interface exposes simulator transitions directly. `replay`
additionally provides policy isolation through copied observations, resource
context, callback budgets, episode budgets and validity feedback.

## Observation and action

An observation contains arrived products and progress, active services,
delivery receipts, past capacities, remaining traffic allowance, cellular
startup state and activation allowance. Full-run replay also supplies
`context.resource_profile` for policy selection.

```python
def policy(observation, memory):
    return {
        "modes": {task_id: "raw"},  # or "compress" for a ready undecided product
        "cpu_job": None,            # or one processing product ID
        "net_order": [],            # shared transmission-queue order
        "cell_enabled": False,
        "cell_cap": 0.0,            # Mbit cap for this slot
    }
```

See the runnable [starter policy](../src/satcraft/policies/seed.py).

## Transition semantics

1. Admit arrivals, expire overdue work, and determine ready products.
2. Apply processing modes and advance at most one computing task.
3. Advance cellular startup and charge active-slot usage.
4. Serve ready outputs with satellite capacity, then usable cellular capacity.
5. Reveal qualities of full deliveries and check service acceptance.
6. Make newly computed outputs available for the following slot.

A selected mode persists for the lifetime of the product. Partial uploads
consume capacity; full delivery creates a receipt. Cellular startup consumes
active-slot allowance, and actual transmitted bytes consume the traffic
budget. A delivery recorded exactly at a service deadline can complete it.

## Outputs and execution budgets

`replay` returns `(result, state)`. Results include validity, completed value,
services completed, computing slots, cellular Mbit, activation usage and policy
execution times. `log=True` retains observations, actions, realized capacities,
resource use and service-completion events in `state.records`.

```python
from satcraft.simulator import RuntimeLimits, replay

result, state = replay(case, policy, limits=RuntimeLimits(
    callback_seconds=1.0, episode_seconds=30.0,
))
```

Use `satcraft simulate --cases scenarios.json --policy policy.py --trace` for
the command-line entry point. JSON scenario files contain a list of cases.

[Architecture](architecture.md) · [Measurement processing](data.md) ·
[Policy construction](optimization.md)
