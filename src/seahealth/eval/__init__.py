"""Naomi gold-eval harness for the extractor + validator pipeline.

Public API:

- :func:`run_eval.main` — score predictions against Naomi's CSV.
- :class:`metrics.BinaryMetrics`, :func:`metrics.compute_capability_metrics`,
  :func:`metrics.compute_contradiction_metrics`.
- :func:`naomi_mapping.map_capability`, :func:`naomi_mapping.map_contradiction`,
  :func:`naomi_mapping.is_contradiction_label`.
"""
from seahealth.eval.metrics import (
    BinaryMetrics,
    compute_capability_metrics,
    compute_contradiction_metrics,
)
from seahealth.eval.naomi_mapping import (
    NAOMI_CAPABILITY_MAP,
    NAOMI_CONTRADICTION_TYPE_MAP,
    UNMAPPED_CAPABILITY_VALUES,
    UNMAPPED_CONTRADICTION_VALUES,
    is_contradiction_label,
    map_capability,
    map_contradiction,
)
from seahealth.eval.run_eval import main as run_eval_main

__all__ = [
    "BinaryMetrics",
    "NAOMI_CAPABILITY_MAP",
    "NAOMI_CONTRADICTION_TYPE_MAP",
    "UNMAPPED_CAPABILITY_VALUES",
    "UNMAPPED_CONTRADICTION_VALUES",
    "compute_capability_metrics",
    "compute_contradiction_metrics",
    "is_contradiction_label",
    "map_capability",
    "map_contradiction",
    "run_eval_main",
]
