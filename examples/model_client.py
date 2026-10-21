"""Adapter skeleton for a model client used by CommandProvider.

Implement generate_policy with your configured LLM client. Standard input is
the repair prompt; standard output carries the JSON proposal. Send client
logging to standard error. See docs/optimization.md for the response schema.
"""

import json
import sys


def generate_policy(prompt):
    raise NotImplementedError(
        "Connect your LLM client and return code, rationale, and usage"
    )


if __name__ == "__main__":
    print(json.dumps(generate_policy(sys.stdin.read())))
