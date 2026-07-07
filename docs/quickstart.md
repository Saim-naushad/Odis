# ODIS Quickstart

Get from a fresh clone to your first working program in about 10–15 minutes.

## 1. What is ODIS?

ODIS turns a sequence of measurements into an explainable operational decision. You provide observations and a goal; ODIS detects patterns, assesses the situation, and produces a recommendation you can inspect step by step. For the broader vision, design goals, and project status, see the [README](../README.md).

## 2. Installation

Clone the repository and install ODIS in editable mode with development dependencies:

```bash
git clone <repository-url>
cd Odis
pip install -e ".[dev]"
```

You need **Python 3.11+**.

## 3. Explore ODIS

Run the built-in demonstrations:

```bash
odis demo all
```

This walks through three scenarios—rising temperature, stable operations, and oscillating flow—and prints each stage of the lifecycle: observations, signals, assessment, decision, action, and outcome. Watch the output once before writing code; it shows what `ReasoningSession` produces end to end.

Other demos:

```bash
odis demo heatwave
odis demo stable
odis demo oscillating
odis demo fuel-cell
```

Run reasoning from CSV:

```bash
odis demo csv
```

This is the first demonstration that loads observations from a real ingestion example
(a CSV file) instead of constructing them synthetically in code.

## Domain Profiles

ODIS includes multiple **operational profiles**:

- **Default educational profile** — the baseline profile used in most examples.
- **Fuel cell profile** — a representative profile that shows how to extend ODIS with domain-specific operational knowledge.

Profiles are **extension points** for domain-specific operational knowledge, packaged as configuration and policies rather than changes to the core pipeline.

## 4. Your first ODIS program

Create a file named `first_odis.py` with the following content:

```python
from datetime import UTC, datetime, timedelta

from odis import (
    Asset,
    Location,
    MeasurementType,
    Observation,
    OperationalGoal,
    ReasoningSession,
)

asset = Asset(
    id="pump-01",
    name="Pump P-07",
    type="centrifugal_pump",
    location=Location(identifier="cooling-loop-beta"),
)

goal = OperationalGoal(
    id="goal-1",
    description="Keep pump pressure within normal operating range",
)

temperature = MeasurementType(name="temperature")
base_time = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
readings = (68.0, 72.0, 76.0, 80.0, 84.0)

observations = tuple(
    Observation(
        id=f"obs-{index}",
        asset_id=asset.id,
        timestamp=base_time + timedelta(hours=index),
        measurement_type=temperature,
        value=value,
        unit="celsius",
    )
    for index, value in enumerate(readings)
)

result = ReasoningSession().run(goal, observations)

print("Assessment:     ", result.situation.assessment)
print("Recommendation: ", result.plan.recommendation)
print("Priority:       ", result.plan.priority.name)
```

Run it:

```bash
python first_odis.py
```

You should see an increasing-trend assessment and a high-priority investigation recommendation. The readings rise steadily from 68 to 84 °C, so ODIS treats this as operational stress on the pump you defined.

Everything in this example comes from the public `odis` package—no internal imports required.

## 5. Understanding the result

`ReasoningSession.run()` returns a `ReasoningResult` that bundles each stage of the pipeline:

```
Trend        → direction detected from the observation sequence
Variation    → how much the values spread over time
Situation    → operational assessment (human-readable)
Plan         → recommendation, priority, and justification
Action       → record of what was done in response
Outcome      → record that an outcome was observed
```

Your program printed the **situation** (assessment) and **plan** (recommendation). The session also recorded action and outcome snapshots automatically—the same stages you saw in `odis demo all`.

You do not need to configure detectors or planners for a first program. `ReasoningSession` orchestrates them in a fixed order every time.

## 6. Where next?

| Document | What it's for |
|----------|----------------|
| [README](../README.md) | Project overview, capabilities, limitations, and how to run tests |
| [architecture.md](architecture.md) | Layer structure, design principles, and how the codebase is organized |
| [reasoning-pipeline.md](reasoning-pipeline.md) | Stage-by-stage walkthrough of observation → decision |
| [RFC-0001](rfcs/RFC-0001-core-operational-reasoning-architecture.md) | Accepted architectural decisions and domain model |
| [RFC-0002](rfcs/RFC-0002-multi-signal-reasoning.md) | Multi-signal reasoning design (trend + variation) |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to set up your environment, run checks, and open pull requests |

Start with the README if you want context. Read **architecture.md** and **reasoning-pipeline.md** when you are ready to understand *why* the pipeline is shaped the way it is. RFCs are for design history and intentional trade-offs. **CONTRIBUTING.md** is the path to your first code change.

---

**Intentionally out of scope for this guide:** persistence, event publishing, replay from storage, custom planners, telemetry ingestion, and production deployment. Those are covered in later documentation and milestones as the platform grows.
