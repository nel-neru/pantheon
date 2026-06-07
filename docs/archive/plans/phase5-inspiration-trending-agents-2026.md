# Phase 5+ Inspiration from 2025-2026 Trending Self-Evolving & Multi-Agent Projects

**Purpose**: Seed material for autonomous agents (Claude Code etc.) working on Pantheon group governance and monetization. Not prescriptive — use as thinking fuel, then explore more with your own tools (web_search, open_page, etc.).

Pantheon already has strong bones in this area (proposal-driven improvement, policy/HITL, PreTask orchestration + pattern learning, skill/YAML extensibility, meta org as HQ, Organization as composable unit). The opportunity is elegant extension rather than reinvention.

## 1. Self-Evolving / Self-Modification Loops (Hottest Area)
Key projects / surveys:
- Awesome-Self-Evolving-Agents collections (EvoAgentX, XMUDeepLIT, CharlesQ9, etc.)
- EvoAgentX framework: modular, goal-driven, iterative feedback for evolving agents/workflows.
- Hermes (Nous Research): closed learning loop — after task, agent writes reusable "skill" for future use.
- Karpathy-style autoresearch / NFH self-improvement-loop: proposer modifies (code/prompt), separate critic/verifier evaluates (tests + outcomes), apply if good.
- Sakana ShinkaEvolve / evolutionary approaches (MAP-Elites style population + evaluation).
- Common successful pattern across many: **Propose change → Adversarial/critic evaluation (reflection, sandbox, outcome data) → Safe apply + extract learning (new skill/prompt/pattern/org structure) → Accumulate**.

**Adaptation ideas for Pantheon**:
- Our `ImprovementProposal` + review/consultant + `PolicyEngine` + executor + `orchestration_pattern_store` + knowledge is *already* this shape.
- Phase 1 (Atlas as fuel for meta proposals) + Phase 2 (real loop via PreTask, proper agent selection + recording) are making the substrate robust.
- For group/monetization: extend the *same proposal primitive* to "structural interventions on child orgs" and "content/asset improvements" in revenue workspaces.
- After successful revenue-domain runs, have the system (or Meta) propose new or evolved `skills/*.yaml` entries or refined personas — mirrors Hermes skill writing.
- Use critic-style (InternalConsultant or new revenue-specific reviewer) heavily for safety.

**Research prompt for you**: Search for more "proposer critic self modify agent" or "improvement proposal agent loop" examples. Note how they handle verification without full code execution (important for non-code revenue work).

## 2. Hierarchical / Supervisor / Meta-Orchestration Patterns
Popular:
- CrewAI: "crews" with roles, explicit `Process.hierarchical` (manager/supervisor agent delegates to workers, synthesizes).
- LangGraph: supervisor nodes + conditional edges for dynamic routing; stateful graphs with cycles (great for improvement loops).
- AutoGen/AG2: conversational group chat + hierarchical manager patterns.
- MetaGPT: strongest resonance — simulates a full software company with predefined roles (Product Manager, Architect, Engineer, QA, etc.) that collaborate from a single goal to produce artifacts. Very close to Pantheon's Organization → Division (ORG_EVOLUTION etc.) → Team → SpecialistAgent (2-3 skills) model + goal pipeline.
- General trend in 2025-2026: move from flat single agents to orchestrated teams; some papers show rigid pre-defined hierarchies can be outperformed by emergent or lightly-constrained coordination in certain regimes.

**Adaptation ideas for Pantheon**:
- Treat Meta-Improvement Organization (and Platform as "HQ") as the supervisor layer.
- Meta can run cross-org analysis (using existing OrgSelfDiagnostics + PlatformStateManager + shared knowledge) and issue high-level "intervention proposals" (new Division, new skill mix for a child org, new goal for a revenue team, etc.).
- Use existing `GenericSkillAgent` + org_design/strategic_planning/corporate_research skills as the "manager" persona.
- Leverage or strengthen `MultiOrgExecutor`, `CrossOrgCollaborator`, `OrgGoalManager` as the delegation/synchronization substrate.
- For revenue orgs: a child org can itself be hierarchical (e.g., Content Strategy Division supervising Copy Team + Research Team + Publishing Team) using the same model.
- Avoid over-rigid role assignment; let the proposal mechanism and learning (pattern store) discover what combinations work for monetization outcomes.

**Research prompt**: Look at MetaGPT's role definitions and how they produce structured outputs. Compare to Pantheon's `agents/definitions/*.yaml` + `skills/*.yaml`. Consider whether revenue orgs benefit from similar "standard company simulation" templates.

## 3. Content / Affiliate / Monetization Automation Patterns
From MakeMoneyWithAI lists, marketing-automation topics, sales-outreach LangGraph agents, etc.:
- Heavy use of generate (copy, calendars, videos, personalized outreach) → review/critic → apply to workspace or CRM → (often human or narrow auto) execute/publish.
- Many treat assets as versioned (git-friendly markdown, structured data, scripts).
- GitHub Agentic Workflows (2026 technical preview): intent described in natural language Markdown inside the repo; an agentic engine (Claude Code etc.) turns it into CI automation. Strong parallel to Pantheon's AbstractGoalPipeline + proposals.
- Lead gen / outreach agents (SalesGPT, LangGraph sales examples): deep research on targets, generate tailored content, log to knowledge/CRM, but stop short of fully autonomous blasting without gates.
- Common: separate "researcher", "copywriter", "optimizer", "analyst" agents orchestrated together.

**Adaptation ideas for Pantheon**:
- Revenue orgs should often have `target_repo_path` pointing to a **content + automation workspace** (git repo of markdown articles, scripts for generation, tracking configs, etc.). This plays to Pantheon's existing code/workspace strengths.
- Proposals naturally target assets in the workspace (`target_kind="content_asset"`).
- HQ (Meta) excels at improving the *generators, reviewers, and org structures* used by these workspaces (via structural proposals or code improvements in the shared tooling).
- Start Phase 7 actions as "write safe artifacts to designated workspace + generate runnable glue scripts" rather than direct API posting.
- Use the strengthened knowledge + pattern learning to capture what content/offer combinations drive real outcomes.

**Research prompt**: Find examples of "git workspace for AI content agents" or "markdown as source of truth for agentic publishing". Also study how outreach agents handle "research → generate → log insight" without full autonomy.

## 4. Other Resonances
- Skill extraction / evolution after execution (Hermes and several self-evo projects) → Pantheon skills/*.yaml + registry are ready for meta-proposed or runtime-evolved additions.
- Adversarial / multi-critic safety for self-mod (very common) → aligns with our PolicyEngine + InternalConsultant + quality reviews.
- Emergent vs. designed hierarchies → interesting tension to explore when designing HQ-to-child vs. within-child org structures.

## How to Use This as a Starting Agent

**Primary entry point**: The recommended way to bootstrap is to give the agent **docs/plans/phase5-kickoff.md** and say "始めて" (or equivalent). That single file tells the agent exactly which three documents to read first (including this one) and how to operate.

After that:
1. Read this file + the main `docs/design/group-monetization-roadmap.md` (especially its Claude section) + `docs/plans/phase5-kickoff.md`.
2. Do fresh `web_search` / `open_page` on the project names above + "self evolving agents 2026", "crewai hierarchical", "metagpt roles", "github agentic workflows".
3. Grep Pantheon for the core mechanisms listed in the invariants section of the kickoff.
4. Pick or invent a small slice (see suggestions in the kickoff and roadmap).
5. Design the minimal change that reuses proposal/policy/PreTask/GenericSkill as much as possible.
6. Implement, test, document, update flows + this research note + the kickoff/roadmap with your new insights.
7. Reflect on how the slice makes the *next* slice (deeper revenue, real actions, economic feedback) easier and more trustworthy.

The best contributions will feel like natural growth of Pantheon's existing proposal-driven, policy-gated, learning self-improvement organism — now applied at the group level and into revenue domains.

Add your own findings, counter-examples, and adaptation proposals below or in follow-up edits.