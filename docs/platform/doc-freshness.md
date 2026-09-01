# Documentation Freshness System

How CaseHub prevents documentation from drifting behind code changes.

Three components work together: a detection script identifies candidate-stale
sections, the work-end gate enforces freshness during LLM sessions, and a
GitHub Action catches drift on all other merge paths.

---

## How It Works

Documentation sections declare the code elements they describe via
**structural anchors** in YAML frontmatter:

```yaml
---
capability: notifications
audience: consumer
repo: casehub-platform
anchors:
  classes:
    - io.casehub.platform.notification.NotificationBridge
  spis:
    - io.casehub.platform.notification.spi.DeliveryChannel
  config-keys:
    - casehub.notification.digest.interval
  protocols:
    - notification-delivery-contract
---
```

When an anchored element changes in a branch diff, the detection script flags
the anchoring documentation section as candidate-stale. An LLM adversarial
check then verifies whether the section actually needs updating.

---

## 1. Detection Script

**Location:** `scripts/doc_freshness_core.py` (vendored in parent for CI),
canonical source in `soredium/doc-freshness/doc_freshness_check.py`.

**What it does:**
1. Scans a docs directory for markdown files with YAML frontmatter anchors
2. Takes a list of changed files (from `git diff --name-only`)
3. Matches changed files against anchors to find candidate-stale sections

**Anchor matching rules:**

| Anchor type | Matches when |
|-------------|-------------|
| `classes` | Changed file path ends with the class's expected Java/Kotlin path |
| `spis` | Same as classes — SPI interfaces are just Java files |
| `config-keys` | Any `application.properties`/`.yaml`/`.yml` file changed |
| `protocols` | Protocol name appears in the changed file path |

**Override mechanism:** A `verified-current` annotation in frontmatter
suppresses re-flagging until the next anchor change:

```yaml
verified-current: "2026-08-31 | commit:abc123"
```

**CLI usage:**
```bash
python3 scripts/doc_freshness_core.py  # not a CLI itself — imported by wrappers

# CI wrapper:
python3 scripts/doc-freshness-check-ci.py \
    --diff /tmp/diff-files.txt \
    --docs docs/ \
    --repo casehub-platform

# Anchor integrity check:
python3 scripts/check-anchor-integrity.py \
    --docs docs/ \
    --repo casehub-platform \
    --source-root .
```

**Output:** JSON with candidate-stale sections. Exit code 1 if candidates
found, 0 if clean.

---

## 2. Work-End Gate

**Step:** `doc_freshness_gate` in the work-end orchestrator, positioned after
`impl_doc_sync` and before `adr`.

**Phase:** `closing:review` (runs during the review sweep).

**How it runs:**

1. Generates the branch diff file list:
   `git diff --name-only $BASE_BRANCH...HEAD`
2. Runs the detection script against the project's `docs/` directory
3. If candidates found: reads each flagged section alongside the changed code,
   determines whether an update is needed (adversarial check)
4. Updates stale sections inline or adds `verified-current` annotation

**Current mode: advisory.** Reports findings but does not block the close.
The hard gate activates after the validation corpus confirms detection
precision ≥80% and recall ≥60% (F1 ≥0.69). The validation corpus comes from
the first-wave doc audit of foundation repos.

**Configuration:** The step is in `SWEEP_STEPS` and `PER_REPO_SWEEP_STEPS`,
meaning it can be deselected during the sweep config phase if not relevant
to a particular close.

---

## 3. GitHub Actions

### Dependency Graph (`dependency-graph.yml`)

**Trigger:** Daily at 06:00 UTC + manual dispatch.

**What it does:**
1. Clones all 28+ child repos (shallow, depth 1)
2. Runs `scripts/generate-dependency-graph.py` — parses all `pom.xml` files,
   extracts `io.casehub` dependencies, builds a directed graph
3. Commits `dependency-graph.json` to the parent repo

**Output:** `dependency-graph.json` at the repo root — a map of
`repo → {depends_on: [...], depended_on_by: [...]}`. The work-end gate
reads this to determine which downstream repos need doc checks when an
API module changes.

**Staleness window:** Up to 24 hours for newly added dependencies (daily
schedule). Manual dispatch via `workflow_dispatch` for immediate refresh.

### Doc Freshness Check (`doc-freshness.yml`)

**Type:** Reusable workflow — called from child repos, not triggered directly.

**Child repo caller:**
```yaml
on: pull_request
jobs:
  doc-freshness:
    uses: casehubio/parent/.github/workflows/doc-freshness.yml@main
```

**What it does:**
1. Checks out the child repo + parent repo (for detection scripts)
2. Generates the PR diff file list
3. Runs the doc freshness detection (structural anchor check only — no LLM)
4. Runs anchor integrity check — verifies every anchored class/SPI resolves
   in the codebase. Cross-repo anchors (different `repo` field) are skipped.
5. Posts PR comments for any broken anchors or candidate-stale sections

**Why both CI and work-end?** Work-end has richer context (session memory,
blog history, git log analysis) but only runs for LLM sessions. The GitHub
Action covers human PRs, manual merges, and CI pipeline merges — the four
merge paths to main are all covered between the two.

---

## Adding Structural Anchors to Documentation

When writing or updating a documentation section, add YAML frontmatter:

```yaml
---
capability: <topic-name>
audience: consumer        # or: contributor
repo: casehub-<name>
anchors:
  classes:
    - io.casehub.<package>.<ClassName>
  spis:
    - io.casehub.<package>.spi.<SpiName>
  config-keys:
    - casehub.<module>.<property>
  protocols:
    - <protocol-name-from-garden>
---
```

Every anchor must resolve in the codebase. The CI anchor integrity check
catches broken anchors on every PR.

**Capability chunks** (standalone files under `docs/repos/<repo>/capabilities/`)
always have frontmatter. Guide sections that remain inline in
`consumer-guide.md` do not have frontmatter — they rely on diff-based triage
(the transition fallback) until they are decomposed into chunks.

---

## File Inventory

| File | Purpose |
|------|---------|
| `scripts/doc_freshness_core.py` | Core detection logic (vendored from soredium) |
| `scripts/doc-freshness-check-ci.py` | CI wrapper — runs detection, reports findings |
| `scripts/check-anchor-integrity.py` | Verifies anchored classes/SPIs resolve in source |
| `scripts/generate-dependency-graph.py` | POM analysis → `dependency-graph.json` |
| `scripts/tests/test_doc_freshness_ci.py` | 4 tests for the vendored core module |
| `.github/workflows/dependency-graph.yml` | Daily CI for dependency graph generation |
| `.github/workflows/doc-freshness.yml` | Reusable PR workflow for child repos |
| `docs/capabilities.md` | Cross-repo capability index (discovery entry point) |
| `docs/audit/audit-process.md` | 7-step per-repo audit process template |
