"""Bridge from confirmed ML fault-alert events into deterministic ODIS
reasoning (PR178).

A confirmed ML alert is evidence, never authority: this package validates
`fault_alert_transition.v1` events, deterministically corroborates the
diagnosed fault against observable telemetry, and — only when corroboration
supports it — produces a bounded, traceable operator recommendation. It
never invokes `src.application.reasoning_session.ReasoningSession` (that
7-stage pipeline is hard-wired to `Sequence[Observation]` with no evidence
extension point — see `docs/reasoning-bridge.md`'s "Reasoning bridge
architecture" section for the audit that established this) and it never
lets the model construct an `Action` or final recommendation directly.

Non-goals: dashboard UI, new model work, retraining, autonomous control,
actuator commands. See `docs/reasoning-bridge.md`.
"""
