"""Connect the optimization loop to an LLM client or a supplied candidate."""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Proposal:
    code: str
    rationale: str = ""
    usage: dict = field(default_factory=dict)


class CandidateProvider(Protocol):
    def propose(self, prompt: str) -> Proposal: ...


class CommandProvider:
    """Send a prompt to an external model client through standard input.

    The client returns JSON containing code, rationale, and optional usage.
    Credentials and model selection are configured by the client.
    """

    def __init__(self, command, timeout_seconds=900):
        if not command or not all(isinstance(arg, str) for arg in command):
            raise ValueError("Provide a command as a nonempty list of strings")
        self.command, self.timeout_seconds = command, timeout_seconds

    def propose(self, prompt):
        result = subprocess.run(
            self.command,
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
            timeout=self.timeout_seconds,
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload.get("code"), str):
            raise ValueError(
                "The LLM client must return a JSON object with a code string"
            )
        return Proposal(
            payload["code"], payload.get("rationale", ""), payload.get("usage", {})
        )


class FileCandidateProvider:
    """Replay supplied source candidates through the optimization workflow."""

    def __init__(self, paths):
        self.paths = iter(Path(path) for path in paths)

    def propose(self, prompt):
        return Proposal(
            next(self.paths).read_text(), "Replay of a supplied policy candidate"
        )
