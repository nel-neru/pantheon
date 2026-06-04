# Pantheon — architecture overview (diagrams)

Visual companion to `AGENTS.md` and `docs/architecture.md`. All generation flows through the local
`claude` CLI — there are no hosted-LLM API keys.

## System context

```mermaid
flowchart TB
    user([Developer])
    subgraph CLI["pantheon CLI (main.py)"]
      parser[build_parser → HANDLERS] --> cmds[commands/*]
    end
    subgraph WEB["Web (web/server.py, FastAPI)"]
      api["/api REST + /ws WebSocket"] --> spa[web/dist SPA · React 19]
    end
    subgraph CORE["core/ domain"]
      orch[orchestration\npre_task · task_router] --> agents[agents/*\nBaseAgent]
      agents --> skills[intelligence\nAgentSkillEngine + skills/*.yaml]
      goals[goals\nabstract_goal_pipeline] --> orch
      policy[policy\nHuman-in-the-Loop] --- state
      state[(state/manager\n<repo>/.pantheon)]
      platform[(platform/state\n~/.pantheon)]
    end
    backend[["claude CLI\ncore/runtime/claude_code"]]
    gh[(GitHub\ngithub_integration)]

    user --> CLI
    user --> WEB
    cmds --> orch
    api --> orch
    agents --> backend
    goals --> backend
    agents --> gh
    orch --> platform
```

## CLI request flow

```mermaid
sequenceDiagram
    participant U as User
    participant M as main.HANDLERS[handler_name]
    participant C as commands/<mod>.cmd_*
    participant O as OrchestratorAgent
    participant P as PreTaskOrchestrator / task_router
    participant A as SpecialistAgent (BaseAgent)
    participant K as claude CLI (ClaudeCodeProvider)
    participant S as state (~/.pantheon | <repo>/.pantheon)

    U->>M: pantheon <cmd> (argparse → handler_name)
    M->>C: cmd_*(args, injected deps)
    C->>O: OrchestratorAgent.create()
    O->>P: analyze task, pick agent + pattern
    P->>A: route by task-type × skill weights
    A->>K: generate (headless claude -p)
    K-->>A: LLMResponse
    A-->>S: persist results / proposals
    A-->>U: AgentResult (summary)
```

## ImprovementProposal lifecycle

```mermaid
flowchart LR
    analyze[analyze\ncode_review_agent] --> prop[ImprovementProposal\ncore/models]
    prop --> store[(state/manager\n<repo>/.pantheon)]
    store --> review{Human-in-the-Loop\npolicy/engine}
    review -- approve --> apply[improvement_executor_agent\nwork branch + PR]
    review -- reject --> store
    apply --> gh[(GitHub PR)]
```

## Layer responsibilities (quick map)

| Layer | Responsibility |
|---|---|
| `main.py` / `commands/` | CLI entrypoint; parser → `HANDLERS` → `cmd_*` (dep injection) |
| `agents/` | `BaseAgent` framework (review, executor, explorer, orchestrator, …) |
| `core/orchestration` | pre-task meta-analysis, routing, learned execution patterns |
| `core/intelligence` | skill engine, capability registry/gap analysis, codebase index |
| `core/goals` | NL goal → org gen → plan → execute → verify |
| `core/policy` · `quality` · `metrics` | approval gating; self-improvement loop; health/growth |
| `core/platform` · `state` | global `~/.pantheon` vs per-repo `<repo>/.pantheon` |
| `core/runtime` | `claude_code` provider (sole backend) + wmux multiplexer |
| `web/` | FastAPI API (`/api`, `/ws`, explicit 404) + React 19/Vite/Tailwind SPA |
| `github_integration/` | PR creation & repo linkage |
