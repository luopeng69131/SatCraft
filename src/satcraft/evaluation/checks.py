"""Check candidate source against the scheduling program interface."""

import ast
import inspect

ALLOWED_IMPORTS = {
    "math",
    "itertools",
    "functools",
    "collections",
    "statistics",
    "copy",
    "heapq",
    "random",
}
FORBIDDEN_NAMES = {
    "open",
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "vars",
    "breakpoint",
    "input",
}


def check_source(source):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name.split(".")[0] not in ALLOWED_IMPORTS for alias in node.names
            ):
                raise ValueError(
                    "Policy imports must use the permitted standard library"
                )
        elif isinstance(node, ast.ImportFrom):
            if (
                node.level
                or not node.module
                or node.module.split(".")[0] not in ALLOWED_IMPORTS
            ):
                raise ValueError(
                    "Policy imports must use the permitted standard library"
                )
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden policy operation: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Dunder attribute access is outside the policy interface")
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "policy"
        for node in tree.body
    ):
        raise ValueError("Define policy(observation, memory) at module scope")
    return tree


def load_policy(source):
    check_source(source)
    namespace = {"__name__": "satcraft_candidate"}
    exec(compile(source, "<satcraft-policy>", "exec"), namespace)
    policy = namespace["policy"]
    inspect.signature(policy).bind({}, {})
    return policy
