# Fuel Cell Operational Profile

Fuel cells are a helpful domain for demonstrating operational profiles because they combine **electrochemistry**, **thermal behavior**, and **fluid flow** in a single system. In practice, operators care about how these signals move together over time: not to solve physics in software, but to spot coherent patterns and investigate mismatches.

This document describes `FuelCellOperationalProfile`, the first domain-specific operational profile in ODIS. It is intentionally representative and educational — it does not claim to model any proprietary controls or algorithms.

## What measurements are represented

The profile introduces a small set of measurement types commonly seen in a fuel-cell stack context:

- **`stack_temperature`**: a representative stack temperature signal.
- **`stack_pressure`**: a representative stack pressure signal (e.g., a stack or manifold pressure proxy).
- **`current`**: electrical current drawn from the stack.
- **`voltage`**: electrical voltage produced by the stack.
- **`fuel_flow`**: a representative fuel flow signal.

ODIS does not attach units, hardware context, or physics to these names. The profile simply declares which measurements are interesting to relate.

## Relationship policy: illustrative pairs

`FuelCellOperationalProfile` contributes a `relationship_policy` that enumerates **which measurement pairs** should be evaluated by ODIS’s existing cross-measurement relationship detectors.

Initial illustrative (deterministic) relationships:

- **Stack Temperature ↔ Stack Pressure** (`stack_temperature` ↔ `stack_pressure`)
- **Current ↔ Voltage** (`current` ↔ `voltage`)
- **Fuel Flow ↔ Stack Temperature** (`fuel_flow` ↔ `stack_temperature`)

These rules are intentionally simple: they exist to demonstrate how an operational profile can express real engineering “what to compare” knowledge without inventing complex physics or changing detector logic.

## How this differs from the default educational profile

The default ODIS profile is intentionally minimal and generic: it defines a single educational relationship between `temperature` and `pressure`.

The fuel-cell profile differs in two ways:

1. **More representative measurement naming** (stack signals, electrical signals, and flow).
2. **Multiple relationship pairs** that reflect the multi-physics nature of fuel-cell operation.

Importantly, this change is achieved by adding a new profile and policy — **no planner, detector, replay, analytics, or framework redesign is required**.

