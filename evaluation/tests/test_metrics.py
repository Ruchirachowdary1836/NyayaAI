import math

import pytest
from evaluation.metrics.retrieval import (
    average_precision,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    retrieval_metrics,
)
from evaluation.statistics import compare_systems, holm_bonferroni


def test_retrieval_metrics_hand_computed_example() -> None:
    ranked = ["a", "x", "b", "c"]
    relevance = {"a": 1, "b": 2}

    assert precision_at_k(ranked, {"a", "b"}, 3) == pytest.approx(2 / 3)
    assert recall_at_k(ranked, {"a", "b"}, 3) == 1
    assert reciprocal_rank(ranked, {"b"}) == pytest.approx(1 / 3)
    assert average_precision(ranked, {"a", "b"}) == pytest.approx((1 + 2 / 3) / 2)
    assert ndcg_at_k(ranked, relevance, 3) == pytest.approx(
        (1 + 3 / math.log2(4)) / (3 + 1 / math.log2(3))
    )
    assert retrieval_metrics(ranked, relevance)["map"] == pytest.approx((1 + 2 / 3) / 2)


def test_statistics_and_holm_adjustment_are_paired_and_reproducible() -> None:
    result = compare_systems([0.1, 0.2, 0.3], [0.2, 0.3, 0.5], seed=10, bootstrap_samples=100)

    assert result["query_count"] == 3
    assert result["mean_difference"] == pytest.approx(0.13333, rel=1e-3)
    assert result["bootstrap_95_ci_low"] <= result["bootstrap_95_ci_high"]
    assert holm_bonferroni([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
