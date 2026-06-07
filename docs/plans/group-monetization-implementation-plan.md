# Pantheon Group Structure & Monetization Implementation Plan
**Detailed phased work for the current effort (Post-Phase 0-4)**

**Status**: Active implementation planning document. To be updated as work progresses, then archived/cleaned after completion (enduring vision extracted to `docs/design/group-monetization-vision.md`).
**Date**: 2026 (aligned with current recovery work)
**Owner**: User + agents working on the phased recovery
**Prerequisites**: Completion (or strong progress) on user's defined Phases 0-4 is **mandatory** before heavy investment here.

**Note**: The high-level vision for this specific effort lives alongside in `docs/plans/group-monetization-vision.md` (also under plans/ because it is tied to the current planning and may be archived after implementation). This file focuses on the tactical phased breakdown, current tasks, hygiene rules, and enforcement ideas.

## Guiding Principles

1. **Trust substrate first**. Phases 0-4 (Policy universal enforcement, Atlas as fuel, real SelfImprovementLoop via PreTask, universal PreTask routing + learning accumulation, state/maintenance hygiene) create a trustworthy self-improving engine. Any group or monetization work built on a broken core will amplify risk (especially once real money, accounts, or public posting is involved).

2. **HQ strengthens the substrate and designs, not (initially) executes revenue actions**. The most powerful use of the "group company" vision is:
   - Meta-Improvement Organization (HQ) + Platform become excellent at *designing, diagnosing, and continuously improving* other purpose-driven Organizations.
   - Revenue orgs (affiliate, SNS growth, Note sales, etc.) specialize in their domain.
   - Early value comes from Meta improving the *automation code, workflows, prompts, org structures, and tools* that revenue orgs use, rather than Pantheon directly controlling external accounts.

3. **Recursive flywheel over flat multi-org**. A real group structure creates compounding: better HQ → better child org designs and capabilities → real-world outcomes and learnings → better HQ designs and platform capabilities.

4. **Generalize the improvement contract, don't bolt on exceptions everywhere**. The analyze → proposal → PolicyEngine → execute loop (strengthened in 0-4) must be extended cleanly rather than special-cased to death.

5. **Safety and auditability remain non-negotiable**. Every new path (structural intervention on another org, content asset change, external action) **must** route through the universal PreTaskOrchestrator + PolicyEngine that Phases 0/3 are enforcing. No bypasses.

6. **State and artifacts discipline**. Follow Phase 4 spirit: flows.json / subsystem_maps.json updates are mandatory for new flows. Atlas introspect coverage is required. Prefer JSON as primary where it already is (per-repo .pantheon and platform orgs), make SQLite decision explicit.

## Current Architectural Reality (Grounding)

- PlatformStateManager is already documented as "本社" managing "子会社" Organizations globally in `~/.pantheon/organizations/`.
- Meta-Improvement Organization exists with purpose "Pantheon システム全体の強化・改善・自己進化を担う中核 Organization", auto-created, `is_system=True`, and wired to the core repo.
- `meta_improvement.yaml` is deliberately modeled on large corporate HQ functions (org evolution research, agent architecture, tool integration, QA, performance optimization, knowledge management across the group).
- GroupHQState, shared knowledge, MultiOrgExecutor, CrossOrgCollaborator, OrgGoalManager, and OrgSelfDiagnostics exist but are thin or under-used for actual HQ-to-child governance.
- ImprovementProposal + ImprovementExecutorAgent + CodeReviewAgent are heavily optimized for `file_path` inside a `target_repo_path` (code changes + git branch/PR). `policy/engine.py` still has `auto_reject` on empty `file_path`.
- Goal* pipeline, OrganizationDesigner, and task templates are SE-domain heavy.
- No native revenue skills, revenue org templates, or non-code action surface.
- Most "management" of multiple orgs today is passive (store + shared knowledge) rather than active governance/strengthening.

Phases 0-4 directly address the biggest trust, learning, and proposal quality issues that would otherwise make any ambitious group/monetization layer brittle or unsafe.

## Recommended Phased Plan (Continuing from 0-4)

### Phase 5: Group Governance Activation (Make HQ real)
**Goal**: Turn "Platform + Meta" into an *active* headquarters that can diagnose, intervene in, and strengthen other Organizations structurally — not just improve Pantheon's own code.

> **STATUS (2026-06): Slice A 実装済み.** 構造的介入提案（モデル拡張 + PolicyEngine
> `intervention.cross_org` ルール）、`HQInterventionProposer`（診断→提案）、PreTask 経由の
> 構造介入 executor による安全な org モデル変更 + 永続化、`pantheon hq` CLI、既存 approve/apply
> （CLI + Web）への自動委任、`hq-intervention` フロー（flows.json）、テスト一式を実装。
> 詳細は `docs/plans/phase5-kickoff.md` の実装ログ参照。残り（cross-org 学習伝播・group
> ダッシュボード拡張・LLM ベース介入設計）は後続スライス。

**Key Work**:
- **Proposal model generalization** (builds directly on Phase 1 meta proposals):
  - Extend `ImprovementProposal` (or introduce parallel `OrgInterventionProposal` / keep one model with new fields):
    - `is_meta: bool`
    - `target_org_id` or `target_org_name`
    - `intervention_type`: "structural" | "capability_injection" | "goal_setting" | "knowledge_injection" | "org_redesign" | "performance_review"
    - `target_kind`: "code_file" | "org_structure" | "content_asset" | "knowledge" | "external_action"
    - `target_ref`: flexible identifier (file path, division name, skill set, campaign id, etc.)
  - Update `PolicyEngine` (Phase 0 work) with rules for meta interventions (still default to HUMAN_REQUIRED for anything that mutates another org; allow auto for low-risk knowledge sharing).
- **HQ diagnostic & intervention cycle**:
  - Extend `OrgSelfDiagnostics` or add `HQOrgDiagnostics` that can pull state from any child org via PlatformStateManager.
  - New (or GenericSkillAgent-powered) HQ specialists using existing high-value skills: `org_design`, `strategic_planning`, `corporate_research`, `performance_analysis`, `knowledge_curation`.
  - Meta periodically (via scheduler or new `hq_cycle`) runs cross-org analysis, generates intervention proposals targeted at specific child orgs, and persists them (to Meta's state or the child's pending proposals with provenance).
- **Structural application path** (safer than direct external actions):
  - "Apply" for org_structure interventions can mutate the child's `Organization` model (add Division/Team/Agent, update skills, set goals via OrgGoalManager) and save it.
  - This is high-leverage for the group vision and stays inside Pantheon's state model.
- **Cross-org learning & pattern propagation**:
  - Strengthen shared knowledge with org-to-org tags.
  - Make orchestration_pattern_store and capability history queryable by "similar org types".
- **Group visibility**:
  - Enhance web dashboard / CLI to show GroupHQState + child org health + pending HQ interventions.
  - Extend metrics (balanced_growth etc.) with cross-org views.

**Deliverables**:
- Updated models + policy rules.
- HQ intervention flow (proposal generation → policy → structural apply).
- Tests using tmp_path + monkeypatch for platform_home.
- flows.json entry for the new "hq_intervention" / "cross_org" flow (per Phase 4 discipline).
- Atlas coverage for the governance surfaces.

**Dependencies on 0-4**: Phase 0 (policy for new proposal shapes), Phase 1 (Atlas/meta proposals as example), Phase 2/3 (PreTask + recording so HQ interventions also learn and improve), Phase 4 (state clarity).

**Risk if skipped**: "Group structure" remains aspirational docs + thin collaborator classes. Meta only improves itself.

### Phase 6: Revenue Domain Substrate Enablement
**Goal**: Make it possible to instantiate and run first-class non-SE "monetization Organizations" (affiliate, SNS nurture, Note/content sales, etc.) without the core machinery rejecting them or forcing everything into code-review shape.

**Key Work**:
- **Skills expansion** (easy win, high signal):
  - Add to `AgentSkill` enum: `CONTENT_STRATEGY`, `COPYWRITING`, `AUDIENCE_GROWTH`, `PERFORMANCE_MARKETING`, `PUBLISHING`, `CAMPAIGN_OPTIMIZATION`, `AFFILIATE_OPTIMIZATION` (or similar — keep to ~10-12 total).
  - Create matching `skills/*.yaml` with strong personas, focus, output_hints (e.g. "あなたはデータ駆動のコンテンツストラテジスト..." for affiliate funnels, compliance, LTV thinking, etc.).
  - Update `AgentSkillEngine`, CapabilityRegistry scan, TASK_SKILL_REQUIREMENTS, TASK_ORCHESTRATION_PROFILES, and any hardcoded skill lists in goal decomposer / LLM prompts.
- **Organization templates & designer**:
  - Add revenue-oriented templates (new files under `config/departments/` or loaded via designer): e.g. `affiliate_marketing.yaml`, `content_operations.yaml`, `sns_growth.yaml`.
  - Or extend `OrganizationDesigner` with LLM + heuristic branches for "affiliate", "content sales", "audience building".
  - Meta's own "組織進化研究部" (in meta_improvement.yaml) can be tasked with researching and proposing these templates.
- **Goal pipeline revenue support**:
  - `GoalType.REVENUE`, `GoalType.CONTENT_OPERATIONS`, `GoalType.GROWTH` in goal_parser.py.
  - Corresponding templates in goal_decomposer.py (research niche/offer, content calendar design, funnel copy, measurement setup, optimization loops — expressed as tasks that can use the new skills).
  - Update OrgInstantiator mapping and name generation.
- **Proposal / change model for non-code**:
  - The fields from Phase 5 (`target_kind`, `target_ref`, `is_meta`) allow proposals like:
    - "Rewrite this landing page section" targeting a markdown file in a content workspace.
    - "Add new audience segment workflow" as org_structure.
    - "Generate 7-day content calendar for X niche" as knowledge/asset.
  - Relax `CodeReviewAgent` collection logic or create parallel `AssetReviewAgent` / `ContentReviewAgent` that can operate on markdown, scripts, data files, etc.
  - `ImprovementExecutorAgent` or a new sibling needs safe "apply non-code change" (write within designated workspace paths, never arbitrary fs).
- **State for non-repo or content-focused orgs**:
  - Make `get_org_state_manager` and flows robust when `target_repo_path` is None or points to a content/git-backed workspace (not a Python/TS codebase).
  - Consider a lightweight "workspace" concept for pure content orgs (still benefits from git for versioning proposals/decisions).
- **Policy updates** (leverage Phase 0):
  - `empty_file_path` auto-reject should only apply to traditional code improvement proposals, not meta/structural/domain proposals.
  - Add category or tag rules for revenue-sensitive actions (e.g. anything touching publishing or money requires human).

**Deliverables**:
- New skills + at least 1-2 revenue org templates.
- Updated designer + goal pipeline for revenue goals.
- Generalized proposal shape + at least one non-code reviewer/executor path.
- Example "Affiliate Operations Organization" that can be instantiated via `pantheon goal` or designer.
- Atlas / flows.json updates for the new domain flows.
- Tests (including one that creates a revenue-style org with no or minimal target_repo and runs a goal through it).

**Dependencies on 0-4**: Phase 1 (meta proposals give the pattern for "special proposals"), Phase 2/3 (PreTask routing + learning must cover the new skills and task types so revenue orgs also get better over time), Phase 4 (state hygiene prevents weirdness when orgs have different target shapes).

### Phase 7: Controlled External Action Surface (Value Creation)
**Goal**: Give revenue orgs (and the HQ when intervening) safe, auditable ways to affect the real world, without turning Pantheon into an unsecured automation platform.

**Key Work** (start narrow):
- **Internal-to-workspace actions first** (lowest risk, highest immediate value):
  - For orgs whose `target_repo_path` is a content + scripts workspace: safe generation + application of articles, threads, landing copy, email sequences, tracking setups, etc.
  - These still produce artifacts that can be versioned, reviewed via the strengthened proposal flow, and "executed" by external schedulers or the child org's own lightweight runners.
- **Scripted / delegated execution**:
  - HQ or child org proposes "add this automation script + schedule" inside the workspace.
  - Actual cron / external runner / wmux / scheduled task lives outside the core loop but is generated and versioned under Pantheon control.
- **Read-first analytics & feedback**:
  - Pullers for platform analytics (Note sales, affiliate dashboards, social insights) that land data into the org's knowledge or platform shared insights. This fuels Phase 8.
- **Later / gated: narrow publish actions**:
  - Only after strong policy + human gates + audit, introduce controlled "publish" tools (e.g. via child-provided credentials or local tools).
  - Use existing MCP/Playwright/wmux surface carefully; all invocations must be recorded and go through PreTask + Policy.
- **Policy & safety extensions**:
  - New policy dimensions for "external effect" proposals (money movement, public posting, account actions).
  - Strong preference for "propose the change + human (or very narrow auto) approves the *act* of execution".
- **Scheduling for revenue rhythms**:
  - Extend AutonomousScheduler or add revenue-specific cycles (daily planning, weekly review + optimization proposal generation) that Meta can also oversee.

**Deliverables**:
- Workspace-safe asset apply path.
- At least one revenue outcome puller (as a tool/skill).
- Policy rules for external-effect category.
- Example end-to-end for a content workspace org (generate calendar → review proposals → apply assets → "run" via script in the workspace).
- flows.json + Atlas coverage.

**Dependencies**: Phases 0-3 (universal policy + PreTask + recording are the only things that make external actions safe to add). Phase 5/6 (you need the group governance and domain substrate before the actions have meaning).

**Strong recommendation**: Do *not* implement real publishing/posting until the self-improvement loop (Phase 2) is reliably producing high-quality proposals and the policy surface (Phase 0) has been battle-tested on meta interventions.

### Phase 8: Closed Flywheel & Economic Feedback (The Real Group Compounding)
**Goal**: Make outcomes from revenue orgs flow back into HQ learning and org design so the whole group gets better at making money sustainably.

**Key Work**:
- Outcome / performance reporting model (lightweight JSON events or knowledge insights emitted by child orgs or their automation scripts): impressions, clicks, conversions, sales, engagement, cost, LTV signals, etc.
- HQ (Meta) analysis that treats revenue outcomes as a first-class signal for:
  - Which org structures + skill combinations + workflows correlate with better results.
  - Prompt / workflow optimization targeted at revenue domains.
  - Prioritizing which child orgs to strengthen next.
- Metrics extension: group-level "value creation velocity", "org ROI on improvement effort", cross-org learning transfer rate.
- Pattern store and capability history become multi-objective (code quality + revenue outcomes).

This phase makes the "group company" vision economically real rather than just organizational.

## Cross-Cutting Requirements (Apply to All Phases)

- **Universal routing (Phase 3 spirit)**: Every new entrypoint (HQ intervention, revenue goal, asset review, action proposal) **must** go through PreTaskOrchestrator. Record patterns. No direct agent construction in production paths.
- **Policy everywhere (Phase 0 spirit)**: New proposal shapes and external effects get explicit policy treatment. Default to human for anything high-impact.
- **Atlas & flows discipline (Phase 1 + 4)**: Every new major flow gets an entry in `core/atlas/data/flows.json`. Update subsystem maps if architecture changes. Treat this as mandatory maintenance.
- **State clarity (Phase 4)**: Decide and document primary source for org definitions, proposals, and outcomes. Keep per-org .pantheon for child autonomy; platform for HQ view.
- **Testing & safety**: All changes follow tmp_path + `get_platform_home` monkeypatch pattern. No breakage of full test collection.
- **Enforcement**: Consider a small hook or script (like the flows check) that fails if new monetization/group flows are added without corresponding Atlas / design doc / flows.json updates.
- **Planning Document Hygiene**: Active/in-progress planning-stage documents (kickoffs, research seeds, tactical roadmaps for upcoming phases) **must** be placed in `docs/plans/` (or a clearly scoped subfolder such as `docs/plans/phase5/`). Never put them directly into `docs/design/` or other permanent documentation folders. Every `docs/plans/` area must contain a README explaining that the contents are temporary and should be cleaned/archived after the work completes. Upon finishing a phase or milestone: (1) extract lasting architectural/decision records into `docs/design/`, `docs/architecture.md`, or equivalent permanent docs, (2) archive or delete the transient planning files (git history preserves the reasoning). This prevents design-folder pollution after implementation. Agents working on the plan (Claude Code etc.) are required to follow this convention when generating new planning artifacts.
  - **Enforcement idea**: Extend the existing flows.json check (or add a simple script) to warn/fail if new .md files appear in `docs/design/` that look like planning/WIP/roadmap/kickoff without being in `docs/plans/`. The `docs/plans/README.md` itself can be referenced from AGENTS.md as a project convention for future planning work. This hygiene rule should be maintained by the Meta-Improvement Organization as part of its "Knowledge Management" and "Org Evolution" responsibilities.
  - **Concrete follow-ups** (to be done as part of or after the core phases):
    - Promote the Planning Document Hygiene rule into `AGENTS.md` (and optionally `.claude/rules/`) so it becomes a project-wide convention, not just for this roadmap.
    - Implement `scripts/check_planning_docs.py` (and wire it into pre-commit / CI / existing validation flows) so that creating a new planning document in the wrong place triggers a warning in the spirit of Phase 4's "flows.json update is mandatory" discipline.
- **Documentation**: Update AGENTS.md / relevant design docs when the group model or revenue org contract changes meaningfully. Consider adding Planning Document Hygiene as a project-wide convention (e.g. in AGENTS.md or a new `docs/conventions.md`).

## Prioritization & Sequencing Advice

**Do not parallelize too aggressively**. Suggested order after 0-4:

1. Finish Phase 0-2 (trust + Atlas fuel + real loop) — these are already in progress.
2. Phase 5 small slice first: Make Meta able to propose and apply *structural / capability changes* to another Organization (this directly realizes the "HQ strengthens subsidiaries" part with existing state model).
3. Phase 6: Add the first 2-3 revenue skills + one org template + generalized proposal fields. Instantiate a toy affiliate or content org via goal pipeline.
4. Use the strengthened Meta (Phase 5) to help *design and improve* the revenue templates themselves.
5. Phase 7 only after the above is working end-to-end in a content-workspace style (safer than direct external).
6. Phase 8 as the payoff that justifies the investment.

**Quick win that advances the vision today (even during 0-4)**:
- Task the existing Meta-Improvement Organization (via a goal or manual proposal) with "research and propose an initial revenue org template + needed skills for affiliate operations".
- This exercises the org_design / corporate_research / strategic_planning muscles in a group-relevant way and produces artifacts that Phase 6 can productize.

## Risks & Anti-Patterns to Avoid

- Treating revenue orgs as "just another SE org with different keywords" — the action surface and verification models are genuinely different.
- Adding bypasses "just for meta" or "just for revenue" — this undoes the value of 0-4.
- Over-investing in direct external actions before HQ governance (Phase 5) and domain substrate (Phase 6) exist. You will have powerful posting scripts with weak organizational learning around them.
- Ignoring that many successful "AI monetization" setups already treat content/assets as git-managed artifacts. Leverage that instead of fighting it.
- Letting the "we abolished the company metaphor" comment prevent using the very useful HQ/child mental model that is already in the platform docs and meta_improvement.yaml.

## Success Metrics (for this roadmap)

- A Meta-Improvement Org can generate and have approved/applied a structural intervention on a different Organization.
- A non-SE "Affiliate Content Operations" Organization can be instantiated, given a goal, produce proposals (some non-file), and have them executed via the same policy/PreTask path.
- Pattern store and shared knowledge contain at least one cross-org or revenue-domain learning that was used in a subsequent run.
- Atlas + flows.json accurately describe the new governance and domain flows.
- No new high-severity trust/safety issues introduced in the Atlas (the explicit goal of Phase 0).

---

This plan is designed to be executed *after or in tight coordination with* the user's current 0-4 work. It turns the latent "本社 + 子会社" scaffolding and the Meta org's corporate-HQ-inspired design into an operational group structure that can genuinely support and benefit from revenue-generating organizations.

Next concrete step after 0-4 basics: create the extended proposal fields + a minimal HQ intervention path (Phase 5 slice) and a first revenue skill + template (Phase 6 slice). These two together make the group company vision feel real in the running system.

Update this document (and flows.json / Atlas) as each phase is broken into tickets.

## For Claude Code / Autonomous Implementation Agents (Phase 5+ Starting Point)

**Best way to start**: Give the agent **only** the file `docs/plans/phase5-kickoff.md` and say:

> 「始めて」または「Begin Phase 5 work. Read the kickoff file and proceed.」

The kickoff file is self-contained and references the two other key documents (this roadmap and the research inspiration file). It is designed so that a capable autonomous agent can immediately understand the mission, invariants, research direction, and how to begin thinking and working without needing long additional context.

**Purpose of this section** (kept for reference): This is not a rigid spec or step-by-step TODO list. It is directional scaffolding, research seeds, open questions, and promising angles so that a capable autonomous agent (like you, Claude Code) can deeply think, research, explore the codebase, draw analogies from 2025-2026 trending projects, and propose concrete, high-quality implementations that respect Pantheon's invariants.

You are expected to:
- Use tools (grep, read_file, list_dir, web_search, open_page, etc.) to explore.
- Reason about design tensions.
- Look for elegant extensions of existing mechanisms (proposal + policy + PreTask + GenericSkillAgent + Org model + meta_improvement structure) rather than bolting on new parallel systems.
- Produce small, valuable slices first, with proper tests, flows.json updates, and documentation.
- Propose changes via diffs or clear descriptions, and be ready to iterate.

### Core Invariants You Must Internalize and Respect (from AGENTS.md + codebase reality)
- New .py files: `from __future__ import annotations`
- All datetimes: `datetime.now(timezone.utc)`
- SpecialistAgent.skills: exactly min 2, max 3.
- State: global `~/.pantheon`, per-org `<target>/.pantheon` (or platform_home fallback).
- Every production execution path should go through PreTaskOrchestrator + PolicyEngine (this is the point of the current 0-4 work).
- Improvement loop quality and safety first — never sacrifice the explicit 404 handling in web/server.py or test collection.
- Prefer generalizing the existing proposal/contract over special cases.
- flows.json + Atlas coverage + this roadmap.md updates are mandatory for new major flows (Phase 4 discipline).

### Research Seeds & Trending Patterns (2025-2026 GitHub / Self-Evolving / Multi-Agent Space)
Do your own deep research with tools, but here are high-signal directions from recent trends (self-evolving agents, hierarchical orchestration, content/monetization automation). Look for patterns Pantheon can **adapt elegantly** (not copy-paste):

**Self-Evolving / Self-Modification Loops** (extremely hot — Awesome-Self-Evolving-Agents lists, EvoAgentX, Hermes from Nous, Sakana ShinkaEvolve, Karpathy autoresearch style, NFH self-improvement-loop, many writer-critic / proposer-verifier adversarial setups):
- Common winning pattern: **Proposer (or Improver) generates a change/patch/skill/workflow → Critic/Verifier/Evaluator judges it (with tests, reflection, or outcome feedback) → Safe apply or rollback → Learn (new skill, pattern, or updated prompt/org structure)**.
- Many emphasize "closed learning loops" where successful executions produce reusable artifacts (skills, prompts, workflows).
- Safety via sandbox/critic/adversarial second agent.
- **Pantheon alignment**: Our ImprovementProposal + review + Policy + execute + recording is *already* a proposal-based self-mod loop. Phase 1 (Atlas as fuel) and Phase 2 (real loop via PreTask) are making it robust. For Phase 5+, extend the *same primitive* to structural interventions on child orgs and revenue-domain "assets".

**Hierarchical / Supervisor / Meta Orchestration** (CrewAI hierarchical process with manager, LangGraph supervisor nodes, AutoGen group/hierarchical chat, MetaGPT "software company" role simulation):
- MetaGPT is particularly resonant: roles like PM/Architect/Engineer/QA producing artifacts from a goal — very close to Pantheon's Organization/Division/Team/SpecialistAgent + goal pipeline.
- Hierarchical: a high-level agent decomposes, delegates to specialists, synthesizes.
- Trend: some research shows rigid pre-assigned roles/hierarchies can underperform emergent or lightly-constrained setups in some cases — worth exploring the tension.
- **Pantheon opportunity**: Make the Meta-Improvement Organization (or a new HQ orchestrator agent) act as a lightweight supervisor that analyzes child orgs (via PlatformStateManager + diagnostics) and issues "intervention proposals" (structural, capability, goal) that child orgs or the system then execute. Leverage existing CrossOrgCollaborator / MultiOrgExecutor / OrgGoalManager seeds.

**Content / Monetization / Automation Workspaces** (MakeMoneyWithAI lists, marketing-automation topics, SalesGPT/LangGraph outreach agents, content gen + review pipelines, GitHub Agentic Workflows 2026 preview):
- Many successful systems treat **content, copy, calendars, scripts as first-class versioned artifacts** (often markdown + assets in git, or structured files).
- Generate → (human or critic) review → apply to workspace → external runner or script executes (posting, ad campaign, etc.).
- GitHub's new Agentic Workflows: describe intent in Markdown in the repo → agentic engine (Claude Code etc.) turns it into executable automation in Actions. Strong parallel to our goal → plan → org → execution + proposals.
- Outreach/content agents often use deep research + personalized generation + CRM/knowledge sync, without full autonomous posting until reviewed.
- **Pantheon fit**: Perfect for Phase 6. Encourage "revenue orgs" whose target is a git content/automation workspace. Proposals can target markdown/scripts. HQ (Meta) improves the generators, reviewers, and org structures for these workspaces. Start with read/analyze/generate/apply-inside-workspace before any real external publish.

**Skill / Capability Evolution**:
- Hermes-style: after a task, the system extracts/writes a reusable "skill" that future agents can use.
- Pantheon already has skills/*.yaml + AgentSkillEngine + GenericSkillAgent + CapabilityRegistry. Extending this with runtime or meta-proposed new skills (or evolved YAML personas) is a natural fit for self-evolution in revenue domains.

**Actionable Research Prompts for You (Claude)**
When you start Phase 5 work:
1. `web_search` and `open_page` on the awesome-self-evolving-agents lists, EvoAgentX, MetaGPT, CrewAI hierarchical examples, recent GitHub Agentic Workflows, and content/affiliate automation repos. Note concrete mechanisms for "proposal + verify + apply + learn" and "supervisor to sub-org".
2. Grep the Pantheon codebase for all uses of ImprovementProposal, PolicyEngine.evaluate, PreTaskOrchestrator.analyze/execute, GenericSkillAgent, OrganizationDesigner, meta_improvement.yaml, GroupHQState, cross_org.
3. Read flows.json (core/atlas/data/) and understand how new flows are documented.
4. Explore how an Organization without target_repo_path or with a non-code workspace would currently behave (state manager, scheduler, review agents).
5. Identify the *smallest* change that lets Meta generate a "structural intervention proposal" for another org (e.g., "add a ContentProduction team with specific skills") that can be approved via existing policy path and applied by mutating/saving the target Organization JSON.

### Suggested Starting Slices (Small, High-Signal, Thinking-Intensive)
These are **proposals for where to begin**, not mandates. Pick, combine, or invent better ones after your exploration. Always deliver with tests, docs updates, and flows.json entry.

**Slice A (Phase 5 minimal, high leverage)**: Proposal model + Policy extension for meta/structural interventions.
- Add the fields (is_meta, target_org_*, intervention_type, target_kind, target_ref) to ImprovementProposal (or a clean subclass / union approach).
- Update PolicyEngine to treat meta proposals differently for empty_file_path / categories (still conservative on mutation of other orgs).
- Add a small HQ "intervention proposer" (can start with GenericSkillAgent + org_design/strategic_planning + corporate_research skills, or a new lightweight definition in agents/definitions/).
- Wire a simple path where Meta (or platform) can generate such a proposal for a child org, persist it, and have it appear in pending for approval/apply.
- Goal: Demonstrate "HQ proposes change to child org structure" end-to-end using as much existing machinery as possible.

**Slice B (Phase 6 entry)**: First revenue-domain skill + tiny template.
- Add 2-3 new AgentSkill values.
- Create high-quality skills/audience_growth.yaml or content_strategy.yaml (strong Japanese/English persona if relevant, focus on compliance, measurement, LTV, etc.).
- Extend OrganizationDesigner heuristically or via LLM for a "content_operations" or "affiliate" purpose, producing a sensible Division/Team/Agent structure (2-3 skills each).
- Update one place in goal_decomposer or org_instantiator so a natural language goal like "build an affiliate content operation for X niche" produces something reasonable.
- Test: Instantiate via existing goal or org commands.

**Slice C (Thinking + Generalization)**: Workspace-friendly review/apply path.
- Experiment with relaxing CodeReviewAgent (or a new thin AssetReviewAgent) to handle markdown + script files in a designated workspace.
- Show a non-code proposal (target_kind="content_asset") flowing through the (soon-to-be-universal) PreTask + Policy + apply (safe write inside repo root only).
- Document the design decision in the roadmap and a small note.

**Slice D (Research-driven)**: After your trending research, write a short `docs/plans/phase5-inspiration-trending-agents-2026.md` (or update this section) with 3-5 specific patterns from external repos that you recommend adapting, with "why it fits Pantheon" and "how to avoid over-engineering".

### Open Questions & Design Tensions (Think Hard About These)
- How much "supervision" should the Meta org exert vs. true autonomy of child revenue orgs? (Inspired by the research showing rigid hierarchies sometimes lose to lighter coordination.)
- Should structural interventions on child orgs produce ImprovementProposals in the *child's* .pantheon or only in Meta's? (Provenance, visibility, audit.)
- For revenue orgs: is a git-backed workspace (markdown + Python scripts for generation/publishing glue) the right "target_repo" abstraction, or do we need a first-class non-repo workspace concept?
- How do we make outcome feedback (sales, engagement) from revenue orgs first-class citizens in the knowledge / pattern learning system without adding fragile external integrations too early?
- When Meta "improves" a revenue org, should it primarily mutate the child's Organization model, or propose changes to the *automation code/scripts* inside the child's workspace (leveraging our existing code strengths)?
- What is the right granularity for new skills in monetization (broad like "audience_growth" vs. very specific)?

### How to Work (Recommended Agent Workflow)
1. Deep research + codebase exploration (use tools liberally).
2. Identify 1-2 smallest valuable slices (as above or better).
3. Sketch the minimal model/policy/orchestration changes needed.
4. Implement the slice end-to-end (including a test that exercises PreTask + Policy).
5. Update flows.json, this roadmap.md, relevant docs, and add a clear summary of decisions + open questions left.
6. If useful, propose a new small agent definition YAML or skill YAML.
7. Reflect: "How does this make future Phase 6/7/8 work easier? Did I preserve the self-improvement learning loop?"
8. When creating any additional planning documents, strictly obey **Planning Document Hygiene** (see the Cross-Cutting Requirements section in this roadmap and `docs/plans/README.md`). Never pollute `docs/design/`. At the end of the work, help promote lasting decisions to permanent docs and ensure the transient planning files are archived or removed.
9. **Explicit required deliverables** (do not treat as optional): 
   - Implement `scripts/check_planning_docs.py` (a simple checker in the style of other `scripts/check_*.py` files). It must catch planning-stage documents being placed in `docs/design/` and enforce the hygiene rule.
   - Promote the Planning Document Hygiene rule into `AGENTS.md` (and optionally `.claude/rules/`) as a project-wide convention.
   - Add enforcement so that creating a new planning document triggers a warning (hook / CI / existing validation), in the exact spirit of Phase 4 ("new planning document → hook warning").

Start by exploring the current state of cross-org, hierarchy, meta_improvement config, proposal/policy paths, and the Atlas flows. Then go research the self-evolving and hierarchical agent trends. Come back with a thoughtful proposal for the first small slice.

The goal is not to "follow the spec" but to **advance the group company + monetization vision in a way that feels native to Pantheon's existing soul** (proposal-driven improvement, local Claude execution, skill/YAML extensibility, strong policy/HITL, self-learning orchestration).

Good luck — the foundation from 0-4 will make whatever you build here much more powerful and trustworthy. Update this document with your findings and progress.