"""Bounded pilot-dataset quality-report capability (PR166).

Audits a dataset already produced by `backend.simulator.dataset.generate`
against its own manifest/spec — structural contract, label integrity,
run-level variation, physical-behavior signatures, raw-threshold
separability, and metadata leakage — and renders `summary.json` +
`quality_report.md` (+ `plots/`, if the `dataset-analysis` optional
dependency is installed). See `docs/dataset-quality-audit.md`.

CLI usage::

    python -m backend.simulator.dataset.audit \\
        --dataset datasets/pem-faults-pilot \\
        --output datasets/pem-faults-pilot-audit

Requires the `dataset` optional dependency group (`pyarrow`); plotting
additionally requires `dataset-analysis` (`pyarrow` + `matplotlib`).
"""

from __future__ import annotations

from backend.simulator.dataset.audit.report import AuditResult, run_audit
from backend.simulator.dataset.audit.verdict import Verdict

__all__ = ["AuditResult", "Verdict", "run_audit"]
