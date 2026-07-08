# Fuel Cell Simulator

The ODIS fuel cell simulator is a lightweight digital twin that models the internal operational state of a PEM fuel cell stack and emits coherent telemetry derived from that state.

It is **not** a random telemetry generator. Measurements evolve together through deterministic subsystem relationships so the ODIS reasoning engine receives believable operational evidence.

---

## Design

The simulator follows a strict pipeline:

```
Machine State  →  State Evolution  →  Telemetry  →  Platform API
```

| Layer | Responsibility |
|-------|----------------|
| **Machine** | Owns internal operating variables (load, current, temperature, flows, etc.) |
| **State evolution** | `tick()` advances state through gradual, coupled updates |
| **Telemetry** | Maps machine state to domain `Observation` entities |
| **Publisher** | Sends observations to `POST /observations` via the public REST API |

The simulator behaves like an external industrial system. It does not write directly to repositories or bypass the platform HTTP boundary.

---

## Machine state

`FuelCellMachine` (`backend/simulator/machine.py`) represents the internal operating condition of a healthy PEM stack.

Representative internal variables:

| Variable | Role |
|----------|------|
| `load` | Present electrical load (% of rated capacity) |
| `target_load` | Commanded load setpoint |
| `current` | Stack current (A) |
| `voltage` | Cell voltage (V) |
| `stack_temperature` | Stack temperature (°C) |
| `stack_pressure` | Stack pressure (kPa) |
| `hydrogen_flow` | Hydrogen supply flow (SLPM) |
| `air_flow` | Cathode air flow (SLPM) — internal, not published |
| `cooling_efficiency` | Cooling subsystem effectiveness |
| `operating_mode` | `idle`, `running`, or `ramping` |

The machine owns this state. Telemetry is always derived from it.

---

## State evolution

Each `tick(dt_seconds)` applies first-order lag toward subsystem targets:

- **Load** gradually approaches `target_load`
- **Current** follows load
- **Voltage** decreases as current rises (polarization)
- **Hydrogen flow** follows load
- **Air flow** tracks hydrogen flow with a stoichiometric ratio
- **Stack temperature** rises with load, moderated by cooling efficiency
- **Stack pressure** moves inversely with temperature

Small bounded variation is added deterministically (sinusoidal, keyed to tick count) so readings are not perfectly flat without introducing unrelated random noise.

Transitions are gradual — the simulator avoids instantaneous jumps between operating points.

---

## Telemetry generation

`observations_from_machine()` (`backend/simulator/telemetry.py`) converts the current machine snapshot into domain `Observation` objects using the measurement types expected by `FuelCellOperationalProfile`:

- `stack_temperature` (°C)
- `stack_pressure` (kPa)
- `current` (A)
- `voltage` (V)
- `fuel_flow` (SLPM) — mapped from internal `hydrogen_flow`

No parallel telemetry model is introduced. The simulator reuses the same `Observation` entity that the reasoning engine and platform API already understand.

---

## Publisher

`ObservationPublisher` (`backend/simulator/publisher.py`) posts each observation to:

```
POST /observations
```

using `httpx` against the configured API base URL. This mirrors how a real edge gateway or protocol adapter would integrate with ODIS.

---

## Scenarios

Scenarios orchestrate how the machine is driven over time.

### Normal operation

`NormalOperationScenario` (`backend/simulator/scenarios/normal_operation.py`) gently varies `target_load` on a five-minute sinusoidal cycle between 45% and 75%. The stack remains healthy — no failures, degradation, or fault injection.

Additional fault scenarios will be added in later phases.

---

## Configuration

Settings are loaded from environment variables with the `SIMULATOR_` prefix (and optional `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATOR_API_BASE_URL` | `http://localhost:8000` | ODIS platform API base URL |
| `SIMULATOR_PUBLISH_INTERVAL_SECONDS` | `5.0` | Seconds between publish cycles |
| `SIMULATOR_ASSET_ID` | `fuel-cell-stack-01` | Asset identifier on observations |

---

## Running

Start the platform API, then run the simulator:

```bash
# Terminal 1 — platform API (requires DATABASE_URL)
uvicorn backend.app.main:app --reload

# Terminal 2 — simulator
python -m backend.simulator
```

Each publish cycle:

1. Advances the normal-operation scenario by one tick
2. Derives five observations from machine state
3. Posts them to `/observations`

Stop with `Ctrl+C`.

---

## Why model behavior instead of random values?

Industrial reasoning depends on **coherent subsystem response**. When load rises, current, fuel flow, and temperature should move together in predictable ways. Random independent sensor values would produce contradictions and false correlations that do not represent real equipment behavior.

By modeling internal state first and deriving telemetry second, the simulator produces evidence suitable for trend detection, relationship analysis, and expectation evaluation in the ODIS reasoning engine.

---

## Related documentation

- [Fuel cell operational profile](profiles/fuel_cell_profile.md)
- [Platform architecture](platform/platform-architecture.md)
