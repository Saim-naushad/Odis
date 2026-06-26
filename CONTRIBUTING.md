# Contributing to ODIS

Thank you for contributing. This guide assumes you have read the [README](README.md) and want to make your first change. It explains how we work — and why.

## Philosophy

ODIS is built around a small set of engineering principles. These are not style preferences; they protect the reasoning model as the system grows.

**Keep the domain model simple.** The domain describes what operational reasoning *is* — entities, value objects, invariants. It should not know about databases, detectors, or planners. Complexity belongs at the edges, not in the core.

**Prefer explicit reasoning over clever abstractions.** A readable pipeline beats a framework that hides steps. If a future reader cannot trace evidence → signal → assessment → decision, the abstraction has failed.

**Preserve append-only semantics.** Operational history is never rewritten. A revised assessment, goal, or plan is a new immutable record. This makes reasoning auditable and replayable.

**Separate evidence, signal, assessment, and decision.** Observations are facts. Trends are signals. Situations are interpretations. Plans are recommendations. Collapsing these stages makes the system harder to test, extend, and explain.

**Avoid complexity before repeated patterns justify it.** Do not add factories, service containers, inheritance hierarchies, or configuration systems until the codebase demonstrates the need. Start explicit; generalize when the pattern repeats.

For deeper context, see [docs/architecture.md](docs/architecture.md) and [docs/reasoning-pipeline.md](docs/reasoning-pipeline.md).

## Development setup

**Requirements:** Python 3.11+

```bash
git clone https://github.com/Saim-naushad/Odis.git
cd Odis
pip install -e ".[dev]"
```

Run the quality checks before opening a pull request:

```bash
ruff check .
mypy src tests
pytest
```

These same checks run automatically in CI on every push and pull request.

To explore the system interactively:

```bash
python examples/run_demo.py
```

## Project structure

| Path | Purpose |
|------|---------|
| `src/domain/` | Entities, value objects, events, repository interfaces, and structural invariants. No dependencies on other layers. |
| `src/application/` | Orchestration — detectors, assessors, planners, and use cases that coordinate domain objects. |
| `examples/` | Executable walkthroughs that demonstrate end-to-end reasoning scenarios. |
| `tests/` | Behavioral specifications. Use `tests/builders.py` to express test intent concisely. |
| `docs/` | Architecture documentation for contributors who need more than code comments. |

`src/infrastructure/` and `src/shared/` are reserved for future persistence and cross-cutting utilities. Do not add infrastructure code unless the PR explicitly requires it.

## Pull requests

**Keep PRs small and focused.** One capability per PR. A detector, a test suite, or a documentation update — not all three at once unless they are inseparable.

**Include tests for behavioral changes.** Tests are executable specifications. If you change how the system reasons, add or update tests that describe the new contract. Use builders (`build_observation_sequence([32, 35, 38])`) rather than verbose setup.

**Update documentation when architecture changes.** If you add a pipeline stage, a new layer responsibility, or an extension point, update `docs/` alongside the code. README changes are only needed when user-facing capabilities or setup instructions change.

**Ensure CI passes.** Lint, type checks, and tests must be green before review.

## Coding guidelines

**Immutable domain entities.** Use frozen dataclasses. Domain records do not mutate after creation.

**Prefer composition over inheritance.** New behavior comes from new components (e.g., a detector beside `TrendDetector`), not from subclass trees.

**Keep application orchestration thin.** Application code coordinates domain objects and validates input coherence. Business invariants belong on entities; planning rules belong in identifiable application components, not scattered across the codebase.

**Avoid hidden side effects.** Functions should not silently persist data, emit events, or mutate global state. Side effects belong in infrastructure (when implemented) and should be explicit.

**Type-annotate application and domain code.** MyPy enforces `disallow_untyped_defs` on `domain.*` and `application.*`. Keep annotations honest.

**No AI or ML in the core pipeline unless explicitly scoped.** ODIS reasoning is deterministic and explainable. Do not introduce opaque models without a dedicated design discussion.

## How ODIS grows

ODIS is developed in milestones, not large feature drops. Each sprint typically delivers one architectural capability — a domain entity, a detector, a use case, a test foundation, or a documentation pass.

This is intentional. Small increments keep the reasoning model understandable and reviewable. If you have a large idea, consider splitting it into a sequence of PRs that each leave the codebase in a working state.

When in doubt, open an issue or draft PR early. It is better to align on scope before building something that fights the architecture.

## Questions

If something in this guide conflicts with the code, trust the code and open an issue. If the code should change, a focused PR with a clear rationale is welcome.
