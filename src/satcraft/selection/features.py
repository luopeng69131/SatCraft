"""Access features computed from the eight initial observations."""

import math

FEATURE_NAMES = (
    "star_mean",
    "cell_mean",
    "cell_star_ratio",
    "star_cv",
    "cell_cv",
    "star_trend",
    "cell_trend",
    "star_zero_fraction",
    "cell_zero_fraction",
    "star_last_mean_ratio",
    "cell_last_mean_ratio",
)


def access_features(rates):
    if len(rates) < 8:
        raise ValueError("Policy selection requires eight observed access slots")
    star = [r[0] for r in rates[:8]]
    cell = [r[1] for r in rates[:8]]
    sm, cm = sum(star) / 8, sum(cell) / 8

    def cv(values, mean):
        return math.sqrt(sum((x - mean) ** 2 for x in values) / 8) / max(mean, 1e-8)

    def trend(values, mean):
        return (sum(values[-3:]) / 3 - sum(values[:3]) / 3) / max(mean, 1e-8)

    return [
        sm,
        cm,
        cm / max(sm, 1e-8),
        cv(star, sm),
        cv(cell, cm),
        trend(star, sm),
        trend(cell, cm),
        sum(x <= 1e-8 for x in star) / 8,
        sum(x <= 1e-8 for x in cell) / 8,
        star[-1] / max(sm, 1e-8),
        cell[-1] / max(cm, 1e-8),
    ]
