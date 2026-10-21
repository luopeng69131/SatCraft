"""Retain admissible policy snapshots and their full-run evaluation records."""

from pathlib import Path
import re

from satcraft.io import read_json, source_hash, write_json


class PolicyLibrary:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, name, source, evaluation):
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", name):
            raise ValueError("Policy names must be Python identifiers")
        if not evaluation["valid"]:
            raise ValueError("Policy retention requires valid complete executions")
        directory = self.root / name
        if directory.exists():
            raise FileExistsError(f"Policy snapshot already exists: {name}")
        directory.mkdir()
        (directory / "policy.py").write_text(source, encoding="utf-8")
        write_json(directory / "evaluation.json", evaluation)
        write_json(
            directory / "metadata.json",
            {"name": name, "sha256": source_hash(source), "total": evaluation["total"]},
        )

    def entries(self):
        return {
            directory.name: {
                "source": (directory / "policy.py").read_text(),
                "evaluation": read_json(directory / "evaluation.json"),
            }
            for directory in sorted(self.root.iterdir())
            if directory.is_dir() and (directory / "metadata.json").exists()
        }
