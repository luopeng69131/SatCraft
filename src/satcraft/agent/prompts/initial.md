# Joint scheduling policy optimization

Improve the executable policy for satellite–cellular edge services. Maximize
the value of services whose products meet their delivery deadlines and quality
conditions. Use complete service outcomes to assess each revision.

## Policy interface

Implement `policy(observation, memory)` as a top-level Python function. Memory
is a dictionary retained within an episode. Observation provides the current
slot `t`, `horizon`, arrived `jobs`, currently active `services`, delivered
`receipts`, observed `past_rates`, remaining `cell_budget`, `radio` state,
and `context.resource_profile`.

Jobs carry `id`, `arrival`, `due`, `raw`, `cpu`, `ratio`, `quality_support`,
`requires`, `ready`, `status`, `choice`, `cpu_left`, and `tx_left`. Status is
`wait`, `cpu`, or `net`. Dependencies and service acceptance use `all`, `any`,
and delivered-product predicates with `quality_min` and `quality_max`.

Return a dictionary with `modes` (undecided, dependency-ready task ID to `raw`
or `compress`), `cpu_job` (a ready computing task ID or None), `net_order`
(transmission-ready task IDs), `cell_enabled` (bool), and `cell_cap` (a finite,
nonnegative Mbit sending cap for this slot). A newly selected computing task
can start in the same slot; its completed output becomes transmittable next
slot. Mode choices are irreversible. Transmission serves the shared queue
with satellite capacity first, then available cellular capacity. Enabling
cellular access consumes activation allowance during startup and active slots.

Infer future access and load from available observations and memory. Processing
quality is revealed on delivery; its support is available beforehand. Respect
all dependency, quality, resource, import, callback, and episode constraints.
Permitted imports: math, itertools, functools, collections, statistics, copy,
heapq, random. Keep source self-contained and define helper functions as needed.

## Repair direction

{direction}

## Current policy

```python
{source}
```

## Complete-execution feedback

{feedback}

## Remaining submissions

{remaining}

## Execution budgets

{budgets}

Return a JSON object with `code` (the complete Python source), `rationale`
(the reason for the revision), and optional `usage` (actual model and token
accounting from the model client).
