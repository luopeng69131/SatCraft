"""Utility-based shallow-tree fitting and preset-tree relabeling."""

from copy import deepcopy

from .features import FEATURE_NAMES, access_features


def predict(tree, features):
    while "policy" not in tree:
        tree = (
            tree["left"]
            if features[tree["feature"]] <= tree["threshold"]
            else tree["right"]
        )
    return tree["policy"]


def _leaf(rows, names):
    values = {name: sum(row["utility"][name] for row in rows) for name in names}
    name = max(names, key=values.get)
    return {"policy": name, "score": values[name], "runs": len(rows)}


def fit_tree(rows, names, max_depth=3, min_leaf=3):
    if not rows or not names or min_leaf < 1 or max_depth < 0:
        raise ValueError(
            "Tree fitting requires samples, policies, and valid tree constraints"
        )

    def grow(samples, depth):
        best = _leaf(samples, names)
        split, best_gain = None, 1e-8
        if depth >= max_depth or len(samples) < 2 * min_leaf:
            return best
        for feature in range(len(FEATURE_NAMES)):
            values = sorted({row["features"][feature] for row in samples})
            for a, b in zip(values, values[1:]):
                threshold = (a + b) / 2
                left = [row for row in samples if row["features"][feature] <= threshold]
                right = [row for row in samples if row["features"][feature] > threshold]
                if min(len(left), len(right)) < min_leaf:
                    continue
                gain = (
                    _leaf(left, names)["score"]
                    + _leaf(right, names)["score"]
                    - best["score"]
                )
                if gain > best_gain:
                    best_gain, split = gain, (feature, threshold, left, right)
        if split is None:
            return best
        feature, threshold, left, right = split
        return {
            "feature": feature,
            "feature_name": FEATURE_NAMES[feature],
            "threshold": threshold,
            "left": grow(left, depth + 1),
            "right": grow(right, depth + 1),
            "runs": len(samples),
        }

    return grow(rows, 0)


def relabel(tree, rows, names):
    """Keep a preset partition and choose each leaf's policy by utility."""
    if not rows:
        raise ValueError("A preset leaf must contain development samples")
    if "policy" in tree:
        return _leaf(rows, names)
    feature, threshold = tree["feature"], tree["threshold"]
    out = deepcopy(tree)
    out["left"] = relabel(
        tree["left"], [r for r in rows if r["features"][feature] <= threshold], names
    )
    out["right"] = relabel(
        tree["right"], [r for r in rows if r["features"][feature] > threshold], names
    )
    return out


def fit_selector(cases, evaluations, presets=(), max_depth=3, min_leaf=3):
    names = sorted(evaluations)
    if not names or not all(evaluations[n]["valid"] for n in names):
        raise ValueError("Selector fitting requires valid policy evaluations")
    rewards = {
        n: {r["case"]: r["service_value"] for r in evaluations[n]["rows"]}
        for n in names
    }
    groups = {}
    for case in cases:
        groups.setdefault((case["profile"], case["source_id"]), []).append(case)
    samples = {}
    for (profile, source), group in groups.items():
        row = {
            "source": source,
            "features": access_features(group[0]["rates"]),
            "utility": {
                n: sum(rewards[n][c["id"]] for c in group) / len(group) for n in names
            },
        }
        samples.setdefault(profile, []).append(row)
    trees = {}
    for profile, rows in sorted(samples.items()):
        candidates = [fit_tree(rows, names, max_depth, min_leaf)]
        candidates.extend(
            relabel(preset["trees"][profile], rows, names) for preset in presets
        )
        trees[profile] = max(
            candidates,
            key=lambda tree: sum(
                row["utility"][predict(tree, row["features"])] for row in rows
            ),
        )
    return {"calibration_slots": 8, "features": list(FEATURE_NAMES), "trees": trees}
