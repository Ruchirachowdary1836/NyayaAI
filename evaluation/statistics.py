from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import stats


def compare_systems(
    baseline: Sequence[float],
    proposed: Sequence[float],
    seed: int = 42,
    bootstrap_samples: int = 1000,
) -> dict[str, float | int | None]:
    if len(baseline) != len(proposed) or not baseline:
        raise ValueError("Paired system scores must be non-empty and have equal lengths")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be greater than zero")
    difference = np.asarray(proposed, dtype=float) - np.asarray(baseline, dtype=float)
    if not np.isfinite(difference).all():
        raise ValueError("System scores must be finite numbers")
    rng = np.random.default_rng(seed)
    samples = rng.choice(difference, size=(bootstrap_samples, len(difference)), replace=True).mean(
        axis=1
    )
    t_result = stats.ttest_rel(proposed, baseline)
    try:
        wilcoxon_p = float(stats.wilcoxon(difference).pvalue) if np.any(difference) else 1.0
    except ValueError:
        wilcoxon_p = 1.0
    deviation = float(np.std(difference, ddof=1)) if len(difference) > 1 else 0.0
    return {
        "query_count": len(difference),
        "mean_difference": float(np.mean(difference)),
        "cohens_d": float(np.mean(difference) / deviation) if deviation else 0.0,
        "paired_t_pvalue": float(t_result.pvalue) if np.isfinite(t_result.pvalue) else None,
        "wilcoxon_pvalue": wilcoxon_p,
        "bootstrap_95_ci_low": float(np.quantile(samples, 0.025)),
        "bootstrap_95_ci_high": float(np.quantile(samples, 0.975)),
    }


def holm_bonferroni(pvalues: Sequence[float]) -> list[float]:
    """Return Holm step-down adjusted p-values in their original order."""
    if any(not 0 <= value <= 1 for value in pvalues):
        raise ValueError("p-values must be in [0, 1]")
    ordered = sorted(enumerate(pvalues), key=lambda pair: pair[1])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    for rank, (index, pvalue) in enumerate(ordered):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalue))
        adjusted[index] = running
    return adjusted
