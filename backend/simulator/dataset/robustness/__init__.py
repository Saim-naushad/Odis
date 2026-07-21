"""PR174 robustness-training comparison: original PR168 model vs. a
candidate trained on a broader operating distribution.

This package never fits, refits, calibrates, or retunes anything of its
own — both models it compares are frozen artifacts already produced by the
existing `models` CLI, scored through the existing PR171 `ood` package's
diagnosis/alert/availability metric functions, and evaluated under the
unchanged PR170 alert-policy configuration (see `config.FROZEN_ALERT_POLICY`).
Its only new logic is the original-vs-robust comparison and promotion
decision, both of which never touch the pilot's or candidate's training
data itself. See `docs/robustness-training.md` for the full rationale.
"""

from __future__ import annotations
