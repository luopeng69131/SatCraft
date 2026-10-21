# Policy optimization

SatCraft improves scheduling programs through bounded revisions evaluated on
complete service executions. Its model-client interface lets a developer
connect an LLM agent to the same policy checks, replay environment, policy
library, and selector fitting.

## 1. Prepare development cases

Follow the [data guide](data.md), or generate an illustrative case set:

```bash
satcraft demo --output outputs/example
```

## 2. Connect a model client

A provider implements:

```python
from satcraft.agent.providers import Proposal

class MyProvider:
    def propose(self, prompt: str) -> Proposal:
        response = my_model_client.generate(prompt)
        return Proposal(
            code=response.policy_source,
            rationale=response.rationale,
            usage=response.usage,
        )
```

For a command-line client, `CommandProvider` sends the prompt to standard
input. The client's standard output is a JSON object:

```json
{
  "code": "def policy(observation, memory):\n    ...\n",
  "rationale": "Coordinate cellular startup with the next ready output.",
  "usage": {
    "model": "configured-model-name",
    "input_tokens": 1234,
    "output_tokens": 567
  }
}
```

Token counts above illustrate the response schema. The client supplies its
actual model-usage fields. Model configuration and authentication remain in
the client environment. Client logs go to standard error.

Start from [examples/model_client.py](../examples/model_client.py) and create
a configuration that points to the implemented client:

```json
{
  "command": ["python", "examples/model_client.py"],
  "timeout_seconds": 900
}
```

## 3. Run bounded optimization

```bash
satcraft optimize \
  --cases /path/to/processed/development.json \
  --seed-policy src/satcraft/policies/seed.py \
  --provider-config /path/to/llm_command.json \
  --direction "Align cellular activation with processing outputs and reserve capacity for later services." \
  --submissions 6 \
  --output outputs/repair-01
```

Each run uses a fresh output directory. The default execution limits are
two seconds per callback and 90 seconds per episode. In Python, pass
`RuntimeLimits` to `optimize` to configure those budgets.

The [initial prompt](../src/satcraft/agent/prompts/initial.md) specifies the
objective, observation/action interface, timing semantics, repair direction,
current source, and remaining budget. The
[continuation prompt](../src/satcraft/agent/prompts/continuation.md) incorporates
the next execution feedback. Feedback includes validity, completed-service
value, resource use, runtime, and selected execution events. Full results and
traces remain in the run directory for further diagnosis.

## 4. Inspect and reuse the exported deployment

```text
repair-01/
  seed_evaluation.json
  ledger.json
  attempts/candidate_01/
    prompt.md
    policy.py
    evaluation.json
  library/
    seed/
    candidate_01/
  deployment/
    selector.json
    policies/
  deployment_evaluation.json
```

`ledger.json` records proposal usage and candidate outcomes. Valid alternatives
enter the library even when their aggregate utility is lower, allowing the
selector to exploit conditions where they work well. Selector fitting uses
the development cases; evaluation on validation or test cases executes the
exported selector and policy code.

```bash
satcraft evaluate \
  --policy outputs/repair-01/deployment \
  --cases /path/to/processed/test.json \
  --output outputs/repaired-test.json
```

Supply a preset tree through `--preset-selector path/to/selector.json` to
include leaf relabeling alongside fresh tree fitting.

## Replay supplied candidates

`FileCandidateProvider` replays existing candidate source files through the
evaluation and retention workflow. This is useful for studying a code change
or testing a model-client integration:

```bash
satcraft optimize \
  --cases outputs/example/cases.json \
  --seed-policy src/satcraft/policies/seed.py \
  --candidate src/satcraft/policies/library/policy_04.py \
  --submissions 1 \
  --output outputs/candidate-replay
```

The original policy development used a GPT-6.1-sol LLM agent in OpenAI Codex
with extra-high reasoning effort. The public orchestration interface exposes
candidate submission and execution feedback for connection to a configured
model client.
