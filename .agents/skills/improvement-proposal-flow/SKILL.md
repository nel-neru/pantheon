---
name: improvement-proposal-flow
description: Pantheon's central domain workflow — analyze a repo, generate ImprovementProposals, approve/reject via the Human-in-the-Loop policy, then apply via the executor (branch/PR). Use when working on analyze/proposals/approve/apply, the proposal model, the policy engine, or the improvement executor.
paths:
  - "agents/improvement_executor_agent.py"
  - "agents/code_review_agent.py"
  - "core/state/manager.py"
  - "core/policy/**/*.py"
---

# ImprovementProposal lifecycle

The product's core loop. Touching any stage usually means touching several of these files — read the
actual code for exact method signatures before editing; this skill is the map, not a substitute.

## Stages & owners

1. **Analyze** — `agents/code_review_agent.py` inspects a target repo and emits `ImprovementProposal`
   objects. CLI: `pantheon analyze --org-name <X>`.
2. **Persist / list** — `core/state/manager.py` stores proposals & decisions in the target repo's
   `<repo>/.pantheon/` (per-repo state). CLI: `pantheon proposals --org-name <X>`,
   `pantheon proposal show <id>`.
3. **Decide (Human-in-the-Loop)** — `core/policy/engine.py` (`DEFAULT_POLICY`) gates approval.
   CLI: `pantheon approve ...`, `pantheon proposal reject <id>`. Respect the policy — do not
   auto-apply changes that the policy says require human approval.
4. **Apply** — `agents/improvement_executor_agent.py` applies an APPROVED proposal: writes changes
   **only inside the target repo**, creates a local work branch, and (via `github_integration/`)
   can open a PR. CLI: `pantheon proposal apply <id>`.

## State-location rule (hard)

- Platform/global data → `~/.pantheon`.
- Per-target-repo proposals/decisions/indexes → `<target-repo>/.pantheon`.
  Never write proposal state into the Pantheon source repo.

## Models

`ImprovementProposal` and friends live in `core/models/organization.py`. Keep them Pydantic v2;
add fields with sensible defaults so existing persisted JSON still loads.

## When adding a stage or field

- Update the model, the `state/manager` (de)serialization, and the relevant agent.
- Add a test mirroring the existing proposal tests (they use `tmp_path` + a fake repo).
- If a new CLI verb is needed, use the `/add-cli-command` flow.

## Verify

```
.venv/Scripts/python.exe -m pytest tests/ -q -k "proposal or policy or executor or analyze"
```
