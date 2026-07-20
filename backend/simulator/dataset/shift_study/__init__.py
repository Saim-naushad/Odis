"""PR172 isolated distribution-shift evaluation.

Consumes already-produced PR171 `ood` evaluation output directories (one
per cohort — the combined OOD v1 dataset and four single-dimension
isolated-shift datasets, all scored against the same frozen PR168 model
and PR170 alert policy) and produces one comparative study: per-metric
damage rankings, a minor/moderate/major/catastrophic classification per
shift, an invalid-feature-row rollup, and a combined-vs-isolated
interaction analysis.

This package never recomputes a diagnosis or alert metric itself — every
number here is read from a PR171 `ood_evaluation_summary.json`/
`feature_shift.json`/`error_cases.json` already on disk. See
`docs/isolated-shift-evaluation.md`.
"""

from __future__ import annotations
