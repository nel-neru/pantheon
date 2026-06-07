# PHASE 5+ KICKOFF — Pantheon Group Structure & Monetization Strengthening

**For autonomous implementation agents (Claude Code, etc.)**

**Single file to start with**: Point an agent at this file and say:

> 「始めて」または「Begin Phase 5 work on group governance and monetization. Follow this kickoff.」

This file + the two documents it references contain everything needed to understand the mission, constraints, direction, research seeds, and how to proceed productively.

## Mission (in one paragraph)

After the current Phase 0-4 work (trust/safety recovery, Atlas as self-improvement fuel, real SelfImprovementLoop through PreTask, universal PreTask routing + learning, state hygiene) is sufficiently complete, extend Pantheon so that:

- The **Meta-Improvement Organization + Platform** act as a real **HQ** that can diagnose, structurally intervene in, and strengthen other Organizations.
- **Revenue-focused Organizations** (affiliate marketing, SNS account growth, Note/content sales, etc.) become first-class citizens that can be instantiated, given goals, improved via the same proposal/policy/execution machinery, and produce real value.
- The overall system creates a recursive flywheel: better HQ → better child org designs and tooling → real-world outcomes and learnings → even better HQ and platform.

The core philosophy must remain: elegant generalization of the existing **analyze → ImprovementProposal → PolicyEngine → (PreTask-routed) execution + learning** loop, not new parallel systems.

## Required Reading (read these in order, completely)

1. This file (`docs/plans/phase5-kickoff.md`) — the mission and operating instructions.
2. `docs/plans/group-monetization-implementation-plan.md` — the detailed phased implementation plan (especially the Cross-Cutting Requirements, Planning Document Hygiene rule, Concrete follow-ups, and current tasks). 
3. `docs/plans/group-monetization-vision.md` — the pure high-level vision for this specific group/monetization effort (Core Idea of HQ + revenue child orgs, recursive flywheel, abstract guiding principles, and pre-existing architectural grounding). It is kept in plans/ (not design/) because it is tied to the current planning work and may be archived or integrated after implementation. It contains no current-phase details or transient tasks.
4. `docs/plans/phase5-inspiration-trending-agents-2026.md` — curated 2025-2026 trends in self-evolving agents, hierarchical orchestration, and content/monetization automation, with adaptation ideas for Pantheon.

After reading the above three, you may need to explore more of the codebase and do fresh research.

## Non-Negotiable Invariants (never break these)

- Every new Python file starts with `from __future__ import annotations`.
- All datetimes use `datetime.now(timezone.utc)`.
- `SpecialistAgent.skills`: minimum 2, maximum 3.
- Global state in `~/.pantheon`, per-Organization state in `<target_repo>/.pantheon` (or platform_home fallback when no target_repo).
- **All production execution paths must go through PreTaskOrchestrator + PolicyEngine** (this is the entire point of the ongoing 0-4 work). No bypasses for "meta" or "revenue".
- Preserve explicit 404 handling in `web/server.py` and full test collection (`python -m pytest tests/ -q` must still work).
- Prefer extending the existing proposal + policy + GenericSkillAgent + Organization model + skill YAML system.
- For any new major flow or architecture change: update `core/atlas/data/flows.json`, this kickoff/roadmap, and relevant docs. Treat this as mandatory (Phase 4 discipline).
- **Planning Document Hygiene**: When creating additional planning artifacts during this work, place them under `docs/plans/` (not `docs/design/`). Follow the rules in `docs/plans/README.md` and the Cross-Cutting section of the main roadmap. At the end of the work, ensure key decisions are folded into permanent docs and the transient planning files are cleaned/archived.
- **Explicit required deliverables for this work (Claude must implement)**:
  - Create `scripts/check_planning_docs.py` (simple validator in the style of other scripts/check_*.py). It should detect planning-stage documents (kickoff, inspiration, WIP, phase-specific planning) placed in `docs/design/` instead of `docs/plans/`, and exit non-zero with clear messages. Follow the exact "Planning Document Hygiene" rule described in the roadmap.
  - Update `AGENTS.md` to document the Planning Document Hygiene rule as a project-wide convention (add it to the development norms / new-feature pattern section).
  - Wire the checker into enforcement (at minimum document how to call it from pre-commit / existing hooks in `scripts/hooks/` or `.claude/hooks/`, and ideally add a call so that "creating a new planning document triggers a warning" in the spirit of Phase 4's flows.json discipline).
  - Ensure that after these changes, running the checker on the current tree passes, and future planning work will be guided to `docs/plans/`.
- Safety and auditability first — especially anything that could affect real money, public posting, or other Organizations.

## Current Reality Snapshot (what the codebase actually has today)

- PlatformStateManager is already framed as "本社" managing "子会社" Organizations.
- Meta-Improvement Organization exists with an explicit HQ-like purpose and a department structure modeled on corporate evolution/research functions (`config/departments/meta_improvement.yaml`).
- GroupHQState, shared knowledge, MultiOrgExecutor, CrossOrgCollaborator, OrgGoalManager, and OrgSelfDiagnostics exist but are thin.
- The improvement machinery (ImprovementProposal, CodeReviewAgent, ImprovementExecutorAgent, PolicyEngine with empty_file_path auto-reject, etc.) is heavily optimized for code files inside a `target_repo_path`.
- Goal pipeline, OrganizationDesigner, and task templates are software-engineering centric.
- No native revenue skills or non-code-first org templates yet.
- Most multi-org "management" today is passive storage rather than active HQ strengthening.

Phases 0-4 are fixing the trustworthiness and learning loop that will make Phase 5+ actually compound instead of accumulating technical debt or safety holes.

## Research Direction (you must do this)

The 2025-2026 ecosystem is full of relevant patterns:
- Self-evolving loops with proposer → critic/verifier → safe apply + skill extraction (Hermes, EvoAgentX, autoresearch-style, writer-critic patterns).
- Hierarchical supervisor / manager agents that decompose and delegate (CrewAI hierarchical, LangGraph supervisors, MetaGPT role-based "company" simulation — the latter is especially close to Pantheon's Organization model).
- Content and monetization automation that treats git-backed markdown/assets/scripts as the workspace, with generate-review-apply loops (often stopping short of fully autonomous external actions until gated).
- GitHub Agentic Workflows (2026) idea: natural language intent in Markdown inside the repo becomes executable agent work.

**Your job**: Use tools (`web_search`, `open_page`, etc.) to go deeper on the projects mentioned in the research inspiration file (and others you discover). Then decide which patterns adapt *elegantly* into Pantheon's existing proposal-driven, policy-gated, skill/YAML, PreTask-learning substrate — without over-engineering or creating bypasses.

Document your key findings and adaptation decisions as you go (update the research file or add notes).

## Suggested First Actions (open-ended — think, then choose or invent better)

After reading the three required files and doing initial research + codebase exploration:

**Strongly recommended minimal high-leverage starting slice (Phase 5)**:
Extend the proposal model and PolicyEngine so that Meta/HQ can generate "structural intervention" proposals targeted at another Organization (e.g. "add a ContentProduction Division with these skills to this affiliate org"). The proposal should be able to flow through the existing (or soon-universal) PreTask + Policy path and result in a safe mutation of the target Organization model.

This demonstrates real HQ → child strengthening using mostly existing machinery.

Other good early slices (pick one or combine after thinking):
- First 2-3 revenue-domain skills (e.g. `audience_growth`, `content_strategy`, `performance_marketing`) + high-quality `skills/*.yaml`.
- Small extension to `OrganizationDesigner` or a new lightweight template so a goal like "create an affiliate content operation" produces a sensible org structure.
- A thin "asset/workspace" review/apply path that can target markdown or scripts inside a designated content workspace (as a generalization of code review).

Do **not** jump straight to external posting or heavy new action surfaces. Build the governance and domain substrate first.

## Operating Rules for This Work

- Start small and valuable. Deliver one clean slice with tests (`tmp_path` + platform_home monkeypatch pattern), flows.json update, and doc updates before expanding.
- Every change must preserve (or improve) the learning loop (pattern recording, knowledge, capability gaps).
- When in doubt, reuse: GenericSkillAgent + existing skills, the proposal model, PolicyEngine, PreTaskOrchestrator, Organization/ Division/Team model.
- Think recursively about the flywheel: "How does this change make the *next* phase (deeper revenue, controlled actions, outcome feedback) easier and safer?"
- Update this kickoff file, the main roadmap, and the research inspiration file with your decisions, open questions, and new insights.
- If you create new agent definitions or skills, put them in the proper `agents/definitions/` and `skills/` locations following existing patterns.

## What "Success" Looks Like for Early Work

- Meta can propose and (after policy) apply a structural or capability change to a different Organization, and the change is visible and usable.
- A revenue-style Organization (with appropriate skills) can be created from a natural language goal and participate in the normal improvement loop.
- The work feels like a natural evolution of Pantheon's existing soul rather than a bolted-on feature.
- All new flows are properly documented in Atlas/flows.json and this roadmap.

## Now Begin

You have the mission, the constraints, the research seeds, and the suggested entry points.

**Next actions for you**:
1. Confirm you have read the three required files above.
2. Explore the relevant parts of the codebase (start with anything related to ImprovementProposal, PolicyEngine, PreTaskOrchestrator, meta_improvement, cross-org, OrganizationDesigner, skills, and state management).
3. Do fresh research on the trending patterns mentioned.
4. Decide on your first small slice.
5. Think about the design, propose it clearly (in thinking or as a plan), then implement.

The foundation from Phases 0-4 will make whatever you build here significantly more powerful.

Start. Think. Research. Propose. Build carefully.

When you have a clear first step or slice ready, describe it and proceed.

Good luck — this is where Pantheon can become something much larger than a personal code-improvement tool.

---

## 実装ログ — Phase 5 Slice A: HQ 構造的介入（実装済み / 2026-06）

「HQ が子 Organization を構造的に強化する」最小スライスを、既存の
analyze → ImprovementProposal → PolicyEngine → 適用 + 学習 ループの *一般化* として実装した
（並行システムは作らず、コードファイル変更を「組織モデル変更」へ拡張）。

**追加・変更点**
- モデル: `ImprovementProposal` に cross-org 介入フィールド（`target_org_id/name`,
  `source_org_name`, `intervention_type`, `target_kind`, `target_ref`, `intervention_spec`）を
  *additive・Optional* で追加（既存 JSON は後方互換でロード可）。`StructuralInterventionType`
  enum / `STRUCTURAL_INTERVENTION_CATEGORY` / `is_structural_intervention()`。
- ポリシー: `PolicyEngine._check_intervention()` で **cross-org 介入は必ず HUMAN_REQUIRED**
  （rule `intervention.cross_org`）。auto_reject の carve-out を介入にも拡張し、
  `structural_intervention` を human_required カテゴリへ。auto_approve には決して落ちない。
- 適用: `core/orchestration/structural_intervention.py`（純粋・冪等な `apply_intervention_to_org`、
  ロード→system拒否→変更→永続化の `apply_structural_intervention`、PreTask 経由の
  `execute_structural_intervention`、安定 dedupe の `build_intervention_proposal`）。
  専用 `StructuralInterventionExecutorAgent`（LLM 不使用・決定論的）＋ YAML 定義。
  ルーティング: `structural_intervention` プロファイル + skill 要件を登録。
- HQ: `core/hierarchy/hq_interventions.py`（`HQInterventionProposer` が子 org を診断 →
  弱み→介入のヒューリスティックで提案生成 → 子 org の `.pantheon` に保存・dedupe）。
- 面: CLI `pantheon hq diagnose | propose | apply`。既存の `pantheon proposal apply` と
  Web `POST /api/proposals/{org}/{id}/approve` は、空 file_path 棄却の **前に** 構造介入を
  専用 executor へ自動委任（通常提案・通常 meta 提案の挙動は不変）。
- 可視化/規約: `flows.json` に `hq-intervention` フロー追加（Atlas 自動反映）。
  **必須デリバラブル**完了: `scripts/check_planning_docs.py` + PostToolUse フック
  `check-planning-docs.mjs` + `AGENTS.md` の Planning Document Hygiene 規約。
- テスト: `tests/test_hq_intervention.py`（モデル/ポリシー/純粋変更/永続化/PreTask e2e/
  HQ プロポーザ/Web・CLI 統合）, `tests/test_check_planning_docs.py`。全バックエンド回帰なし
  （既知ベースラインのみ）。

**未対応（次スライスの種）**: 弱み→介入の写像は 3 パターンの決定論ヒューリスティックのみ
（LLM ベースの設計提案は Phase 6+）。収益ドメイン skill / org テンプレート（Phase 6）、
非コード asset の review/apply（Phase 7）、成果フィードバック（Phase 8）は未着手。