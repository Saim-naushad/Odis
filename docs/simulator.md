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
- **Voltage** decreases as current rises (polarization), and separately drops under sustained hydrogen starvation (`fuel_supply_factor` below a healthy threshold) via a bounded, monotonic penalty — a lumped correction, not a full electrochemical model. Without it, starvation's own current-limiting could otherwise make voltage *rise* along the polarization relationship alone, which is not a physically defensible fault signature; see `FuelCellMachine._fuel_starvation_voltage_penalty` in `backend/simulator/machine.py`.
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

The simulator supports two transports:

| Transport | Config | Use |
|-----------|--------|-----|
| **MQTT** (default for Compose demo) | `SIMULATOR_TRANSPORT=mqtt` | Full pipeline through Mosquitto and the MQTT bridge |
| **HTTP** (local dev fallback) | `SIMULATOR_TRANSPORT=http` | Direct `POST /observations` — not E2E acceptance |

`MqttObservationPublisher` posts to `odis/v1/{site}/{asset}/telemetry/{measurement}`.

`HttpObservationPublisher` posts to `POST /observations` via httpx.

For Plant Alpha fleet setup, scenarios, throughput limits, and validation, see [Demo Environment](platform/demo-environment.md).

---

## Configuration

Settings use the `SIMULATOR_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATOR_TRANSPORT` | `mqtt` | `mqtt` or `http` |
| `SIMULATOR_MQTT_BROKER_URL` | `mqtt://localhost:1883` | Mosquitto broker |
| `SIMULATOR_API_BASE_URL` | `http://localhost:8000` | API (HTTP transport) |
| `SIMULATOR_SITE_ID` | `plant-alpha` | MQTT site segment |
| `SIMULATOR_SCENARIO_SCRIPT` | `demo_presentation` | Timed demo script |
| `SIMULATOR_CORE_PUBLISH_INTERVAL_SECONDS` | `15` | Core measurement cadence |
| `SIMULATOR_DERIVED_PUBLISH_INTERVAL_SECONDS` | `60` | Derived metric cadence |
| `SIMULATOR_SIM_DT_SECONDS` | `45` | Simulation timestep per tick |
| `SIMULATOR_RUN_ID` | auto | Optional fixed run id for tests |

The three cadence settings above are the platform defaults. `demo_presentation`
overrides them with its own faster cadence (`cadence_for_script` in
`backend/simulator/scenario_script.py`) unless you explicitly set one of them
yourself, in which case your value wins — see
[Demo Environment → Throughput and cadence](platform/demo-environment.md#throughput-and-cadence).

---

## Running

### Compose demo (MQTT)

```bash
docker compose --profile demo up --build -d
```

### Local HTTP fallback

```bash
SIMULATOR_TRANSPORT=http python -m backend.simulator --scenario normal_operation
```

---

## Legacy configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATOR_PUBLISH_INTERVAL_SECONDS` | `15.0` | Alias for core publish interval |
| `SIMULATOR_ASSET_ID` | `fuel-cell-stack-01` | Single-asset fallback |

---

## Why model behavior instead of random values?

Industrial reasoning depends on **coherent subsystem response**. When load rises, current, fuel flow, and temperature should move together in predictable ways. Random independent sensor values would produce contradictions and false correlations that do not represent real equipment behavior.

By modeling internal state first and deriving telemetry second, the simulator produces evidence suitable for trend detection, relationship analysis, and expectation evaluation in the ODIS reasoning engine.

---

## Related documentation

- [Fuel cell operational profile](profiles/fuel_cell_profile.md)
- [Platform architecture](platform/platform-architecture.md)
