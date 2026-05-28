# Arc42Stories — Architecture Documentation Specification

**Version:** 0.1 (draft)
**Status:** Proposed — seeking community feedback
**Origin:** Extended from [arc42](https://arc42.org) by Gernot Starke & Peter Hruschka
**Maintainer:** Hortora

---

## Why this exists

[arc42](https://arc42.org) has been the gold standard for architecture documentation since 2005. It answers: *what is the system, how is it structured, and why were the key decisions made?*

Arc42Stories extends arc42 to answer three questions arc42 cannot:

1. **How is the system being built incrementally?** — delivery planning, Chapter sequencing, layer impact tracking
2. **How does an LLM pick up a session and know where to continue?** — living document structure fed by session journals
3. **How does an LLM in a completely different domain replicate the same architecture?** — Pattern to replicate per layer entry

These are not cosmetic additions. They reflect a fundamental shift in how software is built: iteratively, with LLM assistance, by teams that rely on structured documentation as shared memory across sessions. Arc42 was designed for a world where an architect wrote documentation once. Arc42Stories is designed for a world where documentation grows continuously alongside the system, serves as context for AI assistants, and enables any capable team to replicate the architecture in a new domain.

**Arc42Stories does not replace arc42.** It extends it. All 12 arc42 sections are preserved. Arc42Stories adds Journeys and Chapters as an evolutionary delivery layer, augments layer entries with replication and wiring knowledge, and defines a session lifecycle that keeps the document current.

---

## Diagrams — C4 with Mermaid

Arc42Stories uses the [C4 Model](https://c4model.com) for visual hierarchy, rendered as [Mermaid](https://mermaid.js.org) diagrams. Mermaid renders natively on GitHub, works inline in `.md` files, and requires no external tooling.

**Four diagram types, used in specific sections:**

| C4 level | Mermaid type | Used in |
|---|---|---|
| System Context | `C4Context` | §3 Context and Scope |
| Container | `C4Container` | §5 Building Block View |
| Component | `C4Component` | §5 per-layer detail; §9.3 Chapter entries |
| Dynamic | `C4Dynamic` | §6 Runtime View; §9.3 Chapter flows |

**Minimal example:**
````markdown
```mermaid
C4Container
  title PR Review System — Container View
  Person(dev, "Developer", "Submits a PR")
  System_Boundary(app, "devtown") {
    Container(api, "Review API", "Quarkus REST", "POST /api/reviews")
    Container(engine, "Case Engine", "casehub-engine", "Opens CasePlanModel instance")
    ContainerDb(db, "Work DB", "H2 / PostgreSQL", "WorkItems, SLA records")
  }
  Rel(dev, api, "POST /api/reviews", "HTTPS")
  Rel(api, engine, "startCase()")
  Rel(engine, db, "WorkItem CRUD")
```
````

**In Chapter entries:** use `C4Component` filtered to elements involved in that Chapter. Colour convention: new elements green (`$tags="new"`), modified yellow (`$tags="modified"`).

**Layout note:** Mermaid's C4 auto-layout can be hard to control for large diagrams. Keep diagrams focused — one Chapter, one layer, or one flow. For large systems, prefer multiple small diagrams over one comprehensive one. For production-grade diagrams requiring precise layout, PlantUML + [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML) is the alternative.

---

## Core Concepts

| Term | Definition |
|---|---|
| **Journey** | A major user or business flow — the overarching story the application tells |
| **Chapter** | A vertical cut through the architectural layers delivering one user-visible capability end-to-end. Chapters are the planning and delivery unit. |
| **Layer** | A horizontal architectural concern — a technical tier, foundation module, or infrastructure component. Layers are the implementation unit. |
| **Delta** | The amount of change a Chapter introduces to a layer: `None` / `Low` / `Medium` / `High` |
| **Accountability gap** | A formal requirement — compliance, audit, or user-visible — not met before this Chapter ships |
| **Pattern to replicate** | Domain-agnostic numbered steps an LLM follows to implement the same layer in a different project |
| **Profile** | A domain- or stack-specific instantiation of Arc42Stories (e.g. CaseHub Profile, Spring Boot Profile) |

**Naming note:** "Chapter" is used deliberately rather than "slice" to avoid confusion with [Vertical Slice Architecture](https://jimmybogard.com/vertical-slice-architecture/) — a code organisation pattern where source code is co-located by feature. Chapters are a documentation and delivery planning concept, not a code organisation pattern. The metaphor is the same — a vertical cut through horizontal layers — but the domain is different.

---

## The Two Principles

### 1. Chapters are the delivery unit; layers are the implementation unit

A Chapter defines a user-visible capability and identifies which layers it requires. To deliver a Chapter: implement each required layer in turn, doing only what the Chapter needs from that layer, until the Chapter works end-to-end. Move to the next Chapter. Deepen a layer further only when a later Chapter requires more from it.

The layer ordering in §9.4 is for *reading* — the sequence a developer follows to understand the system. It is not the build sequence. Build sequence is governed by the Chapter plan.

### 2. Minimal delta sequencing

When sequencing Chapters, apply two criteria in order:

1. **Sequential dependencies first.** Some Chapters can only follow another because the earlier Chapter provides something the later one needs at runtime. Identify these hard constraints before sequencing.

2. **Minimal layer delta next.** Among unblocked Chapters, prefer the one that touches the fewest new layers. Smaller deltas mean smaller, more reviewable delivery steps.

Document soft orderings (Chapters that appear independent but produce artefacts the next one consumes) as rationale, not as blocking constraints.

---

## Document Structure

### §1 Introduction and Goals
*(standard arc42)*

What problem does this application solve? Who are the stakeholders? What are the top quality goals?

### §2 Constraints
*(standard arc42)*

Technical and organisational constraints — compliance requirements, platform dependencies, technology choices imposed externally.

### §3 Context and Scope
*(standard arc42 + C4 System Context diagram)*

System boundaries, external interfaces, and neighbouring systems. Include a C4 System Context diagram.

### §4 Solution Strategy
*(standard arc42, augmented with Chapter sequencing rationale)*

Fundamental decisions shaping the architecture. Include:

- Core architectural patterns and why they were chosen
- Layer taxonomy for this application (see Profiles)
- Journey and Chapter sequencing rationale — which Chapters must precede which, and why

**Chapter sequencing rationale format:**
```
- Chapter N before Chapter M: [hard dependency reason]
- Chapter N and Chapter P: [soft ordering or minimal-delta reason]
```

### §5 Building Block View
*(standard arc42 + C4 Container and Component diagrams)*

Static decomposition of the system. For Arc42Stories, tag each building block with its layer. C4 Component diagrams should use layer colouring to make the horizontal structure visible.

Define each layer and its responsibilities here. The layer taxonomy is stack-specific — see Profiles for pre-defined taxonomies.

### §6 Runtime View
*(standard arc42 + C4 Dynamic diagrams)*

Key behavioral scenarios showing how components interact at runtime.

### §7 Deployment View
*(standard arc42 + C4 Deployment diagram)*

Infrastructure, hosting, and deployment topology.

### §8 Crosscutting Concepts
*(standard arc42)*

System-wide patterns — security, observability, error handling, coding conventions. Reference external protocol documents rather than duplicating them here.

---

### §9 Journeys and Chapters *(Core Extension)*

This section replaces arc42's §9 (Architecture Decisions), which moves to §10.

#### §9.1 Journey Overview

```markdown
| Journey | Description | Chapters | Status |
|---|---|---|---|
| [Name] | [One sentence] | [N] | In progress / Complete |
```

#### §9.2 Chapter Index

Navigable summary of all Chapters in delivery sequence. Link each Chapter name to its full entry in §9.3.

```markdown
| # | Chapter | Journey | Layers touched | Delta summary | Status |
|---|---|---|---|---|---|
| 1 | [Name] | [Journey] | L1, L3 | Low, High | ✅ |
| 2 | [Name] | [Journey] | + L2 | Medium | 🔲 |

**Sequencing rationale:**
- C1 before C2: [hard dependency — C1 provides X that C2 requires at runtime]
- C2 before C3: [soft ordering — C2 generates Y that makes C3 meaningful]
- C3 and C4 independent: [minimal delta — C3 adds one layer vs C4's three]
```

The sequencing rationale lives here — adjacent to the Chapter Index — not only in §4. A reader scanning the index sees *why* things are ordered this way without jumping to another section. §4 Solution Strategy summarises the overall delivery approach; §9.2 holds the per-Chapter rationale.

#### §9.3 Chapter Entries

One entry per Chapter, in delivery sequence.

```markdown
### Chapter N — [Name]

**Journey:** [Parent Journey]
**Sequence:** N of M
**Status:** ✅ complete / 🔲 pending / 🚧 in progress
**Delivered:** [date or sprint]
**Issues:** [issue tracker refs — e.g. org/repo#N]
**Navigation:** `git log --grep="#N" --oneline`
**Blog:** [session blog entry capturing the narrative — e.g. blog/YYYY-MM-DD-title.md]

**Purpose and business value**
[1–2 paragraphs: what this Chapter delivers and why it matters]

**End-to-end readiness**
- Fully end-to-end: Yes / No
- What works after this Chapter ships: [description]
- Next required Chapters: [list]

**Accountability gaps closed**

| Gap | What breaks without it | Layer |
|---|---|---|
| [Requirement not met before this Chapter] | [Consequence] | [Layer that closes it] |

**Layer Impact**

| Layer | Changes in this Chapter | Delta | Notes |
|---|---|---|---|
| [Layer name] | [What changed] | None / Low / Medium / High | New / Extended / Unchanged |

**C4 views for this Chapter**
- Component diagram: filtered view, new elements green, modified yellow
- Dynamic diagram: key flows for this Chapter

**Dependencies and risks**
- Dependencies on other Chapters or external systems
- Technical risks and mitigation
- Architectural debt introduced (if any)
```

#### §9.4 Layer Entries

One entry per layer integrated, in reading order (learning progression — not delivery sequence). Layer entries complement Chapter entries: Chapters show *what was delivered and when*; layer entries show *how each integration was built and how to replicate it in another project*.

```markdown
### Layer — [Name]

**Participates in chapters:** C2, C3, C4, C5
**Architectural patterns:** [names from your architectural patterns reference — e.g. Hexagonal, Clean, DDD, Event-Driven, CQRS-lite, Strategy, Registry, Observer]
**Key protocols:** [governing rules and standards — e.g. flyway-migration-rules.md, module-tier-structure.md]
**Design refs:** [design specs, analysis docs, brainstorm outputs — separate from protocols; e.g. docs/specs/YYYY-MM-DD-topic.md §Section, docs/comparison-analysis.md §Phase]
**Issues:** [issue tracker refs]
**Navigation:** `git log --grep="#N" --oneline`
**Blog:** [session blog entry — e.g. blog/YYYY-MM-DD-title.md]
**Completed:** [date or 🔲 pending]

#### What it adds
[Teaching narrative: what this layer introduces, what gap it closes relative to the
previous layer, contrast with the before state]

#### Accountability gaps closed

| Gap | What breaks without it | Closed by |
|---|---|---|

#### Key wiring
[Non-obvious configuration not visible in code or official documentation.
The things that trip people up. Format: what it is, why it's needed, where to set it.]

#### Gotchas
[What went wrong; what would go wrong without prior knowledge.
Format: **Symptom** → Cause → Fix]

#### Pattern to replicate
[Domain-agnostic numbered steps an LLM follows to implement this same layer
in a different project. Written so that an LLM building in a completely
different domain can follow these steps without knowledge of the original domain.]

1. ...
2. ...
```

Mark pending sections with 🔲 and include a pointer to what will fill them (e.g. `🔲 at Chapter 3 close — blocked on [dependency]`).

---

### §10 Architectural Decisions
*(arc42's §9, moved here — sparse by design)*

Only decisions not captured inline elsewhere. Arc42's rule applies directly: if a decision belongs in a layer entry or Chapter entry, put it there. This section should be sparse — if it grows large, decisions have been placed in the wrong section.

### §11 Quality Requirements
*(standard arc42)*

### §12 Risks and Technical Debt
*(standard arc42)*

- Outstanding risks with mitigation
- Technical debt accumulated across Chapters
- Layer churn observations — layers modified by many Chapters may indicate a boundary problem

### §13 Glossary

Definitions of terms used in this document and in the domain.

---

## Session Lifecycle

Arc42Stories is a living document. It grows with the system across development sessions.

**Working document** (per epic or sprint): A `JOURNAL.md` or equivalent captures in-session reasoning, decisions made, and approaches rejected. This is ephemeral — it exists during the epic and is discarded after.

**Permanent record** (this document): At epic close, two things are distilled from the working document:
1. What was built → Chapter entry and layer entry updated
2. Cross-cutting decisions → §10 if not captured inline

**Rule:** if something is worth remembering between sessions, it belongs in Arc42Stories. If it only mattered during the session, it belongs in the session narrative (blog, diary) or is discarded.

---

## Profiles

A **Profile** is a domain- or stack-specific instantiation of Arc42Stories. A Profile defines:
- The layer taxonomy for the target stack (replaces generic UI/Application/Domain/Persistence)
- Stack-specific protocols and conventions referenced from §8
- Example Journeys and Chapters for the domain

**Defining a Profile:**
```markdown
## Arc42Stories Profile: [Name]

### Layer Taxonomy
| Layer | What it represents | Typical Delta range |
|---|---|---|
| [Layer 1] | [Description] | Low–High |
| [Layer 2] | [Description] | Low–Medium |
...

### Conventions
[Stack-specific conventions for §8 Crosscutting Concepts]

### Example Journey and Chapters
[A worked example showing the profile in use]
```

**Available Profiles:**
- [Arc42Stories CaseHub Profile](arc42stories-casehub-profile.md) — CaseHub agentic harness applications
- *(More profiles welcome — contribute via Hortora)*

---

## Comparison with arc42

| Concern | arc42 | Arc42Stories |
|---|---|---|
| Static architecture description | ✅ §1–8, 10–12 | ✅ same sections |
| Delivery planning | ❌ | ✅ Journeys + Chapters (§9) |
| Layer × delivery intersection | ❌ | ✅ Chapter Layer Impact table |
| LLM session continuity | ❌ | ✅ living document + session lifecycle |
| LLM replication in new domain | ❌ | ✅ Pattern to replicate per layer entry |
| Non-obvious wiring knowledge | ❌ | ✅ Key wiring per layer entry |
| Known failure modes | ❌ | ✅ Gotchas per layer entry |
| Accountability / gap tracking | ❌ | ✅ Accountability gaps per Chapter |
| Minimal delta planning | ❌ | ✅ §4 sequencing rationale |

---

## References

- [arc42](https://arc42.org) — Starke & Hruschka, 2005–present
- [arc42 §9 — only decisions not described elsewhere](https://docs.arc42.org/section-9/)
- [C4 Model](https://c4model.com) — Simon Brown
- [Vertical Slice Architecture](https://jimmybogard.com/vertical-slice-architecture/) — Jimmy Bogard (distinct from Arc42Stories Chapters)
- [Arc42Stories CaseHub Profile](arc42stories-casehub-profile.md)
