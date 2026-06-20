# Revenue integrity — NEVER falsify monetization with fake/mock data

**NON-NEGOTIABLE.** Monetization in Pantheon must reflect *only* real, confirmed money/data.
Fabricating, mocking, simulating, or seeding revenue to make the product *look* monetized is
prohibited. This protects the user from acting on illusory profit.

## Hard rules

- **Confirmed revenue = recorded `OutcomeStore` events only.** The single source of truth for
  "確定収益 / profit" is real events recorded into `~/.pantheon/outcomes.json` via manual entry,
  CSV import, or a real collector. `core/metrics/revenue_integrity.assess_revenue_integrity` is the
  one place that computes it; surface confirmed revenue through it, not ad-hoc sums that could mix in
  estimates.
- **Estimates are not revenue.** `analyze_revenue` (forecast), `project_to_target`,
  `analyze_revenue_extended`, and `compute_goal_status` produce *projections/概算*. Any API/CLI/GUI
  that shows them MUST label them as estimates (`estimate: true` + `ESTIMATE_DISCLAIMER`) and MUST NOT
  present them as confirmed revenue. The revenue estimate endpoints already carry these flags — keep them.
- **Collectors never invent numbers.** `core/metrics/revenue_collectors` adapters return `[]` when a
  source is unconfigured (no real data); real revenue arrives only from `revenue_imports/<source>.csv`
  or connected credentials. Do NOT add a collector/seed/demo that emits made-up revenue. (Sample-org
  auto-generation was already removed for the same reason — `POST /api/welcome` creates nothing.)
- **No demo/seed revenue, ever** — not in tests-as-fixtures leaking into prod, not in onboarding, not
  in screenshots-by-default. Tests may construct events in a `tmp_path` store; production code paths
  must not.
- **When there is no confirmed data, say so.** Show `NO_CONFIRMED_REVENUE_WARNING` rather than implying
  a number is real. The GUI shows a "確定収益" badge and a warning banner when `has_confirmed_data` is false.

## How to comply when adding revenue features

- New revenue figure to display as actual? Route it through `assess_revenue_integrity` /
  `OutcomeStore` recorded events.
- New predictive feature? Return `estimate: true` + the disclaimer, label it 概算/予測 in CLI/GUI,
  and keep it visually separated from confirmed revenue.
- New ingestion path? It must carry a real, auditable `source` per record (collector/import/manual);
  never synthesize values.
