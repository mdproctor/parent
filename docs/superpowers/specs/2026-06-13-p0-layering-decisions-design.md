# P0 Layering Decisions — CloudEvents, Platform Streams, and Deployment YAML Compiler

**Date:** 2026-06-13
**Status:** Decided
**Issue:** casehubio/parent#235
**Scope:** Cross-cutting — casehub-platform, casehub-ras, casehub-ops, casehub-desiredstate
**Supersedes:** Research doc §5 open questions 1–3 (`docs/superpowers/research/2026-06-12-platform-evolution-desiredstate-ras-deployment.md`)

---

## Context

Three P0 architectural questions were left open after the 2026-06-12 platform evolution session. All three block implementation of casehub-ras, the platform stream modules, and casehub-ops/deployment. This document records the decisions and their rationale.

---

## Decision 1 — CloudEvent as the Platform's Typed Event Envelope

### Decision

Use `io.cloudevents.CloudEvent` from the CloudEvents Java SDK (`io.cloudevents:cloudevents-core`) directly as the CDI event type. `casehub-platform-api` takes a `compile` scope dependency on `cloudevents-core`. There is no wrapper type.

### Rationale

`SensoryEvent` — the working name from the research doc — over-specialises a general-purpose foundation primitive. The type is produced by foundation repos (casehub-iot, casehub-qhorus, casehub-connectors) and consumed by any interested observer, not only casehub-ras. The name must describe structure, not the first consumer.

CloudEvents (CNCF graduated, Jan 2024) is the industry standard envelope for exactly this: a typed, source-agnostic event carrier. CasehHub is already built on CNCF Serverless Workflow 1.0 — CloudEvents is the sibling spec. Quarkus SmallRye reactive messaging has native CloudEvents support, meaning Kafka stream modules receive CloudEvents without a translation layer. Taking `cloudevents-core` as a compile dependency is justified by the same reasoning as `jakarta.inject-api` and `jakarta.enterprise.cdi-api` in Tier 1 — pure Java interfaces, no runtime, ~70KB.

### Type structure

Producers fire `Event<CloudEvent>.fireAsync()`. Consumers observe `@ObservesAsync CloudEvent`.

| CloudEvents field | Purpose in CasehHub |
|---|---|
| `type` | Logical event type — reverse-DNS, e.g. `io.casehub.iot.temperature` |
| `source` | Logical producer — stream module URI, device path, topic name |
| `subject` | The entity the event is about — `device/thermostat-1`, `patient/1234`, `case/9a3f` |
| `id` | Unique event ID |
| `time` | When the event occurred (not when received) |
| `data` | The typed payload |
| `tenancyid` (extension) | CasehHub tenant ID — CloudEvents extension attribute; extracted at ingestion boundary |

`subject` is a routing and correlation aid, not a tenancy field. Tenancy is a CloudEvents extension attribute (`tenancyid`), following CloudEvents naming rules (lowercase, ≤20 chars).

### StreamContext SPI

`StreamContext` is a new SPI in `casehub-platform-api` (`io.casehub.platform.api.streams`), the async equivalent of `CurrentPrincipal`. It propagates `tenancyId` through async CDI event processing chains without call sites extracting it manually. `NoOpStreamContext @DefaultBean` in `casehub-platform`. Stream modules extract `tenancyid` from the CloudEvent extension attribute at the ingestion boundary and populate `StreamContext` for downstream processing.

### Placement satisfies platform-api-scope protocol

`CloudEvent` as a CDI event type is needed by casehub-iot, casehub-qhorus, casehub-connectors, and all five platform stream modules — multiple peer foundation repos. Cannot be hosted in any single domain `*-api` module. Qualifies for `casehub-platform-api`.

### Future abstraction

If a future need arises to abstract the CloudEvents SDK dependency, a `PlatformEvent extends CloudEvent` interface can be introduced without breaking consumers. No premature abstraction now.

---

## Decision 2 — Platform Stream Modules as casehub-platform Submodules

### Decision

The five platform stream modules are submodules of `casehub-platform`, following the `memory-inmem/`, `memory-jpa/` classpath-activated adapter pattern. No new `casehub-streams` repo.

### Rationale

Stream modules are thin adapters (~300 lines each) for a platform SPI (`Event<CloudEvent>`). The established pattern for classpath-activated platform adapters is submodules of `casehub-platform`. A separate repo would add build complexity and cross-repo release coordination for what is currently thin wrapper code. Extract to a dedicated repo if the content grows substantially or release cadence diverges materially.

The stream infrastructure is general-purpose — not scoped to casehub-ras. casehub-iot emits `CloudEvent` from `StateChangeEvent`; casehub-qhorus emits from `MessageReceivedEvent`; casehub-connectors emits from `InboundMessage`. The stream modules handle external transport sources (Kafka, AMQP, REST, Camel routes).

### Modules

| Module | Transport | Notes |
|--------|-----------|-------|
| `platform-streams-kafka` | Quarkus SmallRye reactive messaging | Native CloudEvents deserialization from Kafka; extracts `tenancyid` from Kafka headers |
| `platform-streams-amqp` | Quarkus AMQP reactive messaging | Same pattern |
| `platform-streams-webhook` | Quarkus REST `@POST` | Maps HTTP body + headers to CloudEvent; registers own endpoint in EndpointRegistry at startup |
| `platform-streams-poll` | Quarkus `@Scheduled` + REST client | Polls EndpointRegistry-configured HTTP endpoints on interval |
| `platform-streams-camel` | Apache Camel routes | Constructs routes at `@PostConstruct` from EndpointRegistry — the dynamic topology path |

All modules activate by classpath presence. All fire `Event<CloudEvent>.fireAsync()`.

### EndpointRegistry integration

Each module discovers its connection targets from `EndpointRegistry` at startup using the appropriate `EndpointProtocol` (`KAFKA`, `CAMEL`, `MCP`). This connects to the deployment YAML story: `casehub-desiredstate` provisions stream endpoints into the registry; stream modules self-configure without hardcoded `application.properties` entries.

### Quarkus build-time constraint

Quarkus reactive messaging wires Kafka topics at build time via `application.properties`. Topics cannot be added at runtime via this mechanism. `platform-streams-camel` resolves this: Camel routes are constructed at `@PostConstruct` from EndpointRegistry content, enabling a new Kafka topic registered by desiredstate at runtime to be picked up without a rebuild. `platform-streams-camel` is the dynamic topology path; the static modules (`kafka`, `amqp`) cover the common case where topics are known at deploy time.

---

## Decision 3 — DeploymentGoalCompiler in casehub-ops/deployment

### Decision

The `DeploymentGoalCompiler` — the CasehHub deployment YAML processor — lives in `casehub-ops/deployment`, as a domain implementation of the `GoalCompiler` SPI defined in `casehub-desiredstate`.

### Rationale

`casehub-desiredstate` is domain-agnostic: it defines `DesiredStateGraph`, `TransitionPlanner`, `ReconciliationLoop`, `FaultPolicyEngine`, and the `GoalCompiler` SPI. It must not know what a CasehHub agent, channel, trust configuration, or stream source is. The deployment YAML compiler requires that knowledge — it is a domain implementation, not the generic runtime.

`casehub-ops` already owns CasehHub-specific domain implementations: `deployment`, `infra`, `compliance`, `iot`. The deployment compiler is one more module there. Dependency direction is correct: `casehub-ops` depends on `casehub-desiredstate`; the reverse does not hold.

### Sub-compiler delegation

```
DeploymentGoalCompiler (casehub-ops/deployment)
  ├── agents section      → claudony/openclaw NodeProvisioner SPI
  ├── streams section     → EndpointRegistry (registers KAFKA/CAMEL endpoints)
  ├── detection section   → casehub-ras RasEngine configuration
  ├── channels section    → casehub-qhorus ChannelService
  └── trust section       → PreferenceProvider (trust-routing.yaml entries)
```

The deployment YAML committed to git is the compliance record for infrastructure changes. The reconciliation case history is the audit trail.

---

## Impact on Existing Platform

### casehub-ras-api

Does **not** define `SensoryEvent` or any equivalent. `casehub-ras` observes `@ObservesAsync CloudEvent` from `casehub-platform-api`. `Ganglion`, `DetectionResult`, `SituationDefinition`, `RasTriggerPolicy` remain in `casehub-ras-api`.

### casehub-iot, casehub-qhorus, casehub-connectors

Each gets a lightweight adapter that maps its own event type to `CloudEvent` and fires it on the CDI bus:
- `casehub-iot`: `StateChangeEvent → CloudEvent` (type `io.casehub.iot.<deviceClass>`)
- `casehub-qhorus`: `MessageReceivedEvent → CloudEvent` (type `io.casehub.qhorus.message.received`)
- `casehub-connectors`: `InboundMessage → CloudEvent` (type `io.casehub.connectors.inbound.<connectorType>`)

These adapters activate by classpath presence — existing consumers that don't add them are unaffected.

### PLATFORM.md updates required

- Add `CloudEvent` capability row to the Capability Ownership table (`casehub-platform-api`)
- Add `StreamContext` capability row (`casehub-platform-api`)
- Add platform stream modules to the Repository Map (`casehub-platform` submodules, Foundation tier)
- Classify `casehub-ops` correctly in Repository Map (Integration tier — domain implementations of desiredstate SPIs)
- Update `casehub-ras` capability row to reflect it observes `CloudEvent` not a proprietary event type

---

## What Remains Open (P1+)

These questions are unblocked by the decisions above but not yet resolved:

| # | Question | Blocks |
|---|----------|--------|
| P1.4 | Quarkus build-time constraint — can the deployment YAML wire stream sources at runtime via Camel, or is Quarkus config always required? `platform-streams-camel` addresses this but the full constraint surface is not yet mapped. | Deployment UX completeness |
| P2.5 | `SituationStore` persistence — in-memory for prototype; JPA for durable correlation across restarts. Retention policy for expired situations. | casehub-ras production readiness |
| P2.6 | Drools CEP session model — stateful `KieSession` per situation vs shared session with tenant isolation. | casehub-ras Drools ganglion |
| P2.7 | Ganglion-as-case pattern — optional or first-class in the `Ganglion` SPI? | casehub-ras SPI design |
| P3.8 | `StreamContext` SPI contract detail — how `tenancyId` flows from CloudEvent extension through async CDI to ledger entries. | casehub-platform-api implementation |
| P3.9 | `StreamEventLedgerEntry` home — casehub-ras, casehub-ledger, or a bridge module? | Audit trail completeness |
| P3.10 | Self-governance bootstrap — who manages casehub-desiredstate on first deployment? | casehub-ops operational story |
