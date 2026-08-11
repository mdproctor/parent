# Scenario Format — YAML Schema and Semantics

> **Scope:** Cross-platform scenario format for scripted demos and automated verification
> **Audience:** All (app builders writing scenarios; platform builders implementing executors and demo SPIs)
> **Key repos:** casehub-pages (executor), casehub-connectors (demo SPIs), application repos (scenario files)
> **Design spec:** `specs/2026-08-11-cross-platform-scenario-engine-design.md`

## Overview

A scenario file is a YAML document that drives scripted demos and automated
verifications across CaseHub services. The same file coordinates backend
integration (REST calls, simulated inbound events, bulk data loads) and
frontend automation (form fills, navigation, observable interactions).

Pages is the execution engine. Its Quarkus backend (ScenarioExecutor)
parses the YAML, builds a trigger graph, and executes steps across target
services. Its frontend engine (ScenarioController from #140) handles UI
actions dispatched by the backend via ControlChannel.

## 1. Top-Level Structure

```yaml
scenario: life-household-demo
description: "A week in the life of a family"
speed: 1
loop: false
on-error: continue

data:
  bank-transactions: "data/bank-transactions-6mo.json"
  whatsapp-history: "data/whatsapp-messages.json"

steps:
  - name: seed-actors
    # ...
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `scenario` | string | yes | — | Unique identifier for this scenario |
| `description` | string | no | — | Human-readable description |
| `speed` | number | no | `1` | Default playback speed multiplier |
| `loop` | boolean | no | `false` | Restart scenario when all steps complete |
| `on-error` | enum | no | `continue` | `continue`, `stop`, or `pause` — failure policy (see §9) |
| `data` | map&lt;string, string&gt; | no | — | Named external data file references (paths relative to scenario file) |
| `steps` | Step[] | yes | — | Ordered list of scenario steps |

## 2. Step Schema

A step is the atomic unit of scenario execution.

```yaml
- name: create-task-visible
  action: create-task
  delivery: ui-form
  trigger: { after: seed-actors, delay: 3000 }
  actor: household-admin
  data:
    title: "Chase Bob for quote"
    domain: "CONTRACTOR_COORDINATION"
  ui-actions:
    - navigate: "#home"
    - click: "[data-action='new-task']"
    - fill: { from: data }
    - click: "[data-action='submit']"
    - await: { event: "work-item-created" }
  fast-fallback:
    delivery: rest
    endpoint: POST /life-tasks
```

| Field | Type | Required | Default | Valid when | Description |
|-------|------|----------|---------|-----------|-------------|
| `name` | string | always | — | — | Unique identifier within the scenario |
| `action` | string | all steps except pure-await | — | — | Freeform string describing the action |
| `delivery` | enum | when `action` present | `rest` | — | `rest`, `ui-form`, or `simulated` |
| `endpoint` | string | yes | — | `delivery: rest` | HTTP method + path (e.g. `POST /life-tasks`) |
| `target` | string | yes | — | `delivery: simulated` | Connector name (e.g. `chat`, `bank`, `calendar`) |
| `trigger` | Trigger | no | fires at T=0 | — | When to start this step (see §3) |
| `data` | object or DataRef | no | — | — | Inline payload or external file reference (see §5) |
| `ui-actions` | UIAction[] | yes | — | `delivery: ui-form` | Sequence of UI action primitives (see §6) |
| `await` | Await | no | — | — | Completion condition (see §8) |
| `actor` | string | no | `demo-admin` | — | Actor identity for `X-Scenario-Actor` header |
| `fast-fallback` | object | no | — | `delivery: ui-form` | Alternative delivery for `fast` speed mode (see §7) |

### Validation rules

- `name` must be unique across all steps in the scenario.
- `endpoint` is required when `delivery` is `rest` and ignored otherwise.
- `target` is required when `delivery` is `simulated` and ignored otherwise.
- `ui-actions` is required when `delivery` is `ui-form` and ignored otherwise.
- `data` cannot have both `source` and inline properties — `source` references an external file; inline properties are the payload. The `mode` field is only valid with `source`.
- `fast-fallback` requires its own `delivery` and `endpoint` — the executor does not infer endpoints from action names.

## 3. Trigger Types

Steps without a trigger fire at T=0. Multiple steps can share the same
trigger — they execute concurrently. Steps form a directed graph connected
by triggers, not a sequential list.

### 3.1 TimeTrigger

Fires when the scenario clock reaches the specified offset.

```yaml
trigger: { at: 10000 }     # 10 seconds into the scenario
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `at` | number (ms) | yes | Scenario-time offset from start |

### 3.2 AfterTrigger

Fires when a named step completes, with an optional delay.

```yaml
trigger: { after: "seed-actors", delay: 5000 }
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `after` | string | yes | — | Name of the prerequisite step |
| `delay` | number (ms) | no | `0` | Wait time after the prerequisite completes |

The referenced step must exist in the scenario. If the prerequisite step
fails, this step is skipped with a diagnostic (unless `on-error: stop`
aborts first).

### 3.3 DataTrigger

Fires when a polled endpoint response matches a predicate. Evaluation is
always server-side — the backend executor polls the target service's API.

```yaml
trigger:
  when:
    endpoint: GET /life-tasks
    match: { status: "COMPLETED" }
    poll: 500
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `endpoint` | string | yes | — | HTTP method + path to poll |
| `match` | object | yes | — | Key-value predicate — fires when any response item matches all pairs |
| `poll` | number (ms) | no | `500` | Polling interval |

DataTrigger and `await: { endpoint, match }` (§8) are syntactically
convergent — both poll an endpoint and match a predicate. The difference
is semantic: a trigger gates step *start*; an await gates step
*completion*. The executor shares the polling implementation.

**Evaluation boundary:** The client-side DataSet from pages #140 is not
involved. The backend owns the trigger graph and evaluates all triggers
consistently across delivery modes.

## 4. Delivery Modes

### 4.1 REST — `delivery: rest`

HTTP call to the target app's normal API. Invisible to the user.

```yaml
- name: seed-trial
  action: create-trial
  delivery: rest
  endpoint: POST /trials
  data: { source: "data/trial-seed.json", mode: bulk }
```

The executor sends the step's `data` as the request body. The `actor`
field sets the `X-Scenario-Actor` header.

**Use case:** Fast seeding, background state creation, API-driven actions
that don't need visual feedback.

### 4.2 UI Form — `delivery: ui-form`

Navigate, fill fields, and submit via UI automation. Fully visible to the
audience.

```yaml
- name: approve-invoice
  action: approve-oversight-gate
  delivery: ui-form
  data: { decision: "APPROVED", amount: 450 }
  ui-actions:
    - navigate: "#inbox"
    - click: "[data-urgency='OVERDUE']:first-child"
    - click: "[data-action='approve']"
    - fill: { from: data }
    - click: "[data-action='confirm']"
    - await: { event: "oversight-gate-resolved" }
```

The executor dispatches the `ui-actions` sequence to the frontend via
ControlChannel. The frontend executes each UIAction in order and reports
completion (or failure) back to the executor.

**Use case:** Demo audience watches data entry, form interaction, and
navigation in real time.

### 4.3 Simulated — `delivery: simulated`

HTTP call to the target app's injection endpoint. Fires CDI events as if
the external system sent them. Invisible to application code.

```yaml
- name: plumber-message
  action: whatsapp-message-arrives
  delivery: simulated
  target: chat
  data:
    from: "Bob's Plumbing"
    text: "Thursday 2pm works for us"
```

The executor calls `POST /scenario/inject/{target}` on the target service.
The service fires the corresponding CDI event — application code processes
it identically to a real inbound message.

**Consumer obligation:** Visibility of injected events in the UI requires
the target app to emit SSE events for the relevant domain events. This is
not automatic — apps must have SSE wiring for those event types. This is
the same requirement as for real external events.

**Use case:** External events (messages, transactions, sensor readings)
that trigger application workflows.

## 5. Data Shapes and Sourcing

### 5.1 Data shapes

| Shape | `mode` value | Behaviour |
|-------|-------------|-----------|
| **Single** | (default) | One data payload, one action |
| **Bulk** | `bulk` | Async ingestion of full dataset. Other steps continue while loading |
| **Stepped** | `stepped` | One item at a time, paced by scenario speed. Each item is a separate action |
| **Stream** | `stream` | Continuous emission at configured interval. Runs until scenario ends or step is cancelled |

`mode` is only valid with `source` (external data reference).

#### Single (default)

Inline data payload — one action:

```yaml
- name: plumber-message
  action: whatsapp-message
  delivery: simulated
  target: chat
  data:
    from: "Bob's Plumbing"
    text: "Thursday 2pm confirmed"
```

#### Bulk

Asynchronous ingestion of a full dataset. Non-blocking — other steps
continue while the bulk load runs:

```yaml
- name: seed-transactions
  action: load-transactions
  delivery: simulated
  target: bank
  data:
    source: transactions          # key lookup from top-level data map
    mode: bulk
```

#### Stepped

One item at a time from the dataset, paced by scenario speed:

```yaml
- name: daily-messages
  action: whatsapp-message
  delivery: simulated
  target: chat
  data:
    source: "data/whatsapp-week.json"
    mode: stepped
```

#### Stream

Continuous emission at a fixed interval until the scenario ends:

```yaml
- name: temperature-readings
  action: sensor-reading
  delivery: simulated
  target: iot
  data:
    source: "data/temperature-readings.json"
    mode: stream
    interval: 10000               # emit one reading every 10 seconds
```

| Field | Type | Required | Default | Valid when |
|-------|------|----------|---------|-----------|
| `interval` | number (ms) | no | `1000` | `mode: stream` |

### 5.2 Data sourcing

Data can be **inline** (in the scenario file) or **external** (referenced
file path):

```yaml
# Inline — small payloads
data:
  title: "GP follow-up"
  domain: "HEALTH"

# External — large datasets
data:
  source: "data/bank-transactions-6mo.json"
  mode: bulk
```

External files are resolved relative to the scenario file. Scenario files
and their data files ship together as a directory.

### 5.3 Source resolution

The `source` field supports two forms:

1. **Key lookup** — a bare word matching a key in the top-level `data:`
   map: `source: actors` resolves to the path declared under `data:`.
2. **Literal path** — a quoted string containing `/`:
   `source: "data/bank-transactions-6mo.json"`. Resolved relative to the
   scenario file.

Resolution order: if the value matches a key in the top-level `data:` map,
use the mapped path. Otherwise, treat it as a literal file path. Keys must
not contain `/` — any value containing `/` is always a literal path.

## 6. UI Action Primitives

UI actions target DOM elements via `data-*` attributes, not CSS classes —
decoupled from styling.

### 6.1 Vocabulary

| YAML | Behaviour | Example |
|------|-----------|---------|
| `navigate: "#path"` | Hash navigation to a page/view | `navigate: "#cases"` |
| `click: "[selector]"` | Click the matching element | `click: "[data-action='submit']"` |
| `fill: { field: value, ... }` | Set field values explicitly | `fill: { title: "Chase Bob" }` |
| `fill: { from: data }` | Map step data to form fields (see §6.2) | `fill: { from: data }` |
| `select: { target, value }` | Select a dropdown option | `select: { target: "[data-field='priority']", value: "HIGH" }` |
| `hover: "[selector]"` | Hover over an element | `hover: "[data-row='patient-001']"` |
| `scroll: { target, to }` | Scroll an element | `scroll: { target: "[data-list='inbox']", to: "bottom" }` |
| `await: { ... }` | Wait for a condition (see §8) | `await: { event: "work-item-created" }` |

Selectors follow standard CSS selector syntax. Prefer `data-*` attribute
selectors over class or ID selectors.

### 6.2 `fill: { from: data }` resolution

The `from: data` form maps the step's `data` properties to form fields via
`data-field` attributes:

1. For each key `k` in the step's `data` object, find the element with
   `data-field="${k}"` within the current form context.
2. Element type determines the dispatch action:

| Element | Action |
|---------|--------|
| `<input type="text">`, `<textarea>` | Type — sets value via keyboard simulation |
| `<input type="checkbox">` | Click — toggles if current state differs from data value |
| `<select>` | Select — selects the option matching the data value |
| `<input type="date">`, `<input type="number">` | Type — sets value as string |

3. Only top-level keys are resolved — no nested dot-path expansion. For
   nested form sections, expand the section first with
   `click: "[data-expand='...']"`, then use a second `fill`.
4. A `data-field` not found in the DOM produces a step warning (non-fatal,
   logged). A DOM element with no matching data key is ignored.

Explicit `fill: { field: value }` entries bypass this resolution — use
when the data object shape doesn't match the form field names.

## 7. Speed Control and Fast Fallback

| Mode | Speed | UI form behaviour | Use case |
|------|-------|-------------------|----------|
| Demo | 0.5x–1x | Visible — slow form fills, annotations | Sales demo, conference |
| Normal | 1x | Visible — real-time pace | Development testing |
| Fast | 10x–100x | Uses `fast-fallback` if defined; skipped otherwise | Rapid seeding, speed testing |
| Step | manual | One step at a time | Debugging |

In `fast` mode, steps with `fast-fallback` switch to the fallback delivery
instead of `ui-form`. Steps without `fast-fallback` are skipped in fast
mode (no REST equivalent exists).

```yaml
- name: create-task
  action: create-task
  delivery: ui-form
  fast-fallback:
    delivery: rest
    endpoint: POST /life-tasks
  data: { title: "Chase Bob" }
  ui-actions:
    - navigate: "#home"
    - click: "[data-action='new-task']"
    - fill: { from: data }
    - click: "[data-action='submit']"
```

The `fast-fallback` block requires its own `delivery` and `endpoint` —
the executor does not infer endpoints from action names.

## 8. Await and Verification

Every step can include an `await` that confirms the backend processed the
action. Await can appear as a step-level field or as a UI action within
`ui-actions`.

### 8.1 Await types

| Type | Syntax | Behaviour |
|------|--------|-----------|
| SSE event | `{ event: "work-item-created" }` | Wait for matching SSE event |
| Endpoint poll | `{ endpoint: "GET /life-tasks", match: { title: "Chase Bob" } }` | Poll endpoint until response matches |
| Delay | `{ delay: 2000 }` | Simple wait (ms) |

### 8.2 Timeout rules

| Await type | Default timeout | Override | Verify mode |
|-----------|----------------|---------|------------|
| `{ event }` | 10s | `timeout` field | Becomes assertion — failure recorded |
| `{ endpoint, match }` | 10s (polled every 500ms) | `timeout` field | Becomes assertion — failure recorded |
| `{ delay }` | N/A | — | Skipped (pure timing has no assertion value) |

```yaml
await: { event: "work-item-created", timeout: 30000 }
```

### 8.3 Verification mode

Activated by runtime property `casehub.scenario.mode=verify` (default:
`demo`). In verify mode:

- Every `await` becomes an assertion with a configurable timeout.
- `{ delay }` awaits are skipped.
- All delivery modes execute normally — `ui-form` steps are not skipped.
  Speed defaults to `normal` (1x). The operator can set speed to `fast`
  explicitly (which applies `fast-fallback` rules from §7).
- Failure produces a JUnit XML report at `target/scenario-results.xml`
  for CI integration, plus a human-readable summary on stderr.
- Non-zero exit code on any assertion failure.

**Failure output example:**
```
FAIL: step "create-task-visible" — await { event: "work-item-created" }
      timed out after 10000ms. No matching SSE event received.
      Last SSE events: [commitment-created, oversight-gate-resolved]
```

## 9. Error Model

### 9.1 Per-delivery-mode failures

| Failure | Behaviour |
|---------|-----------|
| `rest` gets 4xx/5xx | Step fails. Error logged with status code and response body. |
| `simulated` injection endpoint unreachable | Step fails. Scenario pauses with diagnostic: "Target service {host}:{port} unreachable for connector {name}". |
| `await` event never fires | Timeout (default 10s). Step fails. |
| `ui-form` selector not found | Step fails after 5s selector wait. Error: "Selector `[data-action='submit']` not found in DOM". |
| Bulk data load partial failure | Failed items logged. Step completes with warning. |

### 9.2 `on-error` policy

| Value | Behaviour |
|-------|-----------|
| `continue` (default) | Failed step is logged. Dependent steps (via `AfterTrigger`) are skipped with a diagnostic. Independent steps continue. |
| `stop` | Scenario aborts immediately on the first step failure. Use for demo scenarios where partial execution is worse than stopping. |
| `pause` | Scenario pauses on failure. Operator can fix the issue and resume via `<scenario-controls>`. Use for live demos where recovery is preferable to restart. |

In `verify` mode, any step failure is recorded as an assertion failure in
the JUnit report regardless of `on-error` setting. `on-error: stop`
additionally halts the scenario on the first failure.

## 10. Vocabulary Mapping — YAML to TypeScript

The pages YAML parser converts scenario files into TypeScript objects that
the existing ScenarioController (#140) and ScenarioExecutor execute.

### 10.1 UI actions

| YAML | TypeScript UIAction | Notes |
|------|-------------------|-------|
| `navigate: "#path"` | `{ type: 'navigate', page: '#path' }` | Direct mapping |
| `click: "[selector]"` | `{ type: 'click', target: '[selector]' }` | Direct mapping |
| `fill: { field: value }` | `{ type: 'type', target: '[data-field="field"]', value }` | One UIAction per field |
| `fill: { from: data }` | Multiple `{ type: 'type' \| 'select' \| 'click', ... }` | Resolved per §6.2 |
| `select: { target, value }` | `{ type: 'select', target, value }` | Direct mapping |
| `hover: "[selector]"` | `{ type: 'hover', target: '[selector]' }` | Direct mapping |
| `scroll: { target, to }` | `{ type: 'scroll', target, to }` | Direct mapping |

### 10.2 Triggers

| YAML trigger | TypeScript type | Notes |
|-------------|----------------|-------|
| `{ at: N }` | `TimeTrigger` | Maps to `controller.schedule(N, callback)` |
| `{ after: "name", delay: N }` | `AfterTrigger` | Schedules after named step completion |
| `{ when: { endpoint, match, poll } }` | `DataTrigger` | Server-side polling — no client-side DataSet involvement |
| (absent) | Immediate | Fires at T=0 |

### 10.3 Step and scenario

| YAML | TypeScript type | Notes |
|------|----------------|-------|
| Top-level document | `ScenarioConfig` | Parsed by pages YAML parser |
| Step object | `ScenarioStep` | Contains action, delivery, trigger, data, ui-actions |
| `delivery` field | `DeliveryMode` | Enum: `'rest' \| 'ui-form' \| 'simulated'` |
| `data.mode` field | `DataShape` | Enum: `'single' \| 'bulk' \| 'stepped' \| 'stream'` |
| `await` object | `StepAwait` | Union: `EventAwait \| EndpointAwait \| DelayAwait` |
| `on-error` field | `ErrorPolicy` | Enum: `'continue' \| 'stop' \| 'pause'` |

### 10.4 Controller types (existing — pages-data)

| Type | Location | Role |
|------|----------|------|
| `ScenarioController` | `pages-data/src/datasource/controller.ts` | Client-side virtual-time queue, speed/pause control |
| `ScenarioAnnotation` | `pages-data/src/datasource/controller.ts` | Overlay annotations for demo UI |
| `DataSource` / `DataSink` | `pages-data/src/datasource/types.ts` | Data pipeline primitives |

### 10.5 Executor types (new — pages backend, Java)

| Type | Role |
|------|------|
| `ScenarioExecutor` | Backend trigger graph, step scheduling, REST/injection delivery |
| `ScenarioConfig` | Parsed YAML scenario |
| `ScenarioStep` | Single step with action, delivery, trigger, data |
| `TriggerGraph` | DAG of steps connected by triggers |

## 11. Complete Examples

### 11.1 REST delivery — bulk seed

```yaml
scenario: clinical-trial-seed
description: "Seed a trial with patients and protocol data"
on-error: stop

steps:
  - name: seed-trial
    action: create-trial
    delivery: rest
    endpoint: POST /trials
    data:
      source: "data/trial-seed.json"
      mode: bulk

  - name: seed-patients
    trigger: { after: seed-trial }
    action: register-patients
    delivery: rest
    endpoint: POST /trials/TRIAL-001/patients
    data:
      source: "data/patients.json"
      mode: bulk
    await: { endpoint: "GET /trials/TRIAL-001/patients", match: { count: 50 } }
```

### 11.2 UI form delivery — visible form fill

```yaml
scenario: task-creation-demo
description: "Demo: create a task through the UI"
speed: 0.5
on-error: pause

steps:
  - name: create-task
    action: create-task
    delivery: ui-form
    data:
      title: "Chase Bob for quote"
      domain: "CONTRACTOR_COORDINATION"
      deadline: "+3d"
    ui-actions:
      - navigate: "#home"
      - click: "[data-action='new-task']"
      - fill: { from: data }
      - click: "[data-expand='scheduling']"
      - fill: { recurrence: "weekly" }
      - click: "[data-action='submit']"
      - await: { event: "work-item-created" }
    fast-fallback:
      delivery: rest
      endpoint: POST /life-tasks
```

### 11.3 Simulated delivery — external event injection

```yaml
scenario: whatsapp-message-demo
description: "Simulate an inbound WhatsApp message"

steps:
  - name: plumber-confirms
    action: whatsapp-message
    delivery: simulated
    target: chat
    data:
      from: "Bob's Plumbing"
      text: "Thursday 2pm confirmed for the boiler service"

  - name: verify-commitment
    trigger: { after: plumber-confirms }
    await: { event: "commitment-created", timeout: 15000 }
```

### 11.4 Stream delivery — continuous sensor readings

```yaml
scenario: iot-monitoring-demo
description: "Stream temperature sensor readings"

steps:
  - name: seed-devices
    action: load-devices
    delivery: simulated
    target: iot
    data:
      source: "data/home-devices.json"
      mode: bulk

  - name: temperature-stream
    trigger: { after: seed-devices }
    action: sensor-reading
    delivery: simulated
    target: iot
    data:
      source: "data/temperature-readings.json"
      mode: stream
      interval: 10000
```

### 11.5 Mixed scenario — all delivery modes

```yaml
scenario: life-household-week
description: "A realistic week for a family of four"
on-error: continue

data:
  actors: "data/demo-actors.json"
  transactions: "data/bank-6mo.json"
  calendar: "data/family-calendar.json"

steps:
  # REST — bulk seed (async, non-blocking)
  - name: seed-actors
    action: load-actors
    delivery: rest
    endpoint: POST /external-actors
    data: { source: actors, mode: bulk }

  # Simulated — inject external events
  - name: seed-transactions
    action: load-transactions
    delivery: simulated
    target: bank
    data: { source: transactions, mode: bulk }

  - name: seed-calendar
    action: load-calendar
    delivery: simulated
    target: calendar
    data: { source: calendar, mode: bulk }

  # Simulated — single event after seed completes
  - name: plumber-confirms
    trigger: { after: seed-actors, delay: 5000 }
    action: whatsapp-message
    delivery: simulated
    target: chat
    data:
      from: "Bob's Plumbing"
      text: "Thursday 2pm confirmed for the boiler service"

  # Pure await — no action, just wait for a system event
  - name: system-creates-commitment
    trigger: { after: plumber-confirms }
    await: { event: "commitment-created" }

  # UI form — visible approval workflow
  - name: approve-invoice
    trigger: { after: system-creates-commitment, delay: 8000 }
    action: approve-oversight-gate
    delivery: ui-form
    actor: household-admin
    data: { decision: "APPROVED", amount: 450 }
    ui-actions:
      - navigate: "#inbox"
      - click: "[data-urgency='OVERDUE']:first-child"
      - click: "[data-action='approve']"
      - fill: { from: data }
      - click: "[data-action='confirm']"
      - await: { event: "oversight-gate-resolved" }

  # Stream — continuous sensor data
  - name: home-sensors
    trigger: { at: 0 }
    action: sensor-readings
    delivery: simulated
    target: iot
    data:
      source: "data/sensor-readings.json"
      mode: stream
      interval: 10000

  # DataTrigger — fires when polled condition met
  - name: react-to-task-completion
    trigger:
      when:
        endpoint: GET /life-tasks
        match: { status: "COMPLETED", title: "Chase Bob for quote" }
        poll: 1000
    action: send-completion-notification
    delivery: rest
    endpoint: POST /notifications
    data:
      type: "task-completed"
      message: "Bob task is done"
```

## 12. File Distribution

Scenario files and their data files live in the pages repo (or a shared
`casehub-scenarios` resource module). Target services do not load scenario
files from disk.

The executor pushes Pull-mode data to each target service at startup via a
bootstrap endpoint:

```
POST /scenario/bootstrap
Content-Type: application/json
{
  "scenario": "life-household-demo",
  "datasets": {
    "bank-transactions": [ ... ],
    "whatsapp-history": [ ... ]
  }
}
```

Each target service's demo impl exposes this endpoint and loads the
received datasets for Pull-mode queries.

**Startup sequence:**
1. Executor checks target service health via `GET /q/health`
2. Executor calls `POST /scenario/bootstrap` with relevant data sections
3. Executor starts scenario playback

Health checks retry with exponential backoff (max 30s). Failure to reach
any target service produces a diagnostic and aborts.

## 13. Demo SPI Convention

Every connector SPI ships a demo `@Alternative @Priority(300)` activated
by `@IfBuildProfile("demo")`.

**Pull mode:** Demo impl serves from data bootstrapped by the executor.
**Push mode:** Demo impl accepts injections via `/scenario/inject/{connector}`.

`DemoCurrentPrincipal` is a shared CDI producer in `casehub-platform-api`,
not implemented per-app. It reads the `X-Scenario-Actor` header, falls
back to `demo-admin`, and is activated by `@IfBuildProfile("demo")`.
