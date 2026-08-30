# Shared YAML Core — Design Spec

**Issue:** TBD (file on casehubio/parent)
**Date:** 2026-08-29
**Status:** Draft

## Summary

Extract common YAML declaration primitives from `casehub-desiredstate/yaml/` into a shared
platform module (`casehub-yaml-core` or equivalent). Two CaseHub subsystems use YAML as a
declaration surface with overlapping control constructs:

1. **Desired-state** (`casehub-desiredstate/yaml/`) — declares a graph of typed nodes with
   dependencies. Currently owns `VariableResolver`, `ForEachExpander`, `isTruthy()`, and
   `YamlIterationGroup`.
2. **Scenario automation** (`casehub-pages/backend/scenario-runtime/`) — declares ordered
   sequences of steps with commands for browser automation. Currently has `VariableContext`
   for `${stepName.field}` interpolation but no forEach, when, or structured data iteration.

Both need the same leaf-level primitives. This module extracts them so both domains compose
them into their own compilation pipelines.

## Approach — Port, Don't Rewrite

The existing desiredstate implementations are production-tested and well-covered by unit tests.
The shared module should **copy the existing code and adapt it**, not rewrite from scratch.
Specific files to port:

| Source file | Target in shared module | Adaptation needed |
|---|---|---|
| `io.casehub.desiredstate.yaml.resolver.VariableResolver` | `io.casehub.yaml.core.resolver.VariableResolver` | Remove MicroProfile Config direct dependency — accept pluggable `VariableSource` chain instead. Remove domain-specific prefix handling (`match.*`, `fault.*`) — use deferred prefix registry. |
| `io.casehub.desiredstate.yaml.resolver.UnresolvedVariableException` | `io.casehub.yaml.core.resolver.UnresolvedVariableException` | Package move only. |
| `io.casehub.desiredstate.yaml.ForEachExpander` | `io.casehub.yaml.core.foreach.ForEachExpander<E>` | Genericize over element type (currently hardcoded to `YamlNode`/`DesiredNode`). Extract domain-specific node compilation into a callback interface. Remove ObjectMapper dependency (J2CL constraint). |
| `io.casehub.desiredstate.yaml.model.YamlIterationGroup` | `io.casehub.yaml.core.foreach.IterationGroup` | Package move, rename to drop `Yaml` prefix. |
| `io.casehub.desiredstate.yaml.YamlGraphRecorder.isTruthy()` | `io.casehub.yaml.core.condition.Truthiness.isTruthy()` | Extract static method to its own utility class. |

**Tests to port** (same copy-and-adapt approach):

| Source test | Adaptation |
|---|---|
| `ForEachExpanderTest` | Replace `YamlNode`/`DesiredNode` with test record implementing generic interface |
| `YamlConditionalEvaluationTest` | Minimal — tests `isTruthy()` directly |
| VariableResolver tests (inline in `YamlGraphRecorderTest`) | Extract to standalone `VariableResolverTest` |

## Module Structure

```
casehub-yaml-core/
  src/main/java/io/casehub/yaml/core/
    resolver/
      VariableResolver.java        — pluggable resolution chain
      VariableSource.java           — @FunctionalInterface: String resolve(String name)
      UnresolvedVariableException.java
    foreach/
      ForEachExpander.java          — generic <E> expansion loop
      ForEachAdapter.java           — @FunctionalInterface: domain provides stamp/getId/getForEach
      IterationGroup.java           — record: as, in
      ExpansionResult.java          — record: expanded elements, excluded IDs
    condition/
      Truthiness.java               — isTruthy(String)
    data/
      CsvDataSource.java            — record: name, columns, rows
      CsvColumn.java                — record: name, CsvColumnType
      CsvColumnType.java            — enum: STRING, INTEGER, BOOLEAN, DECIMAL
      CsvParser.java                — parse CSV with typed column headers
  src/test/java/...
```

**Maven coordinates:**

| Element | Value |
|---|---|
| groupId | `io.casehub` |
| artifactId | `casehub-yaml-core` |
| parent | `casehub-parent` |

**Dependencies:** None (pure Java). The J2CL constraint prohibits reflection, CDI, Jackson,
ConcurrentHashMap, Thread, and synchronized blocks in core logic.

## Primitive 1 — Variable Resolution

### Current state (desiredstate)

`VariableResolver` in `desiredstate/yaml/runtime/` handles `${prefix.name}` expressions.
Resolution chain is hardcoded: module params → inline variables → MicroProfile Config.
Domain-specific prefixes (`match.*`, `fault.*`) throw with domain-specific error messages.

**Source:** `io.casehub.desiredstate.yaml.resolver.VariableResolver` (205 lines)

### Current state (pages)

`VariableContext` in `pages/backend/scenario-runtime/` handles `${stepName.field}` expressions.
Resolution is step-result scoped: `stepResults.get(stepName).get(field)`. No prefix system,
no forEach support, no pluggable chain.

**Source:** `io.casehub.pages.scenario.runtime.VariableContext` (73 lines)

### Shared design

```java
@FunctionalInterface
public interface VariableSource {
    String resolve(String name);
}
```

```java
public class VariableResolver {
    private static final Pattern VAR_PATTERN = Pattern.compile("\\$\\{([^}]+)}");

    private final Map<String, VariableSource> prefixSources;  // prefix → resolver
    private final Set<String> deferredPrefixes;                // pass through unresolved
    private final Map<String, String> eachContext;             // forEach iteration values
    private final Map<String, Map<String, Object>> eachRowContext; // CSV row iteration

    // Pluggable construction
    public VariableResolver(Map<String, VariableSource> prefixSources,
                            Set<String> deferredPrefixes) { ... }

    // Child resolvers (immutable — return new instances)
    public VariableResolver withEachContext(Map<String, String> eachContext) { ... }
    public VariableResolver withEachRowContext(Map<String, Map<String, Object>> rowContext) { ... }
    public VariableResolver withScope(String prefix, VariableSource source) { ... }

    // Resolution methods (ported from desiredstate VariableResolver)
    public String resolveString(String template, String elementContext) { ... }
    public Map<String, Object> resolveMap(Map<?, ?> input, String elementContext) { ... }
    public List<?> resolveList(List<?> input, String elementContext) { ... }
}
```

**Key adaptation from desiredstate:**
- `inlineVariables` + `config` + `moduleScope` → single `prefixSources` map with ordered lookup
- `match.*`, `fault.*` hardcoded throws → `deferredPrefixes` set (silently pass through)
- `each.*` resolution unchanged — `eachContext` holds simple string values
- New: `eachRowContext` for CSV row iteration — `${each.env.name}` resolves field from row map

**Domain configuration examples:**

```java
// Desired-state configures:
var resolver = new VariableResolver(
    Map.of("var", chain(moduleParams, inlineVars, configSource)),
    Set.of("match", "fault"));   // deferred — domain handles later

// Scenario configures:
var resolver = new VariableResolver(
    Map.of("params", callerContext, "step", stepResults),
    Set.of());                    // no deferred prefixes
```

**Error model:** `UnresolvedVariableException(variableName, elementContext, detail)` — ported
directly from desiredstate. Unrecognised prefixes (not in `prefixSources` and not in
`deferredPrefixes`) throw with a clear message listing available prefixes.

## Primitive 2 — ForEach Expansion

### Current state (desiredstate)

`ForEachExpander` in `desiredstate/yaml/runtime/` is a 271-line static utility tightly coupled
to `YamlNode`, `DesiredNode`, `NodeSpec`, `NodeSpecRegistry`, and `ObjectMapper`. It handles:
- Inline forEach: `forEach: {as: "region", in: ["us-east", "eu-west"]}`
- Named group reference: `forEach: groupName`
- Stamped ID convention: `originalId.value`
- `when` + `forEach` interaction (per-stamped-copy evaluation)
- Dependency wiring across stamped/non-stamped nodes (same-group, cross-group)
- Safety limit: `maxExpansion` parameter

**Source:** `io.casehub.desiredstate.yaml.ForEachExpander` (271 lines)

### Shared design

The expansion loop is generic over element type `E`. Domains provide an adapter:

```java
@FunctionalInterface
public interface ForEachAdapter<E> {
    E stamp(E template, String stampedId, VariableResolver scopedResolver);
    Object getForEach(E element);
    String getId(E element);
    String getWhen(E element);
}
```

```java
public record ExpansionResult<E>(
    List<E> elements,
    Set<String> excludedIds
) {}
```

```java
public class ForEachExpander<E> {
    public ExpansionResult<E> expand(
            Map<String, E> elements,
            Map<String, IterationGroup> iterationGroups,
            VariableResolver resolver,
            ForEachAdapter<E> adapter,
            int maxExpansion) { ... }
}
```

**Key adaptation from desiredstate:**
- `YamlNode` → generic `E` with `ForEachAdapter<E>` callbacks
- `DesiredNode` creation, `NodeSpec` resolution, `ObjectMapper.convertValue()` → moved into the
  adapter's `stamp()` method. The shared core doesn't know about domain types.
- Dependency wiring (lines 156-207 in current ForEachExpander) — **not extracted**. This is
  graph-specific logic. Desired-state keeps its own dependency wiring that calls the shared
  expander for element expansion, then wires dependencies itself.
- `when` evaluation (truthiness check + exclusion tracking) — extracted into the shared loop.
  The adapter provides `getWhen(E)`, the expander evaluates it.
- `ObjectMapper` dependency removed — the adapter handles any serialisation needed in `stamp()`.
- JSON array parsing for variable-resolved group values — stays in desiredstate's adapter
  (domain-specific, needs ObjectMapper).

**Ported behaviour (must match desiredstate test coverage):**
- Inline forEach stamps N copies with `originalId.value` IDs
- Named group forEach references shared `IterationGroup`
- Variables in `forEach.in` values resolved before expansion
- `when` evaluated per stamped copy (after `each.*` resolution)
- `maxExpansion` limit enforced per template
- Excluded elements tracked in `excludedIds`

## Primitive 3 — Conditional Inclusion (when)

### Current state

`isTruthy()` is a static method in `YamlGraphRecorder` (desiredstate):

```java
static boolean isTruthy(String value) {
    return switch (value.toLowerCase()) {
        case "true", "yes", "on", "y", "1" -> true;
        case "false", "no", "off", "n", "0" -> false;
        default -> throw new IllegalArgumentException(
                "when: condition resolved to '" + value
                + "' which is not a boolean value. "
                + "Expected: true/false/yes/no/on/off/y/n/1/0");
    };
}
```

### Shared design

```java
public final class Truthiness {
    private Truthiness() {}

    public static boolean isTruthy(String value) {
        return switch (value.toLowerCase(java.util.Locale.ROOT)) {
            case "true", "yes", "on", "y", "1" -> true;
            case "false", "no", "off", "n", "0" -> false;
            default -> throw new IllegalArgumentException(
                "Condition resolved to '" + value
                + "' which is not a boolean value. "
                + "Expected: true/false/yes/no/on/off/y/n/1/0");
        };
    }
}
```

Direct port. Only change: `Locale.ROOT` for consistent case folding (J2CL safe), and
generic error message (not `when:`-specific — the caller knows the context).

**Interaction with forEach:** When both `when` and `forEach` are present on an element,
`when` is evaluated per stamped copy after `${each.*}` resolution. This is handled by the
`ForEachExpander` loop — the `Truthiness` class is just the leaf evaluation.

## Primitive 4 — CSV Typed Data Source

### Current state

**Neither domain has this.** New capability.

### Shared design

```java
public enum CsvColumnType {
    STRING, INTEGER, BOOLEAN, DECIMAL;

    public Object parse(String value, int row, String columnName) {
        return switch (this) {
            case STRING  -> value;
            case INTEGER -> parseInteger(value, row, columnName);
            case BOOLEAN -> Truthiness.isTruthy(value);
            case DECIMAL -> parseDecimal(value, row, columnName);
        };
    }
}

public record CsvColumn(String name, CsvColumnType type) {}

public record CsvDataSource(
    String name,
    List<CsvColumn> columns,
    List<Map<String, Object>> rows
) {}
```

```java
public final class CsvParser {

    /** Parse CSV with typed header row: "name:string,region:string,tier:integer" */
    public static CsvDataSource parse(String name, String csvContent) { ... }

    /** Parse from external file content */
    public static CsvDataSource parseFile(String name, String fileContent) { ... }
}
```

**Header format:** First row declares `columnName:type` pairs. Type validation at parse time —
every cell validated against its declared column type. Errors report row number, column name,
expected type, and actual value.

**Integration with VariableResolver:** When `${each.env.name}` is encountered:
1. Resolver looks up `env` in the each-context
2. If the value is a `Map<String, Object>` (a CSV row), resolves `name` as a field lookup
3. If the value is a `String` (simple forEach), `${each.region}` works as today

This means `eachContext` can hold either `String` values (simple iteration) or
`Map<String, Object>` values (CSV row iteration). The `VariableResolver` handles both
via `eachRowContext`.

**Integration with ForEach:** CSV data sources are referenced in forEach declarations:

```yaml
data:
  environments:
    inline: |
      name:string,region:string,tier:integer,production:boolean
      staging,us-east,1,false
      production,eu-west,2,true

steps:
  - label: "Create environment"
    forEach:
      as: env
      in: environments        # references data block
    when: "${each.env.production}"
```

The domain's compilation pipeline loads the `data:` block, parses CSV sources via `CsvParser`,
and passes them to `ForEachExpander` as iteration sources with row-map values.

## Primitive 5 — Named Iteration Groups

### Current state (desiredstate)

`YamlIterationGroup` is a simple record:

```java
public record YamlIterationGroup(String as, Object in) {
    public List<Object> inAsList() { ... }
}
```

Referenced from `ForEachExpander` to share iteration sources across multiple elements.

### Shared design

```java
public record IterationGroup(String as, Object in) {
    public List<Object> inAsList() {
        if (in instanceof List<?> list) { return List.copyOf(list); }
        if (in instanceof String s) { return List.of(s); }
        if (in == null) { return List.of(); }
        throw new IllegalArgumentException(
            "iterations.in must be a list or string, got: " + in.getClass());
    }
}
```

Direct port with package rename. The `in` field can be a list of strings (inline values)
or a string referencing a data source name. The domain's compilation pipeline resolves
data source references to `CsvDataSource` rows before passing to `ForEachExpander`.

**Top-level declaration:**

```yaml
iterations:
  regional:
    as: region
    in: ["us-east", "eu-west"]
  team:
    as: member
    in: team-members              # references a data: block
```

When multiple elements reference the same group, their stamped IDs align (source.us-east
pairs with ingest.us-east — same-group, not cross-product).

## What This Module Does NOT Include

Domain-specific constructs stay in each domain's own compilation pipeline:

**Desired-state specific:**
- Graph nodes, dependencies, rules, invariants, fault policies, lifecycle phases
- Module imports and the `ModuleExpander`
- `NodeSpec` registry and `NodeSpecRegistry`
- `${match.*}` and `${fault.*}` resolution (registered as deferred prefixes)
- Dependency wiring across stamped/non-stamped nodes
- `ObjectMapper` usage for spec conversion

**Scenario specific:**
- Steps, commands, chapters/sections, triggers, ARIA targets
- Executor dispatch and script call composability
- `${step.*}` result interpolation (registered as a prefix source)
- Acyclic validation, labels/metadata, readiness checks

**Compilation orchestration:**
- Desired-state: modules → forEach → rules → invariants
- Scenario: params → data → forEach → call → validate

## J2CL Compatibility Constraint

The shared core must be J2CL-transpilable (see `casehub-pages` frontend constraint):

- No `java.lang.reflect` — no reflection
- No `ConcurrentHashMap` — use plain `HashMap`
- No `Thread`, `Lock`, `synchronized`
- No CDI annotations in core logic
- No Jackson in core logic — accept parsed maps, not JSON strings
- `Records` and `sealed` interfaces are fine
- Prefer `List.of()`, `Map.of()`, `Map.copyOf()`
- No `MicroProfile Config` — accept `VariableSource` function instead

The caller (server-side Quarkus code) bridges CDI/Config/Jackson to the core's pure-Java
interfaces.

## Downstream Migration Path

### Desired-state migration

Once the shared core exists, desired-state ports by:

1. Replace `io.casehub.desiredstate.yaml.resolver.VariableResolver` with the shared
   `VariableResolver`. Configure chain as: `var` → `chain(moduleParams, inlineVars, configSource)`.
   Register `match` and `fault` as deferred prefixes.
2. Replace `ForEachExpander` with the generic version. Provide a `ForEachAdapter<YamlNode>`
   that handles `NodeSpec` resolution, `ObjectMapper.convertValue()`, and `DesiredNode` creation.
   Keep dependency wiring in desiredstate's own code (calls shared expander for element
   expansion, then wires dependencies).
3. Replace `isTruthy()` with `Truthiness.isTruthy()`.
4. `YamlIterationGroup` → depend on `IterationGroup` from shared module.
5. Add CSV data source support via the `data:` block (new capability).

### Scenario automation migration

1. Replace `VariableContext` with the shared `VariableResolver`. Configure chain as:
   `params` → callerContext, `step` → stepResults source.
2. Adopt `ForEachExpander` with a `ForEachAdapter<ScenarioStep>` for step-level iteration.
3. Adopt `when` via `Truthiness.isTruthy()` for conditional step inclusion.
4. Adopt CSV data sources for data-driven test scenarios.

### Migration is separate work

Each downstream repo migrates and adopts independently. This spec covers only the shared
module. File separate issues on `casehubio/desiredstate` and `casehubio/pages` for migration.

## References

- `io.casehub.desiredstate.yaml.resolver.VariableResolver` — existing variable resolver (205 lines)
- `io.casehub.desiredstate.yaml.resolver.UnresolvedVariableException` — error model
- `io.casehub.desiredstate.yaml.ForEachExpander` — existing forEach expansion (271 lines)
- `io.casehub.desiredstate.yaml.model.YamlIterationGroup` — existing iteration group record
- `io.casehub.desiredstate.yaml.YamlGraphRecorder.isTruthy()` — existing truthiness check
- `io.casehub.pages.scenario.runtime.VariableContext` — pages variable context (73 lines)
- `ForEachExpanderTest` — existing test coverage for forEach expansion
- `YamlConditionalEvaluationTest` — existing test coverage for when conditions
