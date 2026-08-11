# Demo SPI Convention — Profile Switching and Scenario Support

> **Scope:** Convention for connector SPIs that ship demo implementations for scenario-driven demos and testing
> **Audience:** All (connector SPI authors; app builders consuming demo impls)
> **Key repos:** casehub-connectors (SPI modules), casehub-platform-api (shared `DemoCurrentPrincipal`), application repos (consumers)
> **Related:** [Scenario Format](scenario-format.md) — the YAML format that drives demo scenarios

## Overview

Every connector SPI that represents an external integration (chat, calendar,
bank feed, email, IoT devices) must ship with a demo implementation. The demo
impl is activated by CDI profile switching and serves two purposes:

1. **Scripted demos** — the scenario executor (pages) drives the demo impl
   via REST calls and injection endpoints.
2. **Development** — developers run the app locally without real external
   service credentials.

Demo impls are invisible to application code — the app cannot distinguish
demo data from real data.

## 1. Profile Convention

Three build profiles govern external integration behaviour:

| Profile | Activated by | External services | Identity | Use case |
|---------|-------------|-------------------|----------|----------|
| `demo` | `quarkus.profile=demo` | Demo impls only — no real connections | `DemoCurrentPrincipal` (shared, reads `X-Scenario-Actor`) | Scripted demos, scenario verification |
| `dev` | `quarkus.profile=dev` (default) | Live dev credentials where available; demo fallback otherwise | App-specific dev principal | Local development |
| `prod` | `quarkus.profile=prod` | Live production credentials | OIDC-backed `CurrentPrincipal` | Production deployment |

**Profile activation:** Quarkus selects the active profile at build time.
`@IfBuildProfile("demo")` beans are only instantiated when the app is built
with the demo profile. This is a compile-time gate — demo code is not
present in production builds.

**Relationship to `dev` profile:** The `dev` profile is for local
development with real (or dev-tier) credentials. The `demo` profile is
for scripted scenarios where all external data is synthetic. An app may
use `dev` profile without the scenario engine. An app running a scenario
must use `demo` profile.

## 2. Demo Implementation Pattern

### 2.1 CDI annotation pattern

```java
@ApplicationScoped
@Alternative
@Priority(300)
@IfBuildProfile("demo")
public class DemoChatPlatform implements ChatPlatform {
    // ...
}
```

| Annotation | Purpose |
|-----------|---------|
| `@ApplicationScoped` | Singleton lifecycle |
| `@Alternative` | Displaces the default/real implementation |
| `@Priority(300)` | Wins over all real implementations (Slack=default, Discord=100, etc.) |
| `@IfBuildProfile("demo")` | Only active in demo builds |

**Priority 300** is reserved for demo impls. Real implementations must
use lower priorities. This ensures demo impls always win when the demo
profile is active.

### 2.2 Module placement

Demo impls live in their own Maven module within the connector repo:

```
connectors/
├── chat-spi/              # SPI interface
├── chat-slack/            # Real implementation (Slack)
├── chat-discord/          # Real implementation (Discord)
├── chat-demo/             # Demo implementation ← new module
├── calendar-spi/
├── calendar-google/
├── calendar-demo/         # Demo implementation ← new module
```

The demo module depends on the SPI module only — no real implementation
dependencies. Apps include the demo module as a compile dependency; the
`@IfBuildProfile("demo")` annotation ensures it is inert in non-demo builds.

## 3. Pull Mode — Serving Pre-Loaded Data

Pull mode serves data from datasets bootstrapped by the scenario executor
at startup.

### 3.1 Bootstrap endpoint

Every demo impl exposes a bootstrap endpoint that receives scenario data
from the executor:

```java
@Path("/scenario/bootstrap")
@IfBuildProfile("demo")
@ApplicationScoped
public class ScenarioBootstrapResource {

    @Inject
    DemoChatPlatform demoChatPlatform;

    @Inject
    DemoCalendarPlatform demoCalendarPlatform;

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    public Response bootstrap(ScenarioBootstrapRequest request) {
        for (var entry : request.datasets().entrySet()) {
            switch (entry.getKey()) {
                case "chat-messages" -> demoChatPlatform.loadMessages(entry.getValue());
                case "calendar-events" -> demoCalendarPlatform.loadEvents(entry.getValue());
            }
        }
        return Response.ok().build();
    }
}
```

### 3.2 Template: Pull-mode demo impl

```java
@ApplicationScoped
@Alternative
@Priority(300)
@IfBuildProfile("demo")
public class DemoChatPlatform implements ChatPlatform {

    private final List<ReceivedMessage> messages = new CopyOnWriteArrayList<>();

    @Override
    public String id() {
        return "demo";
    }

    @Override
    public Messaging messaging() {
        return (channelId, content) -> {
            // Record outbound messages for verification
            messages.add(new ReceivedMessage(channelId, "demo-user", content));
            return new SentMessage(UUID.randomUUID().toString());
        };
    }

    @Override
    public MessageHistory messageHistory() {
        return (channelId, limit) -> messages.stream()
                .filter(m -> m.channelId().equals(channelId))
                .limit(limit)
                .toList();
    }

    // Bootstrap: called by ScenarioBootstrapResource at startup
    public void loadMessages(JsonNode dataset) {
        // Parse dataset JSON into ReceivedMessage objects
        // Available for Pull-mode queries immediately
    }

    // ... other capabilities return degraded defaults
}
```

### 3.3 Template: Pull-mode calendar demo

```java
@ApplicationScoped
@Alternative
@Priority(300)
@IfBuildProfile("demo")
public class DemoCalendarPlatform implements CalendarPlatform {

    private final Map<String, List<CalendarEvent>> events = new ConcurrentHashMap<>();

    @Override
    public String id() {
        return "demo";
    }

    @Override
    public List<CalendarInfo> listCalendars() {
        return events.keySet().stream()
                .map(id -> new CalendarInfo(id, "Demo Calendar: " + id))
                .toList();
    }

    @Override
    public List<CalendarEvent> listEvents(String calendarId, Instant from, Instant to) {
        return events.getOrDefault(calendarId, List.of()).stream()
                .filter(e -> !e.start().isBefore(from) && !e.start().isAfter(to))
                .toList();
    }

    // Bootstrap: called by ScenarioBootstrapResource
    public void loadEvents(JsonNode dataset) {
        // Parse dataset JSON into CalendarEvent objects keyed by calendarId
    }

    // ... remaining CalendarPlatform methods
}
```

## 4. Push Mode — Accepting Injected Events

Push mode accepts event injections from the scenario executor. The
injection endpoint fires CDI events identical to those from real external
systems.

### 4.1 Injection endpoint pattern

```java
@Path("/scenario/inject")
@IfBuildProfile("demo")
@ApplicationScoped
public class ScenarioInjectionResource {

    @Inject
    Event<InboundMessage> chatInboundEvent;

    @Inject
    Event<CalendarEventReceived> calendarEvent;

    @POST
    @Path("/chat")
    @Consumes(MediaType.APPLICATION_JSON)
    public Response injectChatMessage(ReceivedMessage message) {
        chatInboundEvent.fire(new InboundMessage(
                "demo",           // connector id
                message.from(),
                message.text(),
                message.channelId()
        ));
        return Response.accepted().build();
    }

    @POST
    @Path("/calendar")
    @Consumes(MediaType.APPLICATION_JSON)
    public Response injectCalendarEvent(CalendarEvent event) {
        calendarEvent.fire(new CalendarEventReceived("demo", event));
        return Response.accepted().build();
    }
}
```

**Key constraint:** The injection endpoint fires the same CDI event type
that the real connector adapter fires. Application code observing
`@ObservesAsync InboundMessage` cannot distinguish injected events from
real ones.

### 4.2 Consumer obligation

For injected events to be visible in the UI, the target app must have SSE
wiring for the relevant domain events. This is the same requirement as for
real external events — the demo infrastructure does not add any SSE
plumbing.

## 5. Shared DemoCurrentPrincipal

Identity in demo mode is handled by a shared CDI producer in
`casehub-platform-api`, not per-app.

```java
package io.casehub.platform.api.demo;

@RequestScoped
@Alternative
@Priority(200)
@IfBuildProfile("demo")
public class DemoCurrentPrincipal implements CurrentPrincipal {

    @Context
    HttpHeaders headers;

    private static final String HEADER = "X-Scenario-Actor";
    private static final String DEFAULT_ACTOR = "demo-admin";
    private static final String TENANT_ID = "demo-tenant";

    @Override
    public String actorId() {
        String actor = headers.getHeaderString(HEADER);
        return actor != null ? actor : DEFAULT_ACTOR;
    }

    @Override
    public String tenancyId() {
        return TENANT_ID;
    }

    @Override
    public Set<String> groups() {
        return Set.of(); // demo mode — no role restrictions
    }

    @Override
    public boolean isCrossTenantAdmin() {
        return false;
    }
}
```

**Priority 200** ensures `DemoCurrentPrincipal` displaces the mock
(`@DefaultBean`, no priority) and `OidcCurrentPrincipal` (`@Priority(100)`)
in demo builds. Priority 300 is reserved for connector demo impls.

**Per-step actor identity:** The scenario executor passes the step's `actor`
field as the `X-Scenario-Actor` header value. Each REST call to a target
service carries the actor identity for that step. See
[Scenario Format §2](scenario-format.md) — the `actor` field on steps.

### 5.1 Migration from per-app DemoCurrentPrincipal

Existing per-app implementations (e.g. `clinical.demo.DemoCurrentPrincipal`
which uses `@IfBuildProfile("dev")` with fixed identity) should be migrated:

1. Remove the per-app `DemoCurrentPrincipal` class.
2. Add `casehub-platform-api` dependency (already present in most apps).
3. The shared `DemoCurrentPrincipal` activates automatically in demo builds.
4. For `dev` profile, keep the existing app-specific principal if needed
   (it serves a different purpose — fixed dev credentials, not scenario
   actor switching).

## 6. Checklist for New Connector SPIs

When creating a new connector SPI (e.g. `BankFeedPlatform`, `EmailPlatform`):

- [ ] SPI interface in `<connector>-spi/` module
- [ ] Demo module: `<connector>-demo/` with `@Alternative @Priority(300) @IfBuildProfile("demo")`
- [ ] Pull mode: `loadXxx(JsonNode)` method for bootstrap data loading
- [ ] Push mode: injection endpoint entry in `ScenarioInjectionResource` (or separate resource)
- [ ] CDI event: injection fires the same event type as the real adapter
- [ ] Bootstrap: `ScenarioBootstrapResource` routes the connector's datasets to the demo impl
- [ ] No application-specific code in the demo module — SPI dependency only

## 7. Priority Allocation

| Priority range | Owner | Example |
|---------------|-------|---------|
| (none) | `@DefaultBean` — mock/no-op | `MockCurrentPrincipal` |
| 1–99 | In-memory test implementations | `InMemoryAgentRegistry @Priority(1)` |
| 100 | OIDC / production implementations | `OidcCurrentPrincipal @Priority(100)` |
| 150 | Dev-mode implementations | `clinical DemoCurrentPrincipal @Priority(150)` (legacy) |
| 200 | Shared demo identity | `DemoCurrentPrincipal @Priority(200)` |
| 300 | Demo connector impls | `DemoChatPlatform @Priority(300)` |
