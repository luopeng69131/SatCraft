# Completed-service results

## Metric

A service contributes its value when its product deliveries satisfy its quality
and acceptance conditions by its deadline. Cumulative completed-service value
sums this quantity over an evaluated set:

$$V = \sum_{n \in \mathcal{D}} \sum_{s \in \mathcal{S}_n} v_s \; \mathbf{1}\{s \text{ is completed on time with acceptable quality}\}.$$

## Configuration

The reported test comparison uses 30 measured access traces, four resource
configurations, and three quality realizations per trace–configuration pair,
yielding 360 cases. Each case has 119 slots, 24 product tasks, and 12 services.
Policy selection uses eight initial observed slots; the first task batch
arrives at slot eight. The packaged frozen deployment consists of a policy
selector and the 20 policies it references.

## Aggregate comparison

| Method | Completed-service value | SatCraft gain |
| --- | ---: | ---: |
| EDF | 22,848 | 3.61% |
| Rolling | 22,800 | 3.82% |
| ADPRL | 20,251 | 16.89% |
| EdgeOPT | 21,244 | 11.43% |
| TF-DDRL | 22,496 | 5.23% |
| **SatCraft** | **23,672** | — |

Values are rounded to integers. ADPRL and TF-DDRL aggregate the evaluated
training seeds. The gains use the unrounded aggregate values. Baseline
algorithms were adapted to the shared joint scheduling interface and evaluated
on the same service cases.

<img src="assets/performance.png" width="650" alt="Overall completed-service value comparison">

These results connect improved scheduling logic to complete service delivery
under varying measured access and resource constraints. The quick-start demo
generates illustrative cases for exploring execution; the measurement pipeline
rebuilds the configured evaluation cases from the original public data source.
